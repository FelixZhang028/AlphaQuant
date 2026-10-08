import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const routes = [
  "/app",
  "/app/strategies",
  "/app/operations",
  "/app/strategies/ideas",
  "/app/strategies/visual",
  "/app/strategies/natural-language",
  "/app/strategies/python",
  "/app/backtests/new",
  "/app/experiments/optimization",
  "/app/experiments/walk-forward",
  "/app/factors/library",
  "/app/factors/evaluation",
  "/app/factors/combinations",
  "/app/factors/custom",
  "/app/knowledge",
  "/app/research/ai",
  "/app/research/records",
  "/app/research/plans",
  "/app/audits",
  "/app/audits/external",
  "/app/data/update",
  "/app/data/backfill",
  "/app/operations/jobs",
  "/app/data/sources",
  "/app/data/xtick",
  "/app/data/universe",
  "/app/risk",
  "/app/settings",
  "/app/account",
];
test("all workspace routes load real APIs without render or server failures", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 500)
      errors.push(`${response.status()} ${response.url()}`);
  });
  for (const route of routes) {
    await page.goto(route);
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.getByText("页面暂时无法显示")).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});
test("tool search and mobile navigation preserve all 23 entries", async ({
  page,
}) => {
  await page.goto("/app");
  await page.getByRole("button", { name: /搜索工具/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("link")).toHaveCount(23);
  await dialog.getByPlaceholder("搜索全部 23 个工具…").fill("股票池");
  await expect(dialog.getByRole("link")).toHaveCount(1);
  await dialog.getByRole("link").click();
  await expect(page).toHaveURL(/data\/universe/);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app");
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("link", { name: "数据与运行", exact: true }).click();
  await expect(page.locator("h1")).toHaveText("数据与运行");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
test("welcome language switching and research workflow", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "English" }).click();
  await expect(
    page.getByRole("button", { name: "Check environment" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "ideas to evidence",
  );
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "ideas to evidence",
  );
  await page.getByRole("button", { name: "中文" }).click();
  const previews = page.getByRole("tablist", { name: "五类功能" });
  await expect(previews.getByRole("tab")).toHaveCount(5);
  for (const tab of await previews.getByRole("tab").all()) {
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel")).toBeVisible();
  }
  await page.getByRole("link", { name: /开始研究/ }).click();
  await expect(page).toHaveURL(/\/app$/);
});
test("desktop and phone previews", async ({ page }) => {
  const directory = resolve(import.meta.dirname, "../../outputs/migration");
  await mkdir(directory, { recursive: true });
  await page.goto("/app");
  await expect(page.getByText("本机服务已连接")).toBeVisible();
  await page.screenshot({
    path: resolve(directory, "react-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () => (await page.locator(".sidebar").boundingBox())!.x)
    .toBeLessThanOrEqual(-200);
  await page.screenshot({
    path: resolve(directory, "react-mobile.png"),
    fullPage: true,
    animations: "disabled",
  });
});
test("backtest checks, submitted parameters, reload recovery and full report", async ({
  page,
}) => {
  await page.goto("/app/backtests/new");
  await page.getByRole("button", { name: "检查数据并准备回测" }).click();
  const run = page.getByRole("button", { name: "运行已检查方案", exact: true });
  await expect(run).toBeDisabled();
  await page.getByRole("checkbox", { name: /我已核对这份已提交方案/ }).check();
  await expect(run).toBeEnabled();
  await page.getByLabel("初始资金（元）").fill("2000000");
  await expect(page.getByText(/上方草稿已有修改/)).toBeVisible();
  await page.getByText("保存研究方案", { exact: true }).click();
  await page.getByLabel("方案名称").fill("已核对的浏览器方案");
  const savedResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/research/plans") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存当前版本" }).click();
  const savedPlan = await (await savedResponse).json();
  await expect(page.getByText(/方案已保存/)).toBeVisible();
  const request = page.waitForRequest(
    (r) => r.url().endsWith("/api/v1/tasks") && r.method() === "POST",
  );
  await run.click();
  const sent = (await request).postDataJSON();
  expect(sent.input.request.initial_cash).toBe(1000000);
  expect(sent.input.request.plan_id).toBe(savedPlan.plan_id);
  await page.reload();
  await expect(page.getByRole("heading", { name: "回测已完成" })).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByLabel("初始资金（元）")).toHaveValue("2000000");
  await expect(
    page.getByText(/这是上次已执行方案的结果，当前草稿尚未运行/),
  ).toBeVisible();
  await page.getByRole("link", { name: "打开完整报告" }).click();
  const completedRun = page.url().split("/").at(-1);
  const planRows = await (
    await page.request.get("/api/v1/research/plans")
  ).json();
  expect(
    planRows.items.some(
      (row: any) =>
        row.plan_id === savedPlan.plan_id && row.runs.includes(completedRun),
    ),
  ).toBeTruthy();
  await expect(
    page.getByRole("heading", { name: "策略与基准净值" }),
  ).toBeVisible();
  await expect(page.locator(".chart svg").first()).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整净值" }).click();
  expect((await download).suggestedFilename()).toContain("nav");
  await page.getByRole("tab", { name: "全部专业指标" }).click();
  await expect(page.getByText("佣金", { exact: true }).first()).toBeVisible();
  await page.getByRole("tab", { name: "交易与持仓" }).click();
  await page.getByRole("tab", { name: "完整交易", exact: true }).click();
  await expect(page.getByRole("link", { name: "下载全部 CSV" })).toBeVisible();
});
test("visual rule builder validates and saves a version", async ({ page }) => {
  await page.goto("/app/strategies/visual");
  await expect(page.getByLabel("策略名称")).not.toHaveValue("");
  await page.getByLabel("策略名称").fill("浏览器测试策略");
  await page.getByRole("button", { name: "添加条件" }).click();
  await page.getByRole("button", { name: "生成并检查策略" }).click();
  await expect(page.getByText("通过校验的规则", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "另存为我的策略" }).click();
  await expect(page.getByText(/策略已保存：/)).toBeVisible();
  await page.getByRole("button", { name: "保存为新版本" }).click();
  await page.getByRole("button", { name: "准备回测" }).click();
  await expect(
    page.getByRole("heading", { name: "可视化策略回测范围与参数" }),
  ).toBeVisible();
});
test("Python editor blocks dangerous code before registration", async ({
  page,
}) => {
  const catalog = await (
    await page.request.get("/api/v1/strategies/python")
  ).json();
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/strategies/python", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await pending;
    await route.fulfill({ json: catalog });
  });
  await page.goto("/app/strategies/python");
  await page.getByLabel("策略代码").fill("open('unwanted', 'w')");
  release();
  const posted = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/v1/strategies/python") &&
      request.method() === "POST",
  );
  await page.getByRole("button", { name: "检查并注册策略" }).click();
  expect((await posted).postDataJSON().code).toBe("open('unwanted', 'w')");
  await expect(page.getByRole("alert")).toContainText("请修复阻断项");
});
test("factor catalog selection and real factor report", async ({ page }) => {
  await page.goto("/app/factors/library");
  await page.getByLabel("关键词 / 编号").fill("momentum_20");
  await page.getByRole("button", { name: "momentum_20", exact: true }).click();
  await page.getByRole("button", { name: "用于因子评估" }).click();
  await expect(page.getByLabel("因子", { exact: true })).toHaveValue(
    "momentum_20",
  );
  await page.getByRole("button", { name: "开始因子评估" }).click();
  await expect(
    page.getByText("平均 Rank IC", { exact: true }).first(),
  ).toBeVisible({
    timeout: 30000,
  });
  await expect(page.locator(".chart svg").first()).toBeVisible();
});
test("knowledge saves and deletes exact entry", async ({ page }) => {
  await page.goto("/app/knowledge");
  await page
    .getByLabel("内容", { exact: true })
    .fill("浏览器隔离测试：保持证据可追溯。");
  await page.getByLabel("来源", { exact: true }).fill("E2E");
  await page.getByRole("button", { name: "保存知识" }).click();
  await expect(
    page.getByText("浏览器隔离测试：保持证据可追溯。"),
  ).toBeVisible();
  await page.reload();
  await page
    .locator(".knowledge-item")
    .filter({ hasText: "浏览器隔离测试：保持证据可追溯。" })
    .getByRole("button", { name: "删除此条" })
    .click();
  await expect(
    page
      .locator(".knowledge-item")
      .filter({ hasText: "浏览器隔离测试：保持证据可追溯。" }),
  ).toHaveCount(0);
});
test("external material mapping and complete markdown export", async ({
  page,
}) => {
  await page.goto("/app/audits/external");
  await page
    .getByLabel("或粘贴含表头的成交表格")
    .fill(
      "日期,股票代码,买卖方向,成交数量,成交价\n2023-01-03,000001,买入,100,12.5",
    );
  await page.getByRole("button", { name: "识别字段并预览" }).click();
  await expect(page.getByLabel("日期列", { exact: true })).toHaveValue("日期");
  await page.getByRole("button", { name: "开始核查" }).click();
  await expect(page.getByRole("heading", { name: "核查结果" })).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载完整报告" }).click();
  expect((await downloaded).suggestedFilename()).toContain(".md");
});
test("model keys are not restored to browser fields or local storage", async ({
  page,
}) => {
  await page.goto("/app/settings");
  await page.getByLabel("提供方", { exact: true }).selectOption("custom");
  await page.getByLabel("新的 API Key").fill("e2e-private-key");
  await page.getByLabel("模型名称").fill("test-model");
  await page
    .getByLabel("Base URL", { exact: true })
    .fill("http://127.0.0.1:12345/v1");
  await page.getByRole("button", { name: "仅保存配置" }).click();
  await expect(page.getByText("模型配置已保存")).toBeVisible();
  await expect(page.getByLabel("新的 API Key")).toHaveValue("");
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain(
    "e2e-private-key",
  );
});
test("AI full analysis and persistent contextual chat use offline model", async ({
  page,
}) => {
  await page.goto("/app/research/ai");
  await page.getByLabel("分析日期").fill("2023-04-28");
  await page
    .getByRole("checkbox", { name: "允许使用缓存的最终决策" })
    .uncheck();
  await page.getByRole("checkbox", { name: "分析后启用人为介入对话" }).check();
  await page.getByRole("button", { name: "开始 AI 分析", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "决策与研究证据" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByRole("heading", { name: "完整分析与过程回放" }),
  ).toBeVisible();
  await page
    .getByLabel("提出问题、质疑或补充观点")
    .fill("请解释这次分析的风险依据");
  await page.getByRole("button", { name: "发送观点" }).click();
  await expect(page.locator(".chat-history .assistant")).toBeVisible({
    timeout: 30000,
  });
  await page.reload();
  await expect(page.locator(".chat-history .assistant")).toBeVisible();
});
test("XTick catalog exposes every documented interface and typed controls", async ({
  page,
}) => {
  await page.goto("/app/data/xtick");
  const categories = page.getByLabel("分类", { exact: true });
  await expect(categories.locator("option")).toHaveCount(6);
  let total = 0;
  for (const value of await categories
    .locator("option")
    .evaluateAll((options) =>
      options.map((o) => (o as HTMLOptionElement).value),
    )) {
    await categories.selectOption(value);
    total += await page
      .getByLabel("接口", { exact: true })
      .locator("option")
      .count();
  }
  expect(total).toBe(85);
  await expect(page.getByRole("button", { name: "查询此接口" })).toBeEnabled();
});

test("optimization and walk-forward keep independent drafts across navigation and refresh", async ({
  page,
}) => {
  await page.goto("/app/experiments/optimization");
  await page.getByLabel("排序目标").selectOption("annual_return");
  await page.getByLabel("最大回撤约束（小数，可留空）").fill("0.12");
  await page.getByRole("link", { name: "滚动验证", exact: true }).click();
  await expect(page.getByLabel("排序目标")).toHaveValue("sharpe");
  await expect(page.getByLabel("最大回撤约束（小数，可留空）")).toHaveValue("");
  await page.getByLabel("排序目标").selectOption("calmar");
  await page.getByLabel("训练月数").fill("6");
  await page
    .getByRole("link", { name: "参数优化", exact: true })
    .last()
    .click();
  await expect(page.getByLabel("排序目标")).toHaveValue("annual_return");
  await expect(page.getByLabel("最大回撤约束（小数，可留空）")).toHaveValue(
    "0.12",
  );
  await page.reload();
  await expect(page.getByLabel("排序目标")).toHaveValue("annual_return");
  await page.getByRole("link", { name: "滚动验证", exact: true }).click();
  await expect(page.getByLabel("排序目标")).toHaveValue("calmar");
  await expect(page.getByLabel("训练月数")).toHaveValue("6");
});

test("a failed XTick submission clears the previous interface result", async ({
  page,
}) => {
  await page.route("**/api/v1/tasks/acceptance-xtick**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = path.endsWith("/events")
      ? { items: [], next_after: 0 }
      : path.endsWith("/result")
        ? { raw: { acceptance_marker: "old-success" }, tables: [] }
        : {
            id: "acceptance-xtick",
            kind: "xtick_query",
            status: "SUCCESS",
            result_available: true,
            progress: {},
            error: null,
          };
    await route.fulfill({ json });
  });
  let submissions = 0;
  await page.route("**/api/v1/tasks", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submissions += 1;
    await route.fulfill(
      submissions === 1
        ? { status: 202, json: { id: "acceptance-xtick" } }
        : {
            status: 422,
            json: {
              error: { code: "invalid_input", message: "验收：参数不合法" },
            },
          },
    );
  });
  await page.goto("/app/data/xtick");
  await page.getByRole("button", { name: "查询此接口" }).click();
  await expect(page.getByRole("heading", { name: "接口结果" })).toBeVisible();
  await page.getByRole("button", { name: "查询此接口" }).click();
  await expect(page.getByText("验收：参数不合法")).toBeVisible();
  await expect(page.getByRole("heading", { name: "接口结果" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "接口结果" })).toHaveCount(0);
});

