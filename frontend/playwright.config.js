import os from "node:os";
import path from "node:path";
import { defineConfig } from "@playwright/test";

const dbFile = path.join(os.tmpdir(), "reviewai-e2e.db").replace(/\\/g, "/"); // sqlite URLs want forward slashes

// Starts the real backend (demo/mock-AI mode, throw-away DB) and the Vite dev server.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: "http://localhost:5173", trace: "retain-on-failure" },
  webServer: [
    {
      command: `${process.env.PYTHON || "python"} -m uvicorn app.main:app --port 8000`,
      cwd: "../backend",
      url: "http://localhost:8000/health",
      env: { DATABASE_URL: `sqlite:///${dbFile}`, GEMINI_API_KEY: "", RATE_LIMIT_PER_MIN: "1000" },
      reuseExistingServer: !process.env.CI,
    },
    { command: "npm run dev -- --port 5173 --strictPort", url: "http://localhost:5173", reuseExistingServer: !process.env.CI },
  ],
});
