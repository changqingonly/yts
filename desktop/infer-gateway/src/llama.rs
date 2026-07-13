//! 文本后端:代理外部常驻 `llama-server` 的 OpenAI 兼容接口。

use std::time::{Duration, Instant};

use axum::extract::State;
use axum::http::StatusCode;
use axum::Json;
use serde::{Deserialize, Serialize};

use anyhow::{bail, Context, Result};

use crate::GatewayState;

#[derive(Debug)]
pub struct LlamaConfig {
    pub base_url: String,
    pub model: String,
    pub readiness_timeout: Duration,
    pub poll_interval: Duration,
}

impl LlamaConfig {
    pub fn from_env() -> Result<Self> {
        let base_url = required_env("YTS_LLAMA_BASE_URL")?;
        let model = required_env("YTS_LLAMA_MODEL")?;
        let timeout = required_env("YTS_LLAMA_READY_TIMEOUT_SECONDS")?;
        Self::parse_with_model(Some(&base_url), Some(&model), Some(&timeout))
    }

    #[cfg(test)]
    fn parse(base_url: Option<&str>, timeout: Option<&str>) -> Result<Self> {
        Self::parse_with_model(base_url, Some("test-model"), timeout)
    }

    fn parse_with_model(
        base_url: Option<&str>,
        model: Option<&str>,
        timeout: Option<&str>,
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
        let timeout = timeout
            .ok_or_else(|| anyhow::anyhow!("YTS_LLAMA_READY_TIMEOUT_SECONDS is required"))?;
        let seconds: f64 = timeout
            .parse()
            .context("YTS_LLAMA_READY_TIMEOUT_SECONDS must be a positive number")?;
        if !seconds.is_finite() || seconds <= 0.0 {
            bail!("YTS_LLAMA_READY_TIMEOUT_SECONDS must be finite and greater than zero");
        }
        let readiness_timeout = Duration::try_from_secs_f64(seconds)
            .context("YTS_LLAMA_READY_TIMEOUT_SECONDS is outside the supported duration range")?;

        Ok(Self {
            base_url: parsed.to_string().trim_end_matches('/').to_string(),
            model: model.into(),
            readiness_timeout,
            poll_interval: Duration::from_millis(500),
        })
    }
}

#[derive(Clone, Debug)]
pub struct LlamaBackend {
    base_url: String,
    model: String,
    readiness_timeout: Duration,
    poll_interval: Duration,
    http: reqwest::Client,
}

impl LlamaBackend {
    pub async fn connect() -> Result<Self> {
        Self::connect_with_config(LlamaConfig::from_env()?).await
    }

    async fn connect_with_config(config: LlamaConfig) -> Result<Self> {
        let backend = Self {
            base_url: config.base_url,
            model: config.model,
            readiness_timeout: config.readiness_timeout,
            poll_interval: config.poll_interval,
            http: reqwest::Client::builder()
                .build()
                .context("build llama HTTP client")?,
        };
        backend.wait_ready().await?;
        Ok(backend)
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub async fn check_ready(&self) -> Result<()> {
        match tokio::time::timeout(self.readiness_timeout, self.probe()).await {
            Ok(result) => result,
            Err(_) => bail!(
                "llama-server readiness probe timed out after {} seconds",
                self.readiness_timeout.as_secs_f64()
            ),
        }
    }

    async fn wait_ready(&self) -> Result<()> {
        let started = Instant::now();
        loop {
            let remaining = self
                .readiness_timeout
                .checked_sub(started.elapsed())
                .ok_or_else(|| {
                    anyhow::anyhow!(
                        "llama-server at {} not ready within {} seconds",
                        self.base_url,
                        self.readiness_timeout.as_secs_f64()
                    )
                })?;
            match tokio::time::timeout(remaining, self.probe()).await {
                Ok(Ok(())) => return Ok(()),
                Ok(Err(error)) => {
                    if started.elapsed() >= self.readiness_timeout {
                        return Err(error).with_context(|| {
                            format!(
                                "llama-server at {} not ready within {} seconds",
                                self.base_url,
                                self.readiness_timeout.as_secs_f64()
                            )
                        });
                    }
                    tracing::warn!("llama-server readiness probe failed: {error:#}");
                }
                Err(_) => {
                    bail!(
                        "llama-server at {} not ready within {} seconds",
                        self.base_url,
                        self.readiness_timeout.as_secs_f64()
                    );
                }
            }
            let remaining = self.readiness_timeout.saturating_sub(started.elapsed());
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

    #[cfg(test)]
    pub fn from_parts_for_test(base_url: String) -> Self {
        Self {
            base_url,
            model: "test-model".into(),
            readiness_timeout: Duration::from_millis(500),
            poll_interval: Duration::from_millis(10),
            http: reqwest::Client::new(),
        }
    }
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

#[derive(Serialize)]
pub struct TextResp {
    text: String,
    model: String,
}

/// 代理到 llama-server 的 OpenAI 兼容 /v1/chat/completions。
pub async fn gen_text(
    State(state): State<GatewayState>,
    Json(req): Json<TextReq>,
) -> Result<Json<TextResp>, (StatusCode, String)> {
    let llama = &state.llama;
    let mut body = serde_json::json!({
        "model": llama.model,
        "messages": [{"role": "user", "content": req.prompt}],
        "max_tokens": req.max_tokens,
        "stream": false,
    });
    if let Some(fmt) = req.response_format {
        body["response_format"] = fmt; // 透传结构化输出约束(llama.cpp 支持 json_schema/GBNF)
    }

    let url = format!("{}/v1/chat/completions", llama.base_url);
    let resp = llama
        .http
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| {
            (
                StatusCode::BAD_GATEWAY,
                format!("llama-server unreachable: {e}"),
            )
        })?;
    if !resp.status().is_success() {
        let code = resp.status();
        let txt = resp.text().await.map_err(|error| {
            (
                StatusCode::BAD_GATEWAY,
                format!("failed to read llama-server {code} error body: {error}"),
            )
        })?;
        return Err((
            StatusCode::BAD_GATEWAY,
            format!("llama-server {code}: {txt}"),
        ));
    }
    let data: serde_json::Value = resp.json().await.map_err(|e| {
        (
            StatusCode::BAD_GATEWAY,
            format!("bad llama-server json: {e}"),
        )
    })?;
    parse_completion(data).map(Json).map_err(|error| {
        (
            StatusCode::BAD_GATEWAY,
            format!("invalid llama-server completion: {error:#}"),
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
    use std::time::{Duration, Instant};

    use super::{LlamaBackend, LlamaConfig};

    #[tokio::test]
    async fn readiness_timeout_is_an_error() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let _server = tokio::spawn(async move {
            let (_stream, _) = listener.accept().await.unwrap();
            tokio::time::sleep(Duration::from_secs(5)).await;
        });
        let started = Instant::now();
        let config = LlamaConfig {
            base_url: format!("http://{addr}"),
            model: "test-model".into(),
            readiness_timeout: Duration::from_millis(100),
            poll_interval: Duration::from_millis(10),
        };

        let error = LlamaBackend::connect_with_config(config).await.unwrap_err();

        assert!(started.elapsed() < Duration::from_secs(1));
        assert!(error.to_string().contains("not ready"), "{error:#}");
    }

    #[test]
    fn explicit_base_url_and_timeout_are_required() {
        assert!(LlamaConfig::parse(None, Some("1")).is_err());
        assert!(LlamaConfig::parse(Some(""), Some("1")).is_err());
        assert!(LlamaConfig::parse(Some("http://127.0.0.1:8080"), None).is_err());
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
