mod config;
mod execution;

use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use anyhow::{bail, Context, Result};
use tokio::sync::{oneshot, Mutex};
use tokio_util::sync::CancellationToken;
use tokio_util::task::TaskTracker;

pub use config::{ProducerConfig, ProducerKind};
pub use execution::ProducerOutput;

use execution::{
    close_request_directory, execute_tracked_worker, output_path, CloseRequestDirectory,
    ExecutionCancelled,
};

struct ProducerSupervisorInner {
    accepting: Mutex<bool>,
    closing: AtomicBool,
    cancellation: CancellationToken,
    tasks: TaskTracker,
    close_request_directory: CloseRequestDirectory,
}

#[derive(Clone)]
pub struct ProducerSupervisor {
    inner: Arc<ProducerSupervisorInner>,
}

pub struct ProducerExecution {
    cancellation: CancellationToken,
    receiver: oneshot::Receiver<Result<ProducerOutput>>,
    consumed: bool,
}

impl Drop for ProducerExecution {
    fn drop(&mut self) {
        self.cancellation.cancel();
    }
}

impl ProducerSupervisor {
    pub fn new(parent_cancellation: CancellationToken) -> Self {
        Self::with_directory_closer(parent_cancellation, Arc::new(close_request_directory))
    }

    fn with_directory_closer(
        parent_cancellation: CancellationToken,
        close_request_directory: CloseRequestDirectory,
    ) -> Self {
        Self {
            inner: Arc::new(ProducerSupervisorInner {
                accepting: Mutex::new(true),
                closing: AtomicBool::new(false),
                cancellation: parent_cancellation.child_token(),
                tasks: TaskTracker::new(),
                close_request_directory,
            }),
        }
    }

    pub fn is_closing(&self) -> bool {
        self.inner.closing.load(Ordering::Acquire)
    }

    pub async fn cancelled(&self) {
        self.inner.cancellation.cancelled().await;
    }

    pub async fn start(
        &self,
        config: &ProducerConfig,
        output_filename: &str,
        replacements: &[(&str, &str)],
    ) -> Result<ProducerExecution> {
        if !config.enabled {
            bail!("{} capability is disabled", config.kind.name());
        }
        config.validate_executable()?;
        let output_filename = output_filename.to_owned();
        output_path(Path::new("/request"), &output_filename)?;
        let replacements = replacements
            .iter()
            .map(|(name, value)| ((*name).to_owned(), (*value).to_owned()))
            .collect::<Vec<_>>();

        let accepting = self.inner.accepting.lock().await;
        if !*accepting {
            bail!("producer supervisor is closing and rejects new executions");
        }
        let permit = config.try_acquire_execution_permit()?;
        let config = config.clone();
        let cancellation = self.inner.cancellation.child_token();
        let worker_cancellation = cancellation.clone();
        let (sender, receiver) = oneshot::channel();
        let close_request_directory = self.inner.close_request_directory.clone();
        let tasks = self.inner.tasks.clone();
        self.inner.tasks.spawn(async move {
            let result = execute_tracked_worker(
                config,
                output_filename,
                replacements,
                worker_cancellation,
                close_request_directory,
                tasks,
                permit,
            )
            .await;
            if let Err(result) = sender.send(result) {
                match result {
                    Ok(_) => tracing::error!(
                        "tracked producer result receiver was dropped after successful execution"
                    ),
                    Err(error) => tracing::error!(
                        "tracked producer result receiver was dropped after execution failure: {error:#}"
                    ),
                }
            }
        });
        drop(accepting);

        Ok(ProducerExecution {
            cancellation,
            receiver,
            consumed: false,
        })
    }

    pub async fn execute(
        &self,
        config: &ProducerConfig,
        output_filename: &str,
        replacements: &[(&str, &str)],
    ) -> Result<ProducerOutput> {
        self.start(config, output_filename, replacements)
            .await?
            .wait()
            .await
    }

    pub async fn begin_shutdown(&self) {
        let mut accepting = self.inner.accepting.lock().await;
        *accepting = false;
        self.inner.closing.store(true, Ordering::Release);
        self.inner.tasks.close();
        self.inner.cancellation.cancel();
    }

