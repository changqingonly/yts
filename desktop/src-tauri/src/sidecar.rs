//! 管理 Python sidecar(Mac 形态)。sidecar = 复用云端 FastAPI app 的本地 profile 实例。
//! 经 tauri-plugin-shell 的 externalBin 拉起;Windows 形态(in-process DIY PyO3)留后。

use std::sync::Mutex;

use tauri::{AppHandle, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Default)]
pub struct SidecarState(pub Mutex<Option<CommandChild>>);

#[tauri::command]
pub async fn start_sidecar(app: AppHandle) -> Result<String, String> {
    {
        let state = app.state::<SidecarState>();
        let guard = state.0.lock().map_err(|e| e.to_string())?;
        if guard.is_some() {
            return Ok("sidecar already running".into());
        }
    }
    // Finder/LaunchServices 拉起时进程 cwd 默认是只读的 `/`;yts_server 建 run/、public/ 等
    // 相对路径目录会失败。给 sidecar 一个稳定可写的 cwd(app_data_dir()),而不是继承壳的 cwd。
    let work_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&work_dir).map_err(|e| e.to_string())?;
    let sidecar = app
        .shell()
        .sidecar("yts-sidecar")
        .map_err(|e| e.to_string())?
        .current_dir(work_dir)
        .env("YTS_PROFILE", "local")
        .env("PYTHONUTF8", "1");
    let (mut rx, child) = sidecar.spawn().map_err(|e| e.to_string())?;
    {
        let state = app.state::<SidecarState>();
        let mut guard = state.0.lock().map_err(|e| e.to_string())?;
        *guard = Some(child);
    }
    let log_app = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    crate::log_line(&log_app, &format!("[yts-sidecar] {}", String::from_utf8_lossy(&line)));
                }
                CommandEvent::Stderr(line) => {
                    crate::log_line(&log_app, &format!("[yts-sidecar] {}", String::from_utf8_lossy(&line)));
                }
                CommandEvent::Terminated(payload) => {
                    crate::log_line(&log_app, &format!("[yts-sidecar] terminated: {payload:?}"));
                }
                CommandEvent::Error(err) => {
                    crate::log_line(&log_app, &format!("[yts-sidecar] error: {err}"));
                }
                _ => {}
            }
        }
    });
    Ok("sidecar started".into())
}

#[tauri::command]
pub async fn stop_sidecar(app: AppHandle) -> Result<String, String> {
    let child = {
        let state = app.state::<SidecarState>();
        let mut guard = state.0.lock().map_err(|e| e.to_string())?;
        guard.take()
    };
    match child {
        Some(child) => {
            child.kill().map_err(|e| e.to_string())?;
            Ok("sidecar stopped".into())
        }
        None => Ok("sidecar not running".into()),
    }
}
