from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_inference_gateway_does_not_wait_for_llama_before_serving_other_modalities() -> None:
    llama = (ROOT / "desktop/infer-gateway/src/llama.rs").read_text(encoding="utf-8")
    start_block = llama.split("pub async fn start() -> Self {", 1)[1].split(
        "pub fn base_url", 1
    )[0]
    text_handler = llama.split("pub async fn gen_text(", 1)[1].split(
        "let mut body =", 1
    )[0]

    assert "wait_ready" not in start_block
    assert ".spawn()" not in start_block
    assert "async fn ensure_started" in llama
    assert "kill_on_drop(true)" in llama
    assert "llama\n        .wait_ready()" in text_handler
    assert "llama-server exited before readiness" in llama


def test_tauri_gateway_command_returns_only_after_gateway_health_is_ready() -> None:
    gateway = (ROOT / "desktop/src-tauri/src/gateway.rs").read_text(encoding="utf-8")
    start_block = gateway.split("pub async fn start_gateway", 1)[1].split(
        "async fn wait_gateway_ready", 1
    )[0]

    assert "if !already_running" in start_block
    assert "wait_gateway_ready().await" in start_block
    assert 'Some("ggml-gateway")' in gateway
    assert "stop_gateway(app).await" in start_block
