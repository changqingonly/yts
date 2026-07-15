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

use crate::producer::{ProducerConfig, ProducerExecution, ProducerSupervisor};
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
    let supervisor = state.producers.clone();
    ws.on_upgrade(move |socket| handle_socket(socket, producer, supervisor))
}

async fn handle_socket(
    mut socket: WebSocket,
    producer: ProducerConfig,
    supervisor: ProducerSupervisor,
) {
    let (prompt, seconds, channels) = match wait_start(&mut socket, &supervisor).await {
        Some(v) => v,
        None => return,
    };
    if let Err(error) = producer.validate_audio_request(seconds) {
        send_generation_error(&mut socket, format!("{error:#}")).await;
        return;
    }
    let seconds_value = seconds.to_string();
    let mut execution = match supervisor
        .start(
            &producer,
            "audio.wav",
            &[
                ("prompt", prompt.as_str()),
                ("seconds", seconds_value.as_str()),
            ],
        )
        .await
    {
        Ok(execution) => execution,
        Err(error) => {
            send_generation_error(
                &mut socket,
                format!("start audio producer failed: {error:#}"),
            )
            .await;
            return;
        }
    };
    let output = tokio::select! {
        result = execution.wait_result() => result,
        message = socket.recv() => match message {
                Some(Ok(Message::Text(text))) => match serde_json::from_str::<ClientMsg>(&text) {
                    Ok(ClientMsg::Stop) => {
                        if let Err(error) = execution.cancel_and_wait().await {
                            send_generation_error(
                                &mut socket,
                                format!("cancel audio producer cleanup failed: {error:#}"),
                            )
                            .await;
                            return;
                        }
                        send_end(&mut socket, 0, 0).await;
                        let _ = socket.close().await;
                        return;
                    }
                    Ok(ClientMsg::Start { .. }) => {
                        cancel_for_protocol_error(
                            &mut socket,
                            &mut execution,
                            "audio stream already started".into(),
                        )
                        .await;
                        return;
                    }
                    Err(error) => {
                        cancel_for_protocol_error(
                            &mut socket,
                            &mut execution,
                            format!("invalid client message: {error}"),
                        )
                        .await;
                        return;
                    }
                },
                Some(Ok(Message::Close(_))) | None => {
                    if let Err(error) = execution.cancel_and_wait().await {
                        tracing::error!("audio producer cleanup after WebSocket close failed: {error:#}");
                    }
                    return;
                }
                Some(Ok(_)) => {
                    cancel_for_protocol_error(
                        &mut socket,
                        &mut execution,
                        "only text control messages are accepted".into(),
                    )
                    .await;
                    return;
                }
                Some(Err(error)) => {
                    if let Err(cleanup) = execution.cancel_and_wait().await {
                        tracing::error!(
                            "audio WebSocket receive failed: {error}; producer cleanup failed: {cleanup:#}"
                        );
                    }
                    return;
                }
        }
    };
    let output = match output {
        Ok(output) => output,
        Err(error) => {
            send_generation_error(&mut socket, format!("audio producer failed: {error:#}")).await;
            return;
        }
    };
    let pcm = match decode_wav_mono_f32(&output.bytes) {
        Ok(pcm) if !pcm.is_empty() => pcm,
        Ok(_) => {
            send_generation_error(&mut socket, "audio producer returned no samples".into()).await;
            return;
        }
        Err(error) => {
            send_generation_error(&mut socket, error).await;
            return;
        }
    };

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

    send_end(&mut socket, frames, produced / channels as usize).await;
    let _ = socket.close().await;
}

async fn cancel_for_protocol_error(
    socket: &mut WebSocket,
    execution: &mut ProducerExecution,
    message: String,
) {
    let message = match execution.cancel_and_wait().await {
        Ok(()) => message,
        Err(error) => format!("{message}; audio producer cleanup failed: {error:#}"),
    };
    send_protocol_error(socket, &message).await;
}

async fn send_generation_error(socket: &mut WebSocket, message: String) {
    let message = serde_json::to_string(&ServerMsg::Error { message })
        .expect("serialize fixed audio generation error response");
    let _ = socket.send(Message::Text(message)).await;
}

