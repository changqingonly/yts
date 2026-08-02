//! 文本后端:代理常驻 `llama-server`(llama.cpp,OpenAI 兼容 /v1/chat/completions)。
//!
//! 网关在首个文本请求到达时按 `YTS_LLAMA_CMD` spawn，并在 gateway 退出时回收子进程;
//! 未配置时假定外部已在 `YTS_LLAMA_BASE_URL`(默认 http://127.0.0.1:8080)运行。
//! `/text` 接口对上层不变(gateway_adapter.py 无需改动),底层已换成 llama.cpp。

use std::sync::Arc;

use axum::extract::State;
use axum::http::StatusCode;
use axum::Json;
use serde::{Deserialize, Serialize};
use tokio::process::Child;
use tokio::sync::Mutex;

use crate::env_or;

#[derive(Clone)]
pub struct LlamaBackend {
    base_url: String,
    command: Option<String>,
    child: Arc<Mutex<Option<Child>>>,
    http: reqwest::Client,
}

impl LlamaBackend {
    pub async fn start() -> Self {
        let base_url = env_or("YTS_LLAMA_BASE_URL", "http://127.0.0.1:8080");
        let command = match std::env::var("YTS_LLAMA_CMD") {
            Ok(cmd) if !cmd.trim().is_empty() => {
                tracing::info!("llama-server configured for lazy startup");
                Some(cmd)
            }
            _ => {
                tracing::info!(
                    "YTS_LLAMA_CMD unset — expecting external llama-server at {base_url}"
                );
                None
            }
        };
        Self {
            base_url,
            command,
            child: Arc::new(Mutex::new(None)),
            http: reqwest::Client::new(),
        }
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    async fn ensure_started(&self) -> Result<(), String> {
        let Some(command) = self.command.as_deref() else {
            return Ok(());
        };
        let mut child = self.child.lock().await;
        if child.is_some() {
            return Ok(());
        }
        tracing::info!("spawning llama-server: {command}");
        let mut process = tokio::process::Command::new("sh");
        process.arg("-c").arg(command).kill_on_drop(true);
        *child = Some(
            process
                .spawn()
                .map_err(|error| format!("spawn llama-server failed: {error}"))?,
        );
        Ok(())
    }

    /// 文本请求到达时才启动并等待 llama-server；音乐/图片端点不加载文本模型。
    async fn wait_ready(&self) -> Result<(), String> {
        self.ensure_started().await?;
        for _ in 0..120 {
            if let Ok(r) = self
                .http
                .get(format!("{}/health", self.base_url))
                .timeout(std::time::Duration::from_millis(500))
                .send()
                .await
            {
                if r.status().is_success() {
                    tracing::info!("llama-server ready at {}", self.base_url);
                    return Ok(());
                }
            }
            let mut child = self.child.lock().await;
            if let Some(process) = child.as_mut() {
                if let Some(status) = process.try_wait().map_err(|error| error.to_string())? {
                    child.take();
                    return Err(format!("llama-server exited before readiness: {status}"));
                }
            }
            drop(child);
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        }
        Err(format!(
            "llama-server not ready after 60s at {}",
            self.base_url
        ))
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
    State(llama): State<LlamaBackend>,
    Json(req): Json<TextReq>,
) -> Result<Json<TextResp>, (StatusCode, String)> {
    llama
        .wait_ready()
        .await
        .map_err(|error| (StatusCode::SERVICE_UNAVAILABLE, error))?;
    let mut body = serde_json::json!({
        "model": env_or("YTS_LLAMA_MODEL", "local"),
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
        let txt = resp.text().await.unwrap_or_default();
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
    let text = data["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("")
        .to_string();
    let model = data["model"].as_str().unwrap_or("local").to_string();
    Ok(Json(TextResp { text, model }))
}
