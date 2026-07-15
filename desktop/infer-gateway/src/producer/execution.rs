use std::path::{Component, Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{anyhow, bail, Context, Result};
use tokio::io::{AsyncRead, AsyncReadExt};
use tokio::sync::OwnedSemaphorePermit;
use tokio_util::sync::CancellationToken;
use tokio_util::task::TaskTracker;

use super::config::{expand_argument, replacement_map, ProducerConfig, ProducerKind};

const DRAIN_CAPTURE_LIMIT: usize = 64 * 1024;
const PROCESS_CLEANUP_TIMEOUT: Duration = Duration::from_secs(1);

#[derive(Debug)]
pub struct ProducerOutput {
    pub bytes: Vec<u8>,
}

pub(super) type CloseRequestDirectory = Arc<dyn Fn(tempfile::TempDir) -> Result<()> + Send + Sync>;

#[derive(Debug)]
pub(super) struct ExecutionCancelled {
    kind: ProducerKind,
}

impl std::fmt::Display for ExecutionCancelled {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{} execution cancelled", self.kind.name())
    }
}

impl std::error::Error for ExecutionCancelled {}

struct ProcessGroup {
    id: i32,
    armed: bool,
}

impl ProcessGroup {
    fn for_child(child: &tokio::process::Child) -> Result<Self> {
        let id = child
            .id()
            .ok_or_else(|| anyhow!("spawned producer has no process id"))?;
        let id = i32::try_from(id).context("producer process id exceeds i32")?;
        Ok(Self { id, armed: true })
    }

    fn terminate(&mut self) -> Result<()> {
        if !self.armed {
            return Ok(());
        }
        let result = unsafe { libc::kill(-self.id, libc::SIGKILL) };
        if result == 0 {
            self.armed = false;
            return Ok(());
        }
        let error = std::io::Error::last_os_error();
        if error.raw_os_error() == Some(libc::ESRCH) {
            self.armed = false;
            return Ok(());
        }
        Err(error).context("terminate producer process group")
    }
}

impl Drop for ProcessGroup {
    fn drop(&mut self) {
        if let Err(error) = self.terminate() {
            tracing::error!(
                process_group_id = self.id,
                "failed to terminate producer process group during guard drop: {error:#}"
            );
        }
    }
}

pub(super) struct DrainTasks {
    task: tokio::task::JoinHandle<std::io::Result<(Vec<u8>, Vec<u8>)>>,
    cancellation: CancellationToken,
    finished: bool,
}

impl DrainTasks {
    pub(super) fn spawn_tracked(
        stdout: impl AsyncRead + Unpin + Send + 'static,
        stderr: impl AsyncRead + Unpin + Send + 'static,
        tasks: &TaskTracker,
    ) -> Self {
        let cancellation = CancellationToken::new();
        let stdout_cancellation = cancellation.child_token();
        let stderr_cancellation = cancellation.child_token();
        Self {
            task: tasks.spawn(async move {
                tokio::try_join!(
                    drain(stdout, stdout_cancellation),
                    drain(stderr, stderr_cancellation)
                )
            }),
            cancellation,
            finished: false,
        }
    }

    pub(super) async fn collect_until(
        &mut self,
        deadline: tokio::time::Instant,
        kind: ProducerKind,
    ) -> Result<(Vec<u8>, Vec<u8>)> {
        match tokio::time::timeout_at(deadline, &mut self.task).await {
            Ok(result) => {
                self.finished = true;
                result
                    .with_context(|| format!("{} stdout/stderr drain task failed", kind.name()))?
                    .with_context(|| format!("read {} stdout/stderr", kind.name()))
            }
            Err(_) => bail!("{} timed out while draining stdout/stderr", kind.name()),
        }
    }

    pub(super) async fn cancel_and_join_until(
        &mut self,
        deadline: tokio::time::Instant,
    ) -> Result<()> {
        if self.finished {
            return Ok(());
        }
        self.cancellation.cancel();
        match tokio::time::timeout_at(deadline, &mut self.task).await {
            Ok(result) => {
                self.finished = true;
                result
                    .context("join cancelled producer drain task")?
                    .context("read producer stdout/stderr during cancellation")?;
                Ok(())
            }
            Err(_) => bail!("timed out joining cancelled producer drain task"),
        }
    }
}

