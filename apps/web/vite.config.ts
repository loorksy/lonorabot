import { randomBytes } from "node:crypto";
import { lingui } from "@lingui/vite-plugin";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// One id per build: the bundle carries it (__LONORA_BUILD__) and the server reads the
// copy written next to the SPA (GET /api/version), so an open shell can tell that a
// newer build is being served and show the update bar.
const buildId = randomBytes(6).toString("hex");
const buildManifest = (): Plugin => ({
  name: "lonora-build-id",
  generateBundle() {
    this.emitFile({
      type: "asset",
      fileName: "build.json",
      source: JSON.stringify({ build: buildId }),
    });
  },
});
export default defineConfig({
  define: { __LONORA_BUILD__: JSON.stringify(buildId) },
  plugins: [
    react({ babel: { plugins: ["@lingui/babel-plugin-lingui-macro"] } }),
    tailwindcss(),
    lingui(),
    buildManifest(),
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
