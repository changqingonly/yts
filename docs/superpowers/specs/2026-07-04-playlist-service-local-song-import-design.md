# 通用歌单服务与本地歌曲导入设计

## 背景

音乐页需要从“隐藏上传入口”升级为完整的歌单导入能力。新的核心模型分为两层：

- `meta_song` 是平台公共资源，保存歌曲文件的客观事实，必须准确、唯一、可复用。
- `music_playlist_item` 是用户个人歌单中的歌曲别名，引用 `meta_song`，并保存用户可编辑的信息，例如自定义歌名和歌单位置。

本次设计先建设服务端通用歌单服务，再让“导入本地歌曲”对接这套服务。导入功能不直接拥有歌单规则，只消费歌单服务提供的模型和接口。

## 用户体验目标

- 默认展示当前全局环境的歌单：云端环境展示云歌单，本地环境展示本地歌单。
- 提供查看另一个环境歌单的入口，避免用户误以为歌单丢失。
- 导入目标跟随全局环境。当前是云端就上传到云歌单，当前是本地就上传到本地歌单。
- 导入界面必须明确提示目标，例如“将导入到云歌单：默认歌单”。
- 批量导入多首歌曲，默认导入当前歌单，用户可以改选已有歌单或新建歌单。
- 导入时自动提取歌曲客观元信息并写入 `meta_song`。
- 歌单 item 默认使用文件名作为用户侧歌名，后续允许用户自定义。
- 允许重复导入，同一个 `content_hash` 可以在同一个歌单出现多次。
- 单个歌单最多 2000 首歌曲，超过上限时导入失败并提示用户。
- 批量导入中单个文件失败不影响其他文件，失败项可以单独重试。
- 导入完成后只更新歌单，不自动播放，不打断当前播放。

## 核心领域模型

### MetaSong

新增 `meta_song` 表。它属于平台公共资源层，不归属于某个用户。它只保存文件和音频本身的客观事实，不保存用户自定义歌名、歌单位置或个人管理状态。

字段设计：

- `content_hash`: 主键，歌曲文件内容 hash。服务端根据上传文件 bytes 计算，所有引用该文件的地方必须使用同一个值。
- `size_bytes`: 文件大小。
- `mime`: 上传请求或服务端识别到的 MIME。
- `file_format`: 文件格式，例如 `mp3`, `wav`, `flac`, `aac`, `m4a`。
- `duration_ms`: 歌曲时长。
- `sample_rate_hz`: 采样率。
- `bit_rate_bps`: 比特率。
- `channels`: 声道数。
- `codec_name`: 编码器或 codec 名称。
- `codec_profile`: codec profile，可为空。
- `container_format`: 容器格式，可为空。
- `extracted_at_ms`: 元数据提取时间。
- `extractor_name`: Python 提取器名称。
- `extractor_version`: 提取器版本。
- `created_at_ms`: 首次入库时间。
- `updated_at_ms`: 最近更新入库时间。

`content_hash` 表示“同一份文件内容”的唯一性。相同 bytes 必须得到相同 `content_hash`；同一首歌如果经过重新编码导致文件 bytes 不同，会生成不同 `content_hash`，后续可通过音频指纹或人工聚合建立更高层的相同歌曲关系，但这不属于本次范围。

### SongBlob 和 Owner

现有 `LocalImportBlob` 可以演进为通用 blob 存储表，或继续保留名称作为上传文件存储层。无论表名如何，它只负责存储文件实体：

- `content_hash`
- `path`
- `size_bytes`
- `mime`
- `created_at`

用户与文件的关系继续由 owner 表表达：

- `content_hash`
- `user_uuid`
- `created_at`

`meta_song` 公共且唯一，owner 表负责表达当前用户是否有权把该歌曲加入自己的歌单或下载播放。

### MusicPlaylist

`MusicPlaylist` 表示用户的个人歌单资产。

字段设计：

- `id`: 歌单 ID。
- `user_uuid`: 所属用户。
- `name`: 歌单名称。
- `scope`: `cloud` 或 `local`。
- `is_default`: 是否为默认歌单。
- `item_count`: 非删除歌曲数量，便于快速判断 2000 首上限。
- `created_at_ms`: 创建时间。
- `updated_at_ms`: 更新时间。
- `deleted_at_ms`: 软删除时间。
- `op_clock`: 服务端变更时钟，用于增量同步。

