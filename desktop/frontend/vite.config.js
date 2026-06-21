import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// Tauri 期望固定端口
export default defineConfig({
  plugins: [vue()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
});
