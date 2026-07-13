use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use anyhow::{anyhow, bail, Context, Result};
use tokio::io::{AsyncRead, AsyncReadExt};

const DRAIN_CAPTURE_LIMIT: usize = 64 * 1024;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ProducerKind {
    Image,
    Audio,
}

impl ProducerKind {
    fn name(self) -> &'static str {
        match self {
            Self::Image => "imagegen",
            Self::Audio => "audiogen",
        }
    }

    fn enabled_env(self) -> &'static str {
        match self {
            Self::Image => "YTS_IMAGEGEN_ENABLED",
            Self::Audio => "YTS_AUDIOGEN_ENABLED",
        }
    }

    fn argv_env(self) -> &'static str {
        match self {
            Self::Image => "YTS_IMAGEGEN_ARGV",
            Self::Audio => "YTS_AUDIOGEN_ARGV",
        }
    }

    fn timeout_env(self) -> &'static str {
        match self {
            Self::Image => "YTS_IMAGEGEN_TIMEOUT_SECONDS",
            Self::Audio => "YTS_AUDIOGEN_TIMEOUT_SECONDS",
        }
    }

    fn allowed_tokens(self) -> &'static [&'static str] {
        match self {
            Self::Image => &["prompt", "out", "width", "height", "steps"],
            Self::Audio => &["prompt", "out", "seconds"],
        }
    }
}

#[derive(Clone, Debug)]
pub struct ProducerConfig {
    kind: ProducerKind,
    enabled: bool,
    argv: Option<Vec<String>>,
    timeout: Option<Duration>,
}

#[derive(Debug)]
pub struct ProducerOutput {
    pub bytes: Vec<u8>,
}

impl ProducerConfig {
    pub fn from_env(kind: ProducerKind) -> Result<Self> {
        let enabled = optional_env(kind.enabled_env())?;
        let argv = optional_env(kind.argv_env())?;
        let timeout = optional_env(kind.timeout_env())?;
        Self::parse(
            kind,
            enabled.as_deref(),
            argv.as_deref(),
            timeout.as_deref(),
        )
    }

    pub fn parse(
        kind: ProducerKind,
        enabled: Option<&str>,
        argv: Option<&str>,
        timeout_seconds: Option<&str>,
    ) -> Result<Self> {
        let enabled = match enabled {
            Some("true") => true,
            Some("false") => false,
            Some(value) => bail!(
                "{} must be exactly true or false, got {value:?}",
                kind.enabled_env()
            ),
            None => bail!("{} is required", kind.enabled_env()),
        };

        let argv = argv
            .map(|raw| parse_argv(kind, raw))
            .transpose()
            .with_context(|| format!("invalid {}", kind.argv_env()))?;
        let timeout = timeout_seconds
            .map(|raw| parse_timeout(kind, raw))
            .transpose()?;

        if enabled && argv.as_ref().is_none_or(Vec::is_empty) {
            bail!(
                "{} must be a non-empty JSON array when {}=true",
                kind.argv_env(),
                kind.enabled_env()
            );
        }
        if enabled && timeout.is_none() {
            bail!(
                "{} is required when {}=true",
                kind.timeout_env(),
                kind.enabled_env()
            );
        }

        Ok(Self {
            kind,
            enabled,
            argv,
            timeout,
        })
    }

    pub fn enabled(&self) -> bool {
        self.enabled
    }

    pub fn configured(&self) -> bool {
        self.argv.is_some() && self.timeout.is_some()
    }

    #[cfg(test)]
    pub fn argv(&self) -> &[String] {
        self.argv
            .as_deref()
            .expect("enabled test producer must have argv")
    }