test("universe additions, explicit removal confirmation and filters persist", async ({
  page,
}) => {
  await page.goto("/app/data/universe");
  await page
    .getByLabel("证券代码（多个可用逗号或换行分隔）")
    .fill("000003,000003");
  await page.getByRole("button", { name: "添加到股票池" }).click();
  await expect(page.getByText("已添加并归一化证券代码")).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: "000003.SZ" });
  await expect(row).toHaveCount(1);
  await row.click();
  const removeButton = page.getByRole("button", { name: "移除所选 1 只股票" });
  await expect(removeButton).toBeDisabled();
  await page
    .getByRole("checkbox", { name: "确认从股票池移除所选证券" })
    .check();
  await removeButton.click();
  await expect(row).toHaveCount(0);
  await page.getByLabel("最少上市天数").fill("62");
  await page.getByRole("button", { name: "保存过滤规则" }).click();
  await expect(page.getByText("过滤规则已保存")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("最少上市天数")).toHaveValue("62");
  await page.getByLabel("最少上市天数").fill("61");
  await page.getByRole("button", { name: "保存过滤规则" }).click();
  await expect(page.getByText("过滤规则已保存")).toBeVisible();
});

test("custom factors are available after refresh and only the selected factor is deleted", async ({
  page,
}) => {
  await page.goto("/app/factors/custom");
  await page.getByLabel("英文标识").fill("acceptance_factor");
  await page.getByLabel("中文名称").fill("验收因子");
  await page.getByRole("button", { name: "保存因子" }).click();
  await expect(page.getByText("因子已保存，可用于评价与组合。")).toBeVisible();
  await page.reload();
  const item = page
    .locator(".item-row")
    .filter({ hasText: "acceptance_factor" });
  await expect(item).toBeVisible();
  await item.getByRole("link", { name: "评估" }).click();
  await expect(page.getByLabel("因子", { exact: true })).toHaveValue(
    "acceptance_factor",
  );
  await page.goto("/app/factors/custom");
  await item.getByRole("button", { name: "删除该因子" }).click();
  await expect(item).toHaveCount(0);
});

