//! 流式音频生成端点(方案 B)。契约见 desktop/STREAM_PROTOCOL.md。
//!
//! WS /music/stream:client 发 {"type":"start",prompt,seconds} → server 回 header(JSON)
//! → 连续二进制 f32le PCM 帧 → {"type":"end"}。client 可随时发 {"type":"stop"} 取消。
//!
//! Producer 两档(env YTS_AUDIOGEN_CMD 决定):
//!  - 未设置:内置确定性合成器(真实 PCM 流,用于无依赖端到端验证)。
//!  - 已设置:spawn 外部 audiogen 二进制(如 acestep.cpp),它「整段生成」一个 48kHz WAV,
//!    server 读 WAV → 按帧流式喂播(准实时,有首段生成延迟)。命令模板见 spawn_external_producer。
//!
//! 设计:无论哪档,对前端/契约完全一致(来源无关)。acestep.cpp 真集成只需设置 env + 备好二进制/模型。

use std::process::Stdio;
use std::time::Duration;

use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::response::Response;
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use tokio::io::AsyncReadExt;

const SAMPLE_RATE: u32 = 48_000;
const CHUNK_FRAMES: usize = 4_800; // 100ms/块 @ 48k(以"每声道采样"计)

#[derive(Deserialize, Default)]
struct Accept {
    // client 支持的编码(按优先序)。本 producer 暂只产 f32le;Opus 协商位预留(见 STREAM_PROTOCOL)。
    #[serde(default)]
    #[allow(dead_code)]
    codecs: Vec<String>,
    #[serde(default)]
    channels: Option<u16>,
}

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
enum ClientMsg {
    Start {
        prompt: String,
        #[serde(default = "default_seconds")]
        seconds: f32,
        #[serde(default)]
        accept: Accept,
    },
    Stop,
}
fn default_seconds() -> f32 {
    8.0
}

/// 据 client 的 accept 协商声道(支持 1/2;默认 1)。Opus 暂未在本 producer 实现,恒用 f32le。
fn negotiate_channels(accept: &Accept) -> u16 {
    match accept.channels {
        Some(2) => 2,
        _ => 1,
    }
}

#[derive(Serialize)]
#[serde(tag = "type", rename_all = "lowercase")]
enum ServerMsg {
    Header {
        #[serde(rename = "sampleRate")]
        sample_rate: u32,
        channels: u16,
        format: &'static str,
    },
    End {
        frames: usize,
        samples: usize,
    },
    Error {
        message: String,
    },
}

pub async fn music_stream_handler(ws: WebSocketUpgrade) -> Response {
    ws.on_upgrade(handle_socket)
}

async fn handle_socket(mut socket: WebSocket) {
    let (prompt, seconds, accept) = match wait_start(&mut socket).await {
        Some(v) => v,
        None => return,
    };
    let channels = negotiate_channels(&accept);

    // Producer:整段生成 mono f32 PCM(外部 audiogen 或内置合成器)。失败回 error。
    let mono = match produce_pcm(&prompt, seconds).await {
        Ok(p) => p,
        Err(e) => {
            let err = serde_json::to_string(&ServerMsg::Error { message: e }).unwrap();
            let _ = socket.send(Message::Text(err)).await;
            return;
        }
    };
    // 立体声:复制为 LRLR 交错(真实立体声 producer 可直接产交错)。
    let pcm = if channels == 2 { mono_to_stereo(&mono) } else { mono };
    let per_chan = pcm.len() / channels as usize;

    let header = serde_json::to_string(&ServerMsg::Header {
        sample_rate: SAMPLE_RATE,
        channels,
        format: "f32le",
    })
    .unwrap();
    if socket.send(Message::Text(header)).await.is_err() {
        return;
    }

    // 按帧流式喂播。块大小按声道对齐(CHUNK_FRAMES * channels 个交错采样)。
    let chunk = CHUNK_FRAMES * channels as usize;
    let mut produced = 0usize;
    let mut frames = 0usize;
    while produced < pcm.len() {
        if let Ok(Some(Ok(Message::Text(t)))) =
            tokio::time::timeout(Duration::from_millis(0), socket.recv()).await
        {
            if matches!(serde_json::from_str::<ClientMsg>(&t), Ok(ClientMsg::Stop)) {
                break;
            }
        }
        let end = (produced + chunk).min(pcm.len());
        let bytes = pcm_to_bytes(&pcm[produced..end]);
        produced = end;
        frames += 1;
        if socket.send(Message::Binary(bytes)).await.is_err() {
            return;
        }
        tokio::time::sleep(Duration::from_millis(80)).await; // ≈实时速率
    }

    // samples = 每声道采样数(与契约一致)
    let end = serde_json::to_string(&ServerMsg::End { frames, samples: per_chan }).unwrap();
    let _ = socket.send(Message::Text(end)).await;
    let _ = socket.close().await;
}