    #[cfg(test)]
    pub async fn shutdown(&self, timeout: std::time::Duration) -> Result<()> {
        self.shutdown_until(tokio::time::Instant::now() + timeout)
            .await
    }

    pub async fn shutdown_until(&self, deadline: tokio::time::Instant) -> Result<()> {
        self.begin_shutdown().await;
        match tokio::time::timeout_at(deadline, self.inner.tasks.wait()).await {
            Ok(()) => Ok(()),
            Err(_) => bail!("producer shutdown timed out before the gateway shutdown deadline"),
        }
    }
}

impl ProducerExecution {
    async fn receive(&mut self) -> Result<ProducerOutput> {
        if self.consumed {
            bail!("producer execution result was already consumed");
        }
        let result = (&mut self.receiver)
            .await
            .context("tracked producer worker exited without returning a result")?;
        self.consumed = true;
        result
    }

    pub async fn wait(mut self) -> Result<ProducerOutput> {
        self.receive().await
    }

    pub async fn wait_result(&mut self) -> Result<ProducerOutput> {
        self.receive().await
    }

    pub async fn cancel_and_wait(&mut self) -> Result<()> {
        self.cancellation.cancel();
        match self.receive().await {
            Ok(_) => Ok(()),
            Err(error) if error.downcast_ref::<ExecutionCancelled>().is_some() => Ok(()),
            Err(error) => Err(error),
        }
    }
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::path::{Path, PathBuf};
    use std::pin::Pin;
    use std::sync::Arc;
    use std::task::{Context as TaskContext, Poll};
    use std::time::{Duration, Instant};

    use tempfile::TempDir;
    use tokio::io::{AsyncRead, ReadBuf};

    use tokio_util::sync::CancellationToken;
    use tokio_util::task::TaskTracker;

    use super::config::ProducerLimits;
    use super::execution::{
        close_request_directory, merge_operation_and_cleanup, output_path, DrainTasks,
    };
    use super::{ProducerConfig, ProducerKind, ProducerSupervisor};

    struct FailingReader;

    impl AsyncRead for FailingReader {
        fn poll_read(
            self: Pin<&mut Self>,
            _cx: &mut TaskContext<'_>,
            _buf: &mut ReadBuf<'_>,
        ) -> Poll<std::io::Result<()>> {
            Poll::Ready(Err(std::io::Error::other("fixture read failure")))
        }
    }

