//! 管理 Python sidecar(Mac 形态)。sidecar = 复用云端 FastAPI app 的本地 profile 实例。
//! 经 tauri-plugin-shell 的 externalBin 拉起;Windows 形态(in-process DIY PyO3)留后。
//! 本轮 stub:给出拉起形状;生命周期(存 child / kill / PyInstaller 子进程回收)TODO。

use tauri::AppHandle;
use tauri_plugin_shell::ShellExt;

#[tauri::command]
pub async fn start_sidecar(app: AppHandle) -> Result<String, String> {
    let sidecar = app
        .shell()
        .sidecar("yts-sidecar")
        .map_err(|e| e.to_string())?
        .env("YTS_PROFILE", "local")
        .env("PYTHONUTF8", "1");
    let (_rx, _child) = sidecar.spawn().map_err(|e| e.to_string())?;
    // TODO: 把 _child 存入 app state 以便 stop;消费 _rx 转发日志
    Ok("sidecar started (stub: lifecycle TODO)".into())
}

#[tauri::command]
pub async fn stop_sidecar() -> Result<String, String> {
    // TODO: 从 state 取 child 并 kill(注意 PyInstaller 子进程回收;Mac onefile 无 Win AV 问题)
    Ok("sidecar stop (stub)".into())
}
