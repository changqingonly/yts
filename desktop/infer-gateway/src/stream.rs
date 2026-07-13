//! 流式音频生成端点。契约见 desktop/STREAM_PROTOCOL.md。
//!
//! WS /music/stream:client 发 {"type":"start",prompt,seconds} → server 回 header(JSON)
//! → 连续二进制 f32le PCM 帧 → {"type":"end"}。client 可随时发 {"type":"stop"} 取消。
//!
//! 启用时仅执行启动期验证过的结构化 argv producer，并严格读取其 48kHz WAV 输出。

use std::io::Cursor;
use std::time::Duration;

use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::{FromRequestParts, Request, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};

use crate::producer::ProducerConfig;
use crate::GatewayState;

const SAMPLE_RATE: u32 = 48_000;
const CHUNK_FRAMES: usize = 4_800; // 100ms/块 @ 48k(以"每声道采样"计)

#[derive(Deserialize, Default)]
struct Accept {
    #[serde(default)]
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

pub async fn music_stream_handler(State(state): State<GatewayState>, request: Request) -> Response {
    if !state.audio.enabled() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            "audio generation is disabled",
        )
            .into_response();
    }
    let (mut parts, _) = request.into_parts();
    let ws = match WebSocketUpgrade::from_request_parts(&mut parts, &state).await {
        Ok(ws) => ws,
        Err(rejection) => return rejection.into_response(),
    };
    let producer = state.audio.clone();
    ws.on_upgrade(move |socket| handle_socket(socket, producer))
}

