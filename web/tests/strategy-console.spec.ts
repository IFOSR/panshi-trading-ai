import { expect, test } from "@playwright/test";

const chartFixture = "../tests/fixtures/charts/daily_boll_macd_volume.png";

test("opens the strategy list with one registered strategy", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "磐石交易AI" })).toBeVisible();
  await expect(page.getByTestId("conversation-sidebar")).toBeVisible();
  await expect(page.getByText("最近对话")).toBeVisible();
  const trigger = page.getByRole("button", { name: /分析策略/ });
  await expect(trigger).toContainText("结构确认策略");
  await trigger.click();
  const listbox = page.getByRole("listbox", { name: "分析策略" });
  await expect(listbox).toBeVisible();
  await expect(listbox.getByRole("option")).toHaveCount(1);
  await expect(listbox.getByRole("option")).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(listbox).toContainText("v1.0.0");
  await expect(listbox).toContainText("稳定版");
  await expect(page.getByLabel("告诉磐石你想分析什么")).toBeVisible();
  await expect(page.getByLabel("上传图表截图")).toBeVisible();
  await expect(page.getByRole("button", { name: "发送并分析" })).toBeVisible();
  await expect(page.getByText("截图必须包含")).toBeVisible();
  await expect(page.getByText("合约或品种标题")).toBeVisible();
});

test("closes the single-strategy list with Escape from the trigger", async ({
  page
}) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: /分析策略/ });

  await trigger.click();
  await trigger.press("Escape");

  await expect(page.getByRole("listbox", { name: "分析策略" })).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("keeps every strategy option inside the viewport", async ({
  page,
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/strategy-catalog", {
    data: { mode: "multi" }
  });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");
  await page.getByRole("button", { name: /分析策略/ }).click();

  const lastOption = page.getByRole("option").last();
  await expect(lastOption).toBeVisible();
  const optionBox = await lastOption.boundingBox();
  expect(optionBox).not.toBeNull();
  expect((optionBox?.y ?? 0) + (optionBox?.height ?? 0)).toBeLessThanOrEqual(720);
});

test("supports arrow navigation and closes on outside click", async ({ page }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: /分析策略/ });

  await trigger.press("ArrowDown");
  await expect(page.getByRole("option", { name: /结构确认策略/ })).toBeFocused();
  await page.getByRole("heading", { name: "磐石交易AI" }).click();

  await expect(page.getByRole("listbox", { name: "分析策略" })).toHaveCount(0);
});

test("selecting the current strategy only closes the list", async ({ page }) => {
  let switchRequests = 0;
  let analysisRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/strategy")) switchRequests += 1;
    if (request.url().includes("/analysis")) analysisRequests += 1;
  });

  await page.goto("/cases/case-live");
  await page.getByRole("button", { name: /分析策略/ }).click();
  await page.getByRole("option", { name: /结构确认策略/ }).click();

  await expect(page.getByRole("listbox", { name: "分析策略" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /分析策略/ })).toBeFocused();
  expect(switchRequests).toBe(0);
  expect(analysisRequests).toBe(0);
});

test("shows an attachment preview and submits the selected strategy", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("告诉磐石你想分析什么").fill(
    "分析 cf2609，给出当前应该如何操作。"
  );
  await page.getByLabel("上传图表截图").setInputFiles(chartFixture);

  await expect(page.getByTestId("attachment-preview")).toContainText(
    "daily_boll_macd_volume.png"
  );
  await page.getByLabel("已确认截图不含无关个人敏感信息").check();
  await page.getByRole("button", { name: "发送并分析" }).click();

  await expect(page.getByTestId("submission-progress")).toBeVisible();
  await expect(page).toHaveURL(/\/cases\/case-created-\d+/, {
    timeout: 20_000
  });
});

test("resumes the same partially completed conversation after refresh", async ({
  page
}) => {
  const submit = async () => {
    await page.getByLabel("告诉磐石你想分析什么").fill(
      "FAIL_ONCE 验证刷新后恢复同一会话。"
    );
    await page.getByLabel("上传图表截图").setInputFiles(chartFixture);
    await page.getByLabel("已确认截图不含无关个人敏感信息").check();
    await page.getByRole("button", { name: "发送并分析" }).click();
  };

  await page.goto("/");
  await submit();
  await expect(page.locator(".composer-error")).toContainText(
    "temporary analysis failure"
  );
  const recoveryHref = await page
    .getByRole("link", { name: "查看已创建会话" })
    .getAttribute("href");

  await page.reload();
  await expect(
    page.getByRole("link", { name: "查看已创建会话" })
  ).toHaveAttribute("href", recoveryHref ?? "");
  await submit();

  await expect(page).toHaveURL(
    `http://127.0.0.1:3107${recoveryHref}`,
    { timeout: 20_000 }
  );
});

