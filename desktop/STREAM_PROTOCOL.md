# 统一音频帧流契约(方案 B)

生成式音频「边生成边播」的来源无关协议。**云端(server/FastAPI)与本地(candle-server/Rust)是同一契约的两个 producer**;前端单一 AudioWorklet 播放层是唯一 consumer。切换 local/cloud 只换 WS URL,不改播放逻辑(对齐 yts「统一 API + 双实现 + 用户切换」红线)。

## 传输
- **WebSocket**(双向:支持中途 `stop` / 背压)。
- 本地:`ws://127.0.0.1:8799/music/stream`
- 云端:`wss://<cloud>/music/stream`(同消息格式,TODO)

## 消息序列
1. **client → server**(文本 JSON,开始):
   ```json
   {"type":"start","prompt":"夏夜骑行的轻快电子乐","seconds":8}
   ```
2. **server → client**(文本 JSON,首帧 header):
   ```json
   {"type":"header","sampleRate":48000,"channels":1,"format":"f32le"}
   ```
3. **server → client**(二进制,N 个音频帧):
   - 每帧 = 连续 little-endian `f32` PCM 采样(单声道)。
   - 帧长不固定;前端 ring buffer 吸收抖动。
4. **server → client**(文本 JSON,结束):
   ```json
   {"type":"end","frames":120,"samples":61440}
   ```
5. **client → server**(可选,任意时刻取消):
   ```json
   {"type":"stop"}
   ```

## 约定
- **采样格式**:`f32le`,范围 `[-1.0, 1.0]`,**单声道**(立体声后续扩 `channels:2` 交错)。
- **采样率**:`48000`,与浏览器 `AudioContext` 默认对齐,避免前端重采样。
- **背压**:前端 ring buffer 满时不阻塞(本地准实时);WS 层不强制流控(本地无带宽压力)。云端如需限速由 producer 控制推送节奏。
- **错误**:`{"type":"error","message":"..."}`,client 收到后停止并释放 worklet。

## Producer 实现点
- 本地:`desktop/candle-server` `/music/stream` —— 当前用确定性合成器产真实 PCM(验证用);**MusicGen 模型替换点**见 `src/stream.rs` 注释。
- 云端:`server/yts_server` —— 同消息格式,TODO。

## Consumer 实现点
- `desktop/frontend/public/audio/pcm-player-worklet.js` —— ring buffer AudioWorklet。
- `desktop/frontend/src/audio/streamPlayer.js` —— WS 客户端,解析 header / 灌帧 / stop。
