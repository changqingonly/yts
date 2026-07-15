//! yts 桌面壳(Rust)。职责:窗口/壳 + 出口代理 + 管理 GGML 推理网关/Python sidecar。
//! 业务/编排在 Python(core);推理走本地 GGML 网关(desktop/infer-gateway),桌面壳不做推理。

use std::sync::Mutex;

pub mod component_supervisor;
mod egress;
mod sidecar;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Mutex::new(
            component_supervisor::ComponentSupervisor::for_development(),
        ))
        .invoke_handler(tauri::generate_handler![
            sidecar::start_sidecar,
            sidecar::stop_sidecar,
        ])
        .setup(|_app| {
            #[cfg(not(debug_assertions))]
            {
                let root = component_supervisor::development_repo_root();
                let config_dir = root.join("conf");
                let runtime_dir = root.join("run");
                let mut launcher = component_supervisor::ShellLauncher::new(_app.handle().clone());
                let state = _app.state::<Mutex<component_supervisor::ComponentSupervisor>>();
                let mut supervisor = state.lock().map_err(|_| {
                    std::io::Error::new(
                        std::io::ErrorKind::Other,
                        "component supervisor mutex poisoned",
                    )
                })?;
                supervisor
                    .start(&root, &config_dir, &runtime_dir, &mut launcher)
                    .map_err(|error| std::io::Error::new(std::io::ErrorKind::Other, error))?;
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running yts desktop");
}