单个歌单的非删除 item 数量上限是 2000。服务端必须在写入前校验，超过上限时显式失败，错误码为 `playlist_item_limit_exceeded`。

### MusicPlaylistItem

`MusicPlaylistItem` 是 `meta_song` 在用户歌单中的一个个人别名。它不保存时长、文件格式、文件大小、采样率、编码信息等客观事实；这些信息全部来自 `meta_song`。

字段设计：

- `id`: 歌单 item ID。重复歌曲必须有不同 item ID。
- `user_uuid`: 所属用户。
- `playlist_id`: 所属歌单。
- `content_hash`: 必填，引用 `meta_song.content_hash`。
- `title_alias`: 用户自定义歌名；导入时默认由文件名去扩展名生成。
- `artist_alias`: 用户自定义艺人，可为空。
- `position`: 歌单内位置编号，正整数，从 1 开始，按升序展示。
- `added_at_ms`: 加入歌单时间。
- `updated_at_ms`: 更新时间。
- `deleted_at_ms`: 软删除时间。
- `op_clock`: 服务端变更时钟。
- `device_id`: 客户端设备 ID。

同一个歌单允许多条 item 引用同一个 `content_hash`。这表示用户把同一首歌重复放入歌单，属于合法的个人编排行为。

## 位置规则

歌单必须有稳定的位置概念，因为用户会频繁调整歌曲顺序。

- 默认导入时，新 item 追加到目标歌单末尾。
- 默认顺序按歌曲加入歌单时间排列；批量导入队列默认按用户选择文件顺序逐个处理，因此默认位置也等于上传/加入队列顺序。
- `added_at_ms` 由服务端写入，表示该 item 加入歌单的时间。
- 服务端分配连续位置编号：当前最大 `position + 1` 开始递增。
- 用户调整歌单顺序后，服务端必须在一个事务里重新写入完整位置编号。
- 重新编号后，非删除 item 的 `position` 必须是从 1 到 N 的连续整数。
- position 由服务端最终裁决，前端不能只在本地重排后假定成功。

新增领域函数：

- `append_playlist_items(session, user_uuid, playlist_id, items)`: 追加歌曲并分配位置。
- `reorder_playlist_items(session, user_uuid, playlist_id, ordered_item_ids)`: 按完整 item ID 列表重排并重新编号。

`reorder_playlist_items` 必须校验：

- `playlist_id` 属于当前用户。
- `ordered_item_ids` 覆盖该歌单所有非删除 item，不能缺失、重复或包含其他歌单 item。
- 重排数量不能超过 2000。
- 任一校验失败都必须显式失败，不做局部重排。

## 服务端通用歌单服务

服务层拆出 `server/yts_server/domains/playlists.py`，负责歌单、歌单 item、位置、上限和权限校验。`server/yts_server/domains/music.py` 保留歌曲上传、文件存储、`meta_song` 入库和播放文件读取能力。

### 歌单服务能力

- `ensure_default_playlist(session, user_uuid, scope)`: 获取或创建当前 scope 的默认歌单。
- `list_playlists(session, user_uuid, scope, since_clock, limit)`: 列出歌单。
- `create_playlist(session, user_uuid, scope, name)`: 创建歌单。
- `rename_playlist(session, user_uuid, playlist_id, name)`: 重命名歌单。
- `delete_playlist(session, user_uuid, playlist_id)`: 软删除歌单。
- `list_playlist_items(session, user_uuid, playlist_id, since_clock, limit)`: 列出歌单歌曲，响应中 join `meta_song`。
- `append_playlist_items(session, user_uuid, playlist_id, item_inputs)`: 追加 item，校验 2000 上限并分配连续 position。
- `reorder_playlist_items(session, user_uuid, playlist_id, ordered_item_ids)`: 重新排序并连续编号。

服务层必须显式校验：

- 歌单必须属于当前用户。
- 歌曲 item 写入的 `playlist_id` 必须存在且属于当前用户。
- `content_hash` 必须存在于 `meta_song`。
- 当前用户必须拥有该 `content_hash` 的 owner 关系。
- 写入后歌单非删除 item 数量不能超过 2000。
- 不存在的歌单、无权限歌单、无效 `content_hash` 必须显式失败。

