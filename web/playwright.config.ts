import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  webServer: [
    {
      command: "node tests/api-server.mjs",
      port: 3199,
      reuseExistingServer: false
    },
    {
      command: "NEXT_DIST_DIR=.next-playwright TRADING_AGENT_ENVIRONMENT=local TRADING_API_URL=http://127.0.0.1:3199 TRADING_AGENT_API_TOKEN=test-api-token TRADING_AGENT_PRIVACY_REVIEW_TOKEN=test-privacy-token npm run dev -- --hostname panshi.localhost --port 3107",
      port: 3107,
      reuseExistingServer: false
    }
  ],
  use: {
    baseURL: "http://127.0.0.1:3107"
  },
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/
    },
    {
      name: "auth",
      testMatch: /auth\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] }
    },
    {
      name: "desktop",
      dependencies: ["setup"],
      testIgnore: [/auth\.setup\.ts/, /auth\.spec\.ts/],
      use: {
        ...devices["Desktop Chrome"],
        storageState: "tmp/playwright-auth.json"
      }
    }
  ]
});