test("all risk actions and numeric limits save and reload", async ({
  page,
}) => {
  await page.goto("/app/risk");
  await expect(page.getByLabel("最大总仓位")).toHaveValue("1");
  for (const value of ["reduce", "liquidate", "stop_new"]) {
    await page.getByLabel("回撤触线动作").selectOption(value);
    await page.getByRole("button", { name: "保存默认风险规则" }).click();
    await expect(page.getByText("默认风险规则已保存")).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("回撤触线动作")).toHaveValue(value);
  }
  await expect(page.getByLabel("最大持股数")).toHaveAttribute("step", "1");
  await expect(page.getByLabel("降仓目标权重")).toBeVisible();
});

test("filtered data CSV contains all rows beyond the table preview", async ({
  page,
}) => {
  await page.goto("/app/data/update");
  await page.getByRole("tab", { name: "股票行情", exact: true }).click();
  await page.getByLabel("证券代码（标准代码，逗号分隔）").fill("000001.SZ");
  const expected = await (
    await page.request.get(
      "/api/v1/data/tables/daily_bars?symbols=000001.SZ&limit=1",
    )
  ).json();
  expect(expected.total).toBeGreaterThan(200);
  const downloaded = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载全部 CSV" }).click();
  const stream = await (await downloaded).createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const lines = Buffer.concat(chunks).toString("utf8").trim().split(/\r?\n/);
  expect(lines.length - 1).toBe(expected.total);
  expect(
    lines.slice(1).every((line) => line.includes("000001.SZ")),
  ).toBeTruthy();
});