test("renders the conclusion inside a conversation with a persistent composer", async ({
  page
}) => {
  await page.goto("/cases/case-live");

  await expect(page.getByTestId("conversation-sidebar")).toBeVisible();
  await expect(page.getByTestId("chat-message")).toHaveCount(4);
  await expect(page.getByTestId("strategy-conclusion")).toHaveCount(1);
  await expect(page.getByTestId("historical-conclusion")).toContainText(
    "等待补齐数据"
  );
  await expect(page.getByTestId("strategy-conclusion")).toContainText(
    "系统需要重新核验数据"
  );
  await expect(page.getByTestId("strategy-conclusion")).toContainText(
    "结构确认策略"
  );
  await expect(page.getByLabel("继续追问")).toBeVisible();
  await expect(page.getByRole("button", { name: "发送" })).toBeVisible();
  await expect(page.getByRole("button", { name: "查看策略审计" })).toBeVisible();
});

test("keeps the final action immutable while answering a follow-up", async ({
  page
}) => {
  await page.goto("/cases/case-live");
  const conclusion = page.getByTestId("strategy-conclusion");
  await expect(conclusion).toContainText("系统需要重新核验数据");

  await page.getByLabel("继续追问").fill("为什么不是继续持有？");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText("退出结论来自市场状态")).toBeVisible();
  await expect(conclusion).toContainText("系统需要重新核验数据");
  await expect(page.getByTestId("source-analysis-id").last()).toContainText(
    "analysis-live"
  );
});

test("uploads new evidence from the persistent composer and creates a version", async ({
  page
}) => {
  await page.goto("/cases/case-live");
  const historicalBefore = await page
    .getByTestId("historical-conclusion")
    .count();
  await page.getByLabel("上传新图表").setInputFiles(chartFixture);

  await expect(page.getByTestId("chat-attachment-preview")).toContainText(
    "daily_boll_macd_volume.png"
  );
  await page.getByLabel("确认新增截图隐私授权").check();
  await page.getByLabel("继续追问").fill("这是最新日线图，请重新分析。");
  await page.getByRole("button", { name: "用新证据重新分析" }).click();

  await expect(page.getByTestId("historical-conclusion")).toHaveCount(
    historicalBefore + 1
  );
  await expect(page.getByTestId("strategy-conclusion")).toContainText(
    "系统需要重新核验数据"
  );
  await expect(page.getByText("这是最新日线图，请重新分析。")).toBeVisible();
});

test("refreshes public market data into a new analysis version", async ({
  page
}) => {
  await page.goto("/cases/case-live");
  const historicalBefore = await page
    .getByTestId("historical-conclusion")
    .count();
  await page.getByRole("button", { name: "刷新行情重新分析" }).click();

  await expect(page.getByText("刷新公开行情并重新分析。")).toBeVisible();
  await expect(page.getByTestId("historical-conclusion")).toHaveCount(
    historicalBefore + 1
  );
  await expect(page.getByTestId("strategy-conclusion")).toHaveCount(1);
});

test("opens a dynamic strategy audit drawer on demand", async ({ page }) => {
  await page.goto("/cases/case-live");
  await expect(page.getByTestId("strategy-audit-drawer")).toHaveCount(0);

  await page.getByRole("button", { name: "查看策略审计" }).click();

  const drawer = page.getByTestId("strategy-audit-drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("结构确认策略 v1.0.0")).toBeVisible();
  await expect(drawer.getByTestId("strategy-milestone")).toHaveCount(8);
  await expect(drawer.getByTestId("original-evidence-image")).toBeVisible();
  await expect(drawer.getByText("本次变化", { exact: true })).toBeVisible();
});

test("changes strategy through the generic selector and records it in chat", async ({
  page,
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/strategy-catalog", {
    data: { mode: "multi" }
  });
  await page.goto("/cases/case-live");
  const historicalBefore = await page
    .getByTestId("historical-conclusion")
    .count();
  await page.getByRole("button", { name: /分析策略/ }).click();
  await page.getByRole("option", { name: /动量突破策略/ }).click();

  await expect(page.getByText("已切换至动量突破策略 v0.3.0")).toBeVisible();
  await expect(page.getByRole("button", { name: /分析策略/ })).toBeFocused();
  await expect(page.getByTestId("historical-conclusion")).toHaveCount(
    historicalBefore + 1
  );
});

