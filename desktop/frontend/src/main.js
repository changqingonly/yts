import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { ensureDesktopDefaultTarget } from "./services/environment";
import "./styles/base.css";

ensureDesktopDefaultTarget();
createApp(App).use(createPinia()).use(router).mount("#app");