async fn send_end(socket: &mut WebSocket, frames: usize, samples: usize) {
    let message = serde_json::to_string(&ServerMsg::End { frames, samples })
        .expect("serialize fixed audio end response");
    let _ = socket.send(Message::Text(message)).await;
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
    if matches!(spec.sample_format, hound::SampleFormat::Float)
        && samples.iter().any(|sample| !(-1.0..=1.0).contains(sample))
    {
        return Err("audio producer float WAV contains a sample outside [-1, 1]".into());
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
        None | Some(1) | Some(2) => Ok(1),
        Some(channels) => Err(format!(
            "requested audio channels {channels} is unsupported; only mono is available"
        )),
    }
}

async fn wait_start(
    socket: &mut WebSocket,
    supervisor: &ProducerSupervisor,
) -> Option<(String, f32, u16)> {
    let message = tokio::select! {
        message = socket.next() => message,
        () = supervisor.cancelled() => return None,
    };
    match message {
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
    use std::os::unix::fs::PermissionsExt;
    use std::time::Duration;

    use futures_util::{SinkExt, StreamExt};
    use tokio_util::sync::CancellationToken;

    use crate::llama::LlamaBackend;
    use crate::producer::{ProducerConfig, ProducerKind, ProducerSupervisor};
    use crate::{build_router, GatewayState};

    fn wav_path() -> tempfile::NamedTempFile {
        tempfile::NamedTempFile::new().unwrap()
    }

    fn process_exists(pid: &str) -> bool {
        std::process::Command::new("kill")
            .args(["-0", pid])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .unwrap()
            .success()
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

    #[tokio::test]
    async fn websocket_stop_during_generation_cancels_and_waits_for_producer_cleanup() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let fixture = tempfile::tempdir().unwrap();
        let executable = fixture.path().join("audio-producer");
        fs::write(
            &executable,
            "#!/bin/sh\nprintf '%s' \"$$\" > \"$2\"\nprintf '%s' \"$1\" > \"$3\"\nexec sleep 30\n",
        )
        .unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o755)).unwrap();
        let observation = tempfile::tempdir().unwrap();
        let pid_path = observation.path().join("pid");
        let output_path = observation.path().join("output.path");
        let argv = serde_json::to_string(&[
            executable.to_string_lossy().into_owned(),
            "{out}".into(),
            pid_path.to_string_lossy().into_owned(),
            output_path.to_string_lossy().into_owned(),
        ])
        .unwrap();
        let audio =
            ProducerConfig::parse(ProducerKind::Audio, Some("true"), Some(&argv), Some("30"))
                .unwrap();
        let producer_cancellation = CancellationToken::new();
        let producers = ProducerSupervisor::new(producer_cancellation);
        let state = GatewayState {
            llama: LlamaBackend::from_parts_for_test("http://127.0.0.1:1".into()),
            image: ProducerConfig::parse(ProducerKind::Image, Some("false"), None, None).unwrap(),
            audio,
            producers: producers.clone(),
        };
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server_cancellation = CancellationToken::new();
        let server_shutdown = server_cancellation.clone();
        let mut server = tokio::spawn(async move {
            axum::serve(listener, build_router(state))
                .with_graceful_shutdown(server_shutdown.cancelled_owned())
                .await
                .unwrap();
        });
        let (mut websocket, _) =
            tokio_tungstenite::connect_async(format!("ws://{address}/music/stream"))
                .await
                .unwrap();
        websocket
            .send(tokio_tungstenite::tungstenite::Message::Text(
                r#"{"type":"start","prompt":"test","seconds":5,"accept":{"channels":2,"codecs":["f32le"]}}"#
                    .into(),
            ))
            .await
            .unwrap();
        tokio::time::timeout(Duration::from_secs(5), async {
            tokio::select! {
                () = async {
                    while !pid_path.exists() || !output_path.exists() {
                        tokio::task::yield_now().await;
                    }
                } => {}
                result = &mut server => {
                    panic!("gateway server completed before producer markers: {result:?}")
                }
            }
        })
        .await
        .unwrap();

        websocket
            .send(tokio_tungstenite::tungstenite::Message::Text(
                r#"{"type":"stop"}"#.into(),
            ))
            .await
            .unwrap();
        let response = tokio::time::timeout(Duration::from_millis(500), websocket.next()).await;

        producers.shutdown(Duration::from_secs(2)).await.unwrap();
        server_cancellation.cancel();
        tokio::time::timeout(Duration::from_secs(2), server)
            .await
            .unwrap()
            .unwrap();
        let pid = fs::read_to_string(pid_path).unwrap();
        let request_output = std::path::PathBuf::from(fs::read_to_string(output_path).unwrap());
        assert!(!process_exists(pid.trim()));
        assert!(!request_output.parent().unwrap().exists());
        let message = response
            .expect("stop was not processed while audio generation was active")
            .expect("websocket closed without an end response")
            .expect("websocket returned an error");
        let end: serde_json::Value = serde_json::from_str(message.to_text().unwrap()).unwrap();
        assert_eq!(end["type"], "end");
        assert_eq!(end["frames"], 0);
        assert_eq!(end["samples"], 0);
    }

    #[tokio::test]
    async fn websocket_reports_actual_mono_samples_sent_before_streaming_stop() {
        let _process_guard = crate::PROCESS_TEST_LOCK.lock().await;
        let fixture = tempfile::tempdir().unwrap();
        let wav = fixture.path().join("audio.wav");
        let specification = hound::WavSpec {
            channels: 1,
            sample_rate: super::SAMPLE_RATE,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };
        let mut writer = hound::WavWriter::create(&wav, specification).unwrap();
        for _ in 0..(super::CHUNK_FRAMES * 2) {
            writer.write_sample(0_i16).unwrap();
        }
        writer.finalize().unwrap();
        let executable = fixture.path().join("audio-producer");
        fs::write(&executable, "#!/bin/sh\ncp \"$2\" \"$1\"\n").unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o755)).unwrap();
        let argv = serde_json::to_string(&[
            executable.to_string_lossy().into_owned(),
            "{out}".into(),
            wav.to_string_lossy().into_owned(),
        ])
        .unwrap();
        let audio =
            ProducerConfig::parse(ProducerKind::Audio, Some("true"), Some(&argv), Some("2"))
                .unwrap();
        let producers = ProducerSupervisor::new(CancellationToken::new());
        let state = GatewayState {
            llama: LlamaBackend::from_parts_for_test("http://127.0.0.1:1".into()),
            image: ProducerConfig::parse(ProducerKind::Image, Some("false"), None, None).unwrap(),
            audio,
            producers: producers.clone(),
        };
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server_cancellation = CancellationToken::new();
        let server_shutdown = server_cancellation.clone();
        let server = tokio::spawn(async move {
            axum::serve(listener, build_router(state))
                .with_graceful_shutdown(server_shutdown.cancelled_owned())
                .await
                .unwrap();
        });
        let (mut websocket, _) =
            tokio_tungstenite::connect_async(format!("ws://{address}/music/stream"))
                .await
                .unwrap();
        websocket
            .send(tokio_tungstenite::tungstenite::Message::Text(
                r#"{"type":"start","prompt":"test","seconds":5,"accept":{"channels":2,"codecs":["f32le"]}}"#
                    .into(),
            ))
            .await
            .unwrap();

        let header = websocket.next().await.unwrap().unwrap();
        let header: serde_json::Value = serde_json::from_str(header.to_text().unwrap()).unwrap();
        assert_eq!(header["type"], "header", "unexpected response: {header}");
        assert_eq!(header["channels"], 1);
        let first_chunk = websocket.next().await.unwrap().unwrap();
        assert_eq!(first_chunk.into_data().len(), super::CHUNK_FRAMES * 4);
        websocket
            .send(tokio_tungstenite::tungstenite::Message::Text(
                r#"{"type":"stop"}"#.into(),
            ))
            .await
            .unwrap();
        let end = tokio::time::timeout(Duration::from_secs(1), websocket.next())
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        let end: serde_json::Value = serde_json::from_str(end.to_text().unwrap()).unwrap();

        server_cancellation.cancel();
        server.await.unwrap();
        producers.shutdown(Duration::from_secs(1)).await.unwrap();
        assert_eq!(end["type"], "end");
        assert_eq!(end["frames"], 1);
        assert_eq!(end["samples"], super::CHUNK_FRAMES);
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
    fn rejects_finite_float_samples_outside_normalized_range() {
        let file = wav_path();
        let spec = hound::WavSpec {
            channels: 1,
            sample_rate: 48_000,
            bits_per_sample: 32,
            sample_format: hound::SampleFormat::Float,
        };
        let mut writer = hound::WavWriter::new(file.reopen().unwrap(), spec).unwrap();
        writer.write_sample(1.01_f32).unwrap();
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
        assert_eq!(
            super::validate_start(
                "prompt",
                1.0,
                &super::Accept {
                    codecs: vec![],
                    channels: Some(2)
                }
            )
            .unwrap(),
            1
        );
        assert!(super::validate_start("prompt", 0.0, &super::Accept::default()).is_err());
        assert!(super::validate_start("prompt", f32::NAN, &super::Accept::default()).is_err());
    }
}
