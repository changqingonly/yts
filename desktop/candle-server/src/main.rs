//! yts 本地 Candle 推理服务(文本优先)。
//!
//! 架构(v3.1):推理在 Rust(Candle)。Python 编排(write_lyrics 等)经 HTTP 调本服务,
//! 即 yts_core/inference/candle_adapter.py → POST /candle/text。Tauri 桌面壳后续可 spawn 本服务。
//!
//! 模型默认 TinyLlama-1.1B-Chat(llama 架构 GGUF,量化 Q4_K_M),首次运行经 hf-hub 下载。
//! 可用环境变量覆盖:YTS_CANDLE_GGUF_REPO / YTS_CANDLE_GGUF_FILE / YTS_CANDLE_TOKENIZER_REPO。
//!
//! 图片/语音/音乐(SD / Whisper+TTS / MusicGen)为 TODO。

mod stream;

use std::sync::Arc;

use anyhow::{Context, Result};
use axum::{extract::State, routing::get, routing::post, Json, Router};
use candle_core::quantized::gguf_file;
use candle_core::{Device, Tensor};
use candle_transformers::generation::LogitsProcessor;
use candle_transformers::models::quantized_llama::ModelWeights;
use serde::{Deserialize, Serialize};
use tokenizers::Tokenizer;
use tokio::sync::Mutex;

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

fn pick_device() -> Device {
    #[cfg(feature = "metal")]
    {
        if let Ok(d) = Device::new_metal(0) {
            return d;
        }
    }
    Device::Cpu
}

struct Engine {
    model: ModelWeights,
    tokenizer: Tokenizer,
    device: Device,
    eos: u32,
}

impl Engine {
    fn load() -> Result<Self> {
        let api = hf_hub::api::sync::Api::new()?;
        let gguf_repo = env_or("YTS_CANDLE_GGUF_REPO", "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF");
        let gguf_file_name =
            env_or("YTS_CANDLE_GGUF_FILE", "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf");
        let tok_repo = env_or("YTS_CANDLE_TOKENIZER_REPO", "TinyLlama/TinyLlama-1.1B-Chat-v1.0");

        let model_path = api.model(gguf_repo).get(&gguf_file_name).context("download gguf")?;
        let tok_path = api.model(tok_repo).get("tokenizer.json").context("download tokenizer")?;

        let device = pick_device();
        let mut file = std::fs::File::open(&model_path).context("open gguf")?;
        let content = gguf_file::Content::read(&mut file).context("read gguf")?;
        let model = ModelWeights::from_gguf(content, &mut file, &device).context("from_gguf")?;

        let tokenizer = Tokenizer::from_file(&tok_path).map_err(anyhow::Error::msg)?;
        let eos = tokenizer.token_to_id("</s>").unwrap_or(2);

        Ok(Self { model, tokenizer, device, eos })
    }

    fn generate(&mut self, prompt: &str, max_tokens: usize) -> Result<String> {
        let encoding = self.tokenizer.encode(prompt, true).map_err(anyhow::Error::msg)?;
        let prompt_tokens: Vec<u32> = encoding.get_ids().to_vec();

        let mut logits_processor = LogitsProcessor::new(42, Some(0.7), Some(0.9));
        let mut all_tokens: Vec<u32> = Vec::new();

        // prefill
        let input = Tensor::new(prompt_tokens.as_slice(), &self.device)?.unsqueeze(0)?;
        let logits = self.model.forward(&input, 0)?.squeeze(0)?;
        let mut next = logits_processor.sample(&logits)?;
        all_tokens.push(next);

        // decode
        for i in 1..max_tokens {
            if next == self.eos {
                break;
            }
            let input = Tensor::new(&[next], &self.device)?.unsqueeze(0)?;
            let logits = self.model.forward(&input, prompt_tokens.len() + i - 1)?.squeeze(0)?;
            next = logits_processor.sample(&logits)?;
            all_tokens.push(next);
        }

        let text = self.tokenizer.decode(&all_tokens, true).map_err(anyhow::Error::msg)?;
        Ok(text)
    }
}

type SharedEngine = Arc<Mutex<Option<Engine>>>;

#[derive(Deserialize)]
struct TextReq {
    prompt: String,
    #[serde(default = "default_max")]
    max_tokens: usize,
}
fn default_max() -> usize {
    256
}

#[derive(Serialize)]
struct TextResp {
    text: String,
    model: String,
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({"status": "ok", "backend": "candle"}))
}

async fn gen_text(
    State(engine): State<SharedEngine>,
    Json(req): Json<TextReq>,
) -> Result<Json<TextResp>, (axum::http::StatusCode, String)> {
    let mut guard = engine.lock().await;
    // 懒加载:首次调用文本接口时才加载/下载模型,使服务启动即可用、/music/stream 无需模型
    if guard.is_none() {
        tracing::info!("loading candle model on first text request (hf-hub download on cold cache)...");
        let eng = Engine::load().map_err(|e| (axum::http::StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
        *guard = Some(eng);
    }
    let eng = guard.as_mut().unwrap();
    let text = eng
        .generate(&req.prompt, req.max_tokens)
        .map_err(|e| (axum::http::StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    Ok(Json(TextResp { text, model: "tinyllama-q4_k_m".into() }))
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let addr = env_or("YTS_CANDLE_ADDR", "127.0.0.1:8799");
    // 文本引擎懒加载:启动不阻塞,/health 与 /music/stream(流式音频)立即可用
    let engine: SharedEngine = Arc::new(Mutex::new(None));
    tracing::info!("candle-server up on {addr} (text model loads on first /candle/text)");

    let app = Router::new()
        .route("/health", get(health))
        .route("/candle/text", post(gen_text))
        .route("/music/stream", get(stream::music_stream_handler))
        .with_state(engine);

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}
