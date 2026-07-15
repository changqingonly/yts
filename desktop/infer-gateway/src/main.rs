//! yts 本地推理网关。文本代理外部 llama-server，图片和音频执行显式启用的结构化 producer。

mod image;
mod llama;
mod producer;
mod stream;

use anyhow::Context;
use axum::extract::State;
use axum::http::StatusCode;
use axum::{routing::get, routing::post, Json, Router};

use producer::{ProducerConfig, ProducerKind, ProducerSupervisor};
use tokio_util::sync::CancellationToken;

#[cfg(test)]
static PROCESS_TEST_LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());

#[derive(Debug)]
struct GatewayConfig {
    addr: String,
    shutdown_timeout: std::time::Duration,
}

impl GatewayConfig {
    fn from_env() -> anyhow::Result<Self> {
        let addr = required_env("YTS_GATEWAY_ADDR")?;
        let shutdown_timeout = required_env("YTS_GATEWAY_SHUTDOWN_TIMEOUT_SECONDS")?;
        Self::parse(Some(&addr), Some(&shutdown_timeout))
    }

    fn parse(addr: Option<&str>, shutdown_timeout: Option<&str>) -> anyhow::Result<Self> {
        let addr = addr
            .filter(|value| !value.is_empty())
            .ok_or_else(|| anyhow::anyhow!("YTS_GATEWAY_ADDR is required and must not be empty"))?;
        let addr = parse_gateway_address(addr)?;
        let shutdown_timeout =
            parse_positive_duration("YTS_GATEWAY_SHUTDOWN_TIMEOUT_SECONDS", shutdown_timeout)?;
        Ok(Self {
            addr,
            shutdown_timeout,
        })
    }
}

fn parse_gateway_address(value: &str) -> anyhow::Result<String> {
    if let Ok(addr) = value.parse::<std::net::SocketAddr>() {
        if addr.port() == 0 {
            anyhow::bail!("YTS_GATEWAY_ADDR port must be greater than zero");
        }
        return Ok(value.to_owned());
    }

    let (host, port) = value.rsplit_once(':').ok_or_else(|| {
        anyhow::anyhow!(
            "YTS_GATEWAY_ADDR must be an IPv4, bracketed IPv6, or ASCII DNS address with port"
        )
    })?;
    if !is_ascii_dns_host(host) {
        anyhow::bail!("YTS_GATEWAY_ADDR host must be a valid ASCII DNS hostname");
    }
    if port.is_empty() || !port.bytes().all(|byte| byte.is_ascii_digit()) {
        anyhow::bail!("YTS_GATEWAY_ADDR port must be an integer from 1 to 65535");
    }
    let port: u16 = port
        .parse()
        .context("YTS_GATEWAY_ADDR port must be an integer from 1 to 65535")?;
    if port == 0 {
        anyhow::bail!("YTS_GATEWAY_ADDR port must be greater than zero");
    }
    Ok(value.to_owned())
}

fn is_ascii_dns_host(value: &str) -> bool {
    if !value.is_ascii() {
        return false;
    }
    let hostname = value.strip_suffix('.').unwrap_or(value);
    if hostname.is_empty()
        || hostname.len() > 253
        || (hostname.contains('.')
            && hostname
                .bytes()
                .all(|byte| byte.is_ascii_digit() || byte == b'.'))
    {
        return false;
    }
    hostname.split('.').all(|label| {
        let bytes = label.as_bytes();
        !bytes.is_empty()
            && bytes.len() <= 63
            && bytes[0].is_ascii_alphanumeric()
            && bytes[bytes.len() - 1].is_ascii_alphanumeric()
            && bytes
                .iter()
                .all(|byte| byte.is_ascii_alphanumeric() || *byte == b'-')
    })
}

fn required_env(key: &str) -> anyhow::Result<String> {
    match std::env::var(key) {
        Ok(value) if value.is_empty() => anyhow::bail!("{key} is required and must not be empty"),
        Ok(value) => Ok(value),
        Err(std::env::VarError::NotPresent) => anyhow::bail!("{key} is required"),
        Err(std::env::VarError::NotUnicode(value)) => {
            anyhow::bail!("{key} is not valid UTF-8: {value:?}")
        }
    }
}

fn parse_positive_duration(key: &str, value: Option<&str>) -> anyhow::Result<std::time::Duration> {
    let value = value.ok_or_else(|| anyhow::anyhow!("{key} is required"))?;
    let seconds: f64 = value
        .parse()
        .with_context(|| format!("{key} must be a positive number"))?;
    if !seconds.is_finite() || seconds <= 0.0 {
        anyhow::bail!("{key} must be finite and greater than zero");
    }
    std::time::Duration::try_from_secs_f64(seconds)
        .with_context(|| format!("{key} is outside the supported duration range"))
}

