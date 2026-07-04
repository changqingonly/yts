# 通用歌单服务与本地歌曲导入设计

## 背景

音乐页已经具备最小本地导入链路：前端选择音频文件，调用 `/api/music/local_import/upload` 上传文件，再刷新播放列表。当前能力更像一个隐藏上传入口，还没有完整的歌单概念，也没有批量导入、导入目标提示、失败重试和云端/本地歌单隔离。

本次设计目标是先建设服务端通用歌单服务，再让“导入本地歌曲”对接这套服务。导入功能不直接拥有歌单规则，只消费歌单服务提供的模型和接口。

## 用户体验目标

- 默认展示当前全局环境的歌单：云端环境展示云歌单，本地环境展示本地歌单。
- 提供查看另一个环境歌单的入口，避免用户误以为歌单丢失。
- 导入目标跟随全局环境。当前是云端就上传到云歌单，当前是本地就上传到本地歌单。
- 导入界面必须明确提示目标，例如“将导入到云歌单：默认歌单”。
- 批量导入多首歌曲，默认导入当前歌单，用户可以改选已有歌单或新建歌单。
- 导入时只使用文件名生成歌名，不读取音频元数据。
- 允许重复导入，同一个文件可以在同一个歌单出现多次。
- 批量导入中单个文件失败不影响其他文件，失败项可以单独重试。
- 导入完成后只更新歌单，不自动播放，不打断当前播放。

## 服务端通用歌单服务

新增通用歌单服务作为音乐播放、导入、本地/云端歌单管理的主线能力。服务层建议放在 `server/yts_server/domains/music.py` 中继续扩展，或拆出 `server/yts_server/domains/playlists.py`；无论文件如何组织，对外应提供清晰的领域函数，而不是让路由直接拼装业务规则。

### 数据模型

新增 `MusicPlaylist`：

- `id`: 歌单 ID。
- `user_uuid`: 所属用户。
- `name`: 歌单名称。
- `scope`: `cloud` 或 `local`。该字段表达歌单语义，实际请求仍由当前 API target 决定落到云端服务或本地服务。
- `is_default`: 是否为默认歌单。
- `created_at_ms`: 创建时间。
- `updated_at_ms`: 更新时间。
- `op_clock`: 服务端变更时钟，用于增量同步。

继续使用 `MusicPlaylistItem` 表示歌单内歌曲条目：

- `playlist_id` 必须引用 `MusicPlaylist.id`。
- `source=local_file` 表示用户导入文件。
- `source_ref=content_hash` 指向本地导入 blob。
- 同一个 `content_hash` 可以对应多条 `MusicPlaylistItem`，因为用户允许重复导入。

### 服务能力

通用歌单服务需要提供以下领域函数：

- `ensure_default_playlist(session, user_uuid, scope)`: 获取或创建当前 scope 的默认歌单。
- `list_playlists(session, user_uuid, scope, since_clock, limit)`: 列出歌单。
- `create_playlist(session, user_uuid, scope, name)`: 创建歌单。
- `rename_playlist(session, user_uuid, playlist_id, name)`: 重命名歌单。
- `delete_playlist(session, user_uuid, playlist_id)`: 删除歌单。删除策略先设计为软删除，避免歌曲条目立即丢失。
- `list_playlist_items(session, user_uuid, playlist_id, since_clock, limit)`: 列出指定歌单歌曲。
- `upsert_playlist_items(session, user_uuid, uploads)`: 同步歌单歌曲条目。

服务层必须显式校验：

- 歌单必须属于当前用户。
- 歌曲条目写入的 `playlist_id` 必须存在且属于当前用户。
- `local_file` 条目写入前，当前用户必须已经拥有对应 `LocalImportOwner`。
- 不存在的歌单、无权限歌单、无效 `content_hash` 必须显式失败。

## API 设计

local/cloud 的接口契约保持一致，不做两套 API。前端通过全局 `selectedApiTarget()` 决定请求云端服务或本地服务。

### 歌单 API

- `GET /api/music/playlists?scope=cloud|local|all`
  - 返回歌单列表。
  - 不传 `scope` 时返回当前服务默认 scope 的歌单。
  - `cloud` 和 `local` 用同一套响应结构，保证云端服务和本地服务接口一致。
  - 查看另一个环境歌单时，由前端请求另一个 API target 的同一接口；服务端不跨环境代理，也不伪造另一个环境的数据。
  - 如果另一个 target 不可连接，前端显示“无法连接本地/云端服务”，并提示用户切换环境后再管理。

