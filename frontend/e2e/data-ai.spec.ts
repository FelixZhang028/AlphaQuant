import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("daily updates block active backfill, validate dates and preserve partial results after reload", async ({ page }) => {
  let active = true;
  let submitted: any;
  const task = { id: "acceptance-update", kind: "data_update", status: "PARTIAL", result_available: true,
    progress: { stage: "complete", completed: 1, total: 2 }, error: null };
  const results = [
    { dataset: "daily_bars", status: "SUCCESS", rows: 300, version: "successful-version" },
    { dataset: "benchmark_bars", status: "FAILED", rows: 0, error: "供应商暂时不可用" },
  ];
  await page.route("**/api/v1/data/backfill/jobs", route => route.fulfill({ json: { items: active ? [{ id: "active", status: "RUNNING" }] : [] } }));
  await page.route("**/api/v1/tasks", route => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 202, json: task });
  });
  await page.route("**/api/v1/tasks/acceptance-update", route => route.fulfill({ json: task }));
  await page.route("**/api/v1/tasks/acceptance-update/events?**", route => route.fulfill({ json: { items: [], next_after: 0 } }));
  await page.route("**/api/v1/tasks/acceptance-update/result", route => route.fulfill({ json: { results } }));
  await page.goto("/app/data/update");
  await expect(page.getByRole("button", { name: "提交后台更新" })).toBeDisabled();
  await expect(page.getByText(/全市场回填正在运行/)).toBeVisible();
  active = false;
  await page.getByRole("button", { name: "刷新概览" }).click();
  await expect(page.getByRole("button", { name: "提交后台更新" })).toBeEnabled();
  await page.getByLabel("股票日线", { exact: true }).uncheck();
  await page.getByLabel("基准行情", { exact: true }).uncheck();
  await expect(page.getByRole("button", { name: "提交后台更新" })).toBeDisabled();
  await page.getByLabel("股票日线", { exact: true }).check();
  await page.getByLabel("基准行情", { exact: true }).check();
  await page.getByLabel("开始日期", { exact: true }).fill("2023-04-28");
  await page.getByLabel("结束日期", { exact: true }).fill("2023-01-03");
  await page.getByRole("button", { name: "提交后台更新" }).click();
  expect(submitted).toBeUndefined();
  const source = page.getByLabel("本次首选行情来源");
  await expect(source.locator("option")).not.toHaveCount(1);
  const provider = await source.locator("option").nth(1).getAttribute("value");
  await source.selectOption(provider!);
  await page.getByLabel("允许自动回退").uncheck();
  await page.getByLabel("基准代码（可多个，逗号分隔）").fill("000300.SH,000905.SH");
  await page.getByLabel("开始日期", { exact: true }).fill("2023-01-03");
  await page.getByLabel("结束日期", { exact: true }).fill("2023-04-28");
  await page.getByRole("button", { name: "提交后台更新" }).click();
  await expect(page.getByRole("heading", { name: "更新反馈" })).toBeVisible();
  expect(submitted).toEqual({ kind: "data_update", input: {
    start_date: "2023-01-03", end_date: "2023-04-28", datasets: ["daily_bars", "benchmark_bars"],
    market_source_order: [provider], allow_market_fallback: false, benchmark_symbols: ["000300.SH", "000905.SH"],
  } });
  await page.reload();
  await expect(page.getByText("successful-version", { exact: true })).toBeVisible();
  await expect(page.getByText("供应商暂时不可用", { exact: true })).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载全部更新结果" }).click();
  const csv = await readFile((await (await downloaded).path())!, "utf8");
  expect(csv).toContain("successful-version");
  expect(csv).toContain("供应商暂时不可用");
  expect(csv.trim().split(/\r?\n/)).toHaveLength(3);
});

