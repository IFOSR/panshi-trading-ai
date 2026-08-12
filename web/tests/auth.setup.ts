import { mkdirSync } from "node:fs";

import { test as setup } from "@playwright/test";


const authState = "tmp/playwright-auth.json";

setup("prepare strategy tests without authentication", async ({ page }) => {
  setup.setTimeout(90_000);
  // 登录已取消：直接访问首页确认可用，并保存空 storage state
  await page.goto("/");
  mkdirSync("tmp", { recursive: true });
  await page.context().storageState({ path: authState });
});