for (const walkForward of [false, true]) {
  test(`${walkForward ? "walk-forward" : "optimization"} runs the real engine, links children and reloads history`, async ({
    page,
  }) => {
    test.setTimeout(90000);
    const slug = walkForward ? "walk-forward" : "optimization";
    const kind = walkForward ? "walk_forward" : "optimization";
    const runs = await (
      await page.request.get("/api/v1/runs?limit=500")
    ).json();
    const baseline = runs.items.find(
      (r: any) => r.strategy_plugin === "a_share_momentum",
    ).run_id;
    const strategies = await (
      await page.request.get("/api/v1/strategies")
    ).json();
    const label = strategies.items
      .find((s: any) => s.plugin_name === "a_share_momentum")
      .parameters.find((p: any) => p.name === "short_window").label;
    await page.goto(`/app/experiments/${slug}?baseline=${baseline}`);
    await page
      .getByLabel(`${label} · 候选值`)
      .fill(walkForward ? "20" : "15,20");
    if (walkForward) {
      await page.getByLabel("总区间开始日期").fill("2022-07-01");
      await page.getByLabel("总区间结束日期").fill("2023-04-28");
      await page.getByLabel("训练月数").fill("3");
      await page.getByLabel("测试月数").fill("1");
      await page.getByLabel("步长月数").fill("1");
      await page.getByLabel("最多窗口").fill("1");
    }
    await page
      .getByRole("button", {
        name: walkForward ? "开始滚动验证" : "开始参数优化",
      })
      .click();
    await expect(page.getByRole("heading", { name: "实验结果" })).toBeVisible({
      timeout: 60000,
    });
    const taskId = await page.evaluate(
      (key) => JSON.parse(localStorage.getItem(`alphaquant:v1:job:${key}`)!),
      kind,
    );
    const result = await (
      await page.request.get(`/api/v1/tasks/${taskId}/result`)
    ).json();
    const identifier = result.optimization_id || result.validation_id;
    const child = walkForward
      ? result.windows.rows[0].test_run_id
      : result.experiments.rows[0].run_id;
    const link = page.getByRole("link", {
      name: /打开(组合|测试窗口) 1 的完整回测/,
    });
    await expect(link).toHaveAttribute("href", `/app/backtests/${child}`);
    await expect(
      page
        .getByLabel("选择已保存实验")
        .locator(`option[value="${identifier}"]`),
    ).toHaveCount(1);
    await page.getByLabel("选择已保存实验").selectOption(identifier);
    await expect(
      page.getByRole("link", { name: "下载保存实验 CSV" }),
    ).toBeVisible();
    await expect(link).toHaveAttribute("href", `/app/backtests/${child}`);
    const exported = await page.request.get(
      `/api/v1/experiments/${slug}/${identifier}/export.csv`,
    );
    expect(exported.status()).toBe(200);
    expect((await exported.text()).trim().split(/\r?\n/).length - 1).toBe(
      walkForward ? 1 : 2,
    );
    await page.reload();
    await expect(page.getByRole("heading", { name: "实验结果" })).toBeVisible();
  });
}