test("benchmark selection keeps chart table and complete CSV on the same index", async ({ page }) => {
  const rows = ["000300.SH", "000905.SH"].flatMap(symbol => Array.from({ length: 260 }, (_, i) => ({ symbol, trade_date: new Date(Date.UTC(2023, 0, i + 1)).toISOString().slice(0, 10), raw_close: i + 100 })));
  await page.route("**/api/v1/data/tables/benchmark_bars?**", route => {
    const url = new URL(route.request().url());
    const symbols = url.searchParams.getAll("symbols");
    const filtered = rows.filter(row => !symbols.length || symbols.includes(row.symbol));
    const offset = Number(url.searchParams.get("offset") || 0);
    const limit = Number(url.searchParams.get("limit") || 500);
    return route.fulfill({ json: { columns: ["symbol", "trade_date", "raw_close"], rows: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit } });
  });
  await page.route("**/api/v1/data/tables/benchmark_bars/export.csv?**", route => {
    const symbol = new URL(route.request().url()).searchParams.get("symbols");
    return route.fulfill({ contentType: "text/csv", headers: { "Content-Disposition": 'attachment; filename="benchmark_bars.csv"' }, body: "symbol,trade_date,raw_close\n" + rows.filter(r => r.symbol === symbol).map(r => `${r.symbol},${r.trade_date},${r.raw_close}`).join("\n") });
  });
  await page.goto("/app/data/update");
  await page.getByRole("tab", { name: "基准行情", exact: true }).click();
  await expect(page.getByLabel("绘图基准").locator("option")).toHaveCount(2);
  await page.getByLabel("绘图基准").selectOption("000905.SH");
  await expect(page.getByRole("heading", { name: "000905.SH", exact: true })).toBeVisible();
  const link = page.getByRole("link", { name: "下载全部 CSV" });
  await expect(link).toHaveAttribute("href", /symbols=000905.SH/);
  await expect(page.locator("tbody")).toContainText("000905.SH");
  await expect(page.locator("tbody")).not.toContainText("000300.SH");
  const downloaded = page.waitForEvent("download");
  await link.click();
  const csv = await readFile((await (await downloaded).path())!, "utf8");
  expect(csv.trim().split(/\r?\n/)).toHaveLength(261);
  expect(csv).not.toContain("000300.SH");
});

