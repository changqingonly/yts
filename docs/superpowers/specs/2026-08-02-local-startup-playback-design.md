# Local Startup Playback Design

## Goal

让本地模式尽快进入可听歌状态。启动时显示欢迎页，同时后台准备本地 API；只有当前首曲的可播放数据进入关键路径。任何关键失败都必须显式呈现。

## Startup State

前端维护一个共享的本地启动状态：`starting`、`ready`、`failed`、`timeout`。欢迎页消费该状态；音乐页只在 `ready` 后进入，或在 `failed`/`timeout` 时由用户明确选择继续查看错误详情。

欢迎页启动后立即渲染，不等待 sidecar、健康检查或完整曲库。最长等待 5 秒。`ready` 的条件是：sidecar 健康、最小歌单数据已加载、当前首曲（若存在且 playback status 为 ready）的音频 URL 已取得。没有可播放歌曲时，不能伪造 ready；应显示明确的空歌单状态。

## Startup Flow

1. Tauri 完成壳初始化并显示窗口；不启动 gateway。
2. 前端挂载欢迎页、工作区和播放器外壳。
3. 启动协调器以共享 Promise 去重 `startSidecar` 和健康探测；同一目标的并发调用共享同一个结果。
4. 健康后加载最小播放数据：歌单选择、当前歌单和歌曲条目。只请求当前首曲的音频 URL。
5. 达到 `ready` 后切换到音乐页；删除项、封面、转码状态刷新在后台执行。
6. gateway 仍只由显式音乐生成、文本生成或封面生成/重试操作调用 `ensureInferenceReady`。

## Blocking Rules

- 必须阻塞：路由鉴权；本地 API 健康作为 API 请求前置；当前首曲音频 URL 作为自动恢复播放/用户播放前置。
- 不得阻塞：窗口显示、工作区渲染、gateway 启动、删除项加载、封面加载、未完成转码刷新、剩余歌曲 URL 预加载。

## Error Handling

sidecar 启动、健康检查、最小歌单或首曲 URL 的真实错误进入 `failed`，欢迎页显示错误文本和重试操作。5 秒到达仍未 ready 时进入 `timeout`，显示当前阶段和可重试入口；不能静默进入空音乐页。后台非关键数据失败必须在音乐页显示对应错误，不得用空数组掩盖。

## Verification

覆盖共享 Promise 去重、5 秒超时、关键数据失败显式状态、只加载当前首曲 URL、gateway 不进入启动路径，以及现有音乐页生命周期和本地健康检查回归。
