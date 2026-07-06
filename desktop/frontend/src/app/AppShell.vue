<script setup>
import { computed, onMounted, onUnmounted } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { Boxes, Cloud, HardDrive, Music2, Settings2, Sparkles, SquarePen } from "@lucide/vue";
import { useAuthStore } from "../stores/auth";
import { useEnvironmentStore } from "../stores/environment";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const environment = useEnvironmentStore();

const primaryNavItems = [
  { key: "music", label: "音乐", to: "/music", icon: Music2 },
  { key: "studio", label: "创作", to: "/studio", icon: SquarePen },
  { key: "assets", label: "资产", to: "/assets", icon: Boxes },
];
const settingsNavItem = { key: "settings", label: "设置", to: "/settings", icon: Settings2 };
const targetIcons = { local: HardDrive, cloud: Cloud };

const activeNav = computed(() => route.meta.activeNav || "music");

function handleAuthExpired() {
  auth.clearSession();
  router.push({ name: "login", query: { redirect: route.fullPath } });
}

function switchEnvironmentTarget(item) {
  environment.setTarget(item.value);
  void environment.checkHealth(item.value);
}

onMounted(() => {
  window.addEventListener("yts-auth-expired", handleAuthExpired);
  environment.attach();
  void environment.checkHealth(environment.target);
  auth.hydrate();
});
onUnmounted(() => {
  window.removeEventListener("yts-auth-expired", handleAuthExpired);
  environment.detach();
});
</script>

<template>
  <main class="creator-shell">
    <svg class="brand-gradient-defs" aria-hidden="true" focusable="false" width="0" height="0">
      <defs>
        <linearGradient id="yts-brand-gradient" x1="4" y1="4" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stop-color="var(--color-brand-cyan)" />
          <stop offset="100%" stop-color="var(--color-brand-green)" />
        </linearGradient>
      </defs>
    </svg>

    <aside class="creator-sidebar">
      <RouterLink class="creator-brand" to="/music" aria-label="音乐首页">
        <span class="creator-brand-mark"><Sparkles :size="27" /></span>
      </RouterLink>

      <nav class="creator-nav" aria-label="主导航">
        <RouterLink
          v-for="item in primaryNavItems"
          :key="item.key"
          :class="['creator-nav-item', { active: activeNav === item.key }]"
          :to="item.to"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <nav class="creator-bottom-nav" aria-label="底部导航">
        <div class="global-target-switch" aria-label="API 环境">
          <button
            v-for="item in environment.options"
            :key="item.value"
            :class="{ active: environment.target === item.value }"
            :disabled="environment.switchLocked"
            :title="
              environment.switchLocked
                ? '当前任务运行中，不能切换环境'
                : `切换到${item.label} · ${environment.targetHealthDetail(item.value)}`
            "
            type="button"
            @click="switchEnvironmentTarget(item)"
          >
            <component :is="targetIcons[item.value]" :size="14" />
            <span>{{ item.label }}</span>
            <i :class="['target-status-dot', environment.targetHealth(item.value)]"></i>
          </button>
          <small v-if="environment.switchLocked" class="target-lock-note">运行中</small>
        </div>
        <RouterLink
          :class="['creator-nav-item', { active: activeNav === settingsNavItem.key }]"
          :to="settingsNavItem.to"
        >
          <component :is="settingsNavItem.icon" :size="18" />
          <span>{{ settingsNavItem.label }}</span>
        </RouterLink>
      </nav>
    </aside>

    <section class="creator-main">
      <RouterView />
    </section>
  </main>
</template>

<style scoped>
.creator-shell {
  background: var(--color-bg);
  color: var(--color-text);
  display: grid;
  grid-template-columns: 69px minmax(0, 1fr);
  height: 100vh;
  overflow: hidden;
}

.brand-gradient-defs {
  height: 0;
  position: absolute;
  width: 0;
}

.creator-sidebar {
  background: var(--color-sidebar);
  border-right: 1px solid var(--color-border-soft);
  color: var(--color-text);
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  padding: 14px 6px;
  position: relative;
  z-index: 50;
}

.creator-brand,
.creator-nav-item {
  color: inherit;
  text-decoration: none;
}

.creator-brand {
  align-items: center;
  display: flex;
  justify-content: center;
}

.creator-brand-mark {
  align-items: center;
  border-radius: 8px;
  display: inline-flex;
  filter: drop-shadow(0 0 9px var(--color-brand-glow));
  height: 36px;
  justify-content: center;
  width: 36px;
}

.creator-brand-mark svg {
  stroke: url(#yts-brand-gradient);
  color: var(--color-brand-cyan);
}

.creator-nav {
  display: grid;
  gap: 5px;
}

.creator-bottom-nav {
  display: grid;
  gap: 8px;
  margin-top: auto;
}

.global-target-switch {
  background: transparent;
  border-radius: 8px;
  display: grid;
  gap: 5px;
  padding: 0;
}

.global-target-switch button {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 7px;
  color: var(--color-muted-strong);
  cursor: pointer;
  display: grid;
  font: inherit;
  font-size: 10px;
  gap: 2px;
  justify-items: center;
  min-height: 32px;
  position: relative;
  padding: 4px 0;
}

.global-target-switch button:hover,
.global-target-switch button.active {
  background: rgba(14, 165, 233, 0.28);
  box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.18), 0 8px 18px rgba(2, 132, 199, 0.14);
  color: var(--color-heading);
}

.global-target-switch button:hover:not(.active) {
  color: var(--color-heading);
}

.global-target-switch button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.target-status-dot {
  border-radius: 999px;
  bottom: 5px;
  height: 5px;
  position: absolute;
  right: 7px;
  width: 5px;
}

.target-status-dot.online {
  background: var(--color-success);
}

.target-status-dot.offline {
  background: var(--color-danger);
}

.target-status-dot.checking {
  background: var(--color-warning);
}

.target-status-dot.unknown {
  background: var(--color-muted);
}

.target-lock-note {
  color: var(--color-warning);
  font-size: 9px;
  font-weight: 800;
  line-height: 1;
  text-align: center;
}

.creator-nav-item {
  align-items: center;
  border: 1px solid transparent;
  border-radius: 8px;
  color: var(--color-muted-strong);
  display: flex;
  flex-direction: column;
  font-size: 11px;
  gap: 5px;
  justify-content: center;
  min-height: 52px;
  padding: 6px 0;
}

.creator-nav-item:hover,
.creator-nav-item.active {
  background: var(--color-accent-soft);
  color: var(--color-heading);
}

.creator-main {
  min-height: 0;
  overflow: auto;
  position: relative;
  z-index: 0;
}
</style>
