# yts

乐工具新架构(v3.1)脚手架。**原项目 `../yuetools` 保持不动**;本仓是端云重构的新代码。

> 设计源(完整论证 + 图谱):`../yuetools/docs/tech.html` 与 `../yuetools/docs/wiki/`(见 `Arch-V3-1` / `Candle-Inference` / `Platform-Split` / `Server-Stack-Plan` / `Transport-Agnostic-Core`)。

## 架构一句话
- **推理 = Candle(纯 Rust,in-process)**:文本 / 图片 / 语音 / 背景音乐;`llama.cpp` 仅用户授权可选。
- **编排 = Python(LangGraph)调 Candle**:本轮 Mac 走 **sidecar**(Windows in-process 留后)。
- **服务端(云实现)= FastAPI + LangGraph + LiteLLM + Phoenix + PostgreSQL**。
- **统一 API + 双实现 + 用户切换**:本地(桌面)/ 云(服务端)共用 API 契约,自定义 skill 仅本地。

## 架构红线
业务/编排逻辑只写在 **`core/`(传输无关)**。`server/`(FastAPI HTTP)与 `desktop/sidecar`、未来 Windows 的 PyO3 入口都只是**薄入口**,不得内联业务逻辑。

## 目录
```
core/      传输无关核心(LangGraph 编排 + LiteLLM + Pydantic 契约 + 推理端口)
server/    云实现:FastAPI + DB + 计费(TCC) + Phoenix
desktop/   Mac 桌面:frontend(Vue) + src-tauri(Rust 壳 + Candle 推理) + sidecar(复用 server app,本地 profile)
shared/    API 契约导出(OpenAPI/JSON Schema)
scripts/   安装 / 开发 / 打包脚本
```

## 快速开始
```bash
# 1) 安装 uv(若未装)
bash scripts/install_uv.sh

# 2) 安装 Python 依赖(core + server)
uv sync

# 3) 起云端/本地服务(FastAPI)
bash scripts/dev_server.sh          # uvicorn yts_server.main:app --reload

# 4) 桌面端(Mac)
bash scripts/dev_desktop.sh         # tauri dev(需 npm install)

# 5) 打包 Mac sidecar(PyInstaller)
bash scripts/build_sidecar_macos.sh
```

## 现状(本轮脚手架)
- ✅ 目录结构 / 依赖 / 配置 / 关键连线就位;服务端可启动(`/health` + creation stub);Tauri 可编译(Candle 依赖就绪,四模态为 stub)。
- 🚧 stub / TODO:Candle 真实模型推理、creation 6 步完整业务、TCC 真实落账、Alembic 真实表、Phoenix 评估集、离线↔云同步、**Windows in-process(DIY Tauri+PyO3)**。