test("natural language requires current confirmation, clears saved state and discards without registering", async ({
  page,
}) => {
  const templates = await (
    await page.request.get("/api/v1/strategies/templates")
  ).json();
  const packageValue = await (
    await page.request.get(
      `/api/v1/strategies/templates/${templates.items[0].template_id}/balanced`,
    )
  ).json();
  let submissions = 0;
  let saves = 0;
  page.on("request", (request) => {
    if (
      request.url().endsWith("/api/v1/strategies/packages") &&
      request.method() === "POST"
    )
      saves++;
  });
  await page.route("**/api/v1/tasks", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submissions++;
    await route.fulfill(
      submissions <= 2
        ? { status: 202, json: { id: "acceptance-nl" } }
        : {
            status: 422,
            json: {
              error: { code: "model_failure", message: "验收：模型生成失败" },
            },
          },
    );
  });
  await page.route("**/api/v1/tasks/acceptance-nl**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    await route.fulfill({
      json: path.endsWith("/events")
        ? { items: [], next_after: 0 }
        : path.endsWith("/result")
          ? {
              definition: packageValue.definition,
              explanation: "固定模型响应，后端仍校验保存的规则。",
            }
          : {
              id: "acceptance-nl",
              kind: "nl_strategy",
              status: "SUCCESS",
              result_available: true,
              progress: {},
              error: null,
            },
    });
  });
  await page.goto("/app/strategies/natural-language");
  await page.getByLabel("策略描述").fill("创建可核对的动量策略");
  await page.getByRole("button", { name: "生成策略草稿" }).click();
  const save = page.getByRole("button", { name: "确认并保存" });
  await expect(save).toBeDisabled();
  await page
    .getByRole("checkbox", { name: "我已核对规则与原始描述一致" })
    .check();
  await save.click();
  await expect(
    page.getByRole("link", { name: /已保存 · 去策略工作室回测/ }),
  ).toBeVisible();
  expect(saves).toBe(1);
  await page.getByRole("button", { name: "填入示例" }).click();
  await expect(save).toBeDisabled();
  await expect(
    page.getByRole("link", { name: /已保存 · 去策略工作室回测/ }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "生成策略草稿" }).click();
  await expect(
    page.getByRole("heading", { name: "人工核对规则" }),
  ).toBeVisible();
  await expect(save).toBeDisabled();
  await page.getByRole("button", { name: "放弃并重新描述" }).click();
  await expect(page.getByRole("heading", { name: "人工核对规则" })).toHaveCount(
    0,
  );
  expect(saves).toBe(1);
  await page.getByRole("button", { name: "生成策略草稿" }).click();
  await expect(page.getByText("验收：模型生成失败")).toBeVisible();
  await expect(page.getByRole("heading", { name: "人工核对规则" })).toHaveCount(
    0,
  );
});

