<script setup>
defineProps({
  playing: { type: Boolean, default: false },
});
</script>

<template>
  <div :class="['music-playback-backdrop', { active: playing }]" aria-hidden="true">
    <span v-for="index in 3" :key="index" class="playback-bar"></span>
  </div>
</template>

<style scoped>
.music-playback-backdrop {
  align-items: center;
  background: rgba(5, 15, 29, 0.94);
  display: flex;
  gap: 5px;
  inset: 0;
  justify-content: center;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
  position: absolute;
  transition: opacity 180ms ease;
}

.music-playback-backdrop.active {
  opacity: 0.94;
}

.playback-bar {
  background: #22d3ee;
  border-radius: 2px;
  box-shadow: 0 0 10px rgba(34, 211, 238, 0.38);
  display: block;
  height: 22px;
  width: 5px;
}

.playback-bar:nth-child(2) {
  background: #f43f8e;
  box-shadow: 0 0 10px rgba(244, 63, 142, 0.34);
  height: 34px;
}

.playback-bar:nth-child(3) {
  background: #34d399;
  box-shadow: 0 0 10px rgba(52, 211, 153, 0.34);
  height: 16px;
}
</style>