## 上传与元数据提取

上传歌曲由 Python 服务端完成以下步骤：

1. 读取上传文件 bytes。
2. 计算 `content_hash`。
3. 写入或复用 blob 文件。
4. 建立当前用户与 `content_hash` 的 owner 关系。
5. 如果 `meta_song` 不存在，则提取音频元数据并创建 `meta_song`。
6. 如果 `meta_song` 已存在，直接复用，不重新写入客观事实。

元数据提取必须在服务端完成，前端不能作为事实来源。提取失败时上传失败，不创建 `meta_song`，不允许进入歌单。错误码建议：

- `empty_file`
- `unsupported_audio_file`
- `metadata_extract_failed`
- `invalid_content_hash`

元数据提取建议使用 Python 音频解析库封装为独立函数：

- 输入：临时文件路径、MIME、文件名。
- 输出：`duration_ms`, `file_format`, `sample_rate_hz`, `bit_rate_bps`, `channels`, `codec_name`, `codec_profile`, `container_format`。
- 失败：抛出领域错误，不返回半成品。

## API 设计

local/cloud 的接口契约保持一致，不做两套 API。前端通过全局 `selectedApiTarget()` 决定请求云端服务或本地服务。

### 歌单 API

- `GET /api/music/playlists?scope=cloud|local|all`
  - 返回歌单列表。
  - 不传 `scope` 时返回当前服务默认 scope 的歌单。
  - `cloud` 和 `local` 用同一套响应结构，保证云端服务和本地服务接口一致。
  - 查看另一个环境歌单时，由前端请求另一个 API target 的同一接口；服务端不跨环境代理。
  - 如果另一个 target 不可连接，前端显示“无法连接本地/云端服务”，并提示用户切换环境后再管理。

- `POST /api/music/playlists`
  - 入参：`name`, `scope`。
  - 返回新建歌单。

- `POST /api/music/playlists/default`
  - 入参：`scope`。
  - 返回默认歌单，不存在则创建。

- `GET /api/music/playlists/{playlist_id}/items`
  - 返回指定歌单 item。
  - 每个 item 包含用户别名字段和 joined `meta_song` 字段。
  - 默认按 `position asc` 排序。

- `POST /api/music/playlists/{playlist_id}/items`
  - 入参：`items: [{ content_hash, title_alias, artist_alias, device_id }]`。
  - 追加到歌单末尾。
  - 服务端校验 2000 首上限。
  - 返回新建 item 和分配后的 position。

- `POST /api/music/playlists/{playlist_id}/items/reorder`
  - 入参：`ordered_item_ids`。
  - 服务端重写所有非删除 item 的连续 position。
  - 返回重排后的 item 摘要。

### 上传 API

- `POST /api/music/upload`
  - 上传单个音频文件。
  - 返回 `content_hash`, `filename`, `size_bytes`, `mime`, `meta_song`, `deduplicated`。
  - `deduplicated` 只说明 blob 和 `meta_song` 是否复用，不阻止重复加入歌单。
  - 该接口只负责上传和 `meta_song` 入库，不直接创建歌单 item。

不新增“批量上传文件”的服务端接口。前端逐个上传可以让每个文件独立失败、独立重试，符合批量导入体验。

## 前端导入设计

### 组件

新增 `MusicImportDrawer`：

- 从音乐页右侧“导入”图标打开。
- 浮层覆盖在播放器之上，不挤压播放器布局。
- 顶部展示当前环境和目标歌单。
- 支持选择已有歌单。
- 支持创建新歌单并立即作为目标。
- 支持拖拽或文件选择批量添加音频。
- 展示每个文件的导入状态和错误原因。

### 导入前校验

前端在用户选择文件后读取目标歌单当前 item 数量：

- 如果 `current_count + selected_files.length > 2000`，阻止开始上传。
- 提示“该歌单最多 2000 首，还可导入 X 首”。
- 该校验只是提前提示，服务端仍必须做最终校验。

### 导入状态

每个文件维护独立状态：

- `queued`: 已选择，等待上传。
- `uploading`: 正在上传文件。
- `uploaded`: 文件已上传，等待加入歌单。
- `syncing`: 正在写入歌单 item。
- `done`: 已导入歌单。
- `failed`: 导入失败，可重试。

