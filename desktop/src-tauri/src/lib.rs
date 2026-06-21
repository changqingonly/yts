//! yts 桌面壳(Rust)。职责:窗口/壳 + Candle 推理(in-process) + 出口代理 + 管理 Python sidecar。
//! 业务/编排在 Python(core);此处只做原生能力与推理。

mod egress;
mod inference;
mod sidecar;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            inference::candle_info,
            inference::candle_generate_text,
            inference::candle_generate_image,
            inference::candle_generate_speech,
            inference::candle_generate_music,
            sidecar::start_sidecar,
            sidecar::stop_sidecar,
        ])
        .setup(|_app| {
            // TODO: 启动出口代理(egress)、按需起 Python sidecar(Mac 形态)
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running yts desktop");
}
