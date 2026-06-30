// PCM 播放 AudioWorklet —— 方案 B 的唯一播放层(来源无关)。
// 主线程通过 port 灌入 Float32 PCM 块;此处用 ring buffer 吸收「生成速率 ≠ 播放速率」的抖动,
// 播放指针按 128 帧/渲染块消费。缓冲不足时输出静音(不爆音),收到 end 且放空后通知主线程。
//
// 契约见 desktop/STREAM_PROTOCOL.md:f32 @ 48k mono。

class PcmPlayerProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const cap = (options.processorOptions && options.processorOptions.ringCapacity) || 48000 * 10; // 10s
    this.buffer = new Float32Array(cap);
    this.cap = cap;
    this.readIdx = 0;
    this.writeIdx = 0;
    this.available = 0;
    this.ended = false; // 上游已发 end
    this.drainedNotified = false;

    this.port.onmessage = (e) => {
      const msg = e.data;
      if (msg.type === "pcm") {
        this.push(msg.samples);
      } else if (msg.type === "end") {
        this.ended = true;
      } else if (msg.type === "reset") {
        this.readIdx = this.writeIdx = this.available = 0;
        this.ended = false;
        this.drainedNotified = false;
      }
    };
  }

  push(samples) {
    for (let i = 0; i < samples.length; i++) {
      if (this.available >= this.cap) break; // 满则丢弃(背压上限;本地准实时极少触发)
      this.buffer[this.writeIdx] = samples[i];
      this.writeIdx = (this.writeIdx + 1) % this.cap;
      this.available++;
    }
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];
    for (let i = 0; i < out.length; i++) {
      if (this.available > 0) {
        out[i] = this.buffer[this.readIdx];
        this.readIdx = (this.readIdx + 1) % this.cap;
        this.available--;
      } else {
        out[i] = 0; // 欠载输出静音
      }
    }
    if (this.ended && this.available === 0 && !this.drainedNotified) {
      this.drainedNotified = true;
      this.port.postMessage({ type: "drained" });
    }
    // 回报缓冲水位(节流:每 ~0.5s)
    this._tick = (this._tick || 0) + 1;
    if (this._tick % 350 === 0) {
      this.port.postMessage({ type: "level", available: this.available });
    }
    return true;
  }
}

registerProcessor("pcm-player", PcmPlayerProcessor);
