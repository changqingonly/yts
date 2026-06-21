<script setup>
import { ref } from "vue";

// 统一 API 契约;切换实现(本地 sidecar / 云端)不改调用代码,只改 base。
// TODO: 出站应经 Rust 出口代理(认证/拦截);此处 demo 直连。
const target = ref("local"); // local | cloud
const bases = { local: "http://127.0.0.1:8765", cloud: "http://127.0.0.1:8000" };
const health = ref("");
const result = ref("");
const prompt = ref("写一首关于夏夜的轻快小调");

async function checkHealth() {
  health.value = "...";
  try {
    const r = await fetch(`${bases[target.value]}/health`);
    health.value = JSON.stringify(await r.json());
  } catch (e) { health.value = "ERR: " + e; }
}

async function create() {
  result.value = "...";
  try {
    const r = await fetch(`${bases[target.value]}/api/creation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_prompt: prompt.value }),
    });
    result.value = JSON.stringify(await r.json(), null, 2);
  } catch (e) { result.value = "ERR: " + e; }
}
</script>

<template>
  <main style="font-family: -apple-system, sans-serif; padding: 24px; max-width: 760px">
    <h1>yts — 桌面端(脚手架)</h1>
    <p>
      实现切换:
      <label><input type="radio" value="local" v-model="target" /> 本地(Candle + sidecar)</label>
      <label style="margin-left:12px"><input type="radio" value="cloud" v-model="target" /> 云端</label>
      <small style="color:#888"> base = {{ bases[target] }}</small>
    </p>
    <button @click="checkHealth">检查 /health</button>
    <pre>{{ health }}</pre>
    <hr />
    <input v-model="prompt" style="width:100%" />
    <button @click="create" style="margin-top:8px">创作(stub)</button>
    <pre>{{ result }}</pre>
  </main>
</template>
