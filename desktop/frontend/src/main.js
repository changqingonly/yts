import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { loadRuntimeConfig } from "./services/runtimeConfig";
import "./styles/base.css";

bootstrap().catch((error) => {
  renderFatalConfigurationError(error);
  throw error;
});

async function bootstrap() {
  await loadRuntimeConfig();
  createApp(App).use(createPinia()).use(router).mount("#app");
}

function renderFatalConfigurationError(error) {
  const mountPoint = document.getElementById("app");
  if (!mountPoint) return;

  const section = document.createElement("section");
  section.setAttribute("role", "alert");
  section.className = "runtime-config-error";

  const title = document.createElement("h1");
  title.textContent = "前端运行时配置加载失败";

  const detail = document.createElement("p");
  detail.textContent = error instanceof Error ? error.message : String(error);

  section.append(title, detail);
  mountPoint.replaceChildren(section);
}
