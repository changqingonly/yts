//! 管理完整本地 runtime。sidecar = 复用云端 FastAPI app 的本地 profile 实例。
//! 组件进程、推理网关、Python sidecar 均由 ComponentSupervisor 统一持有。

use std::sync::Mutex;

use crate::component_supervisor::{development_repo_root, ComponentSupervisor, ShellLauncher};
use tauri::{AppHandle, State};

#[tauri::command]
pub async fn start_sidecar(
    app: AppHandle,
    supervisor: State<'_, Mutex<ComponentSupervisor>>,
) -> Result<String, String> {
    let root = development_repo_root();
    let config_dir = root.join("conf");
    let runtime_dir = root.join("run");
    let mut launcher = ShellLauncher::new(app);
    let mut supervisor = supervisor
        .lock()
        .map_err(|_| "component supervisor mutex poisoned".to_string())?;
    supervisor
        .start(&root, &config_dir, &runtime_dir, &mut launcher)
        .map_err(|error| error.to_string())?;
    Ok("local runtime started".into())
}

#[tauri::command]
pub async fn stop_sidecar(
    supervisor: State<'_, Mutex<ComponentSupervisor>>,
) -> Result<String, String> {
    let mut supervisor = supervisor
        .lock()
        .map_err(|_| "component supervisor mutex poisoned".to_string())?;
    let killed = supervisor.stop().map_err(|error| error.to_string())?;
    Ok(format!("local runtime stopped: {}", killed.join(", ")))
}
