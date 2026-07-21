//! 打包态首次运行:acestep.cpp(音乐生成)上游无预编译产物(无 GitHub releases/tags),
//! 只能源码构建 —— 检测 git/cmake/cc 工具链是否齐全,`git clone --recurse-submodules` +
//! `./buildcpu.sh`(仓库 README:macOS 上该脚本也会自动启用 Metal + Accelerate),
//! 下载默认 GGUF 权重组(HuggingFace,每类型各一个,取最快档),生成两阶段
//! (ace-lm 生成词+codes → ace-synth 渲染音频)CLI 包装脚本以满足 stream.rs 的单命令
//! YTS_AUDIOGEN_CMD 契约。工具链缺失时明确报错;不影响文本/图片两档(各自独立可用)。

use serde::Serialize;
use std::path::PathBuf;
use tauri::{AppHandle, Manager};

use crate::models::{
    download_file, emit_progress, exists_nonempty, find_file_recursive, make_executable,
};

const ACESTEP_REPO_URL: &str = "https://github.com/ServeurpersoCom/acestep.cpp.git";
const ACESTEP_MODEL_REPO: &str = "Serveurperso/ACE-Step-1.5-GGUF";
// 每类型各取一个「快」档:0.6B LM + 0.6B 文本编码器 + turbo(8 步)DiT + VAE。
const LM_MODEL: &str = "acestep-5Hz-lm-0.6B-Q8_0.gguf";
const TEXT_ENCODER_MODEL: &str = "Qwen3-Embedding-0.6B-Q8_0.gguf";
const DIT_MODEL: &str = "acestep-v15-turbo-Q8_0.gguf";
const VAE_MODEL: &str = "vae-BF16.gguf";
const ACESTEP_MODEL_FILES: [&str; 4] = [LM_MODEL, TEXT_ENCODER_MODEL, DIT_MODEL, VAE_MODEL];

pub struct AcestepPaths {
    root: PathBuf,
}

impl AcestepPaths {
    pub fn new(app: &AppHandle) -> Result<Self, String> {
        let root = app
            .path()
            .app_data_dir()
            .map_err(|e| e.to_string())?
            .join("vendor");
        Ok(Self { root })
    }

    fn src_dir(&self) -> PathBuf {
        self.root.join("acestep-src")
    }
    fn bin_dir(&self) -> PathBuf {
        self.root.join("acestep-bin")
    }
    fn models_dir(&self) -> PathBuf {
        self.root.join("acestep-models")
    }
    fn ace_lm(&self) -> PathBuf {
        self.bin_dir().join("ace-lm")
    }
    fn ace_synth(&self) -> PathBuf {
        self.bin_dir().join("ace-synth")
    }
    fn produce_script(&self) -> PathBuf {
        self.bin_dir().join("produce.sh")
    }

    fn models_ready(&self) -> bool {
        ACESTEP_MODEL_FILES
            .iter()
            .all(|f| exists_nonempty(&self.models_dir().join(f)))
    }

    pub fn ready(&self) -> bool {
        exists_nonempty(&self.ace_lm())
            && exists_nonempty(&self.ace_synth())
            && exists_nonempty(&self.produce_script())
            && self.models_ready()
    }

    /// 拼装 YTS_AUDIOGEN_CMD,约定见 infer-gateway/src/stream.rs
    /// (sh -c 解析,{prompt}/{seconds}/{out} 占位替换)。
    pub fn audiogen_cmd(&self) -> Option<String> {
        if !self.ready() {
            return None;
        }
        Some(format!("{} '{{prompt}}' {{seconds}} {{out}}", self.produce_script().display()))
    }
}

#[derive(Serialize, Clone)]
pub struct AcestepStatus {
    pub toolchain_available: bool,
    pub binaries: bool,
    pub models: bool,
    pub ready: bool,
}

async fn toolchain_available() -> bool {
    for bin in ["git", "cmake", "cc"] {
        let ok = tokio::process::Command::new("which")
            .arg(bin)
            .status()
            .await
            .map(|s| s.success())
            .unwrap_or(false);
        if !ok {
            return false;
        }
    }
    true
}

#[tauri::command]
pub async fn check_acestep(app: AppHandle) -> Result<AcestepStatus, String> {
    let paths = AcestepPaths::new(&app)?;
    Ok(AcestepStatus {
        toolchain_available: toolchain_available().await,
        binaries: exists_nonempty(&paths.ace_lm()) && exists_nonempty(&paths.ace_synth()),
        models: paths.models_ready(),
        ready: paths.ready(),
    })
}

