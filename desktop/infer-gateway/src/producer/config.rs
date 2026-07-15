use std::collections::HashMap;
use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{anyhow, bail, Context, Result};
use tokio::sync::{OwnedSemaphorePermit, Semaphore, TryAcquireError};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ProducerKind {
    Image,
    Audio,
}

impl ProducerKind {
    pub(super) fn name(self) -> &'static str {
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

    fn max_output_bytes_env(self) -> &'static str {
        match self {
            Self::Image => "YTS_IMAGEGEN_MAX_OUTPUT_BYTES",
            Self::Audio => "YTS_AUDIOGEN_MAX_OUTPUT_BYTES",
        }
    }

    fn max_concurrency_env(self) -> &'static str {
        match self {
            Self::Image => "YTS_IMAGEGEN_MAX_CONCURRENCY",
            Self::Audio => "YTS_AUDIOGEN_MAX_CONCURRENCY",
        }
    }

    fn max_width_env(self) -> Option<&'static str> {
        match self {
            Self::Image => Some("YTS_IMAGEGEN_MAX_WIDTH"),
            Self::Audio => None,
        }
    }

    fn max_height_env(self) -> Option<&'static str> {
        match self {
            Self::Image => Some("YTS_IMAGEGEN_MAX_HEIGHT"),
            Self::Audio => None,
        }
    }

    fn max_steps_env(self) -> Option<&'static str> {
        match self {
            Self::Image => Some("YTS_IMAGEGEN_MAX_STEPS"),
            Self::Audio => None,
        }
    }

    fn max_seconds_env(self) -> Option<&'static str> {
        match self {
            Self::Image => None,
            Self::Audio => Some("YTS_AUDIOGEN_MAX_SECONDS"),
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
pub(super) struct ProducerLimits {
    pub(super) max_output_bytes: u64,
    pub(super) max_concurrency: usize,
    pub(super) max_width: Option<u32>,
    pub(super) max_height: Option<u32>,
    pub(super) max_steps: Option<u32>,
    pub(super) max_seconds: Option<f32>,
}

#[derive(Clone, Debug)]
pub struct ProducerConfig {
    pub(super) kind: ProducerKind,
    pub(super) enabled: bool,
    pub(super) argv: Option<Vec<String>>,
    pub(super) timeout: Option<Duration>,
    pub(super) limits: Option<ProducerLimits>,
    concurrency: Arc<Semaphore>,
}

impl ProducerLimits {
    fn from_env(kind: ProducerKind) -> Result<Self> {
        let max_output_bytes = parse_positive_integer::<u64>(
            kind.max_output_bytes_env(),
            required_optional_env(kind.max_output_bytes_env())?.as_deref(),
        )?;
        max_output_bytes
            .checked_add(1)
            .ok_or_else(|| anyhow!("{} is too large", kind.max_output_bytes_env()))?;
        let max_concurrency = parse_positive_integer::<usize>(
            kind.max_concurrency_env(),
            required_optional_env(kind.max_concurrency_env())?.as_deref(),
        )?;
        let max_width = parse_optional_kind_integer(kind.max_width_env())?;
        let max_height = parse_optional_kind_integer(kind.max_height_env())?;
        let max_steps = parse_optional_kind_integer(kind.max_steps_env())?;
        let max_seconds = match kind.max_seconds_env() {
            Some(key) => Some(parse_positive_float(
                key,
                required_optional_env(key)?.as_deref(),
            )?),
            None => None,
        };
        let limits = Self {
            max_output_bytes,
            max_concurrency,
            max_width,
            max_height,
            max_steps,
            max_seconds,
        };
        limits.validate_kind(kind)?;
        Ok(limits)
    }

    #[cfg(test)]
    fn for_test(kind: ProducerKind) -> Self {
        match kind {
            ProducerKind::Image => Self {
                max_output_bytes: 64 * 1024 * 1024,
                max_concurrency: 1,
                max_width: Some(2048),
                max_height: Some(2048),
                max_steps: Some(100),
                max_seconds: None,
            },
            ProducerKind::Audio => Self {
                max_output_bytes: 64 * 1024 * 1024,
                max_concurrency: 1,
                max_width: None,
                max_height: None,
                max_steps: None,
                max_seconds: Some(600.0),
            },
        }
    }

    fn validate_kind(&self, kind: ProducerKind) -> Result<()> {
        self.max_output_bytes
            .checked_add(1)
            .ok_or_else(|| anyhow!("{} is too large", kind.max_output_bytes_env()))?;
        if self.max_concurrency == 0 {
            bail!("{} must be greater than zero", kind.max_concurrency_env());
        }
        match kind {
            ProducerKind::Image => {
                if self.max_width.is_none() || self.max_height.is_none() || self.max_steps.is_none()
                {
                    bail!("imagegen requires max_width, max_height, and max_steps limits");
                }
                if self.max_seconds.is_some() {
                    bail!("imagegen forbids max_seconds limit");
                }
            }
            ProducerKind::Audio => {
                if self.max_seconds.is_none() {
                    bail!("audiogen requires max_seconds limit");
                }
                if self.max_width.is_some() || self.max_height.is_some() || self.max_steps.is_some()
                {
                    bail!("audiogen forbids image request limits");
                }
            }
        }
        Ok(())
    }
}

impl ProducerConfig {
    pub fn from_env(kind: ProducerKind) -> Result<Self> {
        let enabled = optional_env(kind.enabled_env())?;
        let argv = optional_env(kind.argv_env())?;
        let timeout = optional_env(kind.timeout_env())?;
        let limits = match enabled.as_deref() {
            Some("true") => Some(ProducerLimits::from_env(kind)?),
            _ => None,
        };
        Self::parse_with_limits(
            kind,
            enabled.as_deref(),
            argv.as_deref(),
            timeout.as_deref(),
            limits,
        )
    }

    #[cfg(test)]
    pub fn parse(
        kind: ProducerKind,
        enabled: Option<&str>,
        argv: Option<&str>,
        timeout_seconds: Option<&str>,
    ) -> Result<Self> {
        let limits = match enabled {
            Some("true") => Some(ProducerLimits::for_test(kind)),
            _ => None,
        };
        Self::parse_with_limits(kind, enabled, argv, timeout_seconds, limits)
    }

    pub(super) fn parse_with_limits(
        kind: ProducerKind,
        enabled: Option<&str>,
        argv: Option<&str>,
        timeout_seconds: Option<&str>,
        limits: Option<ProducerLimits>,
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
        if enabled
            && !argv
                .as_deref()
                .expect("enabled producer argv was validated above")
                .iter()
                .try_fold(false, |found, argument| {
                    Ok::<_, anyhow::Error>(found || template_has_token(argument, "out")?)
                })?
        {
            bail!(
                "{} must contain an {{out}} template token when enabled",
                kind.argv_env()
            );
        }
        if enabled && timeout.is_none() {
            bail!(
                "{} is required when {}=true",
                kind.timeout_env(),
                kind.enabled_env()
            );
        }
        if enabled && limits.is_none() {
            bail!(
                "{} is required when {}=true",
                kind.max_output_bytes_env(),
                kind.enabled_env()
            );
        }
        if let Some(limits) = &limits {
            limits.validate_kind(kind)?;
        }
        let max_concurrency = limits.as_ref().map_or(0, |limits| limits.max_concurrency);

        Ok(Self {
            kind,
            enabled,
            argv,
            timeout,
            limits,
            concurrency: Arc::new(Semaphore::new(max_concurrency)),
        })
    }

    pub fn enabled(&self) -> bool {
        self.enabled
    }

    pub fn configured(&self) -> bool {
        self.argv.is_some() && self.timeout.is_some() && self.limits.is_some()
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

    pub fn validate_executable(&self) -> Result<()> {
        if !self.enabled {
            return Ok(());
        }
        let executable = self
            .argv
            .as_ref()
            .and_then(|argv| argv.first())
            .ok_or_else(|| anyhow!("{} enabled producer has no executable", self.kind.name()))?;
        let metadata = std::fs::symlink_metadata(executable)
            .with_context(|| format!("inspect {} executable {executable:?}", self.kind.name()))?;
        if !metadata.file_type().is_file() {
            bail!(
                "{} executable {executable:?} is not a regular file",
                self.kind.name()
            );
        }
        if metadata.permissions().mode() & 0o111 == 0 {
            bail!(
                "{} executable {executable:?} is not executable",
                self.kind.name()
            );
        }
        Ok(())
    }

    pub fn validate_image_request(&self, width: u32, height: u32, steps: u32) -> Result<()> {
        let limits = self.required_limits()?;
        require_at_most("width", width, limits.max_width)?;
        require_at_most("height", height, limits.max_height)?;
        require_at_most("steps", steps, limits.max_steps)?;
        Ok(())
    }

    pub fn validate_audio_request(&self, seconds: f32) -> Result<()> {
        let limits = self.required_limits()?;
        let max_seconds = limits
            .max_seconds
            .ok_or_else(|| anyhow!("{} has no max_seconds limit", self.kind.name()))?;
        if seconds > max_seconds {
            bail!("seconds {seconds} exceeds configured maximum {max_seconds}");
        }
        Ok(())
    }

    pub(super) fn required_limits(&self) -> Result<&ProducerLimits> {
        self.limits.as_ref().ok_or_else(|| {
            anyhow!(
                "{} has no limits despite enabled configuration",
                self.kind.name()
            )
        })
    }

    pub(super) fn try_acquire_execution_permit(&self) -> Result<OwnedSemaphorePermit> {
        let maximum = self.required_limits()?.max_concurrency;
        match Arc::clone(&self.concurrency).try_acquire_owned() {
            Ok(permit) => Ok(permit),
            Err(TryAcquireError::NoPermits) => bail!(
                "{} concurrency limit of {maximum} is exhausted",
                self.kind.name()
            ),
            Err(TryAcquireError::Closed) => {
                bail!("{} concurrency limiter is closed", self.kind.name())
            }
        }
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

fn required_optional_env(key: &str) -> Result<Option<String>> {
    let value = optional_env(key)?;
    if value.as_deref().is_none_or(str::is_empty) {
        bail!("{key} is required and must not be empty");
    }
    Ok(value)
}

fn parse_optional_kind_integer(key: Option<&str>) -> Result<Option<u32>> {
    match key {
        Some(key) => Ok(Some(parse_positive_integer::<u32>(
            key,
            required_optional_env(key)?.as_deref(),
        )?)),
        None => Ok(None),
    }
}

fn parse_positive_integer<T>(key: &str, value: Option<&str>) -> Result<T>
where
    T: std::str::FromStr + PartialEq + Default,
    T::Err: std::error::Error + Send + Sync + 'static,
{
    let value = value.ok_or_else(|| anyhow!("{key} is required"))?;
    let parsed = value
        .parse::<T>()
        .with_context(|| format!("{key} must be a positive integer"))?;
    if parsed == T::default() {
        bail!("{key} must be greater than zero");
    }
    Ok(parsed)
}

fn parse_positive_float(key: &str, value: Option<&str>) -> Result<f32> {
    let value = value.ok_or_else(|| anyhow!("{key} is required"))?;
    let parsed = value
        .parse::<f32>()
        .with_context(|| format!("{key} must be a positive number"))?;
    if !parsed.is_finite() || parsed <= 0.0 {
        bail!("{key} must be finite and greater than zero");
    }
    Ok(parsed)
}

fn require_at_most(name: &str, value: u32, maximum: Option<u32>) -> Result<()> {
    let maximum = maximum.ok_or_else(|| anyhow!("missing configured maximum for {name}"))?;
    if value > maximum {
        bail!("{name} {value} exceeds configured maximum {maximum}");
    }
    Ok(())
}

fn parse_argv(kind: ProducerKind, raw: &str) -> Result<Vec<String>> {
    if raw.is_empty() {
        bail!("{} must not be empty", kind.argv_env());
    }
    let argv: Vec<String> = serde_json::from_str(raw)
        .with_context(|| format!("{} must be a JSON string array", kind.argv_env()))?;
    let executable = argv
        .first()
        .ok_or_else(|| anyhow!("{} must not be an empty array", kind.argv_env()))?;
    if executable.is_empty() {
        bail!("{} executable must not be empty", kind.argv_env());
    }
    for argument in &argv {
        validate_template(kind, argument)?;
    }
    if !Path::new(executable).is_absolute() {
        bail!("{} executable must be an absolute path", kind.argv_env());
    }
    if visit_tokens(executable, |_| {
        bail!("executable must not contain template tokens")
    })
    .is_err()
    {
        bail!("{} executable must be token-free", kind.argv_env());
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

fn template_has_token(argument: &str, expected: &str) -> Result<bool> {
    let mut found = false;
    visit_tokens(argument, |token| {
        found |= token == expected;
        Ok(())
    })?;
    Ok(found)
}

pub(super) fn replacement_map<'a>(
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

pub(super) fn expand_argument(
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

#[cfg(test)]
mod tests {
    use super::{parse_positive_integer, ProducerKind};

    #[test]
    fn concurrency_environment_keys_are_kind_specific() {
        assert_eq!(
            ProducerKind::Image.max_concurrency_env(),
            "YTS_IMAGEGEN_MAX_CONCURRENCY"
        );
        assert_eq!(
            ProducerKind::Audio.max_concurrency_env(),
            "YTS_AUDIOGEN_MAX_CONCURRENCY"
        );
    }

    #[test]
    fn concurrency_values_require_a_positive_integer() {
        for kind in [ProducerKind::Image, ProducerKind::Audio] {
            let key = kind.max_concurrency_env();
            for value in [None, Some(""), Some("0"), Some("-1"), Some("1.5")] {
                assert!(
                    parse_positive_integer::<usize>(key, value).is_err(),
                    "accepted {key}={value:?}"
                );
            }
            assert_eq!(parse_positive_integer::<usize>(key, Some("2")).unwrap(), 2);
        }
    }
}
