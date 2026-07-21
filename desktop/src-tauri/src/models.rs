//! 首次运行的本地模型/GGML 二进制下载。从上游 GitHub Releases 拉预编译的 macOS(arm64)
//! llama.cpp / stable-diffusion.cpp,从 HuggingFace 拉同一批 GGUF 权重 —— 仓库名/文件名与
//! scripts/build_llamacpp.sh、scripts/build_sdcpp.sh 保持一致,只是终端用户不需要装
//! cmake/Xcode 工具链自己编译,改为下载预编译产物,存到 app_data_dir()/vendor/ 下。

use serde::Serialize;
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Emitter, Manager};

const LLAMA_RELEASE_REPO: &str = "ggml-org/llama.cpp";
const LLAMA_ASSET_SUFFIX: &str = "bin-macos-arm64.tar.gz";
const LLAMA_MODEL_REPO: &str = "bartowski/Qwen2.5-7B-Instruct-GGUF";
const LLAMA_MODEL_FILE: &str = "Qwen2.5-7B-Instruct-Q4_K_M.gguf";
const LLAMA_CTX: &str = "4096";
const LLAMA_PORT: &str = "18080";
const LLAMA_GPU_LAYERS: &str = "99";

const SD_RELEASE_REPO: &str = "leejet/stable-diffusion.cpp";
const SD_MODEL_REPO: &str = "Green-Sky/flux.1-schnell-GGUF";
const SD_DIFFUSION_MODEL: &str = "flux1-schnell-q4_k.gguf";
const SD_VAE: &str = "ae-f16.gguf";
const SD_CLIP_L: &str = "clip_l-q8_0.gguf";
const SD_T5XXL: &str = "t5xxl_q4_k.gguf";
const SD_MODEL_FILES: [&str; 4] = [SD_DIFFUSION_MODEL, SD_VAE, SD_CLIP_L, SD_T5XXL];

pub(crate) fn exists_nonempty(p: &Path) -> bool {
    std::fs::metadata(p).map(|m| m.len() > 0).unwrap_or(false)
}

/// app_data_dir()/vendor/... 下的本地二进制/权重布局(镜像 desktop/vendor/ 的开发布局)。
#[derive(Clone)]
pub struct LocalPaths {
    root: PathBuf,
}

impl LocalPaths {
    pub fn new(app: &AppHandle) -> Result<Self, String> {
        let root = app
            .path()
            .app_data_dir()
            .map_err(|e| e.to_string())?
            .join("vendor");
        Ok(Self { root })
    }

    fn llama_bin_dir(&self) -> PathBuf {
        self.root.join("llama-bin")
    }
    pub fn llama_server(&self) -> PathBuf {
        self.llama_bin_dir().join("llama-server")
    }
    fn llm_models_dir(&self) -> PathBuf {
        self.root.join("llm-models")
    }
    pub fn llama_model(&self) -> PathBuf {
        self.llm_models_dir().join(LLAMA_MODEL_FILE)
    }
    fn sd_bin_dir(&self) -> PathBuf {
        self.root.join("sd-bin")
    }
    pub fn sd_binary(&self) -> PathBuf {
        self.sd_bin_dir().join("sd")
    }
    fn sd_models_dir(&self) -> PathBuf {
        self.root.join("sd-models")
    }

    pub fn ready(&self) -> bool {
        exists_nonempty(&self.llama_server())
            && exists_nonempty(&self.llama_model())
            && exists_nonempty(&self.sd_binary())
            && SD_MODEL_FILES
                .iter()
                .all(|f| exists_nonempty(&self.sd_models_dir().join(f)))
    }

    /// 拼装 YTS_LLAMA_CMD,约定见 scripts/dev_gateway.sh。二进制/权重任一缺失则 None。
    pub fn llama_cmd(&self) -> Option<String> {
        if !exists_nonempty(&self.llama_server()) || !exists_nonempty(&self.llama_model()) {
            return None;
        }
        Some(format!(
            "{} -m {} --host 127.0.0.1 --port {LLAMA_PORT} -c {LLAMA_CTX} -ngl {LLAMA_GPU_LAYERS} --log-disable",
            self.llama_server().display(),
            self.llama_model().display(),
        ))
    }

    pub fn llama_base_url(&self) -> String {
        format!("http://127.0.0.1:{LLAMA_PORT}")
    }

    /// 拼装 YTS_IMAGEGEN_CMD,约定见 scripts/dev_gateway.sh / infer-gateway/src/image.rs。
    pub fn imagegen_cmd(&self) -> Option<String> {
        if !exists_nonempty(&self.sd_binary()) {
            return None;
        }
        let models = self.sd_models_dir();
        if !SD_MODEL_FILES.iter().all(|f| exists_nonempty(&models.join(f))) {
            return None;
        }
        Some(format!(
            "{} --diffusion-model {} --vae {} --clip_l {} --t5xxl {} -p {{prompt}} -o {{out}} -W {{width}} -H {{height}} --steps 4 --cfg-scale 1.0 --sampling-method euler",
            self.sd_binary().display(),
            models.join(SD_DIFFUSION_MODEL).display(),
            models.join(SD_VAE).display(),
            models.join(SD_CLIP_L).display(),
            models.join(SD_T5XXL).display(),
        ))
    }
}

