//! 文本后端:代理常驻 `llama-server`(llama.cpp,OpenAI 兼容 /v1/chat/completions)。
//!
//! 网关按 `YTS_LLAMA_CMD` spawn 并托管 llama-server 生命周期(子进程随网关退出被回收);
//! 未配置时假定外部已在 `YTS_LLAMA_BASE_URL`(默认 http://127.0.0.1:8080)运行。
//! `/candle/text` 接口对上层不变(candle_adapter.py 无需改动),底层已换成 llama.cpp。

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
    _child: Arc<Mutex<Option<Child>>>, // 持有子进程,Drop 时回收
    http: reqwest::Client,
}

impl LlamaBackend {
    pub async fn start() -> Self {
        let base_url = env_or("YTS_LLAMA_BASE_URL", "http://127.0.0.1:8080");
        let child = match std::env::var("YTS_LLAMA_CMD") {
            Ok(cmd) if !cmd.trim().is_empty() => {
                tracing::info!("spawning llama-server: {cmd}");
                match tokio::process::Command::new("sh").arg("-c").arg(&cmd).spawn() {
                    Ok(c) => Some(c),
                    Err(e) => {
                        tracing::error!("spawn llama-server failed: {e}");
                        None
                    }
                }
            }
            _ => {
                tracing::info!("YTS_LLAMA_CMD unset — expecting external llama-server at {base_url}");
                None
            }
        };
        let me = Self {
            base_url,
            _child: Arc::new(Mutex::new(child)),
            http: reqwest::Client::new(),
        };
        if me._child.lock().await.is_some() {
            me.wait_ready().await;
        }
        me
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// 轮询 llama-server /health 直到就绪(最多 ~60s)。
    async fn wait_ready(&self) {
        for _ in 0..120 {
            if let Ok(r) = self.http.get(format!("{}/health", self.base_url)).send().await {
                if r.status().is_success() {
                    tracing::info!("llama-server ready at {}", self.base_url);
                    return;
                }
            }
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        }
        tracing::warn!("llama-server not ready after wait; proceeding anyway");
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
        .map_err(|e| (StatusCode::BAD_GATEWAY, format!("llama-server unreachable: {e}")))?;
    if !resp.status().is_success() {
        let code = resp.status();
        let txt = resp.text().await.unwrap_or_default();
        return Err((StatusCode::BAD_GATEWAY, format!("llama-server {code}: {txt}")));
    }
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| (StatusCode::BAD_GATEWAY, format!("bad llama-server json: {e}")))?;
    let text = data["choices"][0]["message"]["content"].as_str().unwrap_or("").to_string();
    let model = data["model"].as_str().unwrap_or("local").to_string();
    Ok(Json(TextResp { text, model }))
}
