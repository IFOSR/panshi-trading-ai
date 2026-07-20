import { expect, test } from "@playwright/test";

test("shows deterministic conclusion and all eight milestones", async ({ page }) => {
  await page.goto("/cases/case-1");

  await expect(page.getByTestId("current-action")).toContainText("等待补齐数据");
  await expect(page.getByTestId("strategy-milestone")).toHaveCount(8);
  await expect(page.getByText("下一里程碑")).toBeVisible();
  await expect(page.getByText("本次变化")).toBeVisible();
});

test("expands milestone audit evidence", async ({ page }) => {
  await page.goto("/cases/case-1");
  const firstMilestone = page.getByTestId("strategy-milestone").first();
  await firstMilestone.click();

  await expect(firstMilestone.getByText("规则 DQ-001")).toBeVisible();
  await expect(firstMilestone.getByText("证据与来源")).toBeVisible();
});
