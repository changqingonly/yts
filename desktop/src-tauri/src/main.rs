// 防止 Windows release 弹控制台(本轮 Mac-first,保留惯例)
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    yts_desktop_lib::run()
}