struct ShutdownSignals {
    interrupt: tokio::signal::unix::Signal,
    terminate: tokio::signal::unix::Signal,
}

impl ShutdownSignals {
    fn new() -> anyhow::Result<Self> {
        Ok(Self {
            interrupt: tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt())
                .context("register SIGINT handler")?,
            terminate: tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                .context("register SIGTERM handler")?,
        })
    }

    async fn wait(mut self) -> anyhow::Result<()> {
        let signal = tokio::select! {
            result = self.interrupt.recv() => ("SIGINT", result),
            result = self.terminate.recv() => ("SIGTERM", result),
        };
        if signal.1.is_none() {
            anyhow::bail!("{} signal stream closed unexpectedly", signal.0);
        }
        tracing::info!("received {}", signal.0);
        Ok(())
    }
}

async fn supervise_gateway<Serve, Signal>(
    serve: Serve,
    signal: Signal,
    graceful_shutdown: CancellationToken,
    producers: ProducerSupervisor,
    runtime_cancellation: CancellationToken,
    shutdown_timeout: std::time::Duration,
) -> anyhow::Result<()>
where
    Serve: std::future::Future<Output = anyhow::Result<()>>,
    Signal: std::future::Future<Output = anyhow::Result<()>>,
{
    tokio::pin!(serve);
    tokio::pin!(signal);
    let (early_serve, signal_failure) = tokio::select! {
        result = &mut serve => (Some(result), None),
        result = &mut signal => match result {
            Ok(()) => (None, None),
            Err(error) => (None, Some(error)),
        },
    };

    producers.begin_shutdown().await;
    runtime_cancellation.cancel();
    graceful_shutdown.cancel();
    let deadline = tokio::time::Instant::now() + shutdown_timeout;

    let (serve_result, cleanup_result) = match early_serve {
        Some(result) => (result, producers.shutdown_until(deadline).await),
        None => {
            let (serve, cleanup) = tokio::join!(
                tokio::time::timeout_at(deadline, &mut serve),
                producers.shutdown_until(deadline),
            );
            let serve = match serve {
                Ok(result) => result,
                Err(_) => Err(anyhow::anyhow!(
                    "gateway graceful shutdown timed out before the shutdown deadline"
                )),
            };
            (serve, cleanup)
        }
    };

    let mut failures = Vec::new();
    if let Some(error) = signal_failure {
        failures.push(format!("shutdown signal failed: {error:#}"));
    }
    if let Err(error) = serve_result {
        failures.push(format!("gateway serve failed: {error:#}"));
    }
    if let Err(error) = cleanup_result {
        failures.push(format!("producer cleanup failed: {error:#}"));
    }
    if failures.is_empty() {
        Ok(())
    } else {
        anyhow::bail!(failures.join("; "))
    }
}

#[derive(Clone)]
pub struct GatewayState {
    pub(crate) llama: llama::LlamaBackend,
    pub(crate) image: ProducerConfig,
    pub(crate) audio: ProducerConfig,
    pub(crate) producers: ProducerSupervisor,
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({"status": "ok", "backend": "ggml-gateway"}))
}

