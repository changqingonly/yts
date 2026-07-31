//! yts 本地推理网关(GGML 家族)。文本/图片/音乐统一由本网关对接 GGML 原生二进制:
//!   - 文本:代理常驻 `llama-server`(llama.cpp,OpenAI 兼容)——网关按 YTS_LLAMA_CMD spawn 并托管其生命周期。
//!   - 图片:spawn `stable-diffusion.cpp`(见 image.rs,YTS_IMAGEGEN_CMD)。
//!   - 音乐:spawn `acestep.cpp` / 内置合成器(见 stream.rs,YTS_AUDIOGEN_CMD)。
//!
//! (历史:文本曾用 Candle 内嵌 quantized_llama;现移除 Candle,四模态统一到 GGML 二进制。
//!  crate 名 infer-gateway 保留以兼容现有脚本/配置,实为「GGML 推理网关」。)
//!
//! Python 编排经 gateway_adapter.py → POST /text(本网关代理 llama-server)。

mod image;
mod llama;
mod stream;

use axum::{routing::get, routing::post, Json, Router};

pub fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

fn image_available() -> bool {
    std::env::var("YTS_IMAGEGEN_CMD")
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false)
}

async fn health() -> Json<serde_json::Value> {
    let available = image_available();
    Json(serde_json::json!({
        "status": "ok",
        "backend": "ggml-gateway",
        "image": {
            "available": available,
            "error_code": if available { serde_json::Value::Null } else { serde_json::Value::String("local_image_model_unavailable".into()) }
        }
    }))
}

#[cfg(test)]
mod tests {
    #[test]
    fn image_capability_is_unavailable_without_producer_command() {
        std::env::remove_var("YTS_IMAGEGEN_CMD");
        assert!(!super::image_available());
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let addr = env_or("YTS_GATEWAY_ADDR", "127.0.0.1:8799");

    // 文本:按 YTS_LLAMA_CMD spawn 常驻 llama-server 并托管(未配置则期望外部已在 YTS_LLAMA_BASE_URL)。
    let llama = llama::LlamaBackend::start().await;
    tracing::info!(
        "ggml-gateway up on {addr} (text→llama-server {})",
        llama.base_url()
    );

    let app = Router::new()
        .route("/health", get(health))
        .route("/text", post(llama::gen_text))
        .route("/image", post(image::gen_image))
        .route("/music/stream", get(stream::music_stream_handler))
        .with_state(llama.clone());

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}
