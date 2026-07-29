import { expect, test } from "@playwright/test";


test.beforeEach(async ({ context }) => {
  await context.clearCookies();
});

test("redirects unauthenticated pages and rejects protected browser APIs", async ({
  page,
  request
}) => {
  await page.goto("/");

  await expect(page).toHaveURL(/\/login\?next=%2F$/);
  await expect(page.getByRole("heading", { name: "登录磐石交易AI" })).toBeVisible();

  const response = await request.get("/api/cases");
  expect(response.status()).toBe(401);
  expect(await response.json()).toEqual({ detail: "authentication required" });
});

test("shows a generic error for incorrect credentials", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("用户名").fill("ylfego");
  await page.getByLabel("密码").fill("incorrect");
  await page.getByRole("button", { name: "登录" }).click();

  await expect(
    page.locator(".login-form").getByRole("alert")
  ).toContainText("用户名或密码不正确");
  await expect(page.getByLabel("用户名")).toHaveValue("ylfego");
});

test("logs in, persists across refresh, and displays the current user", async ({
  page,
  context
}) => {
  await page.goto("/login?next=%2Fcases%2Fcase-live");
  await page.getByLabel("用户名").fill("ylfego");
  await page.getByLabel("密码").fill("test-password");
  await page.getByRole("button", { name: "登录" }).click();

  await expect(page).toHaveURL("/cases/case-live", { timeout: 20_000 });
  await expect(page.getByTestId("current-user")).toContainText("ylfego");
  const cookie = (await context.cookies()).find(
    (item) => item.name === "panshi_session"
  );
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");

  await page.reload();
  await expect(page.getByTestId("current-user")).toContainText("ylfego");
});

test("rejects external next targets and tampered cookies", async ({
  page,
  context
}) => {
  await page.goto("/login?next=https%3A%2F%2Fevil.example");
  await page.getByLabel("用户名").fill("ylfego");
  await page.getByLabel("密码").fill("test-password");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL("/");

  await context.addCookies([{
    name: "panshi_session",
    value: "tampered",
    domain: "127.0.0.1",
    path: "/"
  }]);
  await page.goto("/cases/case-live");
  await expect(page).toHaveURL(/\/login\?next=%2Fcases%2Fcase-live$/);
});

test("logout revokes the session and returns to login", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("用户名").fill("ylfego");
  await page.getByLabel("密码").fill("test-password");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL("/", { timeout: 20_000 });
  await expect(page.getByTestId("current-user")).toContainText("ylfego");

  const logout = page.getByRole("button", { name: "退出登录" });
  await logout.focus();
  await logout.press("Enter");

  await expect(page).toHaveURL("/login");
  await page.goto("/");
  await expect(page).toHaveURL(/\/login\?next=%2F$/);
});
