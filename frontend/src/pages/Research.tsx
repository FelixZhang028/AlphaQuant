import { useEffect, useRef, useState } from "react";
import { ArrowRight, Play } from "lucide-react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  api,
  csv,
  download,
  type Obj,
  post,
  query,
  useAction,
  useJob,
  useResource,
  useSticky,
} from "../api";
import {
  Badge,
  Card,
  Chart,
  CheckBox,
  DataTable,
  Empty,
  ErrorBox,
  Field,
  JobPanel,
  Loading,
  MetricGrid,
  Note,
  PageHead,
  Report,
  Tabs,
} from "../components";
import { RunForm } from "./Backtests";

export function Records() {
  const [filters, setFilters] = useSticky("record-filters", {
    q: "",
    status: "SUCCESS",
    strategy: "",
    run_kind: "",
  });
  const [offset, setOffset] = useState(0),
    [chosen, setChosen] = useState<Obj[]>([]),
    [comparison, setComparison] = useState<Obj>();
  const runs = useResource(
      "/runs" +
        query({
          ...filters,
          include_all_status: !filters.status,
          offset,
          limit: 100,
        }),
    ),
    strategies = useResource("/strategies"),
    action = useAction();
  const [planName, setPlanName] = useState("");
  const change = (key: string, value: string) => {
    setFilters({ ...filters, [key]: value });
    setOffset(0);
    setChosen([]);
    setComparison(undefined);
  };
  const toggle = (row: Obj) => {
    setComparison(undefined);
    setChosen((previous) =>
      previous.some((r) => r.run_id === row.run_id)
        ? previous.filter((r) => r.run_id !== row.run_id)
        : previous.length < 5
          ? [...previous, row]
          : previous,
    );
  };
  return (
    <>
      <PageHead
        title="研究记录"
        description="保留每次执行的参数与证据，让结果可以复盘。"
        actions={
          <Link className="button primary" to="/app/backtests/new">
            新建回测
          </Link>
        }
      />
      <Card>
        <div className="form-grid">
          <Field label="搜索名称或编号">
            <input
              value={filters.q}
              placeholder="输入策略名称或运行编号"
              onChange={(e) => change("q", e.target.value)}
            />
          </Field>
          <Field label="运行状态">
            <select
              value={filters.status}
              onChange={(e) => change("status", e.target.value)}
            >
              {[
                ["SUCCESS", "成功"],
                ["FAILED", "失败"],
                ["RUNNING", "运行中"],
                ["CREATED", "已创建"],
                ["", "全部状态"],
              ].map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="策略">
            <select
              value={filters.strategy}
              onChange={(e) => change("strategy", e.target.value)}
            >
              <option value="">全部策略</option>
              {strategies.data?.items.map((s: Obj) => (
                <option key={s.plugin_name} value={s.plugin_name}>
                  {s.display_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="运行类型">
            <select
              value={filters.run_kind}
              onChange={(e) => change("run_kind", e.target.value)}
            >
              <option value="">全部类型</option>
              {(runs.data?.run_kinds || []).map((v: string) => (
                <option key={v} value={v}>
                  {(
                    {
                      single: "单次回测",
                      optimization: "参数搜索（含滚动训练）",
                      walk_forward_oos: "滚动样本外",
                    } as Obj
                  )[v] || v}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="table-toolbar">
          <span>
            {runs.data?.total ?? "—"} 条记录 · 点击记录选择（最多 5 条）
          </span>
          <a
            className="button"
            href={
              "/api/v1/runs/export.csv" +
              query({ ...filters, include_all_status: !filters.status })
            }
          >
            下载全部筛选记录
          </a>
        </div>
        <ErrorBox error={runs.error || action.error} />
        {runs.loading ? (
          <Loading />
        ) : (
          <DataTable
            data={runs.data?.items}
            onRow={toggle}
            selected={(row) => chosen.some((r) => r.run_id === row.run_id)}
          />
        )}
        <div className="pagination">
          <button
            disabled={!offset}
            onClick={() => setOffset((x) => Math.max(0, x - 100))}
          >
            上一批
          </button>
          <button
            disabled={!runs.data || offset + 100 >= runs.data.total}
            onClick={() => setOffset((x) => x + 100)}
          >
            下一批
          </button>
        </div>
      </Card>
      {chosen.length > 0 && (
        <Card title={`已选择 ${chosen.length} 条记录`}>
          <div className="selected-runs">
            {chosen.map((run) => (
              <div key={run.run_id}>
                <span>
                  {run.strategy_id} · {run.run_id.slice(0, 8)}
                </span>
                <Link to={"/app/backtests/" + run.run_id}>打开报告 →</Link>
              </div>
            ))}
          </div>
          <div className="actions">
            <button
              className="primary"
              disabled={
                chosen.length < 2 ||
                chosen.some((r) => r.status !== "SUCCESS") ||
                action.busy
              }
              onClick={() =>
                action.run(
                  () =>
                    post("/runs/compare", {
                      run_ids: chosen.map((r) => r.run_id),
                    }),
                  setComparison,
                )
              }
            >
              对比所选成功结果
            </button>
            {comparison && (
              <button
                onClick={() =>
                  csv(comparison.metrics.rows, "backtest_comparison.csv")
                }
              >
                下载对比 CSV
              </button>
            )}
          </div>
          {chosen.length === 1 && (
            <details>
              <summary>保存为新的研究方案</summary>
              <Field label="新方案名称">
                <input
                  value={planName}
                  placeholder={chosen[0].strategy_id}
                  onChange={(e) => setPlanName(e.target.value)}
                />
              </Field>
              <button
                disabled={action.busy}
                onClick={() =>
                  action.run(
                    () =>
                      post("/research/plans", {
                        title: planName || chosen[0].strategy_id,
                        run_id: chosen[0].run_id,
                      }),
                    () =>
                      action.setMessage("已从执行快照保存方案并关联历史运行"),
                  )
                }
              >
                保存方案
              </button>
              <Report value={chosen[0]} />
            </details>
          )}
          {action.message && <Note tone="success">{action.message}</Note>}
        </Card>
      )}
      {comparison && (
        <Card title="所选运行对比">
          <DataTable data={comparison.metrics} />
          <ComparisonChart nav={comparison.nav.rows} />
          <Note>
            请核对区间、股票池、费用与风险假设，避免直接比较不同条件下的收益。
          </Note>
        </Card>
      )}
    </>
  );
}
function ComparisonChart({ nav }: { nav: Obj[] }) {
  if (!nav.length) return <Empty />;
  const keys = Object.keys(nav[0]).filter(
    (key) => key !== "trade_date" && key !== "date",
  );
  return (
    <Chart
      rows={nav}
      x={"trade_date" in nav[0] ? "trade_date" : "date"}
      series={keys}
    />
  );
}
function parseGrid(raw: Obj, metadata: Obj[]) {
  const grid: Obj = {};
  for (const [key, text] of Object.entries(raw)) {
    if (!String(text).trim()) continue;
    const p = metadata.find((item) => item.name === key);
    const values = String(text)
      .split(/[,，]/)
      .map((v) => v.trim());
    grid[key] = values.map((value) => {
      if (p?.kind === "boolean") {
        if (!["true", "false"].includes(value))
          throw new Error(`${key} 请输入 true 或 false`);
        return value === "true";
      }
      if (p?.kind === "integer" || p?.kind === "number") {
        const number = Number(value);
        if (!Number.isFinite(number) || value === "")
          throw new Error(`${key} 存在无效数值`);
        return number;
      }
      return value;
    });
  }
  if (!Object.keys(grid).length)
    throw new Error("请填写至少一个参数的候选值。");
  const count = Object.values(grid).reduce(
    (n: number, values: any) => n * values.length,
    1,
  );
  if (count > 100) throw new Error(`当前 ${count} 个组合，单次最多 100 组。`);
  return grid;
}
export function Experiments({
  walkForward = false,
}: {
  walkForward?: boolean;
}) {
  const [search] = useSearchParams(),
    [baseline, setBaseline] = useSticky(
      "experiment-baseline",
      search.get("baseline") || "",
    );
  const runs = useResource("/runs?limit=500"),
    strategies = useResource("/strategies"),
    restored = useResource(baseline ? `/runs/${baseline}/request` : null);
  const [draft, setDraft] = useSticky<Obj>(
    "experiment:" + (walkForward ? "wf" : "opt"),
    {
      grid: {},
      objective: "sharpe",
      max_drawdown_limit: "",
      max_workers: 1,
      training_months: 12,
      test_months: 3,
      step_months: 3,
      max_windows: 6,
      start_date: "",
      end_date: "",
    },
  );
  const kind = walkForward ? "walk_forward" : "optimization",
    slug = walkForward ? "walk-forward" : "optimization";
  const job = useJob(kind),
    action = useAction(),
    records = useResource(`/experiments/${slug}`);
  const [record, setRecord] = useState(""),
    saved = useResource(record ? `/experiments/${slug}/${record}` : null);
  useEffect(() => {
    if (["SUCCESS", "PARTIAL"].includes(job.task?.status || ""))
      records.refresh();
  }, [job.task?.id, job.task?.status]);
  useEffect(() => {
    if (search.get("baseline")) setBaseline(search.get("baseline")!);
  }, [search]);
  const metadata =
    strategies.data?.items.find(
      (s: Obj) => s.plugin_name === restored.data?.request?.strategy_plugin,
    )?.parameters || [];
  const change = (key: string, value: any) =>
    setDraft({ ...draft, [key]: value });
  const output = record ? saved.data : job.result;
  const rows =
    output?.experiments?.rows ||
    output?.windows?.rows ||
    output?.results?.rows ||
    [];
  const submit = () =>
    action.run(async () => {
      const input: Obj = {
        baseline_run_id: baseline,
        parameter_grid: parseGrid(draft.grid, metadata),
        objective: draft.objective,
        max_drawdown_limit:
          draft.max_drawdown_limit === ""
            ? null
            : Number(draft.max_drawdown_limit),
        start_date: draft.start_date || null,
        end_date: draft.end_date || null,
      };
      if (walkForward)
        for (const key of [
          "training_months",
          "test_months",
          "step_months",
          "max_windows",
        ])
          input[key] = Number(draft[key]);
      else input.max_workers = Number(draft.max_workers);
      setRecord("");
      return job.submit(kind, input);
    });
  return (
    <>
      <PageHead
        title={walkForward ? "滚动样本外验证" : "参数优化"}
        description={
          walkForward
            ? "只在训练窗口选参，在随后未见数据上检验。"
            : "控制搜索范围，同时观察约束和参数搜索偏差。"
        }
      />
      <div className="subnav">
        <Link
          className={!walkForward ? "active" : ""}
          to={"/app/experiments/optimization" + query({ baseline })}
        >
          参数优化
        </Link>
        <Link
          className={walkForward ? "active" : ""}
          to={"/app/experiments/walk-forward" + query({ baseline })}
        >
          滚动验证
        </Link>
      </div>
      <Card title="基准与实验配置">
        <Field label="基准回测">
          <select
            value={baseline}
            onChange={(e) => {
              setBaseline(e.target.value);
              change("grid", {});
            }}
          >
            <option value="">选择成功且可信的基准运行</option>
            {runs.data?.items.map((r: Obj) => (
              <option key={r.run_id} value={r.run_id}>
                {r.strategy_id} · {r.run_id.slice(0, 8)}
              </option>
            ))}
          </select>
        </Field>
        <ErrorBox error={runs.error || restored.error || action.error} />
        {restored.data && (
          <details>
            <summary>继承的原始执行参数</summary>
            <Report value={restored.data.request} />
          </details>
        )}
        <div className="form-grid">
          {metadata.map((p: Obj) => (
            <Field
              key={p.name}
              label={`${p.label} · 候选值`}
              hint={`逗号分隔；留空表示沿用基准。默认：${String(restored.data?.request.strategy_parameters[p.name])}`}
            >
              <input
                value={draft.grid[p.name] || ""}
                onChange={(e) =>
                  change("grid", { ...draft.grid, [p.name]: e.target.value })
                }
                placeholder={
                  p.kind === "boolean" ? "true,false" : String(p.default)
                }
              />
            </Field>
          ))}
        </div>
        <div className="form-grid">
          <Field label="总区间开始日期">
            <input
              type="date"
              value={draft.start_date}
              onChange={(e) => change("start_date", e.target.value)}
            />
          </Field>
          <Field label="总区间结束日期">
            <input
              type="date"
              value={draft.end_date}
              onChange={(e) => change("end_date", e.target.value)}
            />
          </Field>
          <Field label="排序目标">
            <select
              value={draft.objective}
              onChange={(e) => change("objective", e.target.value)}
            >
              {[
                ["sharpe", "夏普比率"],
                ["annual_return", "年化收益"],
                ["calmar", "卡玛比率"],
                ["max_drawdown", "最小回撤"],
              ].map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="最大回撤约束（小数，可留空）">
            <input
              type="number"
              min={0}
              max={1}
              step="any"
              value={draft.max_drawdown_limit}
              onChange={(e) => change("max_drawdown_limit", e.target.value)}
            />
          </Field>
          {walkForward ? (
            [
              ["training_months", "训练月数", 3, 120],
              ["test_months", "测试月数", 1, 36],
              ["step_months", "步长月数", 1, 36],
              ["max_windows", "最多窗口", 1, 24],
            ].map(([key, label, min, max]) => (
              <Field key={key} label={String(label)}>
                <input
                  type="number"
                  min={Number(min)}
                  max={Number(max)}
                  value={draft[key]}
                  onChange={(e) => change(String(key), Number(e.target.value))}
                />
              </Field>
            ))
          ) : (
            <Field label="并行进程">
              <select
                value={draft.max_workers}
                onChange={(e) => change("max_workers", Number(e.target.value))}
              >
                {[1, 2, 4].map((n) => (
                  <option key={n} value={n}>
                    {n} 个进程
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>
        <button
          className="primary"
          disabled={!baseline || job.active || action.busy}
          onClick={submit}
        >
          <Play size={15} />
          开始{walkForward ? "滚动验证" : "参数优化"}
        </button>
      </Card>
      <JobPanel job={job} showResult={false} />
      {output && (
        <Card
          title="实验结果"
          action={
            <button onClick={() => csv(rows, slug + ".csv")}>
              下载完整 CSV
            </button>
          }
        >
          <Report value={output} />
          <div className="selected-runs">
            {rows
              .filter((row: Obj) => row.run_id || row.test_run_id)
              .map((row: Obj, i: number) => (
                <Link
                  key={i}
                  to={"/app/backtests/" + (row.test_run_id || row.run_id)}
                >
                  打开{walkForward ? "测试窗口" : "组合"} {i + 1} 的完整回测{" "}
                  <ArrowRight size={13} />
                </Link>
              ))}
          </div>
        </Card>
      )}
      <Card title="历史实验">
        <Field label="选择已保存实验">
          <select value={record} onChange={(e) => setRecord(e.target.value)}>
            <option value="">本次任务结果</option>
            {records.data?.items?.map((r: Obj) => (
              <option key={r.id} value={r.id}>
                {r.id}
              </option>
            ))}
          </select>
        </Field>
        <ErrorBox error={records.error || saved.error} />
        {record && (
          <a
            className="button"
            href={`/api/v1/experiments/${slug}/${record}/export.csv`}
          >
            下载保存实验 CSV
          </a>
        )}
      </Card>
    </>
  );
}
export function Plans() {
  const plans = useResource("/research/plans"),
    action = useAction(),
    navigate = useNavigate();
  const [chosen, setChosen] = useState<Obj[]>([]),
    [comparison, setComparison] = useState<Obj>();
  const toggle = (row: Obj) => {
    setComparison(undefined);
    setChosen((previous) =>
      previous.some(
        (p) => p.plan_id === row.plan_id && p.revision === row.revision,
      )
        ? previous.filter(
            (p) => p.plan_id !== row.plan_id || p.revision !== row.revision,
          )
        : previous.length < 4
          ? [...previous, row]
          : previous,
    );
  };
  const restore = (plan: Obj) =>
    action.run(
      () => api(`/research/plans/${plan.plan_id}/${plan.revision}/request`),
      (result) => {
        if (result.inputs?.scope === "guided") {
          sessionStorage.setItem(
            "alphaquant:guided-plan",
            JSON.stringify(result),
          );
          navigate("/app/strategies/ideas");
          return;
        }
        sessionStorage.setItem(
          "alphaquant:prepared-request",
          JSON.stringify(result.request),
        );
        navigate("/app/backtests/new");
      },
    );
  return (
    <>
      <PageHead
        title="研究方案与版本"
        description="保存规则、股票池、区间、费用与风控；每个版本可继续修改和验证。"
      />
      <Note>
        当前显示本机工作区方案。旧账号的私有方案保留在原数据库，登录迁移后按原归属接入。
      </Note>
      <Card title="保存的版本">
        <ErrorBox error={plans.error || action.error} />
        {plans.loading ? (
          <Loading />
        ) : (
          <DataTable
            data={plans.data?.items}
            onRow={toggle}
            selected={(row) =>
              chosen.some(
                (p) => p.plan_id === row.plan_id && p.revision === row.revision,
              )
            }
          />
        )}
        {chosen.length > 0 && (
          <div className="selected-runs">
            {chosen.map((plan) => (
              <div key={`${plan.plan_id}:${plan.revision}`}>
                <span>
                  {plan.title} · v{plan.revision} · {plan.plan_id.slice(0, 6)}
                </span>
                <button onClick={() => restore(plan)}>恢复并修改</button>
                {plan.runs?.map((id: string) => (
                  <Link key={id} to={"/app/backtests/" + id}>
                    关联结果 {id.slice(0, 8)} →
                  </Link>
                ))}
              </div>
            ))}
          </div>
        )}
        <button
          disabled={chosen.length < 2 || action.busy}
          onClick={() =>
            action.run(
              () =>
                post("/research/plans/compare", {
                  versions: chosen.map((p) => ({
                    plan_id: p.plan_id,
                    revision: p.revision,
                  })),
                }),
              setComparison,
            )
          }
        >
          比较所选 2～4 个版本
        </button>
      </Card>
      {comparison && (
        <Card title="方案差异">
          <Note>{comparison.warning}</Note>
          <DataTable data={comparison.differences} />
          <Report value={comparison.results} />
        </Card>
      )}
    </>
  );
}
export function Audit() {
  const { runId } = useParams(),
    navigate = useNavigate(),
    runs = useResource("/runs?limit=500");
  const [selected, setSelected] = useState(runId || "");
  useEffect(() => {
    if (runId) setSelected(runId);
  }, [runId]);
  const report = useResource(selected ? `/runs/${selected}/audit` : null);
  return (
    <>
      <PageHead
        title="可信度审计"
        description="逐项查看数据、时间边界、样本偏差、成本、容量与参数搜索证据。"
        actions={
          <Link className="button" to="/app/audits/external">
            检查外部成交
          </Link>
        }
      />
      <Card>
        <Field label="选择审计运行">
          <select
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              navigate("/app/audits/" + e.target.value);
            }}
          >
            <option value="">选择成功回测</option>
            {runs.data?.items.map((r: Obj) => (
              <option value={r.run_id} key={r.run_id}>
                {r.strategy_id} · {r.run_id.slice(0, 8)}
              </option>
            ))}
          </select>
        </Field>
        <ErrorBox error={runs.error || report.error} />
        {selected ? (
          report.loading ? (
            <Loading />
          ) : (
            report.data && <AuditEvidence report={report.data} />
          )
        ) : (
          <Empty>选择一个结果，开始核对证据。</Empty>
        )}
      </Card>
    </>
  );
}
function AuditEvidence({ report }: { report: Obj }) {
  const statuses: Obj = { pass: "通过", warn: "警告", fail: "失败", unavailable: "无法评估", not_applicable: "不适用" };
  const dimensions: Obj[] = report.dimensions || [];
  const issues = (report.validity?.issues || []).map((issue: Obj) => ({
    问题代码: issue.code, 级别: issue.severity, 说明: issue.message,
  }));
  return <>
    <MetricGrid values={{
      可信度评级: report.grade,
      审计维度通过: `${dimensions.filter(d => d.status === "pass").length}/${dimensions.length}`,
      绩效指标: report.metrics_reliable ? "可用" : "不可用",
      净值观测: `${report.observations} 个交易日`,
      成本占初始资金: report.transaction_cost_ratio == null ? "未记录" : `${(report.transaction_cost_ratio * 100).toFixed(2)}%`,
    }} />
    <Note>{report.headline}</Note>
    <p className="muted">不适用的维度不计通过也不扣分；无法评估参数搜索偏差计一条警告。</p>
    <h3>六维审计</h3>
    <DataTable data={dimensions.map(d => ({ 审计维度: d.title, 结论: statuses[d.status] || d.status, 要点: d.findings?.[0]?.message || "" }))} />
    {dimensions.map(d => <details key={d.key} open={d.status !== "pass"}>
      <summary>{d.title} · {statuses[d.status] || d.status}</summary>
      <Report value={d.findings} />
    </details>)}
    <h3>参数搜索依据</h3>
    <Report value={report.selection_bias} />
    <h3>证据链</h3>
    {issues.length ? <DataTable data={issues} /> : <p className="muted">无有效性问题记录。</p>}
    <h3>执行假设</h3>
    <DataTable data={report.execution_assumptions} />
  </>;
}
export function ExternalAudit() {
  const [draft, setDraft] = useSticky("external-material", {
    content: "",
    mapping: {} as Obj,
    unit: "股",
    raw_prices: true,
    duplicate_confirmed: false,
  });
  const [preview, setPreview] = useState<Obj>(),
    [report, setReport] = useState<Obj>(),
    [filter, setFilter] = useState("");
  const revision = useRef(0);
  const action = useAction(),
    change = (key: string, value: any) => {
      revision.current += 1;
      setDraft({ ...draft, [key]: value,
        ...(key === "content" || key === "mapping" || key === "unit"
          ? { duplicate_confirmed: false } : {}),
      });
      if (key === "content") setPreview(undefined);
      setReport(undefined);
      setFilter("");
    };
  const parse = () => {
    const submittedRevision = revision.current;
    setPreview(undefined);
    setReport(undefined);
    return action.run(
      () => post("/audits/external/preview", draft),
      (result) => {
        if (submittedRevision !== revision.current) return;
        setPreview(result);
        setDraft({ ...draft, mapping: result.mapping, duplicate_confirmed: false });
      },
    );
  };
  const check = () => {
    const submittedRevision = revision.current;
    setReport(undefined);
    setFilter("");
    return action.run(() => post("/audits/external/check", draft), (result) => {
      if (submittedRevision === revision.current) setReport(result);
    });
  };
  return (
    <>
      <PageHead
        title="检查外部成交材料"
        description="核对成交记录与本地市场证据。当前支持表格和 CSV，净值截图暂不支持。"
        actions={
          <button
            onClick={() =>
              download(
                "\ufeff日期,股票代码,买卖方向,成交数量,成交价\r\n2023-01-03,000001,买入,100,12.5",
                "外部成交模板.csv",
                "text/csv",
              )
            }
          >
            下载模板
          </button>
        }
      />
      <Card title="导入材料">
        <Field label="上传 CSV（UTF-8 或 GB18030）">
          <input
            type="file"
            accept=".csv,.txt,.tsv"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              await action.run(async () => {
                if (file.size > 5000000) throw new Error("文件超过 5 MB");
                const buffer = await file.arrayBuffer();
                let text: string;
                try {
                  text = new TextDecoder("utf-8", { fatal: true }).decode(
                    buffer,
                  );
                } catch {
                  text = new TextDecoder("gb18030").decode(buffer);
                }
                change("content", text);
              });
            }}
          />
        </Field>
        <Field label="或粘贴含表头的成交表格">
          <textarea
            rows={9}
            value={draft.content}
            onChange={(e) => {
              change("content", e.target.value);
              setPreview(undefined);
            }}
          />
        </Field>
        <button
          className="primary"
          onClick={parse}
          disabled={action.busy || !draft.content}
        >
          识别字段并预览
        </button>
        <ErrorBox error={action.error} />
      </Card>
      {preview && (
        <Card title={`材料预览 · 共 ${preview.total} 条`}>
          <DataTable data={preview.preview} />
          <div className="form-grid">
            {Object.entries({
              date: "日期列",
              symbol: "证券代码列",
              side: "方向列",
              quantity: "数量列",
              price: "价格列",
            }).map(([key, label]) => (
              <Field key={key} label={label}>
                <select
                  value={draft.mapping[key] || ""}
                  onChange={(e) =>
                    change("mapping", {
                      ...draft.mapping,
                      [key]: e.target.value,
                    })
                  }
                >
                  <option value="">请选择</option>
                  {preview.preview.columns.map((column: string) => (
                    <option key={column}>{column}</option>
                  ))}
                </select>
              </Field>
            ))}
            <Field label="数量单位">
              <select
                value={draft.unit}
                onChange={(e) => change("unit", e.target.value)}
              >
                <option>股</option>
                <option>手</option>
              </select>
            </Field>
          </div>
          <CheckBox
            label="成交价为未复权价格（不确定时取消勾选）"
            checked={draft.raw_prices}
            onChange={(value) => change("raw_prices", value)}
          />
          <CheckBox
            label="我已核对并确认材料中的重复成交"
            checked={draft.duplicate_confirmed}
            onChange={(value) => change("duplicate_confirmed", value)}
          />
          <button
            className="primary"
            disabled={action.busy}
            onClick={check}
          >
            开始核查
          </button>
        </Card>
      )}
      {report && (
        <Card
          title="核查结果"
          action={
            <button
              onClick={() =>
                download(report.markdown, "外部成交检查.md", "text/markdown")
              }
            >
              下载完整报告
            </button>
          }
        >
          <MetricGrid values={report.counts} />
          <Field label="按结论筛选">
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">全部结论</option>
              {Object.keys(report.counts).map((key) => (
                <option key={key}>{key}</option>
              ))}
            </select>
          </Field>
          <DataTable
            data={report.findings.rows.filter(
              (row: Obj) => !filter || row["结论"] === filter,
            )}
          />
        </Card>
      )}
    </>
  );
}