test("data overview exposes empty warehouses and recovers from read failures", async ({ page }) => {
  let fail = true;
  await page.route("**/api/v1/data/overview", route => route.fulfill(fail
    ? { status: 503, json: { error: { code: "read_failed", message: "仓库读取失败" } } }
    : { json: { configured_symbol_count: 4, security_count: 0, market: { rows: 0, symbol_count: 0, unknown_status_rows: 0, coverage_ratio: null } } }));
  await page.goto("/app/data/update");
  await expect(page.getByRole("alert")).toContainText("仓库读取失败");
  fail = false;
  await page.getByRole("button", { name: "刷新概览" }).click();
  await expect(page.getByText("仓库暂无股票行情，请先选择数据集并更新。")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("tab", { name: "股票池覆盖", exact: true }).click();
  await expect(page.getByRole("heading", { name: "配置股票池覆盖率" })).toBeVisible();
  await expect(page.getByRole("link", { name: "下载全部 CSV" })).toHaveAttribute("href", "/api/v1/data/coverage/export.csv");
  await page.getByRole("tab", { name: "基准行情", exact: true }).click();
  await expect(page.getByText("当前范围没有基准行情。")).toBeVisible();
});

for (const [tab, table] of [["证券主表", "security_master"], ["数据版本", "data_manifests"]]) {
  test(`data ${table} pagination and full export retain names sources and versions`, async ({ page }) => {
    const rows = Array.from({ length: 605 }, (_, i) => table === "security_master"
      ? { symbol: `${String(i).padStart(6, "0")}.SZ`, name: `验收证券${i}`, security_type: "stock" }
      : { version_id: `验收版本${i}`, source: "baostock", provider_route: "akshare:failed -> baostock:success", fallback_used: true, completed_at: "2023-04-28T10:00:00", error: "token=***" });
    const columns = Object.keys(rows[0]);
    await page.route(`**/api/v1/data/tables/${table}?**`, route => {
      const url = new URL(route.request().url());
      const offset = Number(url.searchParams.get("offset") || 0);
      const limit = Number(url.searchParams.get("limit") || 200);
      return route.fulfill({ json: { rows: rows.slice(offset, offset + limit), columns, total: 605, offset, limit } });
    });
    await page.route(`**/api/v1/data/tables/${table}/export.csv`, route => route.fulfill({ contentType: "text/csv", headers: { "Content-Disposition": `attachment; filename="${table}.csv"` }, body: columns.join(",") + "\n" + rows.map(row => columns.map(key => (row as any)[key]).join(",")).join("\n") }));
    await page.goto("/app/data/update");
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await expect(page.locator("tbody")).toContainText(table === "security_master" ? "验收证券0" : "验收版本0");
    await page.getByRole("button", { name: "下一批", exact: true }).click();
    await expect(page.locator("tbody")).toContainText(table === "security_master" ? "验收证券200" : "验收版本200");
    const downloaded = page.waitForEvent("download");
    await page.getByRole("link", { name: "下载全部 CSV" }).click();
    const csv = await readFile((await (await downloaded).path())!, "utf8");
    expect(csv.trim().split(/\r?\n/)).toHaveLength(606);
    expect(csv).toContain(table === "security_master" ? "验收证券604" : "验收版本604");
    if (table === "data_manifests") expect(csv).toContain("akshare:failed -> baostock:success");
  });
}

test("AI conversation retains completed history through submission failure reload and retry", async ({ page }) => {
  await page.goto("/app/research/ai");
  await page.getByLabel("分析日期").fill("2023-04-28");
  await page.getByLabel("允许使用缓存的最终决策").uncheck();
  await page.getByLabel("分析后启用人为介入对话").check();
  await page.getByRole("button", { name: "开始 AI 分析", exact: true }).click();
  await expect(page.getByRole("heading", { name: "完整分析与过程回放" })).toBeVisible({ timeout: 30000 });
  await page.getByLabel("提出问题、质疑或补充观点").fill("第一轮：请解释风险依据");
  const firstRequest = page.waitForResponse(response => response.url().endsWith("/api/v1/tasks") && response.request().postDataJSON().kind === "ai_chat");
  await page.getByRole("button", { name: "发送观点" }).click();
  const first = await (await firstRequest).json();
  await expect(page.locator(".chat-history .assistant")).toHaveCount(1, { timeout: 30000 });
  let failures = 0;
  const failedTask = { id: "chat-worker-failed", kind: "ai_chat", status: "FAILED", result_available: false,
    progress: { stage: "ai_chat", completed: 0, total: 1 }, error: { code: "model_error", message: "后台模型请求失败" } };
  await page.route("**/api/v1/tasks/chat-worker-failed", route => route.fulfill({ json: failedTask }));
  await page.route("**/api/v1/tasks/chat-worker-failed/events?**", route => route.fulfill({ json: { items: [], next_after: 0 } }));
  await page.route("**/api/v1/tasks", async route => {
    if (route.request().postDataJSON().kind === "ai_chat") {
      failures++;
      await route.fulfill(failures === 1
        ? { status: 422, json: { error: { code: "provider_failed", message: "模型暂时不可用" } } }
        : { status: 202, json: failedTask });
    }
    else await route.continue();
  });
  await page.getByLabel("提出问题、质疑或补充观点").fill("第二轮：成交依据呢");
  await page.getByRole("button", { name: "发送观点" }).click();
  await expect(page.getByRole("alert")).toContainText("模型暂时不可用");
  await expect(page.locator(".chat-history .assistant")).toHaveCount(1);
  await expect(page.locator(".chat-history")).toContainText("第二轮：成交依据呢");
  await page.reload();
  await expect(page.locator(".chat-history .assistant")).toHaveCount(1);
  await expect(page.locator(".chat-history")).toContainText("第二轮：成交依据呢");
  await page.getByLabel("提出问题、质疑或补充观点").fill("第二轮：成交依据呢");
  await page.getByRole("button", { name: "发送观点" }).click();
  await expect(page.getByText("后台模型请求失败", { exact: true })).toBeVisible();
  await expect(page.locator(".chat-history .assistant")).toHaveCount(1);
  await page.reload();
  await expect(page.getByText("后台模型请求失败", { exact: true })).toBeVisible();
  await expect(page.locator(".chat-history")).toContainText("第二轮：成交依据呢");
  await page.unroute("**/api/v1/tasks");
  await page.getByLabel("提出问题、质疑或补充观点").fill("第二轮：成交依据呢");
  const sent = page.waitForRequest(request => request.url().endsWith("/api/v1/tasks") && request.postDataJSON().kind === "ai_chat");
  await page.getByRole("button", { name: "发送观点" }).click();
  expect((await sent).postDataJSON().input.previous_task_id).toBe(first.id);
  await expect(page.locator(".chat-history .assistant")).toHaveCount(2, { timeout: 30000 });
  await expect(page.locator(".chat-history .user")).toHaveCount(2);
  await page.getByRole("button", { name: "开始 AI 分析", exact: true }).click();
  await expect(page.getByRole("heading", { name: "完整分析与过程回放" })).toBeVisible({ timeout: 30000 });
  await expect(page.locator(".chat-history article")).toHaveCount(0);
});

test("AI cache mode and replay do not invent reports or resubmit on reload", async ({ page }) => {
  let submissions = 0;
  page.on("request", request => { if (request.method() === "POST" && request.url().endsWith("/api/v1/tasks")) submissions++; });
  await page.goto("/app/research/ai");
  await page.getByLabel("分析日期").fill("2023-04-28");
  await page.getByLabel("允许使用缓存的最终决策").check();
  await page.getByRole("button", { name: "开始 AI 分析", exact: true }).click();
  await expect(page.getByRole("heading", { name: "决策与研究证据" })).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/启用了缓存：只提供最终决策/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "完整分析与过程回放" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "决策与研究证据" })).toBeVisible();
  expect(submissions).toBe(1);
  await page.getByLabel("股票代码", { exact: true }).fill("600000.SH");
  await expect(page.getByText("研究参数已修改，以下为上次已提交任务的结果。")).toBeVisible();
});

