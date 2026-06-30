import { createRouter, createWebHistory } from "vue-router";

const AppShell = () => import("../app/AppShell.vue");
const MusicPage = () => import("../pages/MusicPage.vue");
const CreationPage = () => import("../pages/CreationPage.vue");
const AssetsPage = () => import("../pages/AssetsPage.vue");
const SettingsPage = () => import("../pages/SettingsPage.vue");
const ProfileSetupPage = () => import("../pages/ProfileSetupPage.vue");
const LoginPage = () => import("../pages/LoginPage.vue");
const RegisterPage = () => import("../pages/RegisterPage.vue");

const routes = [
  {
    path: "/",
    component: AppShell,
    redirect: "/music",
    children: [
      { path: "/music", name: "music", component: MusicPage, meta: { activeNav: "music", requireAuth: true } },
      { path: "/studio", name: "studio", component: CreationPage, meta: { activeNav: "studio", requireAuth: true } },
      { path: "/assets", name: "assets", component: AssetsPage, meta: { activeNav: "assets", requireAuth: true } },
      { path: "/settings", name: "settings", component: SettingsPage, meta: { activeNav: "settings", requireAuth: true } },
      {
        path: "/profile/setup",
        name: "profile-setup",
        component: ProfileSetupPage,
        meta: { activeNav: "settings", requireAuth: true },
      },
    ],
  },
  { path: "/auth/login", name: "login", component: LoginPage, meta: { guest: true } },
  { path: "/auth/register", name: "register", component: RegisterPage, meta: { guest: true } },
  { path: "/:pathMatch(.*)*", redirect: "/music" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const requiresAuth = to.matched.some((record) => record.meta.requireAuth);
  const token = localStorage.getItem("yts-access-token") || "";
  if (requiresAuth && !token) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.meta.guest && token) {
    return { name: "music" };
  }
  return true;
});

export default router;
