//! 图像生成端点(方案与音乐 producer 对称)。
//!
//! POST /image {prompt,width,height,steps} → {png_base64,model,width,height}。
//! Producer 两档(env YTS_IMAGEGEN_CMD 决定):
//!  - 未设置:内置占位 PNG(随 prompt 变色的渐变),无依赖端到端验证用。
//!  - 已设置:spawn 外部 producer(**stable-diffusion.cpp / leejet,GGML/Metal,GGUF FLUX/Qwen/SD3.5**)。
//!    命令含占位 {prompt} {out} {width} {height} {steps},producer 把 PNG 写到 {out},退出码 0。
//!    server 读 PNG → base64 返回。图像非流式:一次 request/response(几秒~几十秒)。
//!
//! 与前端/契约:候选真模型见 scripts/build_sdcpp.sh;切模型只改 YTS_IMAGEGEN_CMD,端点/前端零改动。

use std::process::Stdio;

use axum::http::StatusCode;
use axum::Json;
use base64::Engine;
use serde::{Deserialize, Serialize};
use tokio::io::AsyncReadExt;

#[derive(Deserialize)]
pub struct ImageReq {
    prompt: String,
    #[serde(default = "default_dim")]
    width: u32,
    #[serde(default = "default_dim")]
    height: u32,
    #[serde(default = "default_steps")]
    steps: u32,
}
fn default_dim() -> u32 {
    512
}
fn default_steps() -> u32 {
    20
}

#[derive(Serialize)]
pub struct ImageResp {
    png_base64: String,
    model: String,
    width: u32,
    height: u32,
}

pub async fn gen_image(Json(req): Json<ImageReq>) -> Result<Json<ImageResp>, (StatusCode, String)> {
    let (png, model) = produce_png(&req)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e))?;
    let b64 = base64::engine::general_purpose::STANDARD.encode(&png);
    Ok(Json(ImageResp { png_base64: b64, model, width: req.width, height: req.height }))
}

/// 产出 PNG 字节 + 模型名。有 YTS_IMAGEGEN_CMD 走外部,否则内置占位。
async fn produce_png(req: &ImageReq) -> Result<(Vec<u8>, String), String> {
    match std::env::var("YTS_IMAGEGEN_CMD") {
        Ok(cmd) if !cmd.trim().is_empty() => spawn_external(&cmd, req).await,
        _ => Err("YTS_IMAGEGEN_CMD is required for local image generation".into()),
    }
}

/// spawn stable-diffusion.cpp 等。约定占位 {prompt} {out} {width} {height} {steps}。
async fn spawn_external(cmd_tmpl: &str, req: &ImageReq) -> Result<(Vec<u8>, String), String> {
    let out_path = std::env::temp_dir().join(format!("yts-imagegen-{}.png", std::process::id()));
    let out_str = out_path.to_string_lossy().to_string();
    let filled = cmd_tmpl
        .replace("{prompt}", &req.prompt)
        .replace("{out}", &out_str)
        .replace("{width}", &req.width.to_string())
        .replace("{height}", &req.height.to_string())
        .replace("{steps}", &req.steps.to_string());

    let mut child = tokio::process::Command::new("sh")
        .arg("-c")
        .arg(&filled)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("spawn imagegen failed: {e}"))?;
    let status = child.wait().await.map_err(|e| format!("imagegen wait failed: {e}"))?;
    if !status.success() {
        let mut err = String::new();
        if let Some(mut s) = child.stderr.take() {
            let _ = s.read_to_string(&mut err).await;
        }
        return Err(format!("imagegen exited {status}: {}", err.trim()));
    }
    let png = std::fs::read(&out_path).map_err(|e| format!("read png: {e}"))?;
    let _ = std::fs::remove_file(&out_path);
    if png.is_empty() {
        return Err("imagegen produced empty png".into());
    }
    Ok((png, "sd.cpp".into()))
}