test("handles genuine missing private facts inside the same conversation", async ({
  page
}) => {
  await page.goto("/cases/case-clarification-desktop");

  await expect(page.getByText("需要确认的私有事实")).toBeVisible();
  await expect(page.getByText("请确认：日线最后一根 K 线是否已经收盘？")).toBeVisible();
  await page.getByLabel("继续追问").fill(
    "日线和 60 分钟都已收盘，持仓量减少 4425，向下回踩未站回。"
  );
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText("我理解为", { exact: true })).toBeVisible();
  await expect(
    page.getByText("日线和 60 分钟均已收盘，持仓量减少 4425")
  ).toBeVisible();
  await page.getByRole("button", { name: "确认并重新分析" }).click();
  await expect(page.getByTestId("strategy-conclusion")).toContainText(
    "等待策略条件"
  );
});

test("restores a pending clarification proposal after refresh", async ({
  page
}) => {
  await page.goto("/cases/case-clarification-pending");

  await expect(page.getByText("我理解为", { exact: true })).toBeVisible();
  await expect(page.getByText("日线和 60 分钟均已收盘")).toBeVisible();
  await expect(page.getByText("你补充：日线和 60 分钟都已收盘。")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "确认并重新分析" })
  ).toBeVisible();

  await page.reload();

  await expect(page.getByText("我理解为", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "确认并重新分析" })
  ).toBeVisible();
});

test("conversation proxies enforce local origin and idempotency", async ({
  request
}) => {
  const crossOrigin = await request.post(
    "/api/cases/case-live/messages",
    {
      headers: {
        Origin: "https://attacker.example",
        "Idempotency-Key": "follow-up-1"
      },
      data: { message: "为什么？" }
    }
  );
  const missingKey = await request.post(
    "/api/cases/case-live/messages",
    {
      headers: { Origin: "http://127.0.0.1:3107" },
      data: { message: "为什么？" }
    }
  );

  expect(crossOrigin.status()).toBe(403);
  expect(missingKey.status()).toBe(400);
});