#[derive(Serialize, Clone)]
pub struct ModelsStatus {
    pub llama_binary: bool,
    pub llama_model: bool,
    pub sd_binary: bool,
    pub sd_model: bool,
    pub ready: bool,
}

#[tauri::command]
pub async fn check_local_models(app: AppHandle) -> Result<ModelsStatus, String> {
    let paths = LocalPaths::new(&app)?;
    let sd_model = SD_MODEL_FILES
        .iter()
        .all(|f| exists_nonempty(&paths.sd_models_dir().join(f)));
    Ok(ModelsStatus {
        llama_binary: exists_nonempty(&paths.llama_server()),
        llama_model: exists_nonempty(&paths.llama_model()),
        sd_binary: exists_nonempty(&paths.sd_binary()),
        sd_model,
        ready: paths.ready(),
    })
}

#[derive(Serialize, Clone)]
pub struct DownloadProgress {
    pub stage: String,
    pub file: String,
    pub downloaded: u64,
    pub total: u64,
    pub done: bool,
    pub error: Option<String>,
}

pub(crate) fn emit_progress(
    app: &AppHandle,
    stage: &str,
    file: &str,
    downloaded: u64,
    total: u64,
    done: bool,
    error: Option<String>,
) {
    let _ = app.emit(
        "model-download-progress",
        DownloadProgress {
            stage: stage.into(),
            file: file.into(),
            downloaded,
            total,
            done,
            error,
        },
    );
}

#[tauri::command]
pub async fn download_local_models(app: AppHandle) -> Result<ModelsStatus, String> {
    let paths = LocalPaths::new(&app)?;
    let client = reqwest::Client::new();
    if let Err(e) = download_all(&app, &client, &paths).await {
        emit_progress(&app, "error", "", 0, 0, true, Some(e.clone()));
        return Err(e);
    }
    emit_progress(&app, "done", "", 0, 0, true, None);
    check_local_models(app).await
}

async fn download_all(
    app: &AppHandle,
    client: &reqwest::Client,
    paths: &LocalPaths,
) -> Result<(), String> {
    // 1) llama-server 预编译二进制(macOS arm64)
    if !exists_nonempty(&paths.llama_server()) {
        let asset_url = latest_release_asset_url(client, LLAMA_RELEASE_REPO, |n| {
            n.ends_with(LLAMA_ASSET_SUFFIX)
        })
        .await?;
        let archive = paths.llama_bin_dir().join("llama-macos-arm64.tar.gz");
        download_file(
            app,
            client,
            &asset_url,
            &archive,
            "llama-binary",
            "llama.cpp (macOS arm64)",
        )
        .await?;
        let extract_dir = paths.llama_bin_dir().join("_extract");
        extract_tar_gz(&archive, &extract_dir).await?;
        let found = find_file_recursive(&extract_dir, "llama-server", 6)
            .ok_or_else(|| "llama-server binary not found in downloaded archive".to_string())?;
        std::fs::copy(&found, paths.llama_server()).map_err(|e| e.to_string())?;
        make_executable(&paths.llama_server())?;
        let _ = std::fs::remove_dir_all(&extract_dir);
        let _ = std::fs::remove_file(&archive);
    }

    // 2) LLM 权重(HuggingFace,与 build_llamacpp.sh 一致)
    let llm_url =
        format!("https://huggingface.co/{LLAMA_MODEL_REPO}/resolve/main/{LLAMA_MODEL_FILE}?download=true");
    download_file(app, client, &llm_url, &paths.llama_model(), "llama-model", LLAMA_MODEL_FILE)
        .await?;

    // 3) sd 预编译二进制(macOS arm64)
    if !exists_nonempty(&paths.sd_binary()) {
        let asset_url = latest_release_asset_url(client, SD_RELEASE_REPO, |n| {
            n.contains("Darwin-macOS") && n.contains("arm64") && n.ends_with(".zip")
        })
        .await?;
        let archive = paths.sd_bin_dir().join("sd-macos-arm64.zip");
        download_file(
            app,
            client,
            &asset_url,
            &archive,
            "sd-binary",
            "stable-diffusion.cpp (macOS arm64)",
        )
        .await?;
        let extract_dir = paths.sd_bin_dir().join("_extract");
        extract_zip(&archive, &extract_dir).await?;
        let found = find_file_recursive(&extract_dir, "sd", 6)
            .ok_or_else(|| "sd binary not found in downloaded archive".to_string())?;
        std::fs::copy(&found, paths.sd_binary()).map_err(|e| e.to_string())?;
        make_executable(&paths.sd_binary())?;
        let _ = std::fs::remove_dir_all(&extract_dir);
        let _ = std::fs::remove_file(&archive);
    }

    // 4) SD 权重(HuggingFace,与 build_sdcpp.sh 一致)
    for f in SD_MODEL_FILES {
        let url = format!("https://huggingface.co/{SD_MODEL_REPO}/resolve/main/{f}?download=true");
        download_file(app, client, &url, &paths.sd_models_dir().join(f), "sd-model", f).await?;
    }

    Ok(())
}