    fn executable(body: &str) -> (TempDir, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("fixture");
        fs::write(&path, format!("#!/bin/sh\n{body}\n")).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o755)).unwrap();
        (dir, path)
    }

    fn process_exists(pid: &str) -> bool {
        std::process::Command::new("kill")
            .args(["-0", pid])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .unwrap()
            .success()
    }

    async fn wait_for_files_or_completion(
        paths: &[&Path],
        execution: &mut super::ProducerExecution,
    ) {
        let early_completion = tokio::time::timeout(Duration::from_secs(5), async {
            loop {
                if paths.iter().all(|path| path.exists()) {
                    return None;
                }
                tokio::select! {
                    result = execution.wait_result() => return Some(result),
                    () = tokio::task::yield_now() => {}
                }
            }
        })
        .await
        .expect("producer neither wrote markers nor completed before the observation deadline");
        assert!(
            early_completion.is_none(),
            "producer completed before writing all observation markers"
        );
    }

    fn enabled(kind: ProducerKind, argv: Vec<String>, timeout: &str) -> ProducerConfig {
        let json = serde_json::to_string(&argv).unwrap();
        ProducerConfig::parse(kind, Some("true"), Some(&json), Some(timeout)).unwrap()
    }

    fn limits(kind: ProducerKind, max_output_bytes: u64) -> ProducerLimits {
        match kind {
            ProducerKind::Image => ProducerLimits {
                max_output_bytes,
                max_concurrency: 1,
                max_width: Some(2048),
                max_height: Some(2048),
                max_steps: Some(100),
                max_seconds: None,
            },
            ProducerKind::Audio => ProducerLimits {
                max_output_bytes,
                max_concurrency: 1,
                max_width: None,
                max_height: None,
                max_steps: None,
                max_seconds: Some(30.0),
            },
        }
    }

    fn enabled_with_limits(
        kind: ProducerKind,
        argv: Vec<String>,
        timeout: &str,
        limits: ProducerLimits,
    ) -> ProducerConfig {
        let json = serde_json::to_string(&argv).unwrap();
        ProducerConfig::parse_with_limits(
            kind,
            Some("true"),
            Some(&json),
            Some(timeout),
            Some(limits),
        )
        .unwrap()
    }

    fn supervisor() -> ProducerSupervisor {
        ProducerSupervisor::new(CancellationToken::new())
    }

    #[test]
    fn enabled_producer_requires_absolute_token_free_executable_and_limits() {
        let image_limits = limits(ProducerKind::Image, 1024);
        for executable in ["producer", "{out}"] {
            let argv = serde_json::to_string(&[executable, "{out}"]).unwrap();
            assert!(ProducerConfig::parse_with_limits(
                ProducerKind::Image,
                Some("true"),
                Some(&argv),
                Some("1"),
                Some(image_limits.clone()),
            )
            .is_err());
        }
        let argv = r#"["/missing/producer","{out}"]"#;
        assert!(ProducerConfig::parse_with_limits(
            ProducerKind::Image,
            Some("true"),
            Some(argv),
            Some("1"),
            None,
        )
        .is_err());

        let mut invalid_concurrency = image_limits;
        invalid_concurrency.max_concurrency = 0;
        let error = ProducerConfig::parse_with_limits(
            ProducerKind::Image,
            Some("true"),
            Some(argv),
            Some("1"),
            Some(invalid_concurrency),
        )
        .unwrap_err();
        assert!(
            error.to_string().contains("YTS_IMAGEGEN_MAX_CONCURRENCY"),
            "{error:#}"
        );
    }

    #[test]
    fn startup_rejects_missing_and_non_executable_producer() {
        let directory = tempfile::tempdir().unwrap();
        let missing = directory.path().join("missing");
        let config = enabled_with_limits(
            ProducerKind::Image,
            vec![missing.to_string_lossy().into_owned(), "{out}".into()],
            "1",
            limits(ProducerKind::Image, 1024),
        );
        assert!(config.validate_executable().is_err());

        let non_executable = directory.path().join("non-executable");
        fs::write(&non_executable, "fixture").unwrap();
        fs::set_permissions(&non_executable, fs::Permissions::from_mode(0o644)).unwrap();
        let config = enabled_with_limits(
            ProducerKind::Image,
            vec![
                non_executable.to_string_lossy().into_owned(),
                "{out}".into(),
            ],
            "1",
            limits(ProducerKind::Image, 1024),
        );
        assert!(config.validate_executable().is_err());
    }

    #[tokio::test]
    async fn output_is_read_only_up_to_the_configured_limit() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let (_fixture, executable) = executable("printf '12345' > \"$1\"");
        let config = enabled_with_limits(
            ProducerKind::Image,
            vec![executable.to_string_lossy().into_owned(), "{out}".into()],
            "2",
            limits(ProducerKind::Image, 4),
        );
        let supervisor = supervisor();

        let error = supervisor
            .execute(&config, "image.png", &[])
            .await
            .unwrap_err();

        assert!(error.to_string().contains("exceeds"), "{error:#}");
        supervisor.shutdown(Duration::from_secs(1)).await.unwrap();
    }

    #[tokio::test]
    async fn output_must_be_a_non_symlink_regular_file() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let observation = tempfile::tempdir().unwrap();
        let target = observation.path().join("target");
        fs::write(&target, "target bytes").unwrap();
        for body in ["ln -s \"$2\" \"$1\"", "mkdir \"$1\""] {
            let (_fixture, executable) = executable(body);
            let config = enabled_with_limits(
                ProducerKind::Image,
                vec![
                    executable.to_string_lossy().into_owned(),
                    "{out}".into(),
                    target.to_string_lossy().into_owned(),
                ],
                "2",
                limits(ProducerKind::Image, 1024),
            );
            let supervisor = supervisor();

            let error = supervisor
                .execute(&config, "image.png", &[])
                .await
                .unwrap_err();

            assert!(error.to_string().contains("regular file"), "{error:#}");
            supervisor.shutdown(Duration::from_secs(1)).await.unwrap();
        }
    }

    #[tokio::test]
    async fn tracked_worker_surfaces_tempdir_close_failure_on_success_and_primary_error() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        for (body, expected_primary) in [
            ("printf ok > \"$1\"", None),
            ("printf primary >&2; exit 7", Some("primary")),
        ] {
            let (_fixture, executable) = executable(body);
            let config = enabled_with_limits(
                ProducerKind::Image,
                vec![executable.to_string_lossy().into_owned(), "{out}".into()],
                "2",
                limits(ProducerKind::Image, 1024),
            );
            let supervisor = ProducerSupervisor::with_directory_closer(
                CancellationToken::new(),
                Arc::new(|directory| {
                    close_request_directory(directory)?;
                    anyhow::bail!("injected TempDir::close failure")
                }),
            );

            let error = supervisor
                .execute(&config, "image.png", &[])
                .await
                .unwrap_err();

            let message = format!("{error:#}");
            assert!(message.contains("injected TempDir::close failure"));
            if let Some(expected_primary) = expected_primary {
                assert!(message.contains(expected_primary), "{message}");
            }
            supervisor.shutdown(Duration::from_secs(1)).await.unwrap();
        }
    }

    #[tokio::test]
    async fn successful_direct_child_terminates_pipe_holding_descendant_immediately() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let (_fixture, executable) = executable(
            "printf '%s' ok > \"$1\"; sleep 30 & descendant=$!; printf '%s' \"$descendant\" > \"$2\"",
        );
        let observation = tempfile::tempdir().unwrap();
        let descendant_path = observation.path().join("descendant.pid");
        let config = enabled_with_limits(
            ProducerKind::Image,
            vec![
                executable.to_string_lossy().into_owned(),
                "{out}".into(),
                descendant_path.to_string_lossy().into_owned(),
            ],
            "3",
            limits(ProducerKind::Image, 1024),
        );
        let supervisor = supervisor();
        let output = supervisor.execute(&config, "image.png", &[]).await.unwrap();

        assert_eq!(output.bytes, b"ok");
        let descendant = fs::read_to_string(descendant_path).unwrap();
        assert!(!process_exists(descendant.trim()));
        supervisor.shutdown(Duration::from_secs(1)).await.unwrap();
    }

    #[tokio::test]
    async fn shutdown_cancels_and_reaps_active_execution_and_closes_tempdir() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let (_fixture, executable) =
            executable("printf '%s' \"$$\" > \"$2\"; printf '%s' \"$1\" > \"$3\"; exec sleep 30");
        let observation = tempfile::tempdir().unwrap();
        let pid_path = observation.path().join("pid");
        let output_path = observation.path().join("output.path");
        let config = enabled_with_limits(
            ProducerKind::Audio,
            vec![
                executable.to_string_lossy().into_owned(),
                "{out}".into(),
                pid_path.to_string_lossy().into_owned(),
                output_path.to_string_lossy().into_owned(),
            ],
            "30",
            limits(ProducerKind::Audio, 1024),
        );
        let supervisor = supervisor();
        let mut execution = supervisor.start(&config, "audio.wav", &[]).await.unwrap();
        wait_for_files_or_completion(&[&pid_path, &output_path], &mut execution).await;

        supervisor.shutdown(Duration::from_secs(2)).await.unwrap();
        let error = execution.wait().await.unwrap_err();

        let pid = fs::read_to_string(pid_path).unwrap();
        let temporary_output = PathBuf::from(fs::read_to_string(output_path).unwrap());
        assert!(!process_exists(pid.trim()));
        assert!(!temporary_output.parent().unwrap().exists());
        assert!(error.to_string().contains("cancelled"), "{error:#}");
    }

    #[tokio::test]
    async fn dropping_execution_receiver_still_converges_through_tracked_worker() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let (_fixture, executable) =
            executable("printf '%s' \"$$\" > \"$2\"; printf '%s' \"$1\" > \"$3\"; exec sleep 30");
        let observation = tempfile::tempdir().unwrap();
        let pid_path = observation.path().join("pid");
        let output_path = observation.path().join("output.path");
        let config = enabled_with_limits(
            ProducerKind::Audio,
            vec![
                executable.to_string_lossy().into_owned(),
                "{out}".into(),
                pid_path.to_string_lossy().into_owned(),
                output_path.to_string_lossy().into_owned(),
            ],
            "30",
            limits(ProducerKind::Audio, 1024),
        );
        let supervisor = supervisor();
        let mut execution = supervisor.start(&config, "audio.wav", &[]).await.unwrap();
        wait_for_files_or_completion(&[&pid_path, &output_path], &mut execution).await;

        drop(execution);
        supervisor.shutdown(Duration::from_secs(2)).await.unwrap();

        let pid = fs::read_to_string(pid_path).unwrap();
        let temporary_output = PathBuf::from(fs::read_to_string(output_path).unwrap());
        assert!(!process_exists(pid.trim()));
        assert!(!temporary_output.parent().unwrap().exists());
    }

    #[tokio::test]
    async fn concurrency_limit_rejects_without_waiting_and_releases_after_cleanup() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let (_fixture, executable) = executable("printf '%s' \"$$\" > \"$2\"; exec sleep 30");
        let observation = tempfile::tempdir().unwrap();
        let marker = observation.path().join("active.pid");
        let config = enabled_with_limits(
            ProducerKind::Image,
            vec![
                executable.to_string_lossy().into_owned(),
                "{out}".into(),
                marker.to_string_lossy().into_owned(),
            ],
            "30",
            limits(ProducerKind::Image, 1024),
        );
        let supervisor = supervisor();
        let cloned_config = config.clone();
        let mut first = supervisor.start(&config, "image.png", &[]).await.unwrap();
        wait_for_files_or_completion(&[&marker], &mut first).await;

        let second_error = match supervisor.start(&cloned_config, "image.png", &[]).await {
            Err(error) => Some(error),
            Ok(mut unexpected) => {
                unexpected.cancel_and_wait().await.unwrap();
                None
            }
        };
        first.cancel_and_wait().await.unwrap();
        let mut third = supervisor
            .start(&cloned_config, "image.png", &[])
            .await
            .unwrap();
        third.cancel_and_wait().await.unwrap();
        supervisor.shutdown(Duration::from_secs(2)).await.unwrap();

        let error = second_error.expect("second execution exceeded max_concurrency");
        assert!(error.to_string().contains("concurrency"), "{error:#}");
    }

    #[test]
    fn cleanup_failure_is_aggregated_with_the_primary_failure() {
        let error = merge_operation_and_cleanup::<()>(
            Err(anyhow::anyhow!("primary failure")),
            Err(anyhow::anyhow!("cleanup failure")),
        )
        .unwrap_err();

        let message = format!("{error:#}");
        assert!(message.contains("primary failure"));
        assert!(message.contains("cleanup failure"));
    }

    #[tokio::test]
    async fn completed_drain_error_cleanup_does_not_poll_join_handle_twice() {
        let tasks = TaskTracker::new();
        let mut drains = DrainTasks::spawn_tracked(FailingReader, tokio::io::empty(), &tasks);
        tasks.close();

        let error = drains
            .collect_until(
                tokio::time::Instant::now() + Duration::from_secs(1),
                ProducerKind::Image,
            )
            .await
            .unwrap_err();

        assert!(error.to_string().contains("stdout/stderr"), "{error:#}");
        drains
            .cancel_and_join_until(tokio::time::Instant::now() + Duration::from_secs(1))
            .await
            .unwrap();
        tasks.wait().await;
    }

    #[test]
    fn parses_json_argv_without_losing_argument_boundaries() {
        let config = enabled(
            ProducerKind::Image,
            vec![
                "/producer binary".into(),
                "--prompt".into(),
                "two words".into(),
                "{out}".into(),
            ],
            "2",
        );

        assert_eq!(
            config.argv(),
            &["/producer binary", "--prompt", "two words", "{out}"]
        );
    }

    #[test]
    fn enabled_producer_rejects_missing_or_empty_argv() {
        for argv in [None, Some(""), Some("[]")] {
            let error = ProducerConfig::parse(ProducerKind::Image, Some("true"), argv, Some("1"))
                .unwrap_err();
            assert!(error.to_string().contains("ARGV"), "{error:#}");
        }
    }

    #[test]
    fn enabled_producer_requires_output_token() {
        let argv = serde_json::to_string(&["/bin/true"]).unwrap();

        let error =
            ProducerConfig::parse(ProducerKind::Image, Some("true"), Some(&argv), Some("1"))
                .unwrap_err();

        assert!(error.to_string().contains("{out}"), "{error:#}");
    }

    #[test]
    fn output_token_may_be_standalone_or_embedded() {
        for output_argument in ["{out}", "--output={out}"] {
            let argv = serde_json::to_string(&["/bin/true", output_argument]).unwrap();

            ProducerConfig::parse(ProducerKind::Audio, Some("true"), Some(&argv), Some("1"))
                .unwrap();
        }
    }

    #[test]
    fn enabled_flag_is_required_and_strict() {
        for enabled in [None, Some("TRUE"), Some("1"), Some("")] {
            assert!(ProducerConfig::parse(ProducerKind::Audio, enabled, None, None).is_err());
        }
    }

    #[test]
    fn enabled_producer_requires_positive_explicit_timeout() {
        let argv = r#"["producer","{out}"]"#;
        for timeout in [None, Some(""), Some("0"), Some("nan")] {
            assert!(
                ProducerConfig::parse(ProducerKind::Audio, Some("true"), Some(argv), timeout)
                    .is_err()
            );
        }
    }

    #[test]
    fn rejects_unknown_and_malformed_template_tokens() {
        for token in ["{unknown}", "{prompt", "prompt}", "{}"] {
            let argv = serde_json::to_string(&["producer", token]).unwrap();
            assert!(
                ProducerConfig::parse(ProducerKind::Image, Some("true"), Some(&argv), Some("1"))
                    .is_err(),
                "accepted {token}"
            );
        }
    }

    #[tokio::test]
    async fn command_receives_literal_arguments_without_shell_interpretation() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let (_fixture, executable) = executable("printf '%s\\n' \"$2\" \"$3\" > \"$1\"");
        let marker_dir = tempfile::tempdir().unwrap();
        let marker = marker_dir.path().join("executed");
        let prompt = format!("two words {{literal}}; touch {} | $()", marker.display());
        let metacharacters = "literal;|$(touch should-not-run)";
        let config = enabled(
            ProducerKind::Image,
            vec![
                executable.to_string_lossy().into_owned(),
                "{out}".into(),
                "{prompt}".into(),
                metacharacters.into(),
            ],
            "2",
        );
        let supervisor = supervisor();

        let output = supervisor
            .execute(&config, "image.png", &[("prompt", prompt.as_str())])
            .await
            .unwrap();

        assert_eq!(
            String::from_utf8(output.bytes).unwrap(),
            format!("{prompt}\n{metacharacters}\n")
        );
        assert!(!marker.exists());
        supervisor.shutdown(Duration::from_secs(1)).await.unwrap();
    }

    #[tokio::test]
    async fn each_request_uses_a_unique_cleaned_temp_path() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let (_fixture, executable) = executable("printf '%s' \"$1\" > \"$1\"");
        let config = enabled(
            ProducerKind::Image,
            vec![executable.to_string_lossy().into_owned(), "{out}".into()],
            "2",
        );
        let supervisor = supervisor();

        let first = supervisor.execute(&config, "image.png", &[]).await.unwrap();
        let second = supervisor.execute(&config, "image.png", &[]).await.unwrap();
        let first_path = PathBuf::from(String::from_utf8(first.bytes).unwrap());
        let second_path = PathBuf::from(String::from_utf8(second.bytes).unwrap());

        assert_ne!(first_path, second_path);
        assert!(!first_path.exists());
        assert!(!second_path.exists());
        assert!(!first_path.parent().unwrap().exists());
        assert!(!second_path.parent().unwrap().exists());
        supervisor.shutdown(Duration::from_secs(1)).await.unwrap();
    }

    #[tokio::test]
    async fn timeout_kills_the_producer_and_cleans_temp_output() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let (_fixture, executable) = executable("printf '%s' \"$$\" > \"$2\"; exec sleep 10");
        let observation = tempfile::tempdir().unwrap();
        let pid_path = observation.path().join("pid");
        let config = enabled(
            ProducerKind::Audio,
            vec![
                executable.to_string_lossy().into_owned(),
                "{out}".into(),
                pid_path.to_string_lossy().into_owned(),
            ],
            "2",
        );
        let started = Instant::now();
        let supervisor = supervisor();

        let mut execution = supervisor.start(&config, "audio.wav", &[]).await.unwrap();
        wait_for_files_or_completion(&[&pid_path], &mut execution).await;
        let error = execution.wait().await.unwrap_err();

        assert!(started.elapsed() < Duration::from_secs(4));
        assert!(error.to_string().contains("timed out"), "{error:#}");
        let pid = fs::read_to_string(&pid_path).unwrap();
        let status = std::process::Command::new("kill")
            .args(["-0", pid.trim()])
            .stderr(std::process::Stdio::null())
            .status()
            .unwrap();
        assert!(!status.success(), "producer process {pid} survived timeout");
        supervisor.shutdown(Duration::from_secs(1)).await.unwrap();
    }

    #[tokio::test]
    async fn timeout_kills_descendants_bounds_pipe_drain_and_cleans_temp_directory() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let (_fixture, executable) = executable(
            "printf '%s' \"$$\" > \"$2\"; printf '%s' \"$1\" > \"$4\"; sleep 30 & descendant=$!; printf '%s' \"$descendant\" > \"$3\"; wait",
        );
        let observation = tempfile::tempdir().unwrap();
        let parent_pid_path = observation.path().join("parent.pid");
        let descendant_pid_path = observation.path().join("descendant.pid");
        let output_path_observation = observation.path().join("output.path");
        let config = enabled(
            ProducerKind::Image,
            vec![
                executable.to_string_lossy().into_owned(),
                "{out}".into(),
                parent_pid_path.to_string_lossy().into_owned(),
                descendant_pid_path.to_string_lossy().into_owned(),
                output_path_observation.to_string_lossy().into_owned(),
            ],
            "2",
        );
        let started = Instant::now();
        let supervisor = supervisor();
        let mut execution = supervisor.start(&config, "image.png", &[]).await.unwrap();
        let marker_paths = [
            parent_pid_path.as_path(),
            descendant_pid_path.as_path(),
            output_path_observation.as_path(),
        ];
        let early_completion = tokio::time::timeout(Duration::from_secs(3), async {
            loop {
                if marker_paths.iter().all(|path| path.exists()) {
                    return None;
                }
                tokio::select! {
                    result = execution.wait_result() => return Some(result),
                    () = tokio::task::yield_now() => {}
                }
            }
        })
        .await
        .expect("producer neither wrote its markers nor completed before its own timeout");
        assert!(
            early_completion.is_none(),
            "producer completed before writing observation markers"
        );

        let outcome = tokio::time::timeout(Duration::from_secs(3), execution.wait())
            .await
            .expect("tracked producer exceeded its execution and cleanup deadlines");
        let parent_pid = fs::read_to_string(&parent_pid_path).unwrap();
        let descendant_pid = fs::read_to_string(&descendant_pid_path).unwrap();
        let output_path = PathBuf::from(fs::read_to_string(&output_path_observation).unwrap());
        let parent_survived = process_exists(parent_pid.trim());
        let descendant_survived = process_exists(descendant_pid.trim());
        let error = outcome.unwrap_err();
        assert!(started.elapsed() < Duration::from_secs(4));
        assert!(error.to_string().contains("timed out"), "{error:#}");
        assert!(
            !parent_survived,
            "parent process {parent_pid} survived timeout"
        );
        assert!(
            !descendant_survived,
            "descendant process {descendant_pid} survived timeout"
        );
        assert!(!output_path.exists());
        assert!(!output_path.parent().unwrap().exists());
        supervisor.shutdown(Duration::from_secs(1)).await.unwrap();
    }

    #[test]
    fn output_path_is_always_inside_its_request_directory() {
        let request_dir = Path::new("/tmp/request");
        assert_eq!(
            output_path(request_dir, "audio.wav").unwrap(),
            request_dir.join("audio.wav")
        );
        assert!(output_path(request_dir, "../escape.wav").is_err());
    }
}
