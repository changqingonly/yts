# yts

乐兔工具新架构(v3.1)脚手架。**原项目 `../yuetools` 保持不动**;本仓是端云重构的新代码。

> 设计源(完整论证 + 图谱):`../yuetools/docs/tech.html` 与 `../yuetools/docs/wiki/`(见 `Arch-V3-1` / `Platform-Split` / `Server-Stack-Plan` / `Transport-Agnostic-Core`)。

## 架构一句话
- **本地推理 = GGML 推理网关(Rust,`desktop/infer-gateway`)**:文本→llama.cpp、图片→stable-diffusion.cpp、音乐→acestep.cpp(GGML/Metal 原生二进制,spawn/proxy)。
- **编排 = Python(LangGraph)调网关/云**:本轮 Mac 走 **sidecar**(Windows in-process 留后)。
- **服务端(云实现)= FastAPI + LangGraph + LiteLLM + Phoenix + PostgreSQL**。
- **统一 API + 双实现 + 用户切换**:本地(桌面)/ 云(服务端)共用 API 契约,自定义 skill 仅本地。

## 架构红线
业务/编排逻辑只写在 **`core/`(传输无关)**。`server/`(FastAPI HTTP)与 `desktop/sidecar`、未来 Windows 的 PyO3 入口都只是**薄入口**,不得内联业务逻辑。

## 目录
```
core/      传输无关核心(LangGraph 编排 + LiteLLM + Pydantic 契约 + 推理端口)
server/    云实现:FastAPI + DB + 计费(TCC) + Phoenix
desktop/   Mac 桌面:frontend(Vue) + src-tauri(Rust 壳) + infer-gateway(GGML 推理网关) + sidecar(复用 server app,本地 profile)
shared/    API 契约导出(OpenAPI/JSON Schema)
scripts/   安装 / 开发 / 打包脚本
```

## 快速开始
```bash
# 1) 安装客户机运行环境到当前项目目录(.tools + .venv + node_modules)
./install

# 2) 准备真实 profile 配置
cp conf/cloud.example.env conf/cloud.env
# 编辑 conf/cloud.env,填入数据库、鉴权、LLM 等真实值

# 3) 部署 Python 服务端环境 + Node 前端产物
./servctl deploy --profile cloud

# 4) 控制 FastAPI 服务 + Web 前端预览(127.0.0.1:1420)
./servctl start --profile cloud
./servctl status --profile cloud
./servctl stop --profile cloud
./servctl restart --profile cloud   # deploy + stop + start

# 5) 桌面端(Mac)开发态:tauri dev,服务/网关走 servctl(见上)
bash scripts/dev_desktop.sh         # tauri dev(需 npm install)

# 6) 打包安装型 macOS 桌面应用(.app/.dmg),见下方「打包 macOS 桌面应用」
bash scripts/build_desktop_macos.sh
```

`./install` 会用 `curl` 拉取 uv 和 Node 官方二进制到项目 `.tools/` 下,并把 Python
运行环境创建在当前目录 `.venv/`,前端依赖安装到 `desktop/frontend/node_modules/`。
`servctl start` 会在暴露后端端口前检查 `conf/{profile}.env`、端口占用、数据库连接、
FastAPI app 装配和当前推理后端的最小文本调用,后端健康后再用 Vite preview 暴露
Web 前端 `http://127.0.0.1:1420/`。后端默认端口按 profile 区分:`cloud` 使用
`8000`,`local` 使用 `8765`;显式传入 `--port` 时以命令行为准。任一步失败都会非零退出,
不做隐式 fallback。
`servctl deploy` 负责校验配置并构建前端产物(`npm run build`);单独执行 `servctl start`
不会重复安装 Python/Node 环境。

## 推理后端切换(YTS_INFERENCE_BACKEND)
- `local`:本地 **GGML 推理网关**(`desktop/infer-gateway`,:8799),经 `YTS_GATEWAY_BASE_URL` 调用。
  四模态统一走 GGML 原生二进制:**文本→llama.cpp(`llama-server`,OpenAI 兼容)**、图片→stable-diffusion.cpp、音乐→acestep.cpp。
  (历史:文本曾用 Candle 内嵌,现已移除,四模态统一到 GGML 网关。)
