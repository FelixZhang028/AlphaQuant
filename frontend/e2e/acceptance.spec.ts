import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

const trades = "日期,股票代码,买卖方向,成交数量,成交价\n2023-01-03,000001,买入,100,12.5";

test("external duplicate confirmation resets for new materials and units", async ({ page }) => {
  await page.goto("/app/audits/external");
  await page.getByLabel("或粘贴含表头的成交表格").fill(trades + "\n" + trades.split("\n")[1]);
  await page.getByRole("button", { name: "识别字段并预览" }).click();
  await expect(page.getByLabel("日期列", { exact: true })).toHaveValue("日期");
  await page.getByRole("button", { name: "开始核查" }).click();
  await expect(page.getByRole("alert")).toContainText("重复成交");
  await page.getByLabel("我已核对并确认材料中的重复成交").check();
  await page.getByRole("button", { name: "开始核查" }).click();
  await expect(page.getByRole("heading", { name: "核查结果" })).toBeVisible();
  await page.getByLabel("数量单位").selectOption("手");
  await expect(page.getByLabel("我已核对并确认材料中的重复成交")).not.toBeChecked();
  await expect(page.getByRole("heading", { name: "核查结果" })).toHaveCount(0);
  await page.getByLabel("我已核对并确认材料中的重复成交").check();
  await page.getByLabel("上传 CSV（UTF-8 或 GB18030）").setInputFiles({ name: "new.csv", mimeType: "text/csv", buffer: Buffer.from(trades) });
  await expect(page.getByRole("heading", { name: /材料预览/ })).toHaveCount(0);
  await page.getByRole("button", { name: "识别字段并预览" }).click();
  await expect(page.getByLabel("我已核对并确认材料中的重复成交")).not.toBeChecked();
});

test("external delayed preview and check cannot restore superseded material", async ({ page }) => {
  await page.goto("/app/audits/external");
  await page.getByLabel("或粘贴含表头的成交表格").fill(trades);
  let release!: () => void;
  let arrived!: () => void;
  const requested = new Promise<void>(resolve => { arrived = resolve; });
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/audits/external/preview", async route => {
    const response = await route.fetch();
    arrived();
    await gate;
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "识别字段并预览" }).click();
  await requested;
  await page.getByLabel("或粘贴含表头的成交表格").fill(trades.replace("100", "200"));
  const delivered = page.waitForResponse("**/api/v1/audits/external/preview");
  release(); await delivered;
  await expect(page.getByRole("button", { name: "识别字段并预览" })).toBeEnabled();
  await expect(page.getByRole("heading", { name: /材料预览/ })).toHaveCount(0);
  await page.unroute("**/api/v1/audits/external/preview");
  await page.getByRole("button", { name: "识别字段并预览" }).click();
  await expect(page.getByLabel("数量单位")).toBeVisible();
  const requestedCheck = new Promise<void>(resolve => { arrived = resolve; });
  const gateCheck = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/audits/external/check", async route => {
    const response = await route.fetch(); arrived(); await gateCheck; await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "开始核查" }).click();
  await requestedCheck;
  await page.getByLabel("数量单位").selectOption("手");
  const checked = page.waitForResponse("**/api/v1/audits/external/check");
  release(); await checked;
  await expect(page.getByRole("button", { name: "开始核查" })).toBeEnabled();
  await expect(page.getByRole("heading", { name: "核查结果" })).toHaveCount(0);
});

test("external row errors are explicit and filtered exports retain all evidence", async ({ page }) => {
  await page.goto("/app/audits/external");
  const content = trades + "\n2023-01-03,600999,卖出,200,20";
  await page.getByLabel("或粘贴含表头的成交表格").fill(content.replace("12.5", "unknown"));
  await page.getByRole("button", { name: "识别字段并预览" }).click();
  await expect(page.getByLabel("日期列", { exact: true })).toHaveValue("日期");
  await page.getByRole("button", { name: "开始核查" }).click();
  await expect(page.getByRole("alert")).toContainText("错误行");
  await expect(page.getByRole("heading", { name: "核查结果" })).toHaveCount(0);
  await page.getByLabel("或粘贴含表头的成交表格").fill(content);
  await page.getByRole("button", { name: "识别字段并预览" }).click();
  await expect(page.getByLabel("数量单位")).toBeVisible();
  const checked = page.waitForResponse("**/api/v1/audits/external/check");
  await page.getByRole("button", { name: "开始核查" }).click();
  const response = await checked;
  expect(response.status()).toBe(200);
  const report = await response.json();
  expect(report.findings.rows.some((r: any) => r["结论"] === "证据不足")).toBe(true);
  expect(new Set(report.findings.rows.map((r: any) => r["表格行"]))).toEqual(new Set([2, 3]));
  await page.getByLabel("按结论筛选").selectOption("证据不足");
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载完整报告" }).click();
  expect(await readFile((await (await downloaded).path())!, "utf8")).toBe(report.markdown);
  await page.getByLabel("价格列", { exact: true }).selectOption("成交数量");
  await expect(page.getByRole("heading", { name: "核查结果" })).toHaveCount(0);
});