test("AI input and missing credentials give feedback without running a model", async ({ page }) => {
  let submitted: any;
  await page.route("**/api/v1/tasks", route => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 409, json: { error: { code: "model_not_ready", message: "请先配置模型凭证" } } });
  });
  await page.goto("/app/research/ai");
  await page.getByLabel("股票代码", { exact: true }).fill("");
  await page.getByRole("button", { name: "开始 AI 分析", exact: true }).click();
  expect(submitted).toBeUndefined();
  await page.getByLabel("股票代码", { exact: true }).fill("000001");
  await page.getByLabel("模型提供方").selectOption("openai");
  await page.getByRole("button", { name: "全选新闻源", exact: true }).click();
  const settings = await (await page.request.get("/api/v1/settings")).json();
  await page.getByRole("button", { name: "开始 AI 分析", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("请先配置模型凭证");
  expect(submitted.input.provider).toBe("openai");
  expect(submitted.input.news_sources).toEqual(Object.keys(settings.news_sources));
  await expect(page.getByRole("heading", { name: "决策与研究证据" })).toHaveCount(0);
});

test("audit opens the exact result ID and clears old evidence when the next report is missing", async ({ page }) => {
  const runs = await (await page.request.get("/api/v1/runs")).json();
  const id = runs.items[0].run_id;
  const report = await (await page.request.get(`/api/v1/runs/${id}/audit`)).json();
  await page.goto(`/app/backtests/${id}`);
  await page.getByRole("link", { name: "完整审计", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/audits/${id}$`));
  await expect(page.getByLabel("选择审计运行")).toHaveValue(id);
  await expect(page.getByText(report.headline, { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "执行假设", exact: true })).toBeVisible();
  for (const row of report.execution_assumptions.rows)
    await expect(page.getByRole("row").filter({ hasText: row["审计假设"] })).toContainText(row["取值"]);
  await page.route("**/api/v1/runs/missing-audit/audit", route => route.fulfill({ status: 404, json: { error: { code: "result_missing", message: "该运行尚无可审计结果" } } }));
  await page.goto("/app/audits/missing-audit");
  await expect(page.getByRole("alert")).toContainText("该运行尚无可审计结果");
  await expect(page.getByText(report.headline, { exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "检查外部成交", exact: true }).click();
  await expect(page).toHaveURL(/\/audits\/external$/);
});

for (const [grade, statuses] of [
  ["A", ["pass", "pass", "pass", "pass", "pass", "not_applicable"]],
  ["B", ["pass", "pass", "pass", "pass", "pass", "unavailable"]],
  ["C", ["warn", "warn", "pass", "pass", "pass", "pass"]],
  ["D", ["fail", "pass", "pass", "pass", "pass", "pass"]],
] as const) {
  test(`audit grades ${grade} preserve all six dimension meanings evidence and units`, async ({ page }) => {
    const runs = await (await page.request.get("/api/v1/runs")).json();
    const id = runs.items[0].run_id;
    const original = await (await page.request.get(`/api/v1/runs/${id}/audit`)).json();
    const report = { ...original, grade, headline: `验收评级 ${grade}`, transaction_cost_ratio: 0.01234,
      dimensions: original.dimensions.map((dimension: any, i: number) => ({ ...dimension, status: statuses[i], findings: [{ severity: "info", message: `完整证据${i}` }] })),
      validity: { issues: [{ code: "AUDIT_EVIDENCE_CODE", severity: "WARN", message: "原始问题说明" }] },
      execution_assumptions: { columns: ["审计假设", "取值"], rows: [{ 审计假设: "历史分期费率", 取值: "启用" }, { 审计假设: "参与率上限", 取值: "12.5%" }, { 审计假设: "滑点率", 取值: "0.123%" }, { 审计假设: "未知状态策略", 取值: "reject" }] },
    };
    await page.route(`**/api/v1/runs/${id}/audit`, route => route.fulfill({ json: report }));
    await page.goto(`/app/audits/${id}`);
    await expect(page.getByText(`验收评级 ${grade}`, { exact: true })).toBeVisible();
    await expect(page.locator(".metric").filter({ hasText: "可信度评级" }).locator("strong")).toHaveText(grade);
    await expect(page.locator(".metric").filter({ hasText: "审计维度通过" }).locator("strong")).toHaveText(`${statuses.filter(s => s === "pass").length}/6`);
    await expect(page.locator(".metric").filter({ hasText: "成本占初始资金" }).locator("strong")).toHaveText("1.23%");
    const labels: Record<string, string> = { pass: "通过", warn: "警告", fail: "失败", unavailable: "无法评估", not_applicable: "不适用" };
    for (let i = 0; i < 6; i++) {
      const row = page.getByRole("row").filter({ hasText: report.dimensions[i].title });
      await expect(row).toContainText(labels[statuses[i]]);
      await expect(row).toContainText(`完整证据${i}`);
    }
    await expect(page.getByRole("row").filter({ hasText: "AUDIT_EVIDENCE_CODE" })).toContainText("原始问题说明");
    await expect(page.getByRole("row").filter({ hasText: "参与率上限" })).toContainText("12.5%");
    await expect(page.getByRole("row").filter({ hasText: "滑点率" })).toContainText("0.123%");
  });
}

test("knowledge filtering preserves whole-library statistics and distinct sources", async ({ page }) => {
  const ids: string[] = [];
  try {
    for (const [content, source] of [["验收知识甲独立", "验收来源甲"], ["验收知识乙独立", "验收来源乙"]]) {
      const saved = await (await page.request.post("/api/v1/knowledge", { data: { content, source } })).json();
      ids.push(saved.id);
    }
    const all = await (await page.request.get("/api/v1/knowledge")).json();
    await page.goto("/app/knowledge");
    await page.getByLabel("搜索内容或来源").fill("验收知识甲独立");
    await page.getByLabel("来源过滤").selectOption("验收来源甲");
    await expect(page.locator(".knowledge-item")).toHaveCount(1);
    await expect(page.locator(".knowledge-item")).toContainText("验收知识甲独立");
    await expect(page.locator(".metric").filter({ hasText: "全部条目" }).locator("strong")).toHaveText(String(all.all_count));
    await expect(page.locator(".metric").filter({ hasText: "来源数量" }).locator("strong")).toHaveText(String(all.sources.length));
  } finally {
    for (const id of ids) await page.request.delete(`/api/v1/knowledge/${id}`);
  }
});