/// mono → LRLR 交错立体声(本轮双声道同源;真实立体声模型可直接输出交错)。
fn mono_to_stereo(mono: &[f32]) -> Vec<f32> {
    let mut out = Vec::with_capacity(mono.len() * 2);
    for &s in mono {
        out.push(s);
        out.push(s);
    }
    out
}

/// 生成整段 mono f32 PCM。有 YTS_AUDIOGEN_CMD 走外部,否则内置合成器。
async fn produce_pcm(prompt: &str, seconds: f32) -> Result<Vec<f32>, String> {
    match std::env::var("YTS_AUDIOGEN_CMD") {
        Ok(cmd) if !cmd.trim().is_empty() => spawn_external_producer(&cmd, prompt, seconds).await,
        _ => Ok(synth_pcm(prompt, seconds)),
    }
}

/// spawn 外部 audiogen(acestep.cpp 等)。约定:
///   命令中 {prompt} {seconds} {out} 占位被替换;{out} 是 server 指定的临时 WAV 路径;
///   producer 须把 48kHz WAV 写到 {out},退出码 0。server 读 WAV → mono f32 PCM。
/// 例:YTS_AUDIOGEN_CMD="acestep-cli --prompt {prompt} --seconds {seconds} --out {out}"
async fn spawn_external_producer(cmd_tmpl: &str, prompt: &str, seconds: f32) -> Result<Vec<f32>, String> {
    let out_path = std::env::temp_dir().join(format!("yts-audiogen-{}.wav", std::process::id()));
    let out_str = out_path.to_string_lossy().to_string();
    let filled = cmd_tmpl
        .replace("{prompt}", prompt)
        .replace("{seconds}", &format!("{seconds}"))
        .replace("{out}", &out_str);

    // 用 sh -c 解析命令模板
    let mut child = tokio::process::Command::new("sh")
        .arg("-c")
        .arg(&filled)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("spawn audiogen failed: {e}"))?;

    let status = child.wait().await.map_err(|e| format!("audiogen wait failed: {e}"))?;
    if !status.success() {
        let mut err = String::new();
        if let Some(mut s) = child.stderr.take() {
            let _ = s.read_to_string(&mut err).await;
        }
        return Err(format!("audiogen exited {status}: {}", err.trim()));
    }

    let pcm = read_wav_mono_f32(&out_str)?;
    let _ = std::fs::remove_file(&out_path);
    if pcm.is_empty() {
        return Err("audiogen produced empty audio".into());
    }
    Ok(pcm)
}

/// 读 WAV → mono f32 @ 48k。多声道下混为单声道;采样率不符仅告警(本轮不做重采样)。
fn read_wav_mono_f32(path: &str) -> Result<Vec<f32>, String> {
    let mut reader = hound::WavReader::open(path).map_err(|e| format!("open wav: {e}"))?;
    let spec = reader.spec();
    if spec.sample_rate != SAMPLE_RATE {
        tracing::warn!("audiogen WAV sample_rate={} != {SAMPLE_RATE}", spec.sample_rate);
    }
    let ch = spec.channels.max(1) as usize;
    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader
            .samples::<f32>()
            .filter_map(Result::ok)
            .collect(),
        hound::SampleFormat::Int => {
            let max = (1i64 << (spec.bits_per_sample - 1)) as f32;
            reader
                .samples::<i32>()
                .filter_map(Result::ok)
                .map(|s| s as f32 / max)
                .collect()
        }
    };
    if ch <= 1 {
        return Ok(samples);
    }
    // 下混为 mono
    Ok(samples.chunks(ch).map(|f| f.iter().sum::<f32>() / ch as f32).collect())
}

/// 内置确定性合成器(无依赖验证用)。随 prompt 变基频的复合正弦 + 缓慢包络。
fn synth_pcm(prompt: &str, seconds: f32) -> Vec<f32> {
    let total = (seconds.max(0.1) * SAMPLE_RATE as f32) as usize;
    let seed = prompt_seed(prompt);
    let base = 220.0 + (seed % 12) as f32 * 17.0;
    let mut out = Vec::with_capacity(total);
    for i in 0..total {
        let t = i as f32 / SAMPLE_RATE as f32;
        let env = (1.0 - (t * 0.5).fract()).clamp(0.0, 1.0);
        let s = (2.0 * std::f32::consts::PI * base * t).sin() * 0.5
            + (2.0 * std::f32::consts::PI * base * 2.0 * t).sin() * 0.2;
        out.push(s * env * 0.3);
    }
    out
}

async fn wait_start(socket: &mut WebSocket) -> Option<(String, f32, Accept)> {
    while let Some(Ok(msg)) = socket.next().await {
        if let Message::Text(t) = msg {
            match serde_json::from_str::<ClientMsg>(&t) {
                Ok(ClientMsg::Start { prompt, seconds, accept }) => {
                    return Some((prompt, seconds, accept))
                }
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
