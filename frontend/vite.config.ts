import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy sends /api and /healthz to the control plane so `npm run dev`
// works against a locally-running backend. In production the built assets are
// served by FastAPI itself, so no proxy is involved.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8200", changeOrigin: true },
      "/healthz": { target: "http://localhost:8200", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
