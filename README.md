# yts

乐工具新架构(v3.1)脚手架。**原项目 `../yuetools` 保持不动**;本仓是端云重构的新代码。

> 设计源(完整论证 + 图谱):`../yuetools/docs/tech.html` 与 `../yuetools/docs/wiki/`(见 `Arch-V3-1` / `Candle-Inference` / `Platform-Split` / `Server-Stack-Plan` / `Transport-Agnostic-Core`)。

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

# 5) 本地推理组件(Mac)
./servctl components install
./servctl components verify
./servctl components status --profile local
./servctl deploy --profile local
./servctl start --profile local
./servctl status --profile local
./servctl stop --profile local

# 6) 桌面端(Mac)
bash scripts/dev_desktop.sh         # tauri dev(需 npm install)

# 7) 打包 Mac sidecar(PyInstaller)
bash scripts/build_sidecar_macos.sh
```

`./install` 会用 `curl` 拉取 uv 和 Node 官方二进制到项目 `.tools/` 下,并把 Python
运行环境创建在当前目录 `.venv/`,前端依赖安装到 `desktop/frontend/node_modules/`。
`servctl start` 会在暴露后端端口前检查 `conf/{profile}.env`、端口占用、数据库连接、
FastAPI app 装配和当前推理后端的最小文本调用,后端健康后再用 Vite preview 暴露
Web 前端 `http://127.0.0.1:1420/`。任一步失败都会非零退出,不做隐式 fallback。
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

本地推理的组件资产由 `servctl components` 统一管理。安装会按 `desktop/components.toml`
中的固定仓库、固定 commit、固定模型 URL/大小/SHA256 构建并校验;启动只使用已验证资产,
不会下载、reset、checkout 或静默降级:
```bash
./servctl components install
./servctl components verify
./servctl components status --profile local

# 在 conf/local.env 中设置 YTS_PROFILE=local 且 YTS_INFERENCE_BACKEND=local 后:
./servctl deploy --profile local
./servctl start --profile local
```

## 现状(本轮脚手架)
- ✅ 目录结构 / 依赖 / 配置 / 关键连线就位;服务端可启动;Tauri 可编译;四模态经本地 GGML 网关(文本 llama.cpp / 图片 sd.cpp / 音乐 acestep.cpp)。
- 🚧 TODO:语音(ASR/TTS)、creation 6 步完整业务、TCC 真实落账、Phoenix 评估集、离线↔云同步、**Windows in-process(DIY Tauri+PyO3)**。