test("cancels permanent deletion without changing conversation history", async ({
  page,
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/reset-history");
  await page.goto("/");

  await page.getByRole("button", { name: "删除 au2612 对话" }).click();
  await expect(page.getByRole("alertdialog")).toContainText(
    "永久删除此对话及相关截图"
  );
  await page.getByRole("button", { name: "取消" }).click();

  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(page.getByText("au2612", { exact: true })).toBeVisible();
});

test("permanently deletes one non-active conversation", async ({
  page,
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/reset-history");
  await page.goto("/");

  await page.getByRole("button", { name: "删除 au2612 对话" }).click();
  await page.getByRole("button", { name: "永久删除" }).click();

  await expect(page.getByText("au2612", { exact: true })).toHaveCount(0);
  await expect(page.getByText("ag2612", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "删除 ag2612 对话" })
  ).toBeFocused();
});

test("deleting the active conversation returns to the new-analysis page", async ({
  page,
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/reset-history");
  await page.goto("/cases/case-live");

  await page.getByRole("button", { name: "删除 cf2609 对话" }).click();
  await page.getByRole("button", { name: "永久删除" }).click();

  await expect(page).toHaveURL("http://127.0.0.1:3107/");
  await expect(page.getByText("cf2609", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /新建分析/ })).toBeFocused();
});

test("permanently clears all conversation history", async ({
  page,
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/reset-history");
  await page.goto("/");

  await page.getByRole("button", { name: "清空全部对话" }).click();
  await expect(page.getByRole("alertdialog")).toContainText(
    "3 条对话及其全部截图"
  );
  await page.getByRole("button", { name: "全部永久删除" }).click();

  await expect(page.getByText("还没有分析记录。")).toBeVisible();
  await expect(page.getByRole("button", { name: "清空全部对话" })).toHaveCount(0);
});

test("shows the complete deletion count when history exceeds fifty items", async ({
  page,
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/reset-history");
  await request.post("http://127.0.0.1:3199/__test/history-size", {
    data: { extra: 50 }
  });
  await page.goto("/");

  await page.getByRole("button", { name: "清空全部对话" }).click();

  await expect(page.getByRole("alertdialog")).toContainText(
    "53 条对话及其全部截图"
  );
});

test("traps focus in the deletion dialog and restores the opener on Escape", async ({
  page,
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/reset-history");
  await page.goto("/");
  const opener = page.getByRole("button", { name: "删除 au2612 对话" });

  await opener.click();
  const cancel = page.getByRole("button", { name: "取消" });
  const confirm = page.getByRole("button", { name: "永久删除" });
  await expect(cancel).toBeFocused();
  await cancel.press("Shift+Tab");
  await expect(confirm).toBeFocused();
  await confirm.press("Tab");
  await expect(cancel).toBeFocused();
  await page.keyboard.press("Escape");

  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(opener).toBeFocused();
});

test("keeps focus inside the dialog while permanent deletion is running", async ({
  page,
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/reset-history");
  let releaseRequest!: () => void;
  const requestReleased = new Promise<void>((resolve) => {
    releaseRequest = resolve;
  });
  await page.route("**/api/cases/case-delete-a", async (route) => {
    await requestReleased;
    await route.continue();
  });
  await page.goto("/");
  await page.getByRole("button", { name: "删除 au2612 对话" }).click();
  await page.getByRole("button", { name: "永久删除" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByRole("button", { name: "正在删除" })).toBeDisabled();

  await page.keyboard.press("Tab");

  await expect(dialog).toBeFocused();
  releaseRequest();
  await expect(page.getByText("au2612", { exact: true })).toHaveCount(0);
});

test("keeps conversation history visible when permanent deletion fails", async ({
  page,
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/reset-history");
  await request.post("http://127.0.0.1:3199/__test/delete-failure", {
    data: { enabled: true }
  });
  await page.goto("/");

  const opener = page.getByRole("button", { name: "删除 au2612 对话" });
  await opener.click();
  await page.getByRole("button", { name: "永久删除" }).click();

  await expect(page.getByText("永久删除失败，请稍后重试。")).toBeVisible();
  await expect(page.getByText("au2612", { exact: true })).toBeVisible();
  await expect(opener).toBeFocused();
});

test("case deletion proxies enforce local origin and permanently remove history", async ({
  request
}) => {
  await request.post("http://127.0.0.1:3199/__test/reset-history");
  const denied = await request.delete("/api/cases/case-delete-a", {
    headers: { Origin: "https://attacker.example" }
  });
  expect(denied.status()).toBe(403);

  const deleted = await request.delete("/api/cases/case-delete-a", {
    headers: { Origin: "http://127.0.0.1:3107" }
  });
  expect(deleted.status()).toBe(200);
  expect(await deleted.json()).toEqual({ deleted: 1 });

  const afterSingle = await request.get("/api/cases");
  expect(
    (await afterSingle.json() as { case_id: string }[])
      .some((item) => item.case_id === "case-delete-a")
  ).toBe(false);

  const cleared = await request.delete("/api/cases", {
    headers: { Origin: "http://127.0.0.1:3107" }
  });
  expect(cleared.status()).toBe(200);
  expect((await cleared.json() as { deleted: number }).deleted).toBeGreaterThan(0);
  expect(await (await request.get("/api/cases")).json()).toEqual([]);
});

test("rejects cross-origin analysis submissions before parsing input", async ({
  request
}) => {
  const response = await request.post("/api/analysis", {
    headers: { Origin: "https://attacker.example" }
  });

  expect(response.status()).toBe(403);
});

test("rejects non-loopback access to the home page", async ({ request }) => {
  const response = await request.get("http://0.0.0.0:3107/");

  expect(response.status()).toBe(403);
});

test("serves original evidence without browser authentication", async ({
  request
}) => {
  const response = await request.get(
    "/api/cases/case-live/images/image-daily"
  );

  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("image/png");
});

test("does not fabricate analysis for a missing case", async ({ page }) => {
  await page.goto("/cases/missing");

  await expect(page.getByTestId("case-not-found")).toBeVisible();
  await expect(page.getByTestId("strategy-conclusion")).toHaveCount(0);
});
