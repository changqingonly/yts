// PCM 播放 AudioWorklet —— 方案 B 的唯一播放层(来源无关)。
// 主线程灌入交错 Float32 PCM(mono 或 LRLR… 立体声);ring buffer 吸收生成≠播放抖动,
// process() 按声道解交错写各输出通道。欠载输出静音(不爆音),end 且放空后通知主线程。
//
// 契约见 desktop/STREAM_PROTOCOL.md:f32 @ 48k,channels=1|2(交错)。

class PcmPlayerProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opt = options.processorOptions || {};
    this.channels = opt.channels || 1;
    // ring 以「交错采样」为单位存储
    const cap = (opt.ringCapacity || 48000 * 10) * this.channels;
    this.buffer = new Float32Array(cap);
    this.cap = cap;
    this.readIdx = 0;
    this.writeIdx = 0;
    this.available = 0; // 已缓冲的交错采样数
    this.ended = false;
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
        if (msg.channels) this.channels = msg.channels;
      }
    };
  }

  push(samples) {
    for (let i = 0; i < samples.length; i++) {
      if (this.available >= this.cap) break; // 满则丢弃(背压上限)
      this.buffer[this.writeIdx] = samples[i];
      this.writeIdx = (this.writeIdx + 1) % this.cap;
      this.available++;
    }
  }

  process(_inputs, outputs) {
    const out = outputs[0]; // out[ch] 是各声道 Float32Array(长度 128)
    const ch = this.channels;
    const frames = out[0].length;
    for (let f = 0; f < frames; f++) {
      if (this.available >= ch) {
        for (let c = 0; c < out.length; c++) {
          // 输入声道数 ch;输出声道数 out.length。mono→多输出时复制 ch0。
          const srcC = c < ch ? c : 0;
          out[c][f] = this.buffer[(this.readIdx + srcC) % this.cap];
        }
        this.readIdx = (this.readIdx + ch) % this.cap;
        this.available -= ch;
      } else {
        for (let c = 0; c < out.length; c++) out[c][f] = 0;
      }
    }
    if (this.ended && this.available < ch && !this.drainedNotified) {
      this.drainedNotified = true;
      this.port.postMessage({ type: "drained" });
    }
    this._tick = (this._tick || 0) + 1;
    if (this._tick % 350 === 0) {
      this.port.postMessage({ type: "level", available: this.available });
    }
    return true;
  }
}

registerProcessor("pcm-player", PcmPlayerProcessor);
