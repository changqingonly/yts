# 统一音频帧流契约(方案 B)

生成式音频「边生成边播」的来源无关协议。**云端(server/FastAPI)与本地(infer-gateway/Rust)是同一契约的两个 producer**;前端单一 AudioWorklet 播放层是唯一 consumer。切换 local/cloud 只换 WS URL,不改播放逻辑(对齐 yts「统一 API + 双实现 + 用户切换」红线)。

## 传输
- **WebSocket**(双向:支持中途 `stop` / 背压)。
- 本地:`ws://127.0.0.1:8799/music/stream`
- 云端:`wss://<cloud>/music/stream`(同消息格式,TODO)

## 消息序列
1. **client → server**(文本 JSON,开始):client 在 `accept` 声明自己能解码的编码与期望声道(协商)。
   ```json
   {"type":"start","prompt":"夏夜骑行的轻快电子乐","seconds":8,
    "accept":{"codecs":["f32le"],"channels":2}}
   ```
   - `accept.codecs`:client 支持的编码,按优先序;省略=只支持 `f32le`。
   - `accept.channels`:期望声道(1/2);省略=1。
2. **server → client**(文本 JSON,首帧 header):server 据 `accept` 协商出实际参数。
   ```json
   {"type":"header","sampleRate":48000,"channels":2,"format":"f32le"}
   ```
3. **server → client**(二进制,N 个音频帧):
   - `f32le`:连续 little-endian `f32`。**立体声 = LRLRLR… 交错**(每采样点 2 个 f32)。
   - `opus`:每帧 = 一个 Opus packet(可选,见下;前端用 WebCodecs `AudioDecoder` 解)。
   - 帧长不固定;前端 ring buffer 吸收抖动。
4. **server → client**(文本 JSON,结束):
   ```json
   {"type":"end","frames":120,"samples":61440}
   ```
   - `samples` = 每声道采样数(与声道数无关)。
5. **client → server**(可选,任意时刻取消):`{"type":"stop"}`

## 约定
- **采样格式**:默认 `f32le`,范围 `[-1.0, 1.0]`。**单声道**或**立体声交错(LRLR…)**,由 header `channels` 指示。
- **编码协商**:`format=f32le` 全平台稳;`format=opus` 省带宽(云端),但**仅在 client 经 WebCodecs `AudioDecoder.isConfigSupported({codec:'opus'})` 确认可解时**才会被 server 选中(Safari 26.0+/对应 WKWebView 才有,且历史有可靠性 bug)→ 否则回退 `f32le`。
- **采样率**:`48000`,与浏览器 `AudioContext` 默认对齐,避免前端重采样。
- **背压**:前端 ring buffer 满时不阻塞(本地准实时);WS 层不强制流控(本地无带宽压力)。云端如需限速由 producer 控制推送节奏。
- **错误**:`{"type":"error","message":"..."}`,client 收到后停止并释放 worklet。

## Producer 实现点
- 本地:`desktop/infer-gateway` `/music/stream`,两档(env `YTS_AUDIOGEN_CMD`):
  - **未设置**:内置确定性合成器(真实 PCM,无依赖验证用)。
  - **已设置**:spawn 外部 audiogen 二进制(**acestep.cpp / ACE-Step 1.5,GGML/Metal**)。命令含占位 `{prompt}` `{seconds}` `{out}`,producer 把 48kHz WAV 写到 `{out}`;infer-gateway 读 WAV→mono f32→按帧推流。整段生成→流式喂播(准实时,有首段延迟)。
  - 搭建:`scripts/build_acestep.sh`(clone+CMake+Metal),再设 `YTS_AUDIOGEN_CMD`。
- 云端:`server/yts_server` —— 同消息格式,TODO(任务 2)。

## Consumer 实现点
- `desktop/frontend/public/audio/pcm-player-worklet.js` —— ring buffer AudioWorklet。
- `desktop/frontend/src/audio/streamPlayer.js` —— WS 客户端,解析 header / 灌帧 / stop。
