/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin } from "vite";

// Preconnect to the API origin so the first request skips DNS + TLS setup (NF-09).
function preconnectApi(apiBaseUrl: string): Plugin {
  return {
    name: "tristhana-preconnect-api",
    transformIndexHtml() {
      if (!apiBaseUrl) return [];
      const origin = new URL(apiBaseUrl).origin;
      return [
        {
          tag: "link",
          attrs: { rel: "preconnect", href: origin, crossorigin: "" },
          injectTo: "head",
        },
      ];
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [react(), preconnectApi(env.VITE_API_BASE_URL ?? "")],
    build: { target: "es2022" },
    server: {
      // Dev: same-origin /api via the local backend (`uv run tristhana-dev`), so no CORS.
      proxy: { "/api": "http://localhost:8000" },
      // On-device testing through a tunnel (e.g. cloudflared) as @tristhana_dev_bot's URL.
      allowedHosts: [".trycloudflare.com"],
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test-setup.ts"],
      restoreMocks: true,
      env: { VITE_API_BASE_URL: "http://api.test" },
    },
  };
});