- `POST /api/music/playlists`
  - 入参：`name`, `scope`。
  - 返回新建歌单。

- `POST /api/music/playlists/default`
  - 入参：`scope`。
  - 返回默认歌单，不存在则创建。

- `GET /api/music/playlists/{playlist_id}/items`
  - 返回指定歌单的歌曲条目。

### 导入 API

沿用当前两段式主线：

1. `POST /api/music/local_import/upload`
   - 上传单个文件。
   - 返回 `content_hash`, `filename`, `size_bytes`, `mime`, `deduplicated`。
   - `deduplicated` 只说明 blob 存储复用，不阻止重复加入歌单。

2. `POST /api/music/playlist/sync`
   - 把上传成功的文件注册为歌单条目。
   - 每个文件生成一个新的 playlist item。
   - `playlist_id` 必须指向目标歌单。

不新增“批量上传文件”的服务端接口。前端逐个上传可以让每个文件独立失败、独立重试，符合批量导入体验。

## 前端设计

### 组件

新增 `MusicImportDrawer`：

- 从音乐页右侧“导入”图标打开。
- 浮层覆盖在播放器之上，不挤压播放器布局。
- 顶部展示当前环境和目标歌单。
- 支持选择已有歌单。
- 支持创建新歌单并立即作为目标。
- 支持拖拽或文件选择批量添加音频。
- 展示每个文件的导入状态和错误原因。

### 导入状态

每个文件维护独立状态：

- `queued`: 已选择，等待上传。
- `uploading`: 正在上传文件。
- `uploaded`: 文件已上传，等待注册到歌单。
- `syncing`: 正在写入歌单条目。
- `done`: 已导入歌单。
- `failed`: 导入失败，可重试。

批量任务整体展示：

- 成功数量。
- 失败数量。
- 进行中数量。
- “重试失败项”入口。
- “完成”按钮。

### 歌单展示

音乐页默认展示当前环境的当前歌单歌曲。歌单入口需要显示：

- 当前歌单名。
- 当前环境标识：云歌单或本地歌单。
- 查看另一个环境歌单的入口。

查看另一个环境时，不自动切换全局环境。界面只解释“这些是另一个环境的歌单，切换到该环境后可播放和管理”。

## 错误处理

不做静默降级，也不隐藏真实问题：

- 空文件：该文件失败，显示“文件为空”。
- 上传失败：该文件失败，保留重试。
- 歌单不存在：注册到歌单失败，要求用户重新选择歌单。
- 目标服务不可用：导入浮层顶部显示不可用原因，阻止开始导入。
- 文件已上传但写入歌单失败：显示“已上传，写入歌单失败”，重试时只重试写入歌单。
- 播放失败：播放层显式显示错误，不把它伪装成导入成功或静默跳过。

## 测试计划

### 服务端

- 默认歌单不存在时自动创建。
- 创建、列出、重命名、删除歌单。
- 歌曲条目不能写入其他用户歌单。
- `local_file` 条目必须先上传并建立当前用户 owner。
- 同一个 `content_hash` 可以重复写入同一个歌单。
- 单个无效条目必须显式失败。

### 前端

- 音乐页导入图标打开导入浮层。
- 浮层显示当前目标环境和目标歌单。
- 支持选择已有歌单。
- 支持新建歌单后导入。
- 批量导入时成功项进入歌单，失败项留在列表。
- 失败项可以单独重试。
- 导入完成不自动播放，不改变当前播放状态。
- 当前环境切换后展示对应环境歌单，并提供另一个环境的查看入口。

## 实施顺序

1. 建设服务端通用歌单服务和数据模型。
2. 补齐歌单 API，并让现有 `playlist/sync` 依赖歌单存在性校验。
3. 调整前端 playlist store，从单一 `items` 扩展到当前歌单和歌单列表。
4. 实现 `MusicImportDrawer`。
5. 对接批量上传、写入歌单和失败重试。
6. 更新音乐页歌单/队列展示。
7. 补齐服务端和前端测试。
