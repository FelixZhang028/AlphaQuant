import { useEffect, useRef, useState } from "react";
import { ArrowRight, Play, Save, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  fingerprint,
  type BacktestRequest,
  type Obj,
  type TableData,
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
  format,
  JobPanel,
  JsonEditor,
  Loading,
  MetricGrid,
  Note,
  PageHead,
  RemoteTable,
  Report,
  Tabs,
} from "../components";

export function ParameterFields({
  metadata,
  values,
  onChange,
}: {
  metadata: Obj[];
  values: Obj;
  onChange: (v: Obj) => void;
}) {
  return (
    <div className="form-grid">
      {metadata.map((p) => (
        <Field key={p.name} label={p.label || p.name} hint={p.description}>
          {p.kind === "boolean" ? (
            <select
              value={String(values[p.name] ?? p.default)}
              onChange={(e) =>
                onChange({ ...values, [p.name]: e.target.value === "true" })
              }
            >
              <option value="true">是</option>
              <option value="false">否</option>
            </select>
          ) : p.choices?.length ? (
            <select
              value={String(values[p.name] ?? p.default)}
              onChange={(e) =>
                onChange({ ...values, [p.name]: e.target.value })
              }
            >
              {p.choices.map((v: any) => (
                <option key={String(v)} value={v}>
                  {String(v)}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={
                p.kind === "integer" || p.kind === "number" ? "number" : "text"
              }
              value={values[p.name] ?? p.default ?? ""}
              required
              min={p.minimum ?? undefined}
              max={p.maximum ?? undefined}
              step={p.kind === "integer" ? 1 : "any"}
              onChange={(e) =>
                onChange({
                  ...values,
                  [p.name]:
                    p.kind === "integer" || p.kind === "number"
                      ? Number(e.target.value)
                      : e.target.value,
                })
              }
            />
          )}
        </Field>
      ))}
    </div>
  );
}
export function RunForm({
  initial,
  scope = "backtest",
  title = "研究参数",
  planInputs = {},
}: {
  initial?: BacktestRequest;
  scope?: string;
  title?: string;
  planInputs?: Obj;
}) {
  const defaults = useResource<BacktestRequest>("/backtests/defaults"),
    strategies = useResource("/strategies");
  const [draft, setDraft] = useSticky<BacktestRequest | null>(
    "draft:" + scope,
    null,
  );
  const [pending, setPending] = useSticky<{
    request: BacktestRequest;
    checks: Obj;
  } | null>("preflight:" + scope, null);
  const [confirmed, setConfirmed] = useState(false),
    [planTitle, setPlanTitle] = useState("");
  const action = useAction(),
    job = useJob(scope);
  const executed = useResource(job.id ? `/tasks/${job.id}/input` : null);
  useEffect(() => {
    if (!draft && defaults.data) setDraft(defaults.data);
  }, [defaults.data]);
  const initialSignature = JSON.stringify(initial);
  useEffect(() => {
    if (initial) {
      setDraft(initial);
      setPending(null);
      setConfirmed(false);
    }
  }, [initialSignature]);
  const checkedUpdate = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (
      job.task?.kind === "data_update" &&
      ["SUCCESS", "PARTIAL"].includes(job.task.status) &&
      job.task.id !== checkedUpdate.current &&
      (pending?.request || draft)
    ) {
      checkedUpdate.current = job.task.id;
      const request = pending?.request || draft!;
      setPending(null);
      setConfirmed(false);
      void action.run(
        () => post("/backtests/inspect", request),
        (checks) => {
          setPending({ request, checks });
          setConfirmed(false);
          action.setMessage("数据更新结束，已按原方案自动重新检查。");
        },
      );
    }
  }, [job.task?.id, job.task?.status]);
  if (!draft || !strategies.data)
    return (
      <>
        <ErrorBox error={defaults.error || strategies.error} />
        {!defaults.error && !strategies.error && <Loading />}
      </>
    );
  const metadata = strategies.data.items.find(
    (s: Obj) => s.plugin_name === draft.strategy_plugin,
  );
  const change = (key: keyof BacktestRequest, value: any) =>
    setDraft({ ...draft, [key]: value });
  const inspect = () => {
    setPending(null);
    setConfirmed(false);
    return action.run(
      () => post("/backtests/inspect", draft),
      (checks) => {
        setPending({ request: structuredClone(draft), checks });
        setConfirmed(false);
      },
    );
  };
  const save = () =>
    action.run(
      () =>
        post("/research/plans", {
          title: planTitle || draft.strategy_id,
          request: pending?.request || draft,
          plan_id: draft.plan_id,
          inputs: planInputs,
        }),
      (result) => {
        const reference = {
          plan_id: result.plan_id,
          plan_revision: result.revision,
          snapshot_run_id: null,
        };
        setDraft((previous) =>
          previous ? { ...previous, ...reference } : previous,
        );
        setPending((previous) =>
          previous
            ? { ...previous, request: { ...previous.request, ...reference } }
            : previous,
        );
        action.setMessage(`方案已保存 · v${result.revision}`);
      },
    );
  const patchData = () =>
    action.run(async () => {
      const request = pending?.request || draft;
      const input = await post("/backtests/data-request", request);
      return job.submit("data_update", input);
    });
  return (
    <>
      <Card title={title}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void inspect();
          }}
        >
          <div className="form-grid">
            <Field label="策略">
              <select
                value={draft.strategy_plugin}
                onChange={(e) => {
                  const item = strategies.data!.items.find(
                    (s: Obj) => s.plugin_name === e.target.value,
                  );
                  setDraft({
                    ...draft,
                    strategy_plugin: item.plugin_name,
                    strategy_id: item.plugin_name,
                    strategy_parameters: Object.fromEntries(
                      item.parameters.map((p: Obj) => [p.name, p.default]),
                    ),
                  });
                }}
              >
                {strategies.data.items.map((s: Obj) => (
                  <option key={s.plugin_name} value={s.plugin_name}>
                    {s.display_name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="初始资金（元）">
              <input
                type="number"
                required
                min={1000}
                step="any"
                value={draft.initial_cash}
                onChange={(e) => change("initial_cash", Number(e.target.value))}
              />
            </Field>
            <Field label="开始日期">
              <input
                type="date"
                required
                value={draft.start_date}
                onChange={(e) => change("start_date", e.target.value)}
              />
            </Field>
            <Field label="结束日期">
              <input
                type="date"
                required
                min={draft.start_date}
                value={draft.end_date}
                onChange={(e) => change("end_date", e.target.value)}
              />
            </Field>
          </div>
          <p className="muted">{metadata?.description}</p>
          <details open>
            <summary>策略参数</summary>
            <ParameterFields
              metadata={metadata?.parameters || []}
              values={draft.strategy_parameters}
              onChange={(value) => change("strategy_parameters", value)}
            />
          </details>
          <details>
            <summary>高级研究设置</summary>
            <div className="form-grid">
              <Field label="策略编号">
                <input
                  required
                  value={draft.strategy_id}
                  onChange={(e) => change("strategy_id", e.target.value)}
                />
              </Field>
              <Field label="持股数">
                <input
                  type="number"
                  required
                  min={1}
                  value={draft.top_n}
                  onChange={(e) => change("top_n", Number(e.target.value))}
                />
              </Field>
              <Field label="调仓频率">
                <select
                  value={draft.rebalance}
                  onChange={(e) => change("rebalance", e.target.value)}
                >
                  <option value="daily">每日</option>
                  <option value="weekly">每周</option>
                  <option value="monthly">每月</option>
                </select>
              </Field>
              <Field label="组合分配">
                <select
                  value={draft.portfolio_method || "equal_weight"}
                  onChange={(e) => change("portfolio_method", e.target.value)}
                >
                  <option value="equal_weight">等权</option>
                  <option value="inverse_volatility">波动率倒数</option>
                  <option value="risk_parity">风险平价</option>
                  <option value="mean_variance">均值方差</option>
                </select>
              </Field>
              <Field label="股票池口径">
                <select
                  value={draft.universe_mode || "fixed"}
                  onChange={(e) => change("universe_mode", e.target.value)}
                >
                  <option value="fixed">当前固定股票池</option>
                  <option value="historical">历史股票池</option>
                </select>
              </Field>
            </div>
            <Note>
              {draft.universe_mode === "historical"
                ? "历史模式要求当时成分数据；数据不足会明确报错。"
                : "当前股票池回看历史存在选择偏差，请结合可信度审计判断。"}
            </Note>
            {draft.snapshot_run_id && (
              <Note>
                使用历史运行 {draft.snapshot_run_id.slice(0, 8)}{" "}
                的执行与风险快照。
              </Note>
            )}
            {draft.plan_id && (
              <Note>
                基于研究方案 {draft.plan_id.slice(0, 8)} · v
                {draft.plan_revision}，保留原股票池、费用与风控。
              </Note>
            )}
            <details>
              <summary>当前请求的风险限制</summary>
              <Report value={draft.risk_limits} />
            </details>
          </details>
          <div className="actions">
            <button
              className="primary"
              type="submit"
              disabled={action.busy || job.active}
            >
              <ShieldCheck size={15} />
              检查数据并准备回测
            </button>
            <button
              type="button"
              disabled={job.active}
              onClick={() => void patchData()}
            >
              补齐行情与基准
            </button>
            <Link to="/app/risk" className="text-button">
              查看风险规则
            </Link>
          </div>
        </form>
        <ErrorBox error={action.error} />
        {action.message && <Note tone="success">{action.message}</Note>}
        <details>
          <summary>保存研究方案</summary>
          <Field label="方案名称">
            <input
              value={planTitle}
              placeholder={draft.strategy_id}
              onChange={(e) => setPlanTitle(e.target.value)}
            />
          </Field>
          <button onClick={save} disabled={action.busy}>
            <Save size={15} />
            保存当前版本
          </button>
        </details>
        {strategies.data.load_errors?.length > 0 && (
          <details>
            <summary>已保存策略加载问题</summary>
            <Report value={strategies.data.load_errors} />
          </details>
        )}
      </Card>
      {pending && (
        <Card title="已提交的待运行方案">
          <div className="request-strip">
            <span>{pending.request.strategy_id}</span>
            <span>
              {pending.request.start_date} — {pending.request.end_date}
            </span>
            <span>¥ {pending.request.initial_cash.toLocaleString()}</span>
          </div>
          {JSON.stringify(pending.request) !== JSON.stringify(draft) && (
            <Note>
              上方草稿已有修改。运行按钮使用这里已提交的参数；要运行新参数，请重新检查。
            </Note>
          )}
          <DataTable data={pending.checks.checks} />
          <details>
            <summary>核对本次完整执行参数</summary>
            <Report value={pending.request} />
          </details>
          <CheckBox
            label="我已核对这份已提交方案，确认策略规则与执行参数"
            checked={confirmed}
            onChange={setConfirmed}
          />
          <div className="actions">
            <button
              className="primary"
              disabled={!pending.checks.ready || !confirmed || job.active}
              onClick={() =>
                void job.submit("backtest", {
                  request: pending.request,
                  confirmed: true,
                  plan_title: planTitle || pending.request.strategy_id,
                  plan_inputs: planInputs,
                })
              }
            >
              <Play size={15} />
              运行已检查方案
            </button>
            <button
              disabled={action.busy}
              onClick={() => {
                setPending(null);
                setConfirmed(false);
                void action.run(
                  () => post("/backtests/inspect", pending.request),
                  (checks) => {
                    setPending({ ...pending, checks });
                    setConfirmed(false);
                  },
                );
              }}
            >
              重新检查已提交方案
            </button>
          </div>
          <p className="muted">
            运行时后端再次检查数据，并保存实际执行的方案版本。
          </p>
        </Card>
      )}
      <JobPanel job={job} showResult={false} />
      {job.result?.run_id && (
        <Card title="回测已完成">
          {executed.loading ? (
            <Loading />
          ) : executed.error ? (
            <ErrorBox error={executed.error} />
          ) : (
            fingerprint({
              ...draft,
              plan_id: draft.plan_id ?? null,
              plan_revision: draft.plan_revision ?? null,
            }) !== fingerprint(executed.data?.input?.request) && (
              <Note>
                这是上次已执行方案的结果，当前草稿尚未运行。请重新检查并运行新参数；历史结果仍可打开。
              </Note>
            )
          )}
          <details>
            <summary>本次结果实际执行的参数</summary>
            <Report value={executed.data?.input?.request} />
          </details>
          <MetricGrid
            values={job.result.summary}
            keys={[
              "cumulative_return",
              "annual_return",
              "max_drawdown",
              "sharpe",
            ]}
          />
          <Link
            className="button primary"
            to={"/app/backtests/" + job.result.run_id}
          >
            打开完整报告 <ArrowRight size={16} />
          </Link>
        </Card>
      )}
      {job.result && !job.result.run_id && (
        <Card title="更新结果">
          <Report value={job.result} />
          <button onClick={() => void inspect()}>更新后重新检查</button>
        </Card>
      )}
    </>
  );
}
export function BacktestPage() {
  const [initial, setInitial] = useState<BacktestRequest>();
  useEffect(() => {
    const text = sessionStorage.getItem("alphaquant:prepared-request");
    if (text) {
      try {
        setInitial(JSON.parse(text));
      } finally {
        sessionStorage.removeItem("alphaquant:prepared-request");
      }
    }
  }, []);
  return (
    <>
      <PageHead
        title="新建回测"
        description="先确认研究规则和数据条件，再把计算交给后台。"
      />
      <nav className="subnav" aria-label="研究阶段">
        <Link className="active" to="/app/backtests/new">
          单次回测
        </Link>
        <Link
          to={
            "/app/experiments/optimization" +
            query({ baseline: initial?.snapshot_run_id })
          }
        >
          参数优化与稳健性验证
        </Link>
        <Link to="/app/risk">风险规则</Link>
        <Link to="/app/research/plans">方案复用</Link>
      </nav>
      <RunForm initial={initial} />
    </>
  );
}
export function useFullTable(path: string) {
  const [data, setData] = useState<Obj[]>([]),
    [error, setError] = useState<Error>(),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setData([]);
    setError(undefined);
    setLoading(true);
    void (async () => {
      try {
        let rows: Obj[] = [],
          offset = 0,
          total = Infinity;
        while (offset < total) {
          const page = await api<TableData>(
            path +
              (path.includes("?")
                ? "&" + query({ offset, limit: 5000 }).slice(1)
                : query({ offset, limit: 5000 })),
            { signal: controller.signal },
          );
          rows = [...rows, ...page.rows];
          total = page.total;
          offset += page.rows.length;
          if (!page.rows.length) break;
        }
        if (!controller.signal.aborted) {
          setData(rows);
          setLoading(false);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setError(error as Error);
          setLoading(false);
        }
      }
    })();
    return () => controller.abort();
  }, [path]);
  return { data, error, loading };
}
export function RunReport() {
  const { runId = "" } = useParams();
  const detail = useResource(`/runs/${runId}`),
    diagnosis = useResource(`/runs/${runId}/diagnosis`);
  const nav = useFullTable(`/runs/${runId}/tables/nav`);
  const analytics = useResource(`/runs/${runId}/analytics`);
  const records = useResource(
    `/runs${query({ q: runId, include_all_status: true })}`,
  );
  const record = records.data?.items?.find(
    (item: Obj) => item.run_id === runId,
  );
  const [tab, setTab] = useState("summary"),
    [table, setTable] = useState("fills"),
    [, setLast] = useSticky<string | null>("last-run", null);
  const action = useAction();
  useEffect(() => {
    if (detail.data) setLast(runId);
  }, [detail.data, runId]);
  const restore = () =>
    action.run(
      () => api(`/runs/${runId}/request`),
      (value) => {
        sessionStorage.setItem(
          "alphaquant:prepared-request",
          JSON.stringify(value.request),
        );
        location.assign("/app/backtests/new");
      },
    );
  const curves: Obj[] = nav.data.map((row) => ({
    ...row,
    date: row.trade_date || row.date,
  }));
  const normalized = analytics.data?.normalized.rows || [];
  const hasBenchmark =
    analytics.data?.normalized.columns.includes("benchmark_equity");
  const tableNames = [
    "signals",
    "target_positions",
    "orders",
    "fills",
    "closed_trades",
    "positions",
    "risk_events",
    "corporate_actions",
  ];
  return (
    <>
      <PageHead
        title={record?.strategy_id || "回测报告"}
        description={`运行 ${runId}`}
        actions={
          <>
            <button onClick={restore}>从此快照重跑</button>
            <Link className="button" to={"/app/audits/" + runId}>
              <ShieldCheck size={15} />
              完整审计
            </Link>
          </>
        }
      />
      <ErrorBox
        error={detail.error || nav.error || analytics.error || action.error}
      />
      {detail.loading ? (
        <Loading />
      ) : (
        detail.data && (
          <>
            <Card>
              <div className="report-heading">
                <Badge value={record?.status || "SUCCESS"} />
                <span>
                  绩效有效性：{detail.data.validity?.status || "旧版未记录"}
                </span>
                <span>
                  {record?.start_date} — {record?.end_date}
                </span>
              </div>
              <MetricGrid
                values={detail.data.summary || {}}
                keys={[
                  "cumulative_return",
                  "annual_return",
                  "max_drawdown",
                  "sharpe",
                ]}
              />
            </Card>
            <Tabs
              items={["summary", "metrics", "trades", "diagnosis"].map(
                (x, i) =>
                  [
                    x,
                    [
                      "净值与概览",
                      "全部专业指标",
                      "交易与持仓",
                      "诊断与有效性",
                    ][i],
                  ] as [string, string],
              )}
              value={tab}
              onChange={setTab}
            />
            {tab === "summary" && (
              <>
                <Card title="先看懂这次回测">
                  <ResultBrief
                    summary={detail.data.summary || {}}
                    outOfSample={record?.run_kind === "walk_forward_oos"}
                    linkedOos={analytics.data?.linked_oos || 0}
                  />
                </Card>
                <Card
                  title="策略与基准净值"
                  action={
                    <a
                      className="button"
                      href={`/api/v1/runs/${runId}/tables/nav/export.csv`}
                    >
                      下载完整净值
                    </a>
                  }
                >
                  {nav.loading ? (
                    <Loading />
                  ) : (
                    <Chart
                      rows={normalized}
                      x="trade_date"
                      series={[
                        ["equity", "策略净值"],
                        ["benchmark_equity", "基准净值"],
                      ]}
                    />
                  )}
                  {!hasBenchmark && (
                    <Note>该运行缺少同一起点的可用基准曲线。</Note>
                  )}
                </Card>
                <Card title="账户权益与回撤">
                  <Chart rows={curves} series={["equity"]} />
                  <Chart
                    rows={analytics.data?.drawdown.rows || []}
                    x="trade_date"
                    series={["drawdown"]}
                    percent
                  />
                  <Report
                    value={Object.fromEntries(
                      Object.entries(detail.data.summary || {}).filter(
                        ([key]) => key.startsWith("max_drawdown_"),
                      ),
                    )}
                  />
                </Card>
                <Card title="月度收益">
                  <DataTable data={analytics.data?.monthly} />
                  <Report value={detail.data} />
                </Card>
                <div className="actions">
                  <Link
                    className="button primary"
                    to={"/app/experiments/optimization?baseline=" + runId}
                  >
                    继续参数验证 <ArrowRight size={15} />
                  </Link>
                  <Link
                    className="button"
                    to={"/app/experiments/walk-forward?baseline=" + runId}
                  >
                    样本外验证
                  </Link>
                  <Link className="button" to="/app/research/records">
                    研究记录库
                  </Link>
                </div>
              </>
            )}
            {tab === "metrics" && (
              <Card title="全部收益、风险、交易、成本与持仓指标">
                <MetricGrid values={detail.data.summary || {}} />
                <details>
                  <summary>原始指标字段</summary>
                  <Report value={detail.data.summary} />
                </details>
              </Card>
            )}
            {tab === "trades" && (
              <Card title="完整交易与持仓明细">
                <Tabs
                  items={tableNames.map((name) => [
                    name,
                    (
                      {
                        signals: "信号",
                        target_positions: "目标仓位",
                        orders: "订单",
                        fills: "成交",
                        closed_trades: "完整交易",
                        positions: "每日持仓",
                        risk_events: "风险事件",
                        corporate_actions: "公司行为",
                      } as Obj
                    )[name],
                  ])}
                  value={table}
                  onChange={setTable}
                />
                <RemoteTable
                  key={table}
                  path={`/runs/${runId}/tables/${table}`}
                  exportPath={`/runs/${runId}/tables/${table}/export.csv`}
                />
              </Card>
            )}
            {tab === "diagnosis" && (
              <>
                <Card title="通俗诊断">
                  <ErrorBox error={diagnosis.error} />
                  <Report value={diagnosis.data} />
                </Card>
                <Card title="完整有效性证据">
                  <Report value={detail.data.validity} />
                </Card>
              </>
            )}
          </>
        )
      )}
    </>
  );
}

function ResultBrief({
  summary,
  outOfSample,
  linkedOos,
}: {
  summary: Obj;
  outOfSample: boolean;
  linkedOos: number;
}) {
  const valid = (value: unknown): value is number =>
    typeof value === "number" && Number.isFinite(value);
  const total = summary.cumulative_return,
    benchmark = summary.benchmark_return,
    drawdown = summary.max_drawdown;
  const difference = total - benchmark;
  return (
    <>
      <p>
        {valid(total) && valid(benchmark)
          ? `策略累计收益 ${(total * 100).toFixed(2)}%，基准 ${(benchmark * 100).toFixed(2)}%；${difference > 0 ? "高于" : difference < 0 ? "低于" : "等于"}基准 ${Math.abs(difference * 100).toFixed(2)} 个百分点。`
          : "缺少有效的策略或基准收益，暂时无法判断是否跑赢基准。"}
      </p>
      <p>
        {valid(drawdown)
          ? `历史最大回撤 ${(Math.abs(drawdown) * 100).toFixed(2)}%：以高点资产 1 万元举例，最多回落约 ${Math.round(Math.abs(drawdown) * 10000).toLocaleString()} 元；未来可能更大。`
          : "缺少最大回撤数据，暂时无法评估历史回撤。"}
      </p>
      <p className="muted">
        {outOfSample
          ? "当前为样本外结果；单个区间不能证明长期有效。"
          : linkedOos
            ? `已关联 ${linkedOos} 条样本外回测，请查看各区间表现；数量不代表已通过验证。`
            : "尚未找到关联的样本外结果。当前历史收益不能说明换个时间段仍然有效。"}
      </p>
    </>
  );
}
