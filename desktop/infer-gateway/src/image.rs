//! 图像生成端点。启用时只执行启动期验证过的结构化 argv producer。

use axum::extract::State;
use axum::http::StatusCode;
use axum::Json;
use base64::Engine;
use image::ImageDecoder;
use serde::{Deserialize, Serialize};

use crate::GatewayState;

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

pub async fn gen_image(
    State(state): State<GatewayState>,
    Json(req): Json<ImageReq>,
) -> Result<Json<ImageResp>, (StatusCode, String)> {
    if !state.image.enabled() {
        return Err((
            StatusCode::SERVICE_UNAVAILABLE,
            "image generation is disabled".into(),
        ));
    }
    validate_request(&req).map_err(|error| (StatusCode::BAD_REQUEST, error))?;
    state
        .image
        .validate_image_request(req.width, req.height, req.steps)
        .map_err(|error| (StatusCode::BAD_REQUEST, format!("{error:#}")))?;
    let width = req.width.to_string();
    let height = req.height.to_string();
    let steps = req.steps.to_string();
    let output = state
        .producers
        .execute(
            &state.image,
            "image.png",
            &[
                ("prompt", req.prompt.as_str()),
                ("width", width.as_str()),
                ("height", height.as_str()),
                ("steps", steps.as_str()),
            ],
        )
        .await
        .map_err(|error| {
            (
                StatusCode::BAD_GATEWAY,
                format!("image producer failed: {error:#}"),
            )
        })?;
    validate_png(&output.bytes, req.width, req.height)
        .map_err(|error| (StatusCode::BAD_GATEWAY, error))?;
    let png_base64 = base64::engine::general_purpose::STANDARD.encode(&output.bytes);
    Ok(Json(ImageResp {
        png_base64,
        model: state.image.kind_name().into(),
        width: req.width,
        height: req.height,
    }))
}

fn validate_request(req: &ImageReq) -> Result<(), String> {
    if req.prompt.trim().is_empty() {
        return Err("prompt must not be empty".into());
    }
    if req.width == 0 || req.height == 0 {
        return Err("width and height must be greater than zero".into());
    }
    if req.steps == 0 {
        return Err("steps must be greater than zero".into());
    }
    Ok(())
}

fn validate_png(bytes: &[u8], expected_width: u32, expected_height: u32) -> Result<(), String> {
    let decoder = image::codecs::png::PngDecoder::new(std::io::Cursor::new(bytes))
        .map_err(|error| format!("image producer returned invalid PNG header: {error}"))?;
    let dimensions = decoder.dimensions();
    if dimensions != (expected_width, expected_height) {
        return Err(format!(
            "image producer returned {}x{} PNG, expected {expected_width}x{expected_height}",
            dimensions.0, dimensions.1
        ));
    }
    let decoded_size = usize::try_from(decoder.total_bytes())
        .map_err(|_| "decoded PNG size exceeds this platform's address space".to_string())?;
    let mut decoded = vec![0_u8; decoded_size];
    decoder
        .read_image(&mut decoded)
        .map_err(|error| format!("image producer returned invalid PNG data: {error}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use image::{ImageBuffer, ImageEncoder, Rgb};

    #[test]
    fn rejects_corrupt_png_output() {
        assert!(super::validate_png(b"not a png", 64, 64).is_err());
    }

    #[test]
    fn rejects_png_with_unrequested_dimensions() {
        let image = ImageBuffer::<Rgb<u8>, _>::new(32, 64);
        let mut bytes = Vec::new();
        image::codecs::png::PngEncoder::new(&mut bytes)
            .write_image(image.as_raw(), 32, 64, image::ExtendedColorType::Rgb8)
            .unwrap();

        assert!(super::validate_png(&bytes, 64, 64).is_err());
    }

    #[test]
    fn checks_png_header_dimensions_before_decoding_pixels() {
        let image = ImageBuffer::<Rgb<u8>, _>::new(32, 64);
        let mut bytes = Vec::new();
        image::codecs::png::PngEncoder::new(&mut bytes)
            .write_image(image.as_raw(), 32, 64, image::ExtendedColorType::Rgb8)
            .unwrap();
        let error = super::validate_png(&bytes, 64, 64).unwrap_err();

        assert!(error.contains("32x64"), "{error}");
    }
}