test("factor combination runs, exports the full specification and blocks changed inputs", async ({
  page,
}) => {
  await page.goto("/app/factors/combinations");
  await page
    .getByLabel("选择至少两个因子（可多选）")
    .selectOption(["momentum_20", "reversal_5"]);
  await page.getByLabel("训练开始").fill("2022-07-01");
  await page.getByLabel("训练结束").fill("2022-12-30");
  await page.getByLabel("测试开始").fill("2023-01-03");
  await page.getByLabel("测试结束").fill("2023-04-28");
  await page.getByRole("button", { name: "训练权重并在测试期验证" }).click();
  await expect(page.getByRole("heading", { name: "组合研究报告" })).toBeVisible(
    { timeout: 30000 },
  );
  const prepare = page.getByRole("button", { name: "使用验证过的组合回测" });
  await expect(prepare).toBeEnabled();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载完整研究 JSON" }).click();
  const stream = await (await downloaded).createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const result = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  expect(result.spec).toHaveLength(2);
  expect(result.factor_fingerprint).toBeTruthy();
  await page.getByLabel("缺失值处理").selectOption("median");
  await expect(prepare).toBeDisabled();
  await page.getByLabel("缺失值处理").selectOption("drop");
  await prepare.click();
  await expect(page).toHaveURL(/backtests\/new/);
  await expect(page.getByLabel("策略", { exact: true })).toHaveValue(
    "factor_composite",
  );
});

