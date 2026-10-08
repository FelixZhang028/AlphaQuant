import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 15000 },
  reporter: "list",
  globalTeardown: "./e2e/teardown.ts",
  use: {
    baseURL: "http://127.0.0.1:8001",
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "python -X utf8 tests/e2e/server.py --port 8001",
    cwd: resolve(import.meta.dirname, ".."),
    url: "http://127.0.0.1:8001/api/v1/health",
    reuseExistingServer: false,
    timeout: 45000,
  },
});
