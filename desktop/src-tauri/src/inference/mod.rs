//! Candle 多模态推理(纯 Rust,in-process)。本轮为 stub:给出命令形状与特性开关。
//! 真实模型加载/推理在 `--features candle`(mac 叠 `--features metal`)下实现。
//!
//! 暴露给:① 前端(Tauri command);② Mac sidecar 的 Python(经本地 IPC/HTTP 回调,
//! 见 yts_core/inference/candle_adapter.py)。Windows in-process 形态则由 PyO3 同进程直调(留后)。

use serde::Serialize;

#[derive(Serialize)]
pub struct CandleInfo {
    pub feature_enabled: bool,
    pub backend: &'static str,
}

#[tauri::command]
pub fn candle_info() -> CandleInfo {
    CandleInfo {
        feature_enabled: cfg!(feature = "candle"),
        backend: if cfg!(feature = "metal") { "metal" } else { "cpu" },
    }
}

#[tauri::command]
pub fn candle_generate_text(prompt: String) -> String {
    // TODO(candle): 加载 LLM(Qwen3/Llama3 GGUF)推理
    format!("[candle-text-stub] {}", truncate(&prompt, 80))
}

#[tauri::command]
pub fn candle_generate_image(prompt: String) -> String {
    // TODO(candle): Stable Diffusion / SDXL-Turbo,返回图片路径或 base64
    format!("[candle-image-stub] {}", truncate(&prompt, 80))
}

#[tauri::command]
pub fn candle_generate_speech(text: String) -> String {
    // TODO(candle): Parler-TTS / MetaVoice;ASR 用 Whisper
    format!("[candle-tts-stub] {}", truncate(&text, 80))
}

#[tauri::command]
pub fn candle_generate_music(prompt: String, seconds: u32) -> String {
    // TODO(candle): MusicGen + EnCodec
    format!("[candle-music-stub:{}s] {}", seconds, truncate(&prompt, 80))
}

fn truncate(s: &str, n: usize) -> String {
    s.chars().take(n).collect()
}