test("guided research invalidates prepared rules on edits and restores its draft", async ({
  page,
}) => {
  await page.goto("/app/strategies/ideas");
  await page.getByLabel("持股数", { exact: true }).fill("2");
  await page.getByLabel("开始日期", { exact: true }).fill("2023-01-03");
  await page.getByLabel("结束日期", { exact: true }).fill("2023-04-28");
  await page.getByRole("button", { name: "生成待检查的研究规则" }).click();
  await expect(
    page.getByRole("heading", { name: "确认规则并验证数据" }),
  ).toBeVisible();
  await page
    .getByLabel("初始资金（元）", { exact: true })
    .first()
    .fill("1500000");
  await expect(
    page.getByRole("heading", { name: "确认规则并验证数据" }),
  ).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel("初始资金（元）", { exact: true })).toHaveValue(
    "1500000",
  );
  await page.getByRole("button", { name: "生成待检查的研究规则" }).click();
  await page.getByRole("button", { name: "检查数据并准备回测" }).click();
  await expect(
    page.getByRole("button", { name: "运行已检查方案", exact: true }),
  ).toBeDisabled();
});

test("search empty state and account return keep the original workspace", async ({
  page,
}) => {
  await page.goto("/app/factors/library");
  await page.getByRole("link", { name: "个人中心", exact: true }).click();
  await expect(page.getByRole("link", { name: "返回来源页" })).toHaveAttribute(
    "href",
    "/app/factors/library",
  );
  await page.getByRole("link", { name: "返回来源页" }).click();
  await expect(page).toHaveURL(/factors\/library/);
  await page.getByRole("button", { name: /搜索工具/ }).click();
  await page.getByPlaceholder("搜索全部 23 个工具…").fill("不存在的工具xxxx");
  await expect(
    page.getByRole("dialog").getByText("没有匹配的工具。"),
  ).toBeVisible();
  await expect(page.getByRole("dialog").getByRole("link")).toHaveCount(0);
  await page.getByRole("button", { name: "关闭搜索" }).click();
  await page.evaluate(() =>
    sessionStorage.setItem(
      "alphaquant:last-internal-page",
      "https://example.com",
    ),
  );
  await page.goto("/app/account");
  await expect(page.getByRole("link", { name: "返回来源页" })).toHaveAttribute(
    "href",
    "/app",
  );
});

test("four research stages preserve the backtest draft and record filters use actual run kinds", async ({
  page,
}) => {
  await page.goto("/app/backtests/new");
  await page.getByLabel("初始资金（元）").fill("1750000");
  const stages = page.getByRole("navigation", { name: "研究阶段" });
  await expect(stages.getByRole("link")).toHaveCount(4);
  await stages.getByRole("link", { name: "风险规则", exact: true }).click();
  await expect(page).toHaveURL(/\/risk/);
  await page.goBack();
  await expect(page.getByLabel("初始资金（元）")).toHaveValue("1750000");
  await page
    .getByRole("navigation", { name: "研究阶段" })
    .getByRole("link", { name: "方案复用" })
    .click();
  await expect(page).toHaveURL(/research\/plans/);
  await page.goto("/app/research/records");
  const catalog = await (
    await page.request.get("/api/v1/runs?q=does-not-match")
  ).json();
  await expect(page.getByLabel("运行类型").locator("option")).toHaveCount(
    catalog.run_kinds.length + 1,
  );
  const options = await page
    .getByLabel("运行类型")
    .locator("option")
    .evaluateAll((items) =>
      items.map((item) => (item as HTMLOptionElement).value),
    );
  expect(options).toEqual(["", ...catalog.run_kinds]);
  expect(options).not.toContain("walk_forward_training");
});

