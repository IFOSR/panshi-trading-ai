import { expect, test } from "@playwright/test";


test.beforeEach(async ({ context }) => {
  await context.clearCookies();
});

test("serves the home page without authentication", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveURL("/");
  await expect(
    page.getByRole("heading", { name: "磐石交易AI" })
  ).toBeVisible();
  await expect(page.getByTestId("conversation-sidebar")).toBeVisible();
  await expect(page.getByLabel("告诉磐石你想分析什么")).toBeVisible();
});

test("serves protected browser APIs without authentication", async ({
  page,
  request
}) => {
  await page.goto("/");
  await expect(page).toHaveURL("/");

  const response = await request.get("/api/cases");
  expect(response.status()).toBe(200);
});

test("does not redirect to login and has no account footer", async ({
  page
}) => {
  await page.goto("/");

  await expect(page).toHaveURL("/");
  await expect(page.getByTestId("current-user")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "退出登录" })).toHaveCount(0);
  await expect(
    page.locator(".sidebar-account")
  ).toContainText("本地轻量模式");
});