pub(super) async fn execute_tracked_worker(
    config: ProducerConfig,
    output_filename: String,
    replacements: Vec<(String, String)>,
    cancellation: CancellationToken,
    close_request_directory: CloseRequestDirectory,
    tasks: TaskTracker,
    permit: OwnedSemaphorePermit,
) -> Result<ProducerOutput> {
    let request_directory = tempfile::Builder::new()
        .prefix(&format!("yts-{}-", config.kind.name()))
        .tempdir()
        .with_context(|| format!("create {} request directory", config.kind.name()))?;
    let operation = execute_in_request_directory(
        &config,
        request_directory.path(),
        &output_filename,
        &replacements,
        cancellation,
        &tasks,
    )
    .await;
    let cleanup = close_request_directory(request_directory);
    let result = merge_operation_and_cleanup(operation, cleanup);
    drop(permit);
    result
}

async fn execute_in_request_directory(
    config: &ProducerConfig,
    request_directory: &Path,
    output_filename: &str,
    replacements: &[(String, String)],
    cancellation: CancellationToken,
    tasks: &TaskTracker,
) -> Result<ProducerOutput> {
    if cancellation.is_cancelled() {
        return Err(ExecutionCancelled { kind: config.kind }.into());
    }
    let argv = config.argv.as_ref().ok_or_else(|| {
        anyhow!(
            "{} has no argv despite enabled configuration",
            config.kind.name()
        )
    })?;
    let timeout = config.timeout.ok_or_else(|| {
        anyhow!(
            "{} has no timeout despite enabled configuration",
            config.kind.name()
        )
    })?;
    let limits = config.required_limits()?;
    let output = output_path(request_directory, output_filename)?;
    let output_value = output
        .to_str()
        .ok_or_else(|| anyhow!("{} output path is not valid UTF-8", config.kind.name()))?;
    let replacement_refs = replacements
        .iter()
        .map(|(name, value)| (name.as_str(), value.as_str()))
        .collect::<Vec<_>>();
    let values = replacement_map(config.kind, &replacement_refs, output_value)?;
    let expanded = argv
        .iter()
        .map(|argument| expand_argument(config.kind, argument, &values))
        .collect::<Result<Vec<_>>>()?;

    let execution_deadline = tokio::time::Instant::now() + timeout;
    let mut command = tokio::process::Command::new(&expanded[0]);
    command
        .args(&expanded[1..])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0)
        .kill_on_drop(true);
    let mut child = command
        .spawn()
        .with_context(|| format!("spawn {} executable {:?}", config.kind.name(), expanded[0]))?;
    let mut process_group = match ProcessGroup::for_child(&child) {
        Ok(process_group) => process_group,
        Err(error) => {
            let cleanup = cleanup_direct_child(&mut child, config.kind).await;
            return merge_operation_and_cleanup(Err(error), cleanup);
        }
    };
    let stdout = child
        .stdout
        .take()
        .expect("producer stdout is piped before spawn");
    let stderr = child
        .stderr
        .take()
        .expect("producer stderr is piped before spawn");
    let mut drains = DrainTasks::spawn_tracked(stdout, stderr, tasks);

    let wait_result = tokio::select! {
        status = child.wait() => status
            .with_context(|| format!("wait for {} process", config.kind.name())),
        () = cancellation.cancelled() => Err(ExecutionCancelled { kind: config.kind }.into()),
        () = tokio::time::sleep_until(execution_deadline) => Err(anyhow!(
            "{} timed out after {} seconds",
            config.kind.name(),
            timeout.as_secs_f64()
        )),
    };
    let status = match wait_result {
        Ok(status) => status,
        Err(error) => {
            let cleanup =
                cleanup_process_group(&mut process_group, &mut child, &mut drains, config.kind)
                    .await;
            return merge_operation_and_cleanup(Err(error), cleanup);
        }
    };

    if let Err(error) = process_group
        .terminate()
        .with_context(|| format!("terminate remaining {} descendants", config.kind.name()))
    {
        let cleanup =
            cleanup_process_group(&mut process_group, &mut child, &mut drains, config.kind).await;
        return merge_operation_and_cleanup(Err(error), cleanup);
    }
    let (_stdout, stderr) = match drains.collect_until(execution_deadline, config.kind).await {
        Ok(output) => output,
        Err(error) => {
            let cleanup =
                cleanup_process_group(&mut process_group, &mut child, &mut drains, config.kind)
                    .await;
            return merge_operation_and_cleanup(Err(error), cleanup);
        }
    };
    if !status.success() {
        let stderr = String::from_utf8(stderr)
            .with_context(|| format!("{} stderr is not UTF-8", config.kind.name()))?;
        bail!("{} exited {status}: {}", config.kind.name(), stderr.trim());
    }

    let read_output = read_bounded_output(&output, limits.max_output_bytes, config.kind);
    let bytes = tokio::select! {
        result = tokio::time::timeout_at(execution_deadline, read_output) => match result {
            Ok(result) => result?,
            Err(_) => bail!(
                "{} timed out while reading output after {} seconds",
                config.kind.name(),
                timeout.as_secs_f64()
            ),
        },
        () = cancellation.cancelled() => return Err(ExecutionCancelled { kind: config.kind }.into()),
    };
    if bytes.is_empty() {
        bail!("{} produced an empty output file", config.kind.name());
    }
    Ok(ProducerOutput { bytes })
}