- `cloud`:LiteLLM 云模型,provider 由 `YTS_DEFAULT_TEXT_MODEL`、fallbacks 和对应 key/base_url 决定。

OpenAI-compatible 或 DeepSeek 都属于 `cloud` 路由,不要把 provider 名写进 `YTS_INFERENCE_BACKEND`:
```bash
# 编辑 conf/local.env 或 conf/cloud.env:
# YTS_INFERENCE_BACKEND=cloud
# YTS_OPENAI_API_KEY=sk-...
# YTS_OPENAI_TEXT_MODEL=gpt-4.1-mini
# YTS_OPENAI_BASE_URL=        # 可选,兼容代理或私有网关时填写
# YTS_DEFAULT_TEXT_MODEL=openai/gpt-4.1-mini
# YTS_AUTH_JWT_SECRET=dev-yts-auth-secret-that-is-long-enough-for-hs256

# 云端 profile 使用:
# YTS_PROFILE=cloud
```
`conf/*.env` 是 Python 侧唯一的本地配置入口,已覆盖日志、数据库、鉴权、存储、CORS、
LangGraph checkpoint、LiteLLM/OpenAI/本地网关文本模型,以及图片/音频/音乐模型槽位。

本地推理需先准备各模态 GGML 二进制+模型(各一条命令,自动构建+下模型+生成配置):
```bash
bash scripts/build_llamacpp.sh       # 文本:llama.cpp + Qwen2.5-7B GGUF(~4.4GB,Apache-2.0)
bash scripts/build_sdcpp.sh          # 图片:stable-diffusion.cpp + FLUX.1-schnell GGUF(~9.3GB)
# (音乐:build_acestep.sh)
bash scripts/dev_gateway.sh           # 起 GGML 网关(:8799),自动加载上面生成的 producer 配置、spawn llama-server
# 在 conf/{profile}.env 中设置 YTS_INFERENCE_BACKEND=local 后:
./servctl restart --profile local    # write_lyrics 等节点改走本地 GGML 网关
```

## 打包 macOS 桌面应用
上面的 `servctl`/`dev_gateway.sh`/`dev_desktop.sh` 是**开发态**:各进程手动起、依赖本机
已 `git clone` + `cmake build` 好的 `desktop/vendor/`。**打包态**(给终端用户的 `.app`/`.dmg`)不要求
用户装编译工具链,由 Tauri 壳自己管理进程 + 首次运行下载模型:

```bash
bash scripts/build_desktop_macos.sh
# 产物:desktop/src-tauri/target/release/bundle/{macos/乐兔.app, dmg/*.dmg}
```

该脚本依次:构建 `infer-gateway`(release)→ 打包 `yts-sidecar`(PyInstaller,复用
`scripts/build_sidecar_macos.sh`)→ 以 Tauri `externalBin` 约定命名两者(`<name>-<target-triple>`)
→ `tauri build`。两者体积都很小,不含模型权重。

安装后首次启动:壳(`desktop/src-tauri/src/lib.rs`)会自动拉起 `yts-sidecar` 与 `infer-gateway` 两个
子进程;此时 `infer-gateway` 还没有 `YTS_LLAMA_CMD`/`YTS_IMAGEGEN_CMD`(本地二进制/权重未下载),
只有 `/health` 和音乐合成兜底可用。用户在「设置 → 本地模型」里点击下载后,
`desktop/src-tauri/src/models.rs` 会:
- 从 GitHub Releases 拉预编译的 `llama.cpp`(`ggml-org/llama.cpp`,macOS arm64 tar.gz)与
  `stable-diffusion.cpp`(`leejet/stable-diffusion.cpp`,macOS arm64 zip)二进制;
- 从 HuggingFace 拉与 `scripts/build_llamacpp.sh` / `build_sdcpp.sh` 相同的默认 GGUF 权重
  (Qwen2.5-7B-Instruct、FLUX.1-schnell 全套);

