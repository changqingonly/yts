//! 流式音频生成端点(方案 B)。契约见 desktop/STREAM_PROTOCOL.md。
//!
//! WS /music/stream:client 发 {"type":"start",prompt,seconds} → server 回 header(JSON)
//! → 连续二进制 f32le PCM 帧 → {"type":"end"}。client 可随时发 {"type":"stop"} 取消。
//!
//! 本轮帧由确定性合成器(随 prompt 变化的复合正弦 + 包络)逐块产生 —— 这是真实 PCM 流,
//! 用于端到端验证「边生成边播」。★ MusicGen 替换点见 generate_chunk():
//!   把合成替换为 candle MusicGen 的逐步解码输出(EnCodec 解码出的 PCM)即可,协议不变。

use std::time::Duration;

use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::response::Response;
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};

const SAMPLE_RATE: u32 = 48_000;
const CHANNELS: u16 = 1;
const CHUNK_SAMPLES: usize = 4_800; // 100ms/块 @ 48k

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
enum ClientMsg {
    Start { prompt: String, #[serde(default = "default_seconds")] seconds: f32 },
    Stop,
}
fn default_seconds() -> f32 {
    8.0
}

#[derive(Serialize)]
#[serde(tag = "type", rename_all = "lowercase")]
enum ServerMsg {
    Header { #[serde(rename = "sampleRate")] sample_rate: u32, channels: u16, format: &'static str },
    End { frames: usize, samples: usize },
    Error { message: String },
}

pub async fn music_stream_handler(ws: WebSocketUpgrade) -> Response {
    ws.on_upgrade(handle_socket)
}

async fn handle_socket(mut socket: WebSocket) {
    // 等待 start
    let (prompt, seconds) = match wait_start(&mut socket).await {
        Some(v) => v,
        None => return,
    };

    let header = serde_json::to_string(&ServerMsg::Header {
        sample_rate: SAMPLE_RATE,
        channels: CHANNELS,
        format: "f32le",
    })
    .unwrap();
    if socket.send(Message::Text(header)).await.is_err() {
        return;
    }

    let total_samples = (seconds.max(0.1) * SAMPLE_RATE as f32) as usize;
    let seed = prompt_seed(&prompt);
    let mut produced = 0usize;
    let mut frames = 0usize;

    while produced < total_samples {
        // 非阻塞检查 stop
        if let Ok(Some(Ok(Message::Text(t)))) = tokio::time::timeout(Duration::from_millis(0), socket.recv()).await {
            if matches!(serde_json::from_str::<ClientMsg>(&t), Ok(ClientMsg::Stop)) {
                break;
            }
        }

        let n = CHUNK_SAMPLES.min(total_samples - produced);
        let pcm = generate_chunk(seed, produced, n);
        produced += n;
        frames += 1;

        let bytes = pcm_to_bytes(&pcm);
        if socket.send(Message::Binary(bytes)).await.is_err() {
            return;
        }
        // 模拟「准实时」生成节奏(本地生成也并非瞬时);约等于实时速率
        tokio::time::sleep(Duration::from_millis(80)).await;
    }

    let end = serde_json::to_string(&ServerMsg::End { frames, samples: produced }).unwrap();
    let _ = socket.send(Message::Text(end)).await;
    let _ = socket.close().await;
}

async fn wait_start(socket: &mut WebSocket) -> Option<(String, f32)> {
    while let Some(Ok(msg)) = socket.next().await {
        if let Message::Text(t) = msg {
            match serde_json::from_str::<ClientMsg>(&t) {
                Ok(ClientMsg::Start { prompt, seconds }) => return Some((prompt, seconds)),
                Ok(ClientMsg::Stop) => return None,
                Err(e) => {
                    let err = serde_json::to_string(&ServerMsg::Error { message: e.to_string() }).unwrap();
                    let _ = socket.send(Message::Text(err)).await;
                    return None;
                }
            }
        }
    }
    None
}

/// ★ MusicGen 替换点:把下面的合成换成 candle MusicGen 逐步解码出的 PCM。
/// 当前:随 prompt 变化的复合正弦 + 简单 ADSR 包络,产出真实可听 PCM 流。
fn generate_chunk(seed: u64, start_sample: usize, n: usize) -> Vec<f32> {
    let base = 220.0 + (seed % 12) as f32 * 17.0; // 随 prompt 变基频
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        let t = (start_sample + i) as f32 / SAMPLE_RATE as f32;
        let env = (1.0 - (t * 0.5).fract()).clamp(0.0, 1.0); // 缓慢起伏
        let s = (2.0 * std::f32::consts::PI * base * t).sin() * 0.5
            + (2.0 * std::f32::consts::PI * base * 2.0 * t).sin() * 0.2;
        out.push(s * env * 0.3);
    }
    out
}

fn prompt_seed(prompt: &str) -> u64 {
    prompt.bytes().fold(1469598103934665603u64, |h, b| (h ^ b as u64).wrapping_mul(1099511628211))
}

fn pcm_to_bytes(pcm: &[f32]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(pcm.len() * 4);
    for &s in pcm {
        bytes.extend_from_slice(&s.to_le_bytes());
    }
    bytes
}
