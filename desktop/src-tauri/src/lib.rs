//! yts 桌面壳(Rust)。职责:窗口/壳 + 出口代理 + 管理 GGML 推理网关/Python sidecar。
//! 业务/编排在 Python(core);推理走本地 GGML 网关(desktop/infer-gateway),桌面壳不做推理。

mod acestep;
mod egress;
mod gateway;
mod keychain;
mod models;
mod sidecar;
mod vault;

use tauri::{
    menu::{Menu, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
};

const TRAY_ID: &str = "yts-menu-bar";
const OPEN_MENU_ID: &str = "open-yts";
const QUIT_MENU_ID: &str = "quit-yts";

fn show_main_window(app_handle: &tauri::AppHandle) -> tauri::Result<()> {
    let window = app_handle
        .get_webview_window("main")
        .ok_or(tauri::Error::WindowNotFound)?;
    window.show()?;
    window.unminimize()?;
    window.set_focus()?;
    Ok(())
}

/// 打包态由 Finder/LaunchServices 拉起时没有终端,stdout/stderr 不可见;子进程日志与本壳自身
/// 的诊断信息统一落盘到 app_log_dir()/yts-desktop.log,而不是 println!/eprintln!。
pub fn log_line(app: &tauri::AppHandle, line: &str) {
    let Ok(dir) = app.path().app_log_dir() else {
        return;
    };
    if std::fs::create_dir_all(&dir).is_err() {
        return;
    }
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("yts-desktop.log"))
    {
        use std::io::Write;
        let _ = writeln!(file, "{line}");
    }
}

/// 退出时把两个子进程(sidecar/gateway)一并杀掉;std::process 子进程不会随父进程退出自动回收
/// (macOS 无 PDEATHSIG),必须显式 kill,否则残留成孤儿进程。
fn kill_children(app: &tauri::AppHandle) {
    if let Ok(mut guard) = app.state::<sidecar::SidecarState>().0.lock() {
        if let Some(child) = guard.take() {
            let _ = child.kill();
        }
    }
    if let Ok(mut guard) = app.state::<gateway::GatewayState>().0.lock() {
        if let Some(child) = guard.take() {
            let _ = child.kill();
        }
    }
    // yts-sidecar 是 PyInstaller onefile:kill 掉的 bootloader 进程可能已 fork/exec 出真正跑
    // uvicorn 的子进程,该子进程不共享同一 pid,不会被上面的 child.kill() 连带杀掉,会变成孤儿。
    // 按本应用包内该二进制的确切绝对路径兜底清理,避免误杀同名但无关的进程。
    if let Ok(exe) = std::env::current_exe() {
        if let Some(macos_dir) = exe.parent() {
            let sidecar_path = macos_dir.join("yts-sidecar");
            let _ = std::process::Command::new("pkill")
                .arg("-9")
                .arg("-f")
                .arg(sidecar_path.as_os_str())
                .status();
        }
    }
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(sidecar::SidecarState::default())
        .manage(gateway::GatewayState::default())
        .invoke_handler(tauri::generate_handler![
            sidecar::start_sidecar,
            sidecar::stop_sidecar,
            gateway::start_gateway,
            gateway::stop_gateway,
            gateway::restart_gateway,
            models::check_local_models,
            models::download_local_models,
            acestep::check_acestep,
            acestep::build_acestep,
            keychain::keychain_load,
            keychain::keychain_store,
            keychain::keychain_clear,
            vault::vault_exists,
            vault::vault_store,
            vault::vault_unlock,
            vault::vault_clear,
        ])
        .setup(|app| {
            let open = MenuItemBuilder::with_id(OPEN_MENU_ID, "打开乐兔").build(app)?;
            let quit = MenuItemBuilder::with_id(QUIT_MENU_ID, "退出").build(app)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            let icon =
                tauri::image::Image::from_bytes(include_bytes!("../icons/tray-template.png"))
                    .expect("failed to decode the macOS menu bar icon");

            let tray = TrayIconBuilder::with_id(TRAY_ID)
                .icon(icon)
                .icon_as_template(true)
                .tooltip("乐兔")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_tray_icon_event(|tray, event| {
                    if matches!(
                        event,
                        TrayIconEvent::Click {
                            button: MouseButton::Left,
                            button_state: MouseButtonState::Up,
                            ..
                        }
                    ) {
                        show_main_window(tray.app_handle())
                            .expect("failed to show main window from menu bar");
                    }
                })
                .on_menu_event(|app_handle, event| match event.id().as_ref() {
                    OPEN_MENU_ID => show_main_window(app_handle)
                        .expect("failed to show main window from menu item"),
                    QUIT_MENU_ID => app_handle.exit(0),
                    _ => {}
                })
                .build(app)?;
            let tray_rect = tray.rect().expect("menu bar item has no screen rectangle");
            log_line(
                app.handle(),
                &format!("[desktop] menu bar item created rect={tray_rect:?}"),
            );

            // 不在这里自动拉起 sidecar/gateway:两者启动耗时(尤其 PyInstaller onefile 解压)
            // 会拖慢窗口首次可见时间。改为惰性——前端只在真正用到本地目标时(见
            // stores/environment.js 的 checkHealth)才调 start_sidecar/start_gateway,
            // 两个命令本身已是幂等的(见 sidecar.rs/gateway.rs),重复调用安全。
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    window.hide().expect("failed to hide main window");
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building yts desktop");

    app.run(|app_handle, event| match event {
        tauri::RunEvent::Reopen {
            has_visible_windows,
            ..
        } => {
            if !has_visible_windows {
                show_main_window(app_handle).expect("failed to show main window from Dock");
            }
        }
        tauri::RunEvent::Exit => kill_children(app_handle),
        _ => {}
    });
}

#[cfg(test)]
mod tests {
    #[test]
    fn menu_bar_template_has_transparent_background_and_visible_mark() {
        let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/tray-template.png"))
            .expect("failed to decode menu bar template");
        let mut alpha = icon.rgba().iter().skip(3).step_by(4).copied();

        assert!(alpha.clone().any(|value| value == 0));
        assert!(alpha.any(|value| value > 0));
    }
}