#[tauri::command]
pub async fn build_acestep(app: AppHandle) -> Result<AcestepStatus, String> {
    let paths = AcestepPaths::new(&app)?;
    if let Err(e) = build_all(&app, &paths).await {
        emit_progress(&app, "acestep-error", "", 0, 0, true, Some(e.clone()));
        return Err(e);
    }
    emit_progress(&app, "acestep-done", "", 0, 0, true, None);
    check_acestep(app).await
}

async fn build_all(app: &AppHandle, paths: &AcestepPaths) -> Result<(), String> {
    if !toolchain_available().await {
        return Err(
            "缺少 git/cmake/cc 工具链;请先安装 Xcode Command Line Tools \
             (终端执行 xcode-select --install)后重试"
                .into(),
        );
    }

    // 1) 源码构建(上游无预编译产物;clone --recurse-submodules + buildcpu.sh)
    if !exists_nonempty(&paths.ace_lm()) || !exists_nonempty(&paths.ace_synth()) {
        let src = paths.src_dir();
        if !src.join(".git").exists() {
            emit_progress(app, "acestep-clone", "acestep.cpp", 0, 0, false, None);
            std::fs::create_dir_all(&paths.root).map_err(|e| e.to_string())?;
            let status = tokio::process::Command::new("git")
                .args(["clone", "--recurse-submodules", ACESTEP_REPO_URL])
                .arg(&src)
                .status()
                .await
                .map_err(|e| format!("git clone failed: {e}"))?;
            if !status.success() {
                return Err(format!("git clone acestep.cpp failed: {status}"));
            }
            emit_progress(app, "acestep-clone", "acestep.cpp", 1, 1, true, None);
        }

        emit_progress(app, "acestep-build", "acestep.cpp (cmake, 数分钟)", 0, 0, false, None);
        let status = tokio::process::Command::new("sh")
            .arg("buildcpu.sh")
            .current_dir(&src)
            .status()
            .await
            .map_err(|e| format!("acestep.cpp build spawn failed: {e}"))?;
        if !status.success() {
            return Err(format!("acestep.cpp build failed: {status}"));
        }
        emit_progress(app, "acestep-build", "acestep.cpp (cmake, 数分钟)", 1, 1, true, None);

        let build_dir = src.join("build");
        let lm = find_file_recursive(&build_dir, "ace-lm", 3)
            .ok_or_else(|| "ace-lm binary not found after build".to_string())?;
        let synth = find_file_recursive(&build_dir, "ace-synth", 3)
            .ok_or_else(|| "ace-synth binary not found after build".to_string())?;
        std::fs::create_dir_all(paths.bin_dir()).map_err(|e| e.to_string())?;
        std::fs::copy(&lm, paths.ace_lm()).map_err(|e| e.to_string())?;
        std::fs::copy(&synth, paths.ace_synth()).map_err(|e| e.to_string())?;
        make_executable(&paths.ace_lm())?;
        make_executable(&paths.ace_synth())?;
    }

    // 2) 默认权重组(HuggingFace,与仓库 README 推荐的最快组合一致)
    let client = reqwest::Client::new();
    for f in ACESTEP_MODEL_FILES {
        let url = format!("https://huggingface.co/{ACESTEP_MODEL_REPO}/resolve/main/{f}?download=true");
        download_file(app, &client, &url, &paths.models_dir().join(f), "acestep-model", f).await?;
    }

    // 3) 两阶段(ace-lm → ace-synth)CLI 包装脚本,填平 stream.rs 的单命令契约
    write_produce_script(paths)?;

    Ok(())
}

/// 生成 produce.sh:ace-lm(caption→codes)→ ace-synth(codes→wav)两阶段包装,
/// 命名约定见 docs/ARCHITECTURE.md(<stem>.json → <stem>0.json → <stem>00.<ext>)。
fn write_produce_script(paths: &AcestepPaths) -> Result<(), String> {
    let script = format!(
        r#"#!/bin/sh
set -eu
PROMPT="$1"; DURATION="$2"; OUT="$3"
DIR="$(cd "$(dirname "$0")" && pwd)"
MODELS="{models}"
REQ="${{TMPDIR:-/tmp}}/yts-acestep-$$.json"
CAPTION_ESC=$(printf '%s' "$PROMPT" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf '{{"caption": "%s", "duration": %s, "output_format": "wav16"}}' "$CAPTION_ESC" "$DURATION" > "$REQ"
"$DIR/ace-lm" --models "$MODELS" --request "$REQ" >/dev/null
STEM="${{REQ%.json}}"
"$DIR/ace-synth" --models "$MODELS" --request "${{STEM}}0.json" >/dev/null
mv "${{STEM}}00.wav" "$OUT"
rm -f "$REQ" "${{STEM}}0.json"
"#,
        models = paths.models_dir().display(),
    );
    std::fs::write(paths.produce_script(), script).map_err(|e| e.to_string())?;
    make_executable(&paths.produce_script())?;
    Ok(())
}
