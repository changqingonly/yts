//! 文本后端:代理外部常驻 `llama-server` 的 OpenAI 兼容接口。

use std::time::{Duration, Instant};

use axum::extract::State;
use axum::http::StatusCode;
use axum::Json;
use serde::{Deserialize, Serialize};

use anyhow::{bail, Context, Result};
use tokio_util::sync::CancellationToken;

use crate::GatewayState;

#[derive(Debug)]
pub struct LlamaConfig {
    pub base_url: String,
    pub model: String,
    pub startup_timeout: Duration,
    pub probe_timeout: Duration,
    pub completion_timeout: Duration,
    pub poll_interval: Duration,
}

impl LlamaConfig {
    pub fn from_env() -> Result<Self> {
        let base_url = required_env("YTS_LLAMA_BASE_URL")?;
        let model = required_env("YTS_LLAMA_MODEL")?;
        let startup_timeout = required_env("YTS_LLAMA_STARTUP_TIMEOUT_SECONDS")?;
        let probe_timeout = required_env("YTS_LLAMA_PROBE_TIMEOUT_SECONDS")?;
        let completion_timeout = required_env("YTS_LLAMA_COMPLETION_TIMEOUT_SECONDS")?;
        Self::parse_with_model(
            Some(&base_url),
            Some(&model),
            Some(&startup_timeout),
            Some(&probe_timeout),
            Some(&completion_timeout),
        )
    }

    #[cfg(test)]
    fn parse(
        base_url: Option<&str>,
        startup_timeout: Option<&str>,
        probe_timeout: Option<&str>,
        completion_timeout: Option<&str>,
    ) -> Result<Self> {
        Self::parse_with_model(
            base_url,
            Some("test-model"),
            startup_timeout,
            probe_timeout,
            completion_timeout,
        )
    }

    fn parse_with_model(
        base_url: Option<&str>,
        model: Option<&str>,
        startup_timeout: Option<&str>,
        probe_timeout: Option<&str>,
        completion_timeout: Option<&str>,
    ) -> Result<Self> {
        let base_url = base_url.filter(|value| !value.is_empty()).ok_or_else(|| {
            anyhow::anyhow!("YTS_LLAMA_BASE_URL is required and must not be empty")
        })?;
        let mut parsed =
            reqwest::Url::parse(base_url).context("YTS_LLAMA_BASE_URL is not a valid URL")?;
        if !matches!(parsed.scheme(), "http" | "https") {
            bail!("YTS_LLAMA_BASE_URL must use http or https");
        }
        if parsed.query().is_some() || parsed.fragment().is_some() {
            bail!("YTS_LLAMA_BASE_URL must not contain a query or fragment");
        }
        let path = parsed.path().trim_end_matches('/').to_string();
        parsed.set_path(&path);

        let model = model
            .filter(|value| !value.is_empty())
            .ok_or_else(|| anyhow::anyhow!("YTS_LLAMA_MODEL is required and must not be empty"))?;
        let startup_timeout = parse_timeout("YTS_LLAMA_STARTUP_TIMEOUT_SECONDS", startup_timeout)?;
        let probe_timeout = parse_timeout("YTS_LLAMA_PROBE_TIMEOUT_SECONDS", probe_timeout)?;
        let completion_timeout =
            parse_timeout("YTS_LLAMA_COMPLETION_TIMEOUT_SECONDS", completion_timeout)?;

        Ok(Self {
            base_url: parsed.to_string().trim_end_matches('/').to_string(),
            model: model.into(),
            startup_timeout,
            probe_timeout,
            completion_timeout,
            poll_interval: Duration::from_millis(500),
        })
    }
}

#[derive(Clone, Debug)]
pub struct LlamaBackend {
    base_url: String,
    model: String,
    probe_timeout: Duration,
    poll_interval: Duration,
    completion_timeout: Duration,
    shutdown: CancellationToken,
    http: reqwest::Client,
}

impl LlamaBackend {
    pub async fn connect(shutdown: CancellationToken) -> Result<Self> {
        Self::connect_with_config(LlamaConfig::from_env()?, shutdown).await
    }

