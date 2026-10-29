import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests",
  outputDir: "../artifacts/browser-tests/results",
  workers: 1,
  timeout: 180000,
  expect: { timeout: 45000 },
  reporter: "list",
  projects: [
    { name: "ui", testMatch: /(?:landing|layout)\.spec\.ts/, timeout: 30000 },
    { name: "workspace", testMatch: /workspace\.spec\.ts/ },
  ],
  use: {
    baseURL: "http://127.0.0.1:8768",
    browserName: "chromium",
    trace: "retain-on-failure",
  },
  webServer: [
    ...(process.env.CORVUS_TEST_DATABASE_URL && !process.env.CORVUS_TEST_API_URL
      ? [
          {
            command: "../.venv/bin/python ../tests/browser_server.py",
            url: "http://127.0.0.1:8769/api/health",
            reuseExistingServer: false,
            timeout: 120000,
          },
        ]
      : []),
    {
      command: "npm run dev -- --port 8768",
      url: "http://127.0.0.1:8768",
      env: {
        CORVUS_API_URL: process.env.CORVUS_TEST_API_URL ?? "http://127.0.0.1:8769",
        NEXT_TELEMETRY_DISABLED: "1",
      },
      reuseExistingServer: false,
      timeout: 60000,
    },
  ],
});