    pub fn kind_name(&self) -> &'static str {
        self.kind.name()
    }

    pub async fn execute(
        &self,
        output_filename: &str,
        replacements: &[(&str, &str)],
    ) -> Result<ProducerOutput> {
        if !self.enabled {
            bail!("{} capability is disabled", self.kind.name());
        }
        let argv = self.argv.as_ref().ok_or_else(|| {
            anyhow!(
                "{} has no argv despite enabled configuration",
                self.kind.name()
            )
        })?;
        let timeout = self.timeout.ok_or_else(|| {
            anyhow!(
                "{} has no timeout despite enabled configuration",
                self.kind.name()
            )
        })?;

        let request_dir = tempfile::Builder::new()
            .prefix(&format!("yts-{}-", self.kind.name()))
            .tempdir()
            .with_context(|| format!("create {} request directory", self.kind.name()))?;
        let output = output_path(request_dir.path(), output_filename)?;
        let output_value = output
            .to_str()
            .ok_or_else(|| anyhow!("{} output path is not valid UTF-8", self.kind.name()))?;
        let values = replacement_map(self.kind, replacements, output_value)?;
        let expanded = argv
            .iter()
            .map(|argument| expand_argument(self.kind, argument, &values))
            .collect::<Result<Vec<_>>>()?;

        let mut command = tokio::process::Command::new(&expanded[0]);
        command
            .args(&expanded[1..])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        let mut child = command
            .spawn()
            .with_context(|| format!("spawn {} executable {:?}", self.kind.name(), expanded[0]))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| anyhow!("{} stdout pipe missing", self.kind.name()))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| anyhow!("{} stderr pipe missing", self.kind.name()))?;
        let stdout_task = tokio::spawn(drain(stdout));
        let stderr_task = tokio::spawn(drain(stderr));

        let status = match tokio::time::timeout(timeout, child.wait()).await {
            Ok(status) => {
                status.with_context(|| format!("wait for {} process", self.kind.name()))?
            }
            Err(_) => {
                child
                    .kill()
                    .await
                    .with_context(|| format!("kill timed out {} process", self.kind.name()))?;
                child
                    .wait()
                    .await
                    .with_context(|| format!("reap timed out {} process", self.kind.name()))?;
                let _ = collect_drains(stdout_task, stderr_task, self.kind).await?;
                bail!(
                    "{} timed out after {} seconds",
                    self.kind.name(),
                    timeout.as_secs_f64()
                );
            }
        };
        let (_stdout, stderr) = collect_drains(stdout_task, stderr_task, self.kind).await?;
        if !status.success() {
            let stderr = String::from_utf8(stderr)
                .with_context(|| format!("{} stderr is not UTF-8", self.kind.name()))?;
            bail!("{} exited {status}: {}", self.kind.name(), stderr.trim());
        }

        let bytes = std::fs::read(&output)
            .with_context(|| format!("read {} output {}", self.kind.name(), output.display()))?;
        if bytes.is_empty() {
            bail!("{} produced an empty output file", self.kind.name());
        }
        Ok(ProducerOutput { bytes })
    }
}

fn optional_env(key: &str) -> Result<Option<String>> {
    match std::env::var(key) {
        Ok(value) => Ok(Some(value)),
        Err(std::env::VarError::NotPresent) => Ok(None),
        Err(std::env::VarError::NotUnicode(value)) => {
            bail!("{key} is not valid UTF-8: {value:?}")
        }
    }
}

fn parse_argv(kind: ProducerKind, raw: &str) -> Result<Vec<String>> {
    if raw.is_empty() {
        bail!("{} must not be empty", kind.argv_env());
    }
    let argv: Vec<String> = serde_json::from_str(raw)
        .with_context(|| format!("{} must be a JSON string array", kind.argv_env()))?;
    if argv.first().is_some_and(|executable| executable.is_empty()) {
        bail!("{} executable must not be empty", kind.argv_env());
    }
    for argument in &argv {
        validate_template(kind, argument)?;
    }
    Ok(argv)
}