test("backfill selection survives reload and stop stays pending until worker exits", async ({ page }) => {
  let stopping = false;
  let active = true;
  const record = () => ({ id: "acceptance-backfill", status: active ? "RUNNING" : "STOPPED", stopping, start_date: "2023-01-03", end_date: "2023-04-28", datasets: ["bars"] });
  await page.route("**/api/v1/data/backfill/jobs", route => route.fulfill({ json: { items: [record(), { ...record(), id: "previous-backfill", status: "PARTIAL", stopping: false }] } }));
  await page.route("**/api/v1/data/backfill/jobs/*/log", route => route.fulfill({ json: { text: "回填检查点 2 / 4" } }));
  await page.route("**/api/v1/data/backfill/jobs/acceptance-backfill/stop", route => { stopping = true; return route.fulfill({ json: { stop_requested: true } }); });
  await page.goto("/app/data/backfill");
  await expect(page.getByRole("button", { name: "启动后台回填" })).toBeDisabled();
  await page.locator("tr.clickable").filter({ hasText: "previous-backfill" }).click();
  await expect(page.getByRole("button", { name: "沿原范围继续回填" })).toBeDisabled();
  await page.locator("tr.clickable").filter({ hasText: "acceptance-backfill" }).click();
  await page.getByRole("button", { name: "请求安全停止" }).click();
  await expect(page.getByRole("button", { name: "请求安全停止" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "沿原范围继续回填" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("button", { name: "请求安全停止" })).toBeDisabled();
  await expect(page.getByText("回填检查点 2 / 4", { exact: true })).toBeVisible();
  active = false;
  await page.reload();
  await expect(page.getByRole("button", { name: "请求安全停止" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "沿原范围继续回填" })).toBeEnabled();
});

test("an explicitly resubmitted invalid plan clears the old checked request", async ({
  page,
}) => {
  const defaults = await (
    await page.request.get("/api/v1/backtests/defaults")
  ).json();
  await page.addInitScript(
    (request) => {
      sessionStorage.setItem(
        "alphaquant:prepared-request",
        JSON.stringify(request),
      );
    },
    {
      ...defaults,
      strategy_plugin: "factor_composite",
      strategy_parameters: {
        factors_json: '[{"name":"momentum_20","weight":1}]',
      },
    },
  );
  await page.goto("/app/backtests/new");
  const catalog = await (await page.request.get("/api/v1/strategies")).json();
  const parameter = catalog.items
    .find((s: any) => s.plugin_name === "factor_composite")
    .parameters.find((p: any) => p.name === "factors_json");
  await page.getByRole("button", { name: "检查数据并准备回测" }).click();
  await page.getByRole("checkbox", { name: /我已核对这份已提交方案/ }).check();
  await expect(
    page.getByRole("button", { name: "运行已检查方案", exact: true }),
  ).toBeEnabled();
  await page.getByLabel(parameter.label, { exact: true }).fill("{invalid");
  await page.getByRole("button", { name: "检查数据并准备回测" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "运行已检查方案", exact: true }),
  ).toHaveCount(0);
});

test("plan versions compare unrun states and restore original execution settings", async ({
  page,
}) => {
  const runs = await (await page.request.get("/api/v1/runs")).json();
  const runId = runs.items[0].run_id;
  const first = await (
    await page.request.post("/api/v1/research/plans", {
      data: { title: "验收原始版本", run_id: runId },
    })
  ).json();
  const restored = await (
    await page.request.get(
      `/api/v1/research/plans/${first.plan_id}/${first.revision}/request`,
    )
  ).json();
  const secondResponse = await page.request.post("/api/v1/research/plans", {
    data: {
      title: "验收修改版本",
      plan_id: first.plan_id,
      request: { ...restored.request, initial_cash: 2000000 },
    },
  });
  expect(secondResponse.status()).toBe(201);
  await page.goto("/app/research/plans");
  const firstRow = page
    .locator("tr.clickable")
    .filter({ hasText: "验收原始版本" });
  const secondRow = page
    .locator("tr.clickable")
    .filter({ hasText: "验收修改版本" });
  await firstRow.click();
  await expect(
    page.getByRole("button", { name: "比较所选 2～4 个版本" }),
  ).toBeDisabled();
  await secondRow.click();
  await page.getByRole("button", { name: "比较所选 2～4 个版本" }).click();
  await expect(page.getByRole("heading", { name: "方案差异" })).toBeVisible();
  await expect(page.getByText("未运行", { exact: true })).toBeVisible();
  await secondRow.click();
  await page.getByRole("button", { name: "恢复并修改" }).click();
  await expect(page).toHaveURL(/backtests\/new/);
  await expect(page.getByLabel("初始资金（元）")).toHaveValue(
    String(restored.request.initial_cash),
  );
  await page.getByText("高级研究设置", { exact: true }).click();
  await expect(page.getByText(/保留原股票池、费用与风控/)).toBeVisible();
});

test("record comparison uses selected IDs, resets on filters and exports all columns", async ({
  page,
}) => {
  const catalog = await (
    await page.request.get("/api/v1/runs?limit=500")
  ).json();
  const ids = catalog.items.slice(0, 2).map((item: any) => item.run_id);
  await page.goto("/app/research/records");
  await expect(page.getByLabel("运行状态")).toHaveValue("SUCCESS");
  const compare = page.getByRole("button", { name: "对比所选成功结果" });
  await page.getByRole("row").filter({ hasText: ids[0] }).click();
  await expect(compare).toBeDisabled();
  await page.getByRole("row").filter({ hasText: ids[1] }).click();
  const posted = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/v1/runs/compare") &&
      request.method() === "POST",
  );
  await compare.click();
  expect((await posted).postDataJSON().run_ids).toEqual(ids);
  await expect(
    page.getByRole("heading", { name: "所选运行对比" }),
  ).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载对比 CSV" }).click();
  expect((await downloaded).suggestedFilename()).toBe(
    "backtest_comparison.csv",
  );
  await page.getByLabel("搜索名称或编号").fill(ids[0]);
  await expect(page.getByRole("heading", { name: "所选运行对比" })).toHaveCount(
    0,
  );
  await expect(page.getByRole("row").filter({ hasText: ids[1] })).toHaveCount(
    0,
  );
});