test("Python upload rejects invalid UTF-8 and registers, reloads and removes valid source", async ({
  page,
}) => {
  const catalog = await (
    await page.request.get("/api/v1/strategies/python")
  ).json();
  await page.goto("/app/strategies/python");
  const upload = page.getByLabel("上传 .py 文件（UTF-8）");
  await upload.setInputFiles({
    name: "invalid.py",
    mimeType: "text/x-python",
    buffer: Buffer.from([0xff, 0xfe]),
  });
  await expect(page.getByRole("alert")).toBeVisible();
  await upload.setInputFiles({
    name: "acceptance.py",
    mimeType: "text/x-python",
    buffer: Buffer.from(catalog.starter),
  });
  await expect(page.getByLabel("策略代码")).toHaveValue(catalog.starter);
  await page
    .getByRole("checkbox", { name: "我已阅读检查结果，并了解提示的风险" })
    .check();
  await page.getByRole("button", { name: "检查并注册策略" }).click();
  await expect(page.getByText(/已注册：/)).toBeVisible();
  const selected = await page
    .getByLabel("选择策略", { exact: true })
    .inputValue();
  await page.reload();
  await page.getByLabel("选择策略", { exact: true }).selectOption(selected);
  await page.getByRole("button", { name: "载入源码" }).click();
  await expect(page.getByLabel("策略代码")).toHaveValue(catalog.starter);
  await page.getByRole("button", { name: "准备该策略回测" }).click();
  await expect(page.getByLabel("策略", { exact: true })).toHaveValue(selected);
  await page.getByRole("button", { name: "删除所选策略" }).click();
  await expect(
    page
      .getByLabel("选择策略", { exact: true })
      .locator(`option[value="${selected}"]`),
  ).toHaveCount(0);
});

test("every strategy exposes metadata parameter defaults, types and bounds", async ({
  page,
}) => {
  const catalog = await (await page.request.get("/api/v1/strategies")).json();
  await page.goto("/app/backtests/new");
  const strategy = page.getByLabel("策略", { exact: true });
  await expect(strategy.locator("option")).toHaveCount(catalog.items.length);
  for (const item of catalog.items) {
    await strategy.selectOption(item.plugin_name);
    for (const parameter of item.parameters) {
      const field = page
        .getByLabel(parameter.label || parameter.name, { exact: true })
        .first();
      await expect(field).toHaveValue(String(parameter.default ?? ""));
      if (
        ["integer", "number"].includes(parameter.kind) &&
        !parameter.choices?.length
      ) {
        await expect(field).toHaveAttribute("type", "number");
        await expect(field).toHaveAttribute(
          "step",
          parameter.kind === "integer" ? "1" : "any",
        );
        if (parameter.minimum !== null)
          await expect(field).toHaveAttribute("min", String(parameter.minimum));
        if (parameter.maximum !== null)
          await expect(field).toHaveAttribute("max", String(parameter.maximum));
      }
    }
  }
  await page.getByText("高级研究设置", { exact: true }).click();
  await expect(page.getByLabel("组合分配").locator("option")).toHaveCount(4);
  await expect(page.getByLabel("股票池口径").locator("option")).toHaveCount(2);
});

test("every visual template and style loads a current validated definition", async ({
  page,
}) => {
  const catalog = await (
    await page.request.get("/api/v1/strategies/templates")
  ).json();
  await page.goto("/app/strategies/visual");
  await page.getByRole("tab", { name: "策略模板", exact: true }).click();
  for (const template of catalog.items) {
    for (const style of Object.keys(catalog.styles)) {
      await page.getByLabel("策略模板").selectOption(template.template_id);
      await page.getByLabel("研究风格").selectOption(style);
      const expected = await (
        await page.request.get(
          `/api/v1/strategies/templates/${template.template_id}/${style}`,
        )
      ).json();
      await expect(page.getByLabel("策略名称")).toHaveValue(
        expected.definition.name,
      );
      await expect(page.getByLabel("持股数", { exact: true })).toHaveValue(
        String(expected.top_n),
      );
      await page.getByRole("button", { name: "生成并检查策略" }).click();
      await expect(
        page.getByRole("button", { name: "另存为我的策略" }),
      ).toBeEnabled();
    }
  }
  await page.getByLabel("策略名称").fill("已修改模板");
  await expect(
    page.getByRole("button", { name: "另存为我的策略" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "准备回测", exact: true }),
  ).toBeDisabled();
});
