//! yts 桌面壳(Rust)。职责:窗口/壳 + 出口代理 + 管理 GGML 推理网关/Python sidecar。
//! 业务/编排在 Python(core);推理走本地 GGML 网关(desktop/infer-gateway),桌面壳不做推理。

mod egress;
mod sidecar;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            sidecar::start_sidecar,
            sidecar::stop_sidecar,
        ])
        .setup(|_app| {
            // TODO: 启动出口代理(egress)、按需起 GGML 网关 / Python sidecar(Mac 形态)
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running yts desktop");
}
