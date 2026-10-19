import { lingui } from "@lingui/vite-plugin";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
export default defineConfig({
  plugins: [
    react({ babel: { plugins: ["@lingui/babel-plugin-lingui-macro"] } }),
    tailwindcss(),
    lingui(),
  ],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", ws: true },
      "/health": "http://127.0.0.1:8000",
      "/ready": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    assetsDir: "chart-runtime/assets",
    rollupOptions: { input: { app: "index.html", renderer: "chart-runtime/index.html" } },
  },
});
