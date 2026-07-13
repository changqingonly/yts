//! yts 本地推理网关。文本代理外部 llama-server，图片和音频执行显式启用的结构化 producer。

mod image;
mod llama;
mod producer;
mod stream;

use anyhow::Context;
use axum::extract::State;
use axum::http::StatusCode;
use axum::{routing::get, routing::post, Json, Router};

use producer::{ProducerConfig, ProducerKind};

#[derive(Clone)]
pub struct GatewayState {
    pub(crate) llama: llama::LlamaBackend,
    pub(crate) image: ProducerConfig,
    pub(crate) audio: ProducerConfig,
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({"status": "ok", "backend": "ggml-gateway"}))
}

async fn ready(State(state): State<GatewayState>) -> (StatusCode, Json<serde_json::Value>) {
    let text_error = state
        .llama
        .check_ready()
        .await
        .err()
        .map(|error| format!("{error:#}"));
    let text_ready = text_error.is_none();
    let image_ready = !state.image.enabled() || state.image.configured();
    let audio_ready = !state.audio.enabled() || state.audio.configured();
    let aggregate_ready = text_ready && image_ready && audio_ready;
    let status = if aggregate_ready {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };
    (
        status,
        Json(serde_json::json!({
            "status": if aggregate_ready { "ready" } else { "unavailable" },
            "text": {
                "required": true,
                "ready": text_ready,
                "error": text_error,
            },
            "image": {
                "required": state.image.enabled(),
                "enabled": state.image.enabled(),
                "configured": state.image.configured(),
                "ready": image_ready,
            },
            "audio": {
                "required": state.audio.enabled(),
                "enabled": state.audio.enabled(),
                "configured": state.audio.configured(),
                "ready": audio_ready,
            },
        })),
    )
}

pub fn build_router(state: GatewayState) -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route("/text", post(llama::gen_text))
        .route("/image", post(image::gen_image))
        .route("/music/stream", get(stream::music_stream_handler))
        .with_state(state)
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let addr = std::env::var("YTS_GATEWAY_ADDR").unwrap_or_else(|_| "127.0.0.1:8799".into());
    let image = ProducerConfig::from_env(ProducerKind::Image)?;
    let audio = ProducerConfig::from_env(ProducerKind::Audio)?;
    let llama = llama::LlamaBackend::connect().await?;
    tracing::info!(
        "ggml-gateway up on {addr} (text→llama-server {})",
        llama.base_url()
    );
    let state = GatewayState {
        llama,
        image,
        audio,
    };
    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .with_context(|| format!("bind gateway listener at {addr}"))?;
    let app = build_router(state);
    axum::serve(listener, app).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tower::ServiceExt;

    use super::{build_router, GatewayState};
    use crate::llama::LlamaBackend;
    use crate::producer::{ProducerConfig, ProducerKind};

    fn state(base_url: String) -> GatewayState {
        GatewayState {
            llama: LlamaBackend::from_parts_for_test(base_url),
            image: ProducerConfig::parse(ProducerKind::Image, Some("false"), None, None).unwrap(),
            audio: ProducerConfig::parse(ProducerKind::Audio, Some("false"), None, None).unwrap(),
        }
    }

    #[tokio::test]
    async fn disabled_image_returns_service_unavailable() {
        let response = build_router(state("http://127.0.0.1:1".into()))
            .oneshot(
                Request::post("/image")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        r#"{"prompt":"test","width":64,"height":64,"steps":1}"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn disabled_audio_returns_service_unavailable_before_websocket_upgrade() {
        let response = build_router(state("http://127.0.0.1:1".into()))
            .oneshot(
                Request::get("/music/stream")
                    .header("connection", "upgrade")
                    .header("upgrade", "websocket")
                    .header("sec-websocket-version", "13")
                    .header("sec-websocket-key", "dGhlIHNhbXBsZSBub25jZQ==")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn readiness_is_non_success_when_text_backend_is_unavailable() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut request = [0_u8; 1024];
            let _ = stream.read(&mut request).await.unwrap();
            stream
                .write_all(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                .await
                .unwrap();
        });

        let response = tokio::time::timeout(
            Duration::from_secs(1),
            build_router(state(format!("http://{addr}")))
                .oneshot(Request::get("/ready").body(Body::empty()).unwrap()),
        )
        .await
        .unwrap()
        .unwrap();

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }
}
