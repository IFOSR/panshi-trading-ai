import { mkdirSync } from "node:fs";

import { expect, test as setup } from "@playwright/test";


const authState = "tmp/playwright-auth.json";

setup("authenticate strategy tests", async ({ page }) => {
  setup.setTimeout(90_000);
  await page.goto("/login");
  await page.getByLabel("用户名").fill("ylfego");
  await page.getByLabel("密码").fill("test-password");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL("/", { timeout: 45_000 });
  await expect(page.getByTestId("current-user")).toContainText("ylfego");
  mkdirSync("tmp", { recursive: true });
  await page.context().storageState({ path: authState });
});
