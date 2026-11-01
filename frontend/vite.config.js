import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// /api/* is proxied to FastAPI so cookies (GitHub session) stay same-origin.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") } } },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.js"], css: false, include: ["src/**/*.test.{js,jsx}"] },
});