    async fn connect_with_config(config: LlamaConfig, shutdown: CancellationToken) -> Result<Self> {
        let backend = Self {
            base_url: config.base_url,
            model: config.model,
            probe_timeout: config.probe_timeout,
            poll_interval: config.poll_interval,
            completion_timeout: config.completion_timeout,
            shutdown,
            http: reqwest::Client::builder()
                .build()
                .context("build llama HTTP client")?,
        };
        backend.wait_ready(config.startup_timeout).await?;
        Ok(backend)
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub async fn check_ready(&self) -> Result<()> {
        match tokio::time::timeout(self.probe_timeout, self.probe()).await {
            Ok(result) => result,
            Err(_) => bail!(
                "llama-server readiness probe timed out after {} seconds",
                self.probe_timeout.as_secs_f64()
            ),
        }
    }

    async fn wait_ready(&self, startup_timeout: Duration) -> Result<()> {
        let started = Instant::now();
        loop {
            let remaining = startup_timeout
                .checked_sub(started.elapsed())
                .ok_or_else(|| {
                    anyhow::anyhow!(
                        "llama-server at {} not ready within {} seconds",
                        self.base_url,
                        startup_timeout.as_secs_f64()
                    )
                })?;
            let probe_timeout = self.probe_timeout.min(remaining);
            match tokio::time::timeout(probe_timeout, self.probe()).await {
                Ok(Ok(())) => return Ok(()),
                Ok(Err(error)) => {
                    if started.elapsed() >= startup_timeout {
                        return Err(error).with_context(|| {
                            format!(
                                "llama-server at {} not ready within {} seconds",
                                self.base_url,
                                startup_timeout.as_secs_f64()
                            )
                        });
                    }
                    tracing::warn!("llama-server readiness probe failed: {error:#}");
                }
                Err(_) => {
                    tracing::warn!(
                        "llama-server readiness probe timed out after {} seconds",
                        probe_timeout.as_secs_f64()
                    );
                }
            }
            let remaining = startup_timeout.saturating_sub(started.elapsed());
            tokio::time::sleep(self.poll_interval.min(remaining)).await;
        }
    }

    async fn probe(&self) -> Result<()> {
        let response = self
            .http
            .get(format!("{}/health", self.base_url))
            .send()
            .await
            .with_context(|| format!("llama-server at {} is unreachable", self.base_url))?;
        if response.status().is_success() {
            return Ok(());
        }
        let status = response.status();
        let body = response
            .text()
            .await
            .with_context(|| format!("read llama-server readiness error body for HTTP {status}"))?;
        bail!("llama-server readiness returned HTTP {status}: {body}")
    }

    async fn complete(&self, req: TextReq) -> Result<TextResp> {
        let operation = async {
            let mut body = serde_json::json!({
                "model": self.model,
                "messages": [{"role": "user", "content": req.prompt}],
                "max_tokens": req.max_tokens,
                "stream": false,
            });
            if let Some(format) = req.response_format {
                body["response_format"] = format;
            }

            let url = format!("{}/v1/chat/completions", self.base_url);
            let response = self
                .http
                .post(&url)
                .json(&body)
                .send()
                .await
                .with_context(|| format!("llama-server at {} is unreachable", self.base_url))?;
            let status = response.status();
            if !status.is_success() {
                let body = response
                    .text()
                    .await
                    .with_context(|| format!("read llama-server {status} completion error body"))?;
                bail!("llama-server {status}: {body}");
            }
            let bytes = response
                .bytes()
                .await
                .context("read llama-server completion body")?;
            let data = serde_json::from_slice(&bytes).context("decode llama-server JSON body")?;
            parse_completion(data).context("validate llama-server completion")
        };

        tokio::select! {
            () = self.shutdown.cancelled() => {
                bail!("gateway shutdown cancelled llama-server completion")
            }
            result = tokio::time::timeout(self.completion_timeout, operation) => match result {
                Ok(result) => result,
                Err(_) => bail!(
                    "llama-server completion timed out after {} seconds",
                    self.completion_timeout.as_secs_f64()
                ),
            }
        }
    }

    #[cfg(test)]
    pub fn from_parts_for_test(base_url: String) -> Self {
        Self::from_parts_for_test_with_runtime(
            base_url,
            Duration::from_millis(500),
            CancellationToken::new(),
        )
    }

    #[cfg(test)]
    fn from_parts_for_test_with_runtime(
        base_url: String,
        completion_timeout: Duration,
        shutdown: CancellationToken,
    ) -> Self {
        Self {
            base_url,
            model: "test-model".into(),
            probe_timeout: Duration::from_millis(500),
            poll_interval: Duration::from_millis(10),
            completion_timeout,
            shutdown,
            http: reqwest::Client::new(),
        }
    }
}

fn parse_timeout(key: &str, value: Option<&str>) -> Result<Duration> {
    let value = value.ok_or_else(|| anyhow::anyhow!("{key} is required"))?;
    let seconds: f64 = value
        .parse()
        .with_context(|| format!("{key} must be a positive number"))?;
    if !seconds.is_finite() || seconds <= 0.0 {
        bail!("{key} must be finite and greater than zero");
    }
    Duration::try_from_secs_f64(seconds)
        .with_context(|| format!("{key} is outside the supported duration range"))
}

fn required_env(key: &str) -> Result<String> {
    match std::env::var(key) {
        Ok(value) if value.is_empty() => bail!("{key} is required and must not be empty"),
        Ok(value) => Ok(value),
        Err(std::env::VarError::NotPresent) => bail!("{key} is required"),
        Err(std::env::VarError::NotUnicode(value)) => bail!("{key} is not valid UTF-8: {value:?}"),
    }
}

#[derive(Deserialize)]
pub struct TextReq {
    prompt: String,
    #[serde(default = "default_max")]
    max_tokens: usize,
    #[serde(default)]
    response_format: Option<serde_json::Value>,
}
fn default_max() -> usize {
    256
}

#[derive(Debug, Serialize)]
pub struct TextResp {
    text: String,
    model: String,
}

/// 代理到 llama-server 的 OpenAI 兼容 /v1/chat/completions。
pub async fn gen_text(
    State(state): State<GatewayState>,
    Json(req): Json<TextReq>,
) -> Result<Json<TextResp>, (StatusCode, String)> {
    state.llama.complete(req).await.map(Json).map_err(|error| {
        (
            StatusCode::BAD_GATEWAY,
            format!("llama-server completion failed: {error:#}"),
        )
    })
}

fn parse_completion(data: serde_json::Value) -> Result<TextResp> {
    #[derive(Deserialize)]
    struct Completion {
        model: String,
        choices: Vec<Choice>,
    }
    #[derive(Deserialize)]
    struct Choice {
        message: CompletionMessage,
    }
    #[derive(Deserialize)]
    struct CompletionMessage {
        content: String,
    }

    let completion: Completion =
        serde_json::from_value(data).context("decode completion fields")?;
    if completion.model.is_empty() {
        bail!("completion model must not be empty");
    }
    let choice = completion
        .choices
        .into_iter()
        .next()
        .ok_or_else(|| anyhow::anyhow!("completion choices must not be empty"))?;
    Ok(TextResp {
        text: choice.message.content,
        model: completion.model,
    })
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;
    use std::time::{Duration, Instant};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio_util::sync::CancellationToken;

    use super::{LlamaBackend, LlamaConfig, TextReq};

    async fn nonresponding_server() -> (String, Arc<AtomicUsize>) {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let accepted = Arc::new(AtomicUsize::new(0));
        let accepted_by_server = accepted.clone();
        tokio::spawn(async move {
            loop {
                let (stream, _) = listener.accept().await.unwrap();
                accepted_by_server.fetch_add(1, Ordering::SeqCst);
                tokio::spawn(async move {
                    let _stream = stream;
                    tokio::time::sleep(Duration::from_secs(5)).await;
                });
            }
        });
        (format!("http://{addr}"), accepted)
    }

    async fn body_stalling_server(status: &str) -> String {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let status = status.to_owned();
        tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut request = [0_u8; 4096];
            let _ = stream.read(&mut request).await.unwrap();
            stream
                .write_all(
                    format!(
                        "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: 4096\r\nConnection: close\r\n\r\n{{"
                    )
                    .as_bytes(),
                )
                .await
                .unwrap();
            tokio::time::sleep(Duration::from_secs(5)).await;
        });
        format!("http://{addr}")
    }

    fn text_request() -> TextReq {
        TextReq {
            prompt: "hello".into(),
            max_tokens: 8,
            response_format: None,
        }
    }

    #[tokio::test]
    async fn completion_timeout_covers_response_headers() {
        let (base_url, _) = nonresponding_server().await;
        let backend = LlamaBackend::from_parts_for_test_with_runtime(
            base_url,
            Duration::from_millis(60),
            CancellationToken::new(),
        );
        let started = Instant::now();

        let error = backend.complete(text_request()).await.unwrap_err();

        assert!(started.elapsed() < Duration::from_millis(300));
        assert!(error.to_string().contains("timed out"), "{error:#}");
    }

    #[tokio::test]
    async fn completion_timeout_covers_success_and_error_bodies() {
        for status in ["200 OK", "503 Service Unavailable"] {
            let base_url = body_stalling_server(status).await;
            let backend = LlamaBackend::from_parts_for_test_with_runtime(
                base_url,
                Duration::from_millis(60),
                CancellationToken::new(),
            );

            let error = backend.complete(text_request()).await.unwrap_err();

            assert!(
                error.to_string().contains("timed out"),
                "{status}: {error:#}"
            );
        }
    }

    #[tokio::test]
    async fn gateway_shutdown_cancels_inflight_completion() {
        let (base_url, accepted) = nonresponding_server().await;
        let shutdown = CancellationToken::new();
        let backend = LlamaBackend::from_parts_for_test_with_runtime(
            base_url,
            Duration::from_secs(5),
            shutdown.clone(),
        );
        let completion = tokio::spawn(async move { backend.complete(text_request()).await });
        tokio::time::timeout(Duration::from_secs(1), async {
            while accepted.load(Ordering::SeqCst) == 0 {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();

        shutdown.cancel();
        let error = tokio::time::timeout(Duration::from_millis(300), completion)
            .await
            .unwrap()
            .unwrap()
            .unwrap_err();

        assert!(error.to_string().contains("shutdown"), "{error:#}");
    }

    #[tokio::test]
    async fn connect_retries_with_probe_timeout_until_startup_timeout() {
        let (base_url, accepted) = nonresponding_server().await;
        let started = Instant::now();
        let config = LlamaConfig {
            base_url,
            model: "test-model".into(),
            startup_timeout: Duration::from_millis(240),
            probe_timeout: Duration::from_millis(50),
            completion_timeout: Duration::from_secs(1),
            poll_interval: Duration::from_millis(10),
        };

        let error = LlamaBackend::connect_with_config(config, CancellationToken::new())
            .await
            .unwrap_err();

        assert!(started.elapsed() >= Duration::from_millis(180));
        assert!(started.elapsed() < Duration::from_secs(1));
        assert!(error.to_string().contains("not ready"), "{error:#}");
        assert!(accepted.load(Ordering::SeqCst) >= 2);
    }

    #[tokio::test]
    async fn runtime_readiness_is_bounded_by_probe_timeout() {
        let (base_url, _) = nonresponding_server().await;
        let backend = LlamaBackend {
            base_url,
            model: "test-model".into(),
            probe_timeout: Duration::from_millis(60),
            poll_interval: Duration::from_millis(10),
            completion_timeout: Duration::from_secs(1),
            shutdown: CancellationToken::new(),
            http: reqwest::Client::new(),
        };
        let started = Instant::now();

        let error = backend.check_ready().await.unwrap_err();

        assert!(started.elapsed() < Duration::from_millis(300));
        assert!(error.to_string().contains("timed out"), "{error:#}");
    }

    #[test]
    fn explicit_base_url_and_both_timeouts_are_required() {
        assert!(LlamaConfig::parse(None, Some("1"), Some("1"), Some("1")).is_err());
        assert!(LlamaConfig::parse(Some(""), Some("1"), Some("1"), Some("1")).is_err());
        assert!(
            LlamaConfig::parse(Some("http://127.0.0.1:8080"), None, Some("1"), Some("1")).is_err()
        );
        assert!(
            LlamaConfig::parse(Some("http://127.0.0.1:8080"), Some("1"), None, Some("1")).is_err()
        );
        assert!(
            LlamaConfig::parse(Some("http://127.0.0.1:8080"), Some("1"), Some("1"), None).is_err()
        );
    }

    #[test]
    fn missing_completion_fields_are_errors() {
        for value in [
            serde_json::json!({"model":"m"}),
            serde_json::json!({"model":"m","choices":[]}),
            serde_json::json!({"model":"m","choices":[{"message":{}}]}),
            serde_json::json!({"choices":[{"message":{"content":"ok"}}]}),
        ] {
            assert!(super::parse_completion(value).is_err());
        }
    }
}