全部存到 `app_data_dir()/vendor/`(而非开发态的 `desktop/vendor/`),下载完成后前端会调
`restart_gateway` 让新 env 生效。本轮仅覆盖 macOS(arm64);Windows/Linux 打包留后。

音乐生成(acestep.cpp)默认走 `infer-gateway` 内置合成器兜底;它在 GitHub 上没有任何
release/tag,没有预编译产物可下,是「本地模型」里唯一一个只能**源码构建**的分档
(`desktop/src-tauri/src/acestep.rs`)。「设置 → 本地模型 → 音乐生成(acestep.cpp)」里的
「开始构建」会:检测 `git`/`cmake`/`cc` 工具链(缺失时提示装 Xcode Command Line Tools,
不阻塞文本/图片两档)→ `git clone --recurse-submodules` + `./buildcpu.sh`(仓库 README:
macOS 上该脚本也会自动启用 Metal + Accelerate)→ 下载默认权重组(HuggingFace
`Serveurperso/ACE-Step-1.5-GGUF`,每类型取最快档:0.6B LM + 0.6B 文本编码器 + turbo(8 步)
DiT + VAE)→ 生成一个两阶段 shell 包装脚本(`ace-lm` 生成词/编码 → `ace-synth` 渲染音频)
填平 `stream.rs` 的单命令 `YTS_AUDIOGEN_CMD` 契约。整条链路已用仓库里已有的
`desktop/vendor/acestep.cpp` 构建产物+权重实测跑通(`caption→codes→wav` 全程 ~12s,
产出合法 stereo 48kHz WAV)。

已用真实 `tauri build` 产物(非 `tauri dev`)在干净状态下验证过一整套打包/首启/退出流程,期间
修了三个只有打包态才会暴露的坑,已固化进代码,不用再踩:
- `tauri.conf.json` 的 `beforeDevCommand`/`beforeBuildCommand` 必须显式带 `cwd: "../frontend"`——
  本仓 `desktop/frontend` 与 `desktop/src-tauri` 是**同级目录**而非常见的父子嵌套,Tauri 默认按
  `tauri.conf.json` 所在目录的**上一级**去找 `package.json`,不带 `cwd` 会在真正打包时才报错
  (`tauri dev` 此前大概率也没真正跑通过)。
- `scripts/build_desktop_macos.sh` 的 `tauri build` 必须从 `desktop/src-tauri`(含
  `tauri.conf.json`)起跑,不能从 `desktop/frontend` 起跑——tauri CLI 只向下找子目录里的
  `tauri.conf.json`,两者同级会报 `Couldn't recognize the current folder as a Tauri project`。
- `desktop/src-tauri/src/sidecar.rs` spawn `yts-sidecar` 时必须显式 `.current_dir(app_data_dir())`——
  由 Finder/LaunchServices 双击启动时,子进程 cwd 默认是只读的 `/`,而 `yts_server` 建
  `run/`、`public/` 等目录用的是相对路径,会直接崩溃退出;从 Terminal 直接跑二进制不会复现,
  必须真正"双击打开 .app"才能踩到。同时 `yts-sidecar`(PyInstaller onefile)kill 掉的
  bootloader 进程不会连带杀死其 fork 出的实际子进程,退出时额外按本包内二进制的绝对路径
  `pkill -9 -f` 兜底清理,否则退出后仍有孤儿 uvicorn 进程常驻。

## 现状(本轮脚手架)
- ✅ 目录结构 / 依赖 / 配置 / 关键连线就位;服务端可启动;Tauri 可编译并可打包为 macOS `.app`/`.dmg`;
  四模态经本地 GGML 网关(文本 llama.cpp / 图片 sd.cpp 打包态自动下预编译产物;音乐 acestep.cpp
  打包态可一键源码构建,未构建时走内置合成兜底);打包态首次运行按需下载/构建本地推理
  二进制+模型权重。
- 🚧 TODO:语音(ASR/TTS)、creation 6 步完整业务、TCC 真实落账、Phoenix 评估集、离线↔云同步、
  **Windows in-process(DIY Tauri+PyO3)**、Windows/Linux 打包、代码签名与公证(codesign/notarize)。
