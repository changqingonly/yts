// 流式生成音频播放客户端(方案 B,来源无关)。契约见 desktop/STREAM_PROTOCOL.md。
//
// 连 WS(本地 candle-server / 云端 server 同契约)→ 解析 header → 把二进制 PCM 帧
// 灌进 AudioWorklet(pcm-player)→ 边生成边播。切 local/cloud 只换 base,不改逻辑。

const WS_BASES = {
  local: "ws://127.0.0.1:8799",
  cloud: "ws://127.0.0.1:8000", // 云端同契约,TODO 接通
};

export class StreamAudioPlayer {
  constructor() {
    this.ctx = null;
    this.node = null;
    this.ws = null;
    this.onState = () => {};
    this.onError = () => {};
    this.state = "idle"; // idle | connecting | streaming | done | stopped | error
  }

  _set(state) {
    this.state = state;
    this.onState(state);
  }

  async _ensureAudio() {
    if (this.ctx) return;
    // 必须在用户手势内调用(autoplay 限制)
    this.ctx = new AudioContext({ sampleRate: 48000 });
    await this.ctx.audioWorklet.addModule("/audio/pcm-player-worklet.js");
    this.node = new AudioWorkletNode(this.ctx, "pcm-player", {
      outputChannelCount: [1],
      processorOptions: { ringCapacity: 48000 * 15 },
    });
    this.node.connect(this.ctx.destination);
    this.node.port.onmessage = (e) => {
      if (e.data.type === "drained") this._set("done");
    };
  }

  /** 开始流式生成播放。target: 'local' | 'cloud' */
  async start({ prompt, seconds = 8, target = "local" }) {
    await this._ensureAudio();
    if (this.ctx.state === "suspended") await this.ctx.resume();
    this.node.port.postMessage({ type: "reset" });

    const base = WS_BASES[target] || WS_BASES.local;
    this._set("connecting");
    const ws = new WebSocket(`${base}/music/stream`);
    ws.binaryType = "arraybuffer";
    this.ws = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "start", prompt, seconds }));
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        const msg = JSON.parse(ev.data);
        if (msg.type === "header") {
          this._set("streaming");
        } else if (msg.type === "end") {
          // 帧已发完;worklet 放空后会回 drained → done
        } else if (msg.type === "error") {
          this.onError(new Error(msg.message));
          this._set("error");
          ws.close();
        }
      } else {
        // 二进制 PCM 帧:ArrayBuffer → Float32Array,灌入 worklet
        const samples = new Float32Array(ev.data);
        this.node.port.postMessage({ type: "pcm", samples }, [samples.buffer]);
      }
    };
    ws.onerror = () => {
      this.onError(new Error("WebSocket 连接失败"));
      this._set("error");
    };
    ws.onclose = () => {
      if (this.state === "streaming") {
        // 服务端已发 end,等 worklet drained;否则视为停止
      }
    };
  }

  /** 中途停止生成 + 播放 */
  stop() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "stop" }));
      this.ws.close();
    }
    if (this.node) this.node.port.postMessage({ type: "reset" });
    this._set("stopped");
  }

  dispose() {
    this.stop();
    if (this.ctx) {
      this.ctx.close();
      this.ctx = null;
      this.node = null;
    }
  }
}

let _singleton = null;
export function getStreamPlayer() {
  if (!_singleton) _singleton = new StreamAudioPlayer();
  return _singleton;
}