fn parse_timeout(kind: ProducerKind, raw: &str) -> Result<Duration> {
    let seconds: f64 = raw
        .parse()
        .with_context(|| format!("{} must be a positive number", kind.timeout_env()))?;
    if !seconds.is_finite() || seconds <= 0.0 {
        bail!(
            "{} must be finite and greater than zero",
            kind.timeout_env()
        );
    }
    Duration::try_from_secs_f64(seconds).with_context(|| {
        format!(
            "{} is outside the supported duration range",
            kind.timeout_env()
        )
    })
}

fn validate_template(kind: ProducerKind, argument: &str) -> Result<()> {
    visit_tokens(argument, |token| {
        if !kind.allowed_tokens().contains(&token) {
            bail!("unknown {} template token {{{token}}}", kind.name());
        }
        Ok(())
    })
}

fn replacement_map<'a>(
    kind: ProducerKind,
    replacements: &'a [(&'a str, &'a str)],
    output: &'a str,
) -> Result<HashMap<&'a str, &'a str>> {
    let mut values = HashMap::with_capacity(replacements.len() + 1);
    values.insert("out", output);
    for &(token, value) in replacements {
        if token == "out" {
            bail!("{} output token is managed by the gateway", kind.name());
        }
        if !kind.allowed_tokens().contains(&token) {
            bail!("unknown {} replacement token {{{token}}}", kind.name());
        }
        if values.insert(token, value).is_some() {
            bail!("duplicate {} replacement token {{{token}}}", kind.name());
        }
    }
    Ok(values)
}

fn expand_argument(
    kind: ProducerKind,
    argument: &str,
    values: &HashMap<&str, &str>,
) -> Result<String> {
    let mut expanded = String::with_capacity(argument.len());
    let mut cursor = 0;
    visit_token_ranges(argument, |start, end, token| {
        expanded.push_str(&argument[cursor..start]);
        let value = values
            .get(token)
            .ok_or_else(|| anyhow!("missing {} replacement for {{{token}}}", kind.name()))?;
        expanded.push_str(value);
        cursor = end;
        Ok(())
    })?;
    expanded.push_str(&argument[cursor..]);
    Ok(expanded)
}

fn visit_tokens(argument: &str, mut visitor: impl FnMut(&str) -> Result<()>) -> Result<()> {
    visit_token_ranges(argument, |_, _, token| visitor(token))
}

fn visit_token_ranges(
    argument: &str,
    mut visitor: impl FnMut(usize, usize, &str) -> Result<()>,
) -> Result<()> {
    let bytes = argument.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'{' => {
                let close = bytes[index + 1..]
                    .iter()
                    .position(|byte| *byte == b'}')
                    .map(|offset| index + 1 + offset)
                    .ok_or_else(|| anyhow!("unclosed template token in argument {argument:?}"))?;
                let token = &argument[index + 1..close];
                if token.is_empty() || token.as_bytes().contains(&b'{') {
                    bail!("malformed template token in argument {argument:?}");
                }
                visitor(index, close + 1, token)?;
                index = close + 1;
            }
            b'}' => bail!("unmatched closing brace in argument {argument:?}"),
            _ => index += 1,
        }
    }
    Ok(())
}

pub fn output_path(request_dir: &Path, filename: &str) -> Result<PathBuf> {
    let mut components = Path::new(filename).components();
    match (components.next(), components.next()) {
        (Some(Component::Normal(name)), None) => Ok(request_dir.join(name)),
        _ => bail!("producer output filename must be a single normal path component"),
    }
}

async fn drain(mut stream: impl AsyncRead + Unpin) -> std::io::Result<Vec<u8>> {
    let mut captured = Vec::new();
    let mut chunk = [0_u8; 8192];
    loop {
        let count = stream.read(&mut chunk).await?;
        if count == 0 {
            return Ok(captured);
        }
        let remaining = DRAIN_CAPTURE_LIMIT.saturating_sub(captured.len());
        captured.extend_from_slice(&chunk[..count.min(remaining)]);
    }
}