批量任务整体展示：

- 成功数量。
- 失败数量。
- 进行中数量。
- “重试失败项”入口。
- “完成”按钮。

### 导入控制流

单个文件的导入控制流：

1. 调用 `POST /api/music/upload`。
2. 获取 `content_hash` 和 `meta_song`。
3. 生成默认 `title_alias`：文件名去掉扩展名。
4. 调用 `POST /api/music/playlists/{playlist_id}/items`。
5. 服务端追加 item 并分配 position。
6. 前端刷新当前歌单 item 列表。

如果第 1 步成功、第 4 步失败，文件状态显示“已上传，加入歌单失败”，重试时只重试第 4 步，不重复上传。

### 歌单展示

音乐页默认展示当前环境的当前歌单歌曲。歌单入口需要显示：

- 当前歌单名。
- 当前环境标识：云歌单或本地歌单。
- 当前歌曲数量，例如 `128 / 2000`。
- 查看另一个环境歌单的入口。

查看另一个环境时，不自动切换全局环境。界面只解释“这些是另一个环境的歌单，切换到该环境后可播放和管理”。

## 错误处理

不做静默降级，也不隐藏真实问题：

- 空文件：该文件失败，显示“文件为空”。
- 元数据提取失败：该文件失败，显示“无法读取音频信息”。
- 不支持的音频格式：该文件失败，显示格式不支持。
- 上传失败：该文件失败，保留重试。
- 歌单达到 2000 首：阻止导入并显示剩余容量。
- 歌单不存在：加入歌单失败，要求用户重新选择歌单。
- 目标服务不可用：导入浮层顶部显示不可用原因，阻止开始导入。
- 文件已上传但写入歌单失败：显示“已上传，加入歌单失败”，重试时只重试写入歌单。
- 播放失败：播放层显式显示错误，不把它伪装成导入成功或静默跳过。

## 测试计划

### 服务端

- 默认歌单不存在时自动创建。
- 创建、列出、重命名、软删除歌单。
- 歌单 item 默认按追加顺序获得连续 position。
- 重排后 position 从 1 到 N 连续更新。
- 重排请求缺失、重复、包含其他歌单 item 时显式失败。
- 歌单超过 2000 首时追加失败。
- `content_hash` 必填，缺失时失败。
- `content_hash` 必须存在于 `meta_song`。
- 歌单 item 不能写入其他用户歌单。
- 当前用户必须拥有对应 `content_hash` owner。
- 同一个 `content_hash` 可以重复写入同一个歌单。
- 上传同一文件得到同一 `content_hash`，并复用同一 `meta_song`。
- 上传时能提取时长、文件格式、文件大小、采样率、编码信息。
- 元数据提取失败时上传失败且不创建 `meta_song`。

### 前端

- 音乐页导入图标打开导入浮层。
- 浮层显示当前目标环境和目标歌单。
- 歌单容量显示 `count / 2000`。
- 选择文件后超过 2000 上限时阻止上传并提示。
- 支持选择已有歌单。
- 支持新建歌单后导入。
- 批量导入时成功项进入歌单，失败项留在列表。
- 文件已上传但加入歌单失败时，重试不重复上传。
- 导入完成不自动播放，不改变当前播放状态。
- 当前环境切换后展示对应环境歌单，并提供另一个环境的查看入口。

## 实施顺序

1. 新增 `meta_song` 模型和迁移，补齐 blob/owner 与 `meta_song` 的关系。
2. 实现 Python 音频元数据提取函数，上传失败必须显式暴露。
3. 建设服务端通用歌单服务和数据模型，包含 position、2000 上限、owner 校验。
4. 补齐歌单 API：列表、默认歌单、创建歌单、追加 item、重排 item。
5. 调整上传 API，让它只负责文件上传、owner 建立和 `meta_song` 入库。
6. 调整前端 playlist store，从单一 `items` 扩展到当前歌单、歌单列表、容量信息和 item/meta_song 组合数据。
7. 实现 `MusicImportDrawer`。
8. 对接批量上传、加入歌单、容量提示和失败重试。
9. 更新音乐页歌单/队列展示和播放数据映射。
10. 补齐服务端和前端测试。