async fn ready(State(state): State<GatewayState>) -> (StatusCode, Json<serde_json::Value>) {
    let closing = state.producers.is_closing();
    let text_error = state
        .llama
        .check_ready()
        .await
        .err()
        .map(|error| format!("{error:#}"));
    let text_ready = text_error.is_none();
    let image_error = state
        .image
        .enabled()
        .then(|| state.image.validate_executable().err())
        .flatten()
        .map(|error| format!("{error:#}"));
    let audio_error = state
        .audio
        .enabled()
        .then(|| state.audio.validate_executable().err())
        .flatten()
        .map(|error| format!("{error:#}"));
    let image_ready = !state.image.enabled() || image_error.is_none();
    let audio_ready = !state.audio.enabled() || audio_error.is_none();
    let aggregate_ready = !closing && text_ready && image_ready && audio_ready;
    let status = if aggregate_ready {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };
    (
        status,
        Json(serde_json::json!({
            "status": if aggregate_ready { "ready" } else { "unavailable" },
            "closing": closing,
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
                "error": image_error,
            },
            "audio": {
                "required": state.audio.enabled(),
                "enabled": state.audio.enabled(),
                "configured": state.audio.configured(),
                "ready": audio_ready,
                "error": audio_error,
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
    let config = GatewayConfig::from_env()?;
    let addr = config.addr;
    let cancellation = CancellationToken::new();
    let producers = ProducerSupervisor::new(cancellation.clone());
    let image = ProducerConfig::from_env(ProducerKind::Image)?;
    let audio = ProducerConfig::from_env(ProducerKind::Audio)?;
    image.validate_executable()?;
    audio.validate_executable()?;
    let llama = llama::LlamaBackend::connect(cancellation.clone()).await?;
    tracing::info!(
        "ggml-gateway up on {addr} (text→llama-server {})",
        llama.base_url()
    );
    let state = GatewayState {
        llama,
        image,
        audio,
        producers: producers.clone(),
    };
    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .with_context(|| format!("bind gateway listener at {addr}"))?;
    let app = build_router(state);
    let signals = ShutdownSignals::new()?;
    let graceful_shutdown = CancellationToken::new();
    let graceful_wait = graceful_shutdown.clone();
    let serve = async move {
        axum::serve(listener, app)
            .with_graceful_shutdown(graceful_wait.cancelled_owned())
            .await
            .context("serve gateway")
    };
    supervise_gateway(
        serve,
        signals.wait(),
        graceful_shutdown,
        producers,
        cancellation,
        config.shutdown_timeout,
    )
    .await
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::time::Duration;

    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tower::ServiceExt;

    use super::{build_router, supervise_gateway, GatewayConfig, GatewayState};
    use crate::llama::LlamaBackend;
    use crate::producer::{ProducerConfig, ProducerKind, ProducerSupervisor};
    use tokio_util::sync::CancellationToken;

    fn state(base_url: String) -> GatewayState {
        let producers = ProducerSupervisor::new(CancellationToken::new());
        GatewayState {
            llama: LlamaBackend::from_parts_for_test(base_url),
            image: ProducerConfig::parse(ProducerKind::Image, Some("false"), None, None).unwrap(),
            audio: ProducerConfig::parse(ProducerKind::Audio, Some("false"), None, None).unwrap(),
            producers,
        }
    }

    async fn healthy_backend() -> (String, CancellationToken, tokio::task::JoinHandle<()>) {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let cancellation = CancellationToken::new();
        let server_cancellation = cancellation.clone();
        let server = tokio::spawn(async move {
            loop {
                let accepted = tokio::select! {
                    result = listener.accept() => result,
                    () = server_cancellation.cancelled() => return,
                };
                let (mut stream, _) = accepted.unwrap();
                let mut request = [0_u8; 1024];
                let _ = stream.read(&mut request).await.unwrap();
                stream
                    .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                    .await
                    .unwrap();
            }
        });
        (format!("http://{addr}"), cancellation, server)
    }

    #[test]
    fn gateway_address_and_shutdown_timeout_are_strictly_required() {
        assert!(GatewayConfig::parse(None, Some("1")).is_err());
        assert!(GatewayConfig::parse(Some(""), Some("1")).is_err());
        assert!(GatewayConfig::parse(Some("localhost"), Some("1")).is_err());
        assert!(GatewayConfig::parse(Some("bad host:8799"), Some("1")).is_err());
        assert!(GatewayConfig::parse(Some("localhost:not-a-port"), Some("1")).is_err());
        assert!(GatewayConfig::parse(Some("localhost:0"), Some("1")).is_err());
        assert!(GatewayConfig::parse(Some("127.0.0.1:0"), Some("1")).is_err());
        assert!(GatewayConfig::parse(Some("127.0.0.1:8799"), None).is_err());
        assert!(GatewayConfig::parse(Some("127.0.0.1:8799"), Some("0")).is_err());

        let dns_config = GatewayConfig::parse(Some("localhost:8799"), Some("2")).unwrap();
        assert_eq!(dns_config.addr, "localhost:8799");
        let config = GatewayConfig::parse(Some("127.0.0.1:8799"), Some("2")).unwrap();
        assert_eq!(config.addr, "127.0.0.1:8799");
        assert_eq!(config.shutdown_timeout, Duration::from_secs(2));
    }

    #[tokio::test]
    async fn shutdown_timeout_bounds_graceful_server_and_registry_with_one_deadline() {
        let runtime_cancellation = CancellationToken::new();
        let producers = ProducerSupervisor::new(runtime_cancellation.clone());
        let graceful = CancellationToken::new();
        let serve_graceful = graceful.clone();
        let serve = async move {
            serve_graceful.cancelled().await;
            std::future::pending::<()>().await;
            Ok(())
        };
        let signal = std::future::ready(Ok(()));
        let started = std::time::Instant::now();

        let error = supervise_gateway(
            serve,
            signal,
            graceful,
            producers,
            runtime_cancellation,
            Duration::from_millis(60),
        )
        .await
        .unwrap_err();

        assert!(started.elapsed() < Duration::from_millis(300));
        assert!(error.to_string().contains("timed out"), "{error:#}");
    }

    #[tokio::test]
    async fn main_shutdown_boundary_waits_for_active_producer_process_group_and_tempdir() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let fixture = tempfile::tempdir().unwrap();
        let executable = fixture.path().join("producer");
        fs::write(
            &executable,
            "#!/bin/sh\nprintf '%s' \"$$\" > \"$2\"\nprintf '%s' \"$1\" > \"$4\"\nsleep 30 & descendant=$!\nprintf '%s' \"$descendant\" > \"$3\"\nwait\n",
        )
        .unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o755)).unwrap();
        let observation = tempfile::tempdir().unwrap();
        let parent_pid_path = observation.path().join("parent.pid");
        let descendant_pid_path = observation.path().join("descendant.pid");
        let output_path = observation.path().join("output.path");
        let argv = serde_json::to_string(&[
            executable.to_string_lossy().into_owned(),
            "{out}".into(),
            parent_pid_path.to_string_lossy().into_owned(),
            descendant_pid_path.to_string_lossy().into_owned(),
            output_path.to_string_lossy().into_owned(),
        ])
        .unwrap();
        let producer =
            ProducerConfig::parse(ProducerKind::Image, Some("true"), Some(&argv), Some("30"))
                .unwrap();
        let runtime_cancellation = CancellationToken::new();
        let producers = ProducerSupervisor::new(runtime_cancellation.clone());
        let mut execution = producers.start(&producer, "image.png", &[]).await.unwrap();
        let marker_paths = [
            parent_pid_path.as_path(),
            descendant_pid_path.as_path(),
            output_path.as_path(),
        ];
        let early = tokio::time::timeout(Duration::from_secs(5), async {
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
        .expect("producer did not write shutdown observation markers");
        assert!(early.is_none(), "producer completed before shutdown signal");
        let request_output = std::path::PathBuf::from(fs::read_to_string(&output_path).unwrap());
        let graceful = CancellationToken::new();
        let serve_graceful = graceful.clone();
        let serve = async move {
            serve_graceful.cancelled().await;
            Ok(())
        };

        supervise_gateway(
            serve,
            std::future::ready(Ok(())),
            graceful,
            producers.clone(),
            runtime_cancellation,
            Duration::from_secs(5),
        )
        .await
        .unwrap();
        let error = execution.wait().await.unwrap_err();

        let parent_pid = fs::read_to_string(parent_pid_path).unwrap();
        let descendant_pid = fs::read_to_string(descendant_pid_path).unwrap();
        for pid in [parent_pid.trim(), descendant_pid.trim()] {
            let exists = std::process::Command::new("kill")
                .args(["-0", pid])
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status()
                .unwrap()
                .success();
            assert!(!exists, "producer process {pid} survived main shutdown");
        }
        assert!(!request_output.parent().unwrap().exists());
        assert!(error.to_string().contains("cancelled"), "{error:#}");
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
    async fn image_request_over_configured_limit_is_rejected_without_spawning() {
        let fixture = tempfile::tempdir().unwrap();
        let executable = fixture.path().join("producer");
        let marker = fixture.path().join("spawned");
        fs::write(&executable, "#!/bin/sh\ntouch \"$2\"\nexit 1\n").unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o755)).unwrap();
        let argv = serde_json::to_string(&[
            executable.to_string_lossy().into_owned(),
            "{out}".into(),
            marker.to_string_lossy().into_owned(),
        ])
        .unwrap();
        let mut state = state("http://127.0.0.1:1".into());
        state.image =
            ProducerConfig::parse(ProducerKind::Image, Some("true"), Some(&argv), Some("2"))
                .unwrap();

        let response = build_router(state)
            .oneshot(
                Request::post("/image")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        r#"{"prompt":"test","width":2049,"height":64,"steps":1}"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert!(!marker.exists());
    }

    #[tokio::test]
    async fn readiness_restats_enabled_producer_executable() {
        let (base_url, backend_cancellation, backend_server) = healthy_backend().await;
        let fixture = tempfile::tempdir().unwrap();
        let executable = fixture.path().join("producer");
        fs::write(&executable, "#!/bin/sh\nexit 0\n").unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o755)).unwrap();
        let argv =
            serde_json::to_string(&[executable.to_string_lossy().into_owned(), "{out}".into()])
                .unwrap();
        let mut state = state(base_url);
        state.image =
            ProducerConfig::parse(ProducerKind::Image, Some("true"), Some(&argv), Some("2"))
                .unwrap();
        let router = build_router(state);

        let ready = router
            .clone()
            .oneshot(Request::get("/ready").body(Body::empty()).unwrap())
            .await
            .unwrap();
        fs::remove_file(executable).unwrap();
        let missing = router
            .oneshot(Request::get("/ready").body(Body::empty()).unwrap())
            .await
            .unwrap();

        backend_cancellation.cancel();
        backend_server.await.unwrap();
        assert_eq!(ready.status(), StatusCode::OK);
        assert_eq!(missing.status(), StatusCode::SERVICE_UNAVAILABLE);
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
