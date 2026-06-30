<script setup>
import { computed, onMounted, onUnmounted } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { Boxes, Music2, Settings2, Sparkles, SquarePen } from "@lucide/vue";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const primaryNavItems = [
  { key: "music", label: "音乐", to: "/music", icon: Music2 },
  { key: "studio", label: "创作", to: "/studio", icon: SquarePen },
  { key: "assets", label: "资产", to: "/assets", icon: Boxes },
];
const settingsNavItem = { key: "settings", label: "设置", to: "/settings", icon: Settings2 };

const activeNav = computed(() => route.meta.activeNav || "music");

function handleAuthExpired() {
  auth.clearSession();
  router.push({ name: "login", query: { redirect: route.fullPath } });
}

onMounted(() => {
  window.addEventListener("yts-auth-expired", handleAuthExpired);
  auth.hydrate();
});
onUnmounted(() => {
  window.removeEventListener("yts-auth-expired", handleAuthExpired);
});
</script>

<template>
  <main class="creator-shell">
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

.creator-sidebar {
  background: var(--color-sidebar);
  border-right: 1px solid var(--color-border-soft);
  color: var(--color-text);
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  padding: 14px 6px;
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
  color: var(--color-accent);
  display: inline-flex;
  height: 36px;
  justify-content: center;
  width: 36px;
}

.creator-nav {
  display: grid;
  gap: 5px;
}

.creator-bottom-nav {
  margin-top: auto;
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
}
</style>