async fn read_bounded_output(path: &Path, maximum: u64, kind: ProducerKind) -> Result<Vec<u8>> {
    let metadata = tokio::fs::symlink_metadata(path)
        .await
        .with_context(|| format!("inspect {} output {}", kind.name(), path.display()))?;
    if !metadata.file_type().is_file() {
        bail!(
            "{} output {} is not a regular file",
            kind.name(),
            path.display()
        );
    }
    let file = tokio::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .await
        .with_context(|| format!("open {} output {}", kind.name(), path.display()))?;
    if !file
        .metadata()
        .await
        .with_context(|| format!("inspect opened {} output", kind.name()))?
        .is_file()
    {
        bail!("opened {} output is not a regular file", kind.name());
    }
    let read_limit = maximum
        .checked_add(1)
        .ok_or_else(|| anyhow!("{} output limit is too large", kind.name()))?;
    let mut bytes = Vec::new();
    file.take(read_limit)
        .read_to_end(&mut bytes)
        .await
        .with_context(|| format!("read {} output {}", kind.name(), path.display()))?;
    if bytes.len() as u64 > maximum {
        bail!(
            "{} output exceeds configured maximum of {maximum} bytes",
            kind.name()
        );
    }
    Ok(bytes)
}

async fn cleanup_direct_child(child: &mut tokio::process::Child, kind: ProducerKind) -> Result<()> {
    let deadline = tokio::time::Instant::now() + PROCESS_CLEANUP_TIMEOUT;
    let mut failures = Vec::new();
    if let Err(error) = child.start_kill() {
        failures.push(format!("kill direct {} child: {error}", kind.name()));
    }
    match tokio::time::timeout_at(deadline, child.wait()).await {
        Ok(Ok(_)) => {}
        Ok(Err(error)) => failures.push(format!("reap direct {} child: {error}", kind.name())),
        Err(_) => failures.push(format!("timed out reaping direct {} child", kind.name())),
    }
    if failures.is_empty() {
        Ok(())
    } else {
        bail!(failures.join("; "))
    }
}

pub(super) fn close_request_directory(directory: tempfile::TempDir) -> Result<()> {
    let path = directory.path().to_path_buf();
    directory
        .close()
        .with_context(|| format!("close producer request directory {}", path.display()))
}

pub(super) fn merge_operation_and_cleanup<T>(
    operation: Result<T>,
    cleanup: Result<()>,
) -> Result<T> {
    match (operation, cleanup) {
        (Ok(value), Ok(())) => Ok(value),
        (Err(error), Ok(())) => Err(error),
        (Ok(_), Err(cleanup)) => Err(cleanup).context("producer request directory cleanup failed"),
        (Err(error), Err(cleanup)) => {
            bail!("{error:#}; producer request directory cleanup also failed: {cleanup:#}")
        }
    }
}

