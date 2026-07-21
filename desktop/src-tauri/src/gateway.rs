//! 管理 infer-gateway(本地 GGML 推理网关)子进程的生命周期,壳内第二个 externalBin sidecar。
//! 打包态下由本模块 spawn(取代 dev 态 scripts/dev_gateway.sh);env(YTS_LLAMA_CMD /
//! YTS_IMAGEGEN_CMD / YTS_AUDIOGEN_CMD)按 models.rs / acestep.rs 拼装,指向 app_data_dir()
//! 下载好的二进制/权重;acestep.cpp 未构建时该 env 缺省,网关退回内置音乐合成兜底。

use std::sync::Mutex;

use tauri::{AppHandle, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

use crate::acestep::AcestepPaths;
use crate::models::LocalPaths;

#[derive(Default)]
pub struct GatewayState(pub Mutex<Option<CommandChild>>);

#[tauri::command]
pub async fn start_gateway(app: AppHandle) -> Result<String, String> {
    {
        let state = app.state::<GatewayState>();
        let guard = state.0.lock().map_err(|e| e.to_string())?;
        if guard.is_some() {
            return Ok("gateway already running".into());
        }
    }
    let paths = LocalPaths::new(&app)?;
    let mut cmd = app.shell().sidecar("infer-gateway").map_err(|e| e.to_string())?;
    if let Some(llama_cmd) = paths.llama_cmd() {
        cmd = cmd
            .env("YTS_LLAMA_CMD", llama_cmd)
            .env("YTS_LLAMA_BASE_URL", paths.llama_base_url());
    }
    if let Some(imagegen_cmd) = paths.imagegen_cmd() {
        cmd = cmd.env("YTS_IMAGEGEN_CMD", imagegen_cmd);
    }
    if let Some(audiogen_cmd) = AcestepPaths::new(&app)?.audiogen_cmd() {
        cmd = cmd.env("YTS_AUDIOGEN_CMD", audiogen_cmd);
    }
    let (mut rx, child) = cmd.spawn().map_err(|e| e.to_string())?;
    {
        let state = app.state::<GatewayState>();
        let mut guard = state.0.lock().map_err(|e| e.to_string())?;
        *guard = Some(child);
    }
    let log_app = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    crate::log_line(&log_app, &format!("[infer-gateway] {}", String::from_utf8_lossy(&line)));
                }
                CommandEvent::Stderr(line) => {
                    crate::log_line(&log_app, &format!("[infer-gateway] {}", String::from_utf8_lossy(&line)));
                }
                CommandEvent::Terminated(payload) => {
                    crate::log_line(&log_app, &format!("[infer-gateway] terminated: {payload:?}"));
                }
                CommandEvent::Error(err) => {
                    crate::log_line(&log_app, &format!("[infer-gateway] error: {err}"));
                }
                _ => {}
            }
        }
    });
    Ok("gateway started".into())
}

#[tauri::command]
pub async fn stop_gateway(app: AppHandle) -> Result<String, String> {
    let child = {
        let state = app.state::<GatewayState>();
        let mut guard = state.0.lock().map_err(|e| e.to_string())?;
        guard.take()
    };
    match child {
        Some(child) => {
            child.kill().map_err(|e| e.to_string())?;
            Ok("gateway stopped".into())
        }
        None => Ok("gateway not running".into()),
    }
}

/// 停掉旧的再起(供下载完模型后,前端调用以让新 env 生效)。
#[tauri::command]
pub async fn restart_gateway(app: AppHandle) -> Result<String, String> {
    let _ = stop_gateway(app.clone()).await;
    start_gateway(app).await
}