async fn latest_release_asset_url(
    client: &reqwest::Client,
    repo: &str,
    matches: impl Fn(&str) -> bool,
) -> Result<String, String> {
    let url = format!("https://api.github.com/repos/{repo}/releases/latest");
    let resp = client
        .get(&url)
        .header("User-Agent", "yts-desktop")
        .send()
        .await
        .map_err(|e| format!("github release lookup failed: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("github release lookup {url} -> {}", resp.status()));
    }
    let json: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
    let assets = json["assets"].as_array().ok_or("no assets in release")?;
    for asset in assets {
        if let Some(name) = asset["name"].as_str() {
            if matches(name) {
                if let Some(dl) = asset["browser_download_url"].as_str() {
                    return Ok(dl.to_string());
                }
            }
        }
    }
    Err(format!("no matching asset found in {repo} latest release"))
}

pub(crate) async fn download_file(
    app: &AppHandle,
    client: &reqwest::Client,
    url: &str,
    dest: &Path,
    stage: &str,
    label: &str,
) -> Result<(), String> {
    if exists_nonempty(dest) {
        emit_progress(app, stage, label, 1, 1, true, None);
        return Ok(());
    }
    if let Some(parent) = dest.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let mut resp = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("download {label} failed: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("download {label} -> {}", resp.status()));
    }
    let total = resp.content_length().unwrap_or(0);
    let tmp = dest.with_extension("part");
    let mut file = std::fs::File::create(&tmp).map_err(|e| e.to_string())?;
    let mut downloaded: u64 = 0;
    let mut last_emit: u64 = 0;
    use std::io::Write;
    while let Some(chunk) = resp
        .chunk()
        .await
        .map_err(|e| format!("read chunk {label}: {e}"))?
    {
        file.write_all(&chunk).map_err(|e| e.to_string())?;
        downloaded += chunk.len() as u64;
        if downloaded - last_emit > 2 * 1024 * 1024 {
            emit_progress(app, stage, label, downloaded, total, false, None);
            last_emit = downloaded;
        }
    }
    drop(file);
    std::fs::rename(&tmp, dest).map_err(|e| e.to_string())?;
    emit_progress(app, stage, label, downloaded, total.max(downloaded), true, None);
    Ok(())
}

async fn extract_tar_gz(archive: &Path, dest_dir: &Path) -> Result<(), String> {
    std::fs::create_dir_all(dest_dir).map_err(|e| e.to_string())?;
    let status = tokio::process::Command::new("tar")
        .arg("-xzf")
        .arg(archive)
        .arg("-C")
        .arg(dest_dir)
        .status()
        .await
        .map_err(|e| format!("tar spawn failed: {e}"))?;
    if !status.success() {
        return Err(format!("tar extract failed: {status}"));
    }
    Ok(())
}

async fn extract_zip(archive: &Path, dest_dir: &Path) -> Result<(), String> {
    std::fs::create_dir_all(dest_dir).map_err(|e| e.to_string())?;
    let status = tokio::process::Command::new("unzip")
        .arg("-o")
        .arg(archive)
        .arg("-d")
        .arg(dest_dir)
        .status()
        .await
        .map_err(|e| format!("unzip spawn failed: {e}"))?;
    if !status.success() {
        return Err(format!("unzip extract failed: {status}"));
    }
    Ok(())
}

pub(crate) fn find_file_recursive(dir: &Path, name: &str, max_depth: usize) -> Option<PathBuf> {
    if max_depth == 0 {
        return None;
    }
    let entries = std::fs::read_dir(dir).ok()?;
    let mut subdirs = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            subdirs.push(path);
        } else if path.file_name().map(|n| n == name).unwrap_or(false) {
            return Some(path);
        }
    }
    for sub in subdirs {
        if let Some(found) = find_file_recursive(&sub, name, max_depth - 1) {
            return Some(found);
        }
    }
    None
}

pub(crate) fn make_executable(path: &Path) -> Result<(), String> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = std::fs::metadata(path).map_err(|e| e.to_string())?.permissions();
        perms.set_mode(0o755);
        std::fs::set_permissions(path, perms).map_err(|e| e.to_string())?;
    }
    #[cfg(not(unix))]
    {
        let _ = path;
    }
    Ok(())
}