async fn handle_socket(mut socket: WebSocket, producer: ProducerConfig) {
    let (prompt, seconds, channels) = match wait_start(&mut socket).await {
        Some(v) => v,
        None => return,
    };

    let pcm = match produce_pcm(&producer, &prompt, seconds).await {
        Ok(p) => p,
        Err(e) => {
            let err = serde_json::to_string(&ServerMsg::Error { message: e })
                .expect("serialize fixed audio error response");
            let _ = socket.send(Message::Text(err)).await;
            return;
        }
    };
    let per_chan = pcm.len() / channels as usize;

    let header = serde_json::to_string(&ServerMsg::Header {
        sample_rate: SAMPLE_RATE,
        channels,
        format: "f32le",
    })
    .expect("serialize fixed audio header response");
    if socket.send(Message::Text(header)).await.is_err() {
        return;
    }

    // 按帧流式喂播。块大小按声道对齐(CHUNK_FRAMES * channels 个交错采样)。
    let chunk = CHUNK_FRAMES * channels as usize;
    let mut produced = 0usize;
    let mut frames = 0usize;
    while produced < pcm.len() {
        if let Ok(Some(message)) =
            tokio::time::timeout(Duration::from_millis(1), socket.recv()).await
        {
            match message {
                Ok(Message::Text(text)) => match serde_json::from_str::<ClientMsg>(&text) {
                    Ok(ClientMsg::Stop) => break,
                    Ok(ClientMsg::Start { .. }) => {
                        send_protocol_error(&mut socket, "audio stream already started").await;
                        return;
                    }
                    Err(error) => {
                        send_protocol_error(
                            &mut socket,
                            &format!("invalid client message: {error}"),
                        )
                        .await;
                        return;
                    }
                },
                Ok(Message::Close(_)) => return,
                Ok(_) => {
                    send_protocol_error(&mut socket, "only text control messages are accepted")
                        .await;
                    return;
                }
                Err(_) => return,
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
    let end = serde_json::to_string(&ServerMsg::End {
        frames,
        samples: per_chan,
    })
    .expect("serialize fixed audio end response");
    let _ = socket.send(Message::Text(end)).await;
    let _ = socket.close().await;
}

async fn produce_pcm(
    producer: &ProducerConfig,
    prompt: &str,
    seconds: f32,
) -> Result<Vec<f32>, String> {
    let seconds = seconds.to_string();
    let output = producer
        .execute(
            "audio.wav",
            &[("prompt", prompt), ("seconds", seconds.as_str())],
        )
        .await
        .map_err(|error| format!("audio producer failed: {error:#}"))?;
    let pcm = decode_wav_mono_f32(&output.bytes)?;
    if pcm.is_empty() {
        return Err("audio producer returned no samples".into());
    }
    Ok(pcm)
}

#[cfg(test)]
fn read_wav_mono_f32(path: &str) -> Result<Vec<f32>, String> {
    let bytes = std::fs::read(path).map_err(|error| format!("read WAV: {error}"))?;
    decode_wav_mono_f32(&bytes)
}

fn decode_wav_mono_f32(bytes: &[u8]) -> Result<Vec<f32>, String> {
    let mut reader =
        hound::WavReader::new(Cursor::new(bytes)).map_err(|error| format!("open WAV: {error}"))?;
    let spec = reader.spec();
    if spec.sample_rate != SAMPLE_RATE {
        return Err(format!(
            "audio producer WAV sample rate is {}, expected {SAMPLE_RATE}",
            spec.sample_rate
        ));
    }
    if !matches!(spec.channels, 1 | 2) {
        return Err(format!(
            "audio producer WAV channels is {}, only mono or stereo is supported",
            spec.channels
        ));
    }
    let channels = spec.channels as usize;
    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => {
            if spec.bits_per_sample != 32 {
                return Err(format!(
                    "audio producer float WAV uses {} bits per sample, expected 32",
                    spec.bits_per_sample
                ));
            }
            reader
                .samples::<f32>()
                .collect::<Result<Vec<_>, _>>()
                .map_err(|error| format!("decode float WAV sample: {error}"))?
        }
        hound::SampleFormat::Int => {
            if !(1..=32).contains(&spec.bits_per_sample) {
                return Err(format!(
                    "audio producer integer WAV bits per sample {} is unsupported",
                    spec.bits_per_sample
                ));
            }
            let max = (1i64 << (spec.bits_per_sample - 1)) as f32;
            reader
                .samples::<i32>()
                .collect::<Result<Vec<_>, _>>()
                .map_err(|error| format!("decode integer WAV sample: {error}"))?
                .into_iter()
                .map(|s| s as f32 / max)
                .collect()
        }
    };
    if samples.iter().any(|sample| !sample.is_finite()) {
        return Err("audio producer WAV contains a non-finite sample".into());
    }
    if !samples.len().is_multiple_of(channels) {
        return Err(format!(
            "audio producer WAV has {} samples, not a complete {channels}-channel frame",
            samples.len()
        ));
    }
    if channels == 1 {
        return Ok(samples);
    }
    let mut downmixed = Vec::with_capacity(samples.len() / channels);
    for frame in samples.chunks_exact(channels) {
        let sum = frame.iter().map(|sample| *sample as f64).sum::<f64>();
        if !sum.is_finite() || sum.abs() > f32::MAX as f64 {
            return Err("audio producer WAV stereo downmix accumulation is not finite f32".into());
        }
        let sample = (sum / channels as f64) as f32;
        if !sample.is_finite() {
            return Err("audio producer WAV stereo downmix produced a non-finite sample".into());
        }
        downmixed.push(sample);
    }
    Ok(downmixed)
}

fn validate_start(prompt: &str, seconds: f32, accept: &Accept) -> Result<u16, String> {
    if prompt.trim().is_empty() {
        return Err("prompt must not be empty".into());
    }
    if !seconds.is_finite() || seconds <= 0.0 {
        return Err("seconds must be finite and greater than zero".into());
    }
    if !accept.codecs.is_empty() && !accept.codecs.iter().any(|codec| codec == "f32le") {
        return Err("only f32le audio is supported".into());
    }
    match accept.channels {
        None | Some(1) => Ok(1),
        Some(channels) => Err(format!(
            "requested audio channels {channels} is unsupported; only mono is available"
        )),
    }
}

async fn wait_start(socket: &mut WebSocket) -> Option<(String, f32, u16)> {
    match socket.next().await {
        Some(Ok(Message::Text(text))) => match serde_json::from_str::<ClientMsg>(&text) {
            Ok(ClientMsg::Start {
                prompt,
                seconds,
                accept,
            }) => match validate_start(&prompt, seconds, &accept) {
                Ok(channels) => Some((prompt, seconds, channels)),
                Err(error) => {
                    send_protocol_error(socket, &error).await;
                    None
                }
            },
            Ok(ClientMsg::Stop) => None,
            Err(error) => {
                send_protocol_error(socket, &format!("invalid start message: {error}")).await;
                None
            }
        },
        Some(Ok(Message::Close(_))) | None => None,
        Some(Ok(_)) => {
            send_protocol_error(
                socket,
                "audio stream must start with a text control message",
            )
            .await;
            None
        }
        Some(Err(error)) => {
            tracing::warn!("failed to receive audio stream start message: {error}");
            None
        }
    }
}

async fn send_protocol_error(socket: &mut WebSocket, message: &str) {
    let message = serde_json::to_string(&ServerMsg::Error {
        message: message.into(),
    })
    .expect("serialize fixed audio protocol error response");
    let _ = socket.send(Message::Text(message)).await;
}

fn pcm_to_bytes(pcm: &[f32]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(pcm.len() * 4);
    for &s in pcm {
        bytes.extend_from_slice(&s.to_le_bytes());
    }
    bytes
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::io::Write;

    fn wav_path() -> tempfile::NamedTempFile {
        tempfile::NamedTempFile::new().unwrap()
    }

    fn pcm16_wav(channels: u16, sample_rate: u32, declared_data_len: u32, data: &[u8]) -> Vec<u8> {
        let mut bytes = Vec::new();
        bytes.extend_from_slice(b"RIFF");
        bytes.extend_from_slice(&(36 + declared_data_len).to_le_bytes());
        bytes.extend_from_slice(b"WAVEfmt ");
        bytes.extend_from_slice(&16_u32.to_le_bytes());
        bytes.extend_from_slice(&1_u16.to_le_bytes());
        bytes.extend_from_slice(&channels.to_le_bytes());
        bytes.extend_from_slice(&sample_rate.to_le_bytes());
        bytes.extend_from_slice(&(sample_rate * channels as u32 * 2).to_le_bytes());
        bytes.extend_from_slice(&(channels * 2).to_le_bytes());
        bytes.extend_from_slice(&16_u16.to_le_bytes());
        bytes.extend_from_slice(b"data");
        bytes.extend_from_slice(&declared_data_len.to_le_bytes());
        bytes.extend_from_slice(data);
        bytes
    }

    #[test]
    fn rejects_wav_with_non_48khz_sample_rate() {
        let file = wav_path();
        let spec = hound::WavSpec {
            channels: 1,
            sample_rate: 44_100,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };
        let mut writer = hound::WavWriter::new(file.reopen().unwrap(), spec).unwrap();
        writer.write_sample(0_i16).unwrap();
        writer.finalize().unwrap();

        assert!(super::read_wav_mono_f32(file.path().to_str().unwrap()).is_err());
    }

    #[test]
    fn rejects_truncated_wav_sample_data() {
        let mut file = wav_path();
        file.write_all(&pcm16_wav(1, 48_000, 2, &[0])).unwrap();
        file.flush().unwrap();

        assert!(super::read_wav_mono_f32(file.path().to_str().unwrap()).is_err());
    }

    #[test]
    fn rejects_incomplete_channel_frame() {
        let file = wav_path();
        fs::write(file.path(), pcm16_wav(2, 48_000, 2, &[0, 0])).unwrap();

        assert!(super::read_wav_mono_f32(file.path().to_str().unwrap()).is_err());
    }

    #[test]
    fn rejects_non_finite_float_samples() {
        let file = wav_path();
        let spec = hound::WavSpec {
            channels: 1,
            sample_rate: 48_000,
            bits_per_sample: 32,
            sample_format: hound::SampleFormat::Float,
        };
        let mut writer = hound::WavWriter::new(file.reopen().unwrap(), spec).unwrap();
        writer.write_sample(f32::NAN).unwrap();
        writer.finalize().unwrap();

        assert!(super::read_wav_mono_f32(file.path().to_str().unwrap()).is_err());
    }

    #[test]
    fn rejects_non_finite_stereo_downmix_result() {
        let file = wav_path();
        let spec = hound::WavSpec {
            channels: 2,
            sample_rate: 48_000,
            bits_per_sample: 32,
            sample_format: hound::SampleFormat::Float,
        };
        let mut writer = hound::WavWriter::new(file.reopen().unwrap(), spec).unwrap();
        writer.write_sample(f32::MAX).unwrap();
        writer.write_sample(f32::MAX).unwrap();
        writer.finalize().unwrap();

        assert!(super::read_wav_mono_f32(file.path().to_str().unwrap()).is_err());
    }

    #[test]
    fn rejects_unsupported_requested_channels_and_invalid_seconds() {
        assert!(super::validate_start(
            "prompt",
            1.0,
            &super::Accept {
                codecs: vec![],
                channels: Some(2)
            }
        )
        .is_err());
        assert!(super::validate_start("prompt", 0.0, &super::Accept::default()).is_err());
        assert!(super::validate_start("prompt", f32::NAN, &super::Accept::default()).is_err());
    }
}