async fn collect_drains(
    stdout: tokio::task::JoinHandle<std::io::Result<Vec<u8>>>,
    stderr: tokio::task::JoinHandle<std::io::Result<Vec<u8>>>,
    kind: ProducerKind,
) -> Result<(Vec<u8>, Vec<u8>)> {
    let stdout = stdout
        .await
        .with_context(|| format!("{} stdout drain task failed", kind.name()))?
        .with_context(|| format!("read {} stdout", kind.name()))?;
    let stderr = stderr
        .await
        .with_context(|| format!("{} stderr drain task failed", kind.name()))?
        .with_context(|| format!("read {} stderr", kind.name()))?;
    Ok((stdout, stderr))
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::path::{Path, PathBuf};
    use std::time::{Duration, Instant};

    use tempfile::TempDir;

    use super::{ProducerConfig, ProducerKind};

    fn executable(body: &str) -> (TempDir, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("fixture");
        fs::write(&path, format!("#!/bin/sh\n{body}\n")).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o755)).unwrap();
        (dir, path)
    }

    fn enabled(kind: ProducerKind, argv: Vec<String>, timeout: &str) -> ProducerConfig {
        let json = serde_json::to_string(&argv).unwrap();
        ProducerConfig::parse(kind, Some("true"), Some(&json), Some(timeout)).unwrap()
    }

    #[test]
    fn parses_json_argv_without_losing_argument_boundaries() {
        let config = enabled(
            ProducerKind::Image,
            vec![
                "producer binary".into(),
                "--prompt".into(),
                "two words".into(),
                "{out}".into(),
            ],
            "2",
        );

        assert_eq!(
            config.argv(),
            &["producer binary", "--prompt", "two words", "{out}"]
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

        let output = config
            .execute("image.png", &[("prompt", prompt.as_str())])
            .await
            .unwrap();

        assert_eq!(
            String::from_utf8(output.bytes).unwrap(),
            format!("{prompt}\n{metacharacters}\n")
        );
        assert!(!marker.exists());
    }

    #[tokio::test]
    async fn each_request_uses_a_unique_cleaned_temp_path() {
        let (_fixture, executable) = executable("printf '%s' \"$1\" > \"$1\"");
        let config = enabled(
            ProducerKind::Image,
            vec![executable.to_string_lossy().into_owned(), "{out}".into()],
            "2",
        );

        let first = config.execute("image.png", &[]).await.unwrap();
        let second = config.execute("image.png", &[]).await.unwrap();
        let first_path = PathBuf::from(String::from_utf8(first.bytes).unwrap());
        let second_path = PathBuf::from(String::from_utf8(second.bytes).unwrap());

        assert_ne!(first_path, second_path);
        assert!(!first_path.exists());
        assert!(!second_path.exists());
        assert!(!first_path.parent().unwrap().exists());
        assert!(!second_path.parent().unwrap().exists());
    }

    #[tokio::test]
    async fn timeout_kills_the_producer_and_cleans_temp_output() {
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

        let error = config.execute("audio.wav", &[]).await.unwrap_err();

        assert!(started.elapsed() < Duration::from_secs(4));
        assert!(error.to_string().contains("timed out"), "{error:#}");
        let pid = fs::read_to_string(&pid_path).unwrap();
        let status = std::process::Command::new("kill")
            .args(["-0", pid.trim()])
            .stderr(std::process::Stdio::null())
            .status()
            .unwrap();
        assert!(!status.success(), "producer process {pid} survived timeout");
    }

    #[test]
    fn output_path_is_always_inside_its_request_directory() {
        let request_dir = Path::new("/tmp/request");
        assert_eq!(
            super::output_path(request_dir, "audio.wav").unwrap(),
            request_dir.join("audio.wav")
        );
        assert!(super::output_path(request_dir, "../escape.wav").is_err());
    }
}
