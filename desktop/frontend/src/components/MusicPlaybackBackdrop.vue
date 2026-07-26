<script setup>
defineProps({
  playing: { type: Boolean, default: false },
});
</script>

<template>
  <div :class="['music-playback-backdrop', { active: playing }]" aria-hidden="true">
    <span class="playback-disc"></span>
  </div>
</template>

<style scoped>
.music-playback-backdrop {
  align-items: center;
  background: rgba(5, 15, 29, 0.94);
  display: flex;
  inset: 0;
  justify-content: center;
  opacity: 0;
  overflow: hidden;
  padding-bottom: 12px;
  pointer-events: none;
  position: absolute;
  transition: opacity 180ms ease;
}

.music-playback-backdrop.active {
  opacity: 0.94;
}

.playback-disc {
  background: conic-gradient(
    from 20deg,
    #22d3ee,
    #0b2d45 24%,
    #f43f8e 48%,
    #102c3d 72%,
    #34d399
  );
  border: 2px solid #edf6ff;
  border-radius: 50%;
  box-shadow: 0 0 10px rgba(34, 211, 238, 0.42);
  display: block;
  height: 30px;
  position: relative;
  width: 30px;
}

.playback-disc::before {
  background: #061426;
  border: 2px solid #edf6ff;
  border-radius: 50%;
  content: "";
  height: 8px;
  left: 50%;
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 8px;
}

.playback-disc::after {
  background: rgba(237, 246, 255, 0.88);
  content: "";
  height: 2px;
  left: 15px;
  position: absolute;
  top: 5px;
  transform: rotate(42deg);
  transform-origin: left center;
  width: 10px;
}

.music-playback-backdrop.active .playback-disc {
  animation: disc-spin 2400ms linear infinite;
}

@keyframes disc-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .music-playback-backdrop.active .playback-disc {
    animation: none;
  }
}
</style>
