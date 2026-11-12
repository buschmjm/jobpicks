import { defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const mountPath = (env.VITE_APP_MOUNT_PATH || "").replace(/\/$/, "");
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
  const apiProxyPath = mountPath ? `${mountPath}/api` : "/api";

  return {
    base: mountPath ? `${mountPath}/` : "/",
    plugins: [react(), tailwindcss()],
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
    },
    server: {
      port: 5173,
      proxy: {
        [apiProxyPath]: {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