pub(super) fn output_path(request_dir: &Path, filename: &str) -> Result<PathBuf> {
    let mut components = Path::new(filename).components();
    match (components.next(), components.next()) {
        (Some(Component::Normal(name)), None) => Ok(request_dir.join(name)),
        _ => bail!("producer output filename must be a single normal path component"),
    }
}

async fn drain(
    mut stream: impl AsyncRead + Unpin,
    cancellation: CancellationToken,
) -> std::io::Result<Vec<u8>> {
    let mut captured = Vec::new();
    let mut chunk = [0_u8; 8192];
    loop {
        let count = tokio::select! {
            result = stream.read(&mut chunk) => result?,
            () = cancellation.cancelled() => return Ok(captured),
        };
        if count == 0 {
            return Ok(captured);
        }
        let remaining = DRAIN_CAPTURE_LIMIT.saturating_sub(captured.len());
        captured.extend_from_slice(&chunk[..count.min(remaining)]);
    }
}

async fn cleanup_process_group(
    process_group: &mut ProcessGroup,
    child: &mut tokio::process::Child,
    drains: &mut DrainTasks,
    kind: ProducerKind,
) -> Result<()> {
    let cleanup_deadline = tokio::time::Instant::now() + PROCESS_CLEANUP_TIMEOUT;
    let mut failures = Vec::new();
    if let Err(error) = process_group.terminate() {
        failures.push(format!("terminate process group: {error:#}"));
    }
    match tokio::time::timeout_at(cleanup_deadline, child.wait()).await {
        Ok(Ok(_)) => {}
        Ok(Err(error)) => failures.push(format!("reap direct child: {error}")),
        Err(_) => failures.push("timed out reaping direct child".into()),
    }
    if let Err(error) = drains.cancel_and_join_until(cleanup_deadline).await {
        failures.push(format!("stop stdout/stderr drain: {error:#}"));
    }
    if failures.is_empty() {
        Ok(())
    } else {
        bail!("{} cleanup failed: {}", kind.name(), failures.join("; "))
    }
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::process::Stdio;
    use std::time::Duration;

    use super::ProcessGroup;

    fn process_exists(pid: i32) -> bool {
        let result = unsafe { libc::kill(pid, 0) };
        if result == 0 {
            return true;
        }
        std::io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
    }

    #[tokio::test]
    async fn dropping_process_group_guard_terminates_direct_child_and_descendant() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let fixture = tempfile::tempdir().unwrap();
        let executable = fixture.path().join("process-group-fixture");
        let parent_path = fixture.path().join("parent.pid");
        let descendant_path = fixture.path().join("descendant.pid");
        fs::write(
            &executable,
            "#!/bin/sh\nprintf '%s' \"$$\" > \"$1\"\nsleep 30 & descendant=$!\nprintf '%s' \"$descendant\" > \"$2\"\nwait\n",
        )
        .unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o755)).unwrap();
        let mut command = tokio::process::Command::new(&executable);
        command
            .args([&parent_path, &descendant_path])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .process_group(0)
            .kill_on_drop(true);
        let mut child = command.spawn().unwrap();
        let process_group = ProcessGroup::for_child(&child).unwrap();
        let process_group_id = process_group.id;
        {
            let wait = child.wait();
            tokio::pin!(wait);
            tokio::time::timeout(Duration::from_secs(5), async {
                loop {
                    if parent_path.exists() && descendant_path.exists() {
                        return;
                    }
                    tokio::select! {
                        result = &mut wait => panic!("fixture exited before writing markers: {result:?}"),
                        () = tokio::task::yield_now() => {}
                    }
                }
            })
            .await
            .unwrap();
        }
        let parent = fs::read_to_string(parent_path)
            .unwrap()
            .parse::<i32>()
            .unwrap();
        let descendant = fs::read_to_string(descendant_path)
            .unwrap()
            .parse::<i32>()
            .unwrap();

        drop(process_group);
        drop(child);
        let terminated = tokio::time::timeout(Duration::from_secs(1), async {
            while process_exists(parent) || process_exists(descendant) {
                tokio::task::yield_now().await;
            }
        })
        .await
        .is_ok();
        if !terminated {
            unsafe {
                libc::kill(-process_group_id, libc::SIGKILL);
            }
        }

        assert!(
            terminated,
            "dropping the process-group guard left a process alive"
        );
    }
}
