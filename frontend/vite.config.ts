import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, /api is proxied to the FastAPI backend so no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
