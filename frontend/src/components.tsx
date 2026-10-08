import {
  lazy,
  Suspense,
  type ComponentProps,
  Children,
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useState,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  LoaderCircle,
  RotateCw,
} from "lucide-react";

import {
  ApiError,
  type Job,
  type Obj,
  type TableData,
  query,
  statusLabel,
  useResource,
} from "./api";

export const labels: Obj = {
  cumulative_return: "累计收益",
  annual_return: "年化收益",
  max_drawdown: "最大回撤",
  sharpe: "夏普比率",
  final_equity: "最终权益",
  annual_volatility: "年化波动率",
  downside_volatility: "下行波动率",
  sortino: "索提诺比率",
  calmar: "卡玛比率",
  best_day_return: "最佳单日",
  worst_day_return: "最差单日",
  positive_day_ratio: "正收益日比例",
  positive_month_ratio: "正收益月比例",
  information_ratio: "信息比率",
  tracking_error: "跟踪误差",
  regression_alpha: "回归 Alpha（年化）",
  beta: "回归 Beta",
  orders: "订单数",
  fills: "成交数",
  closed_trades: "完整交易",
  order_fill_rate: "订单成交率",
  rejected_orders: "拒单数",
  trade_win_rate: "交易胜率",
  payoff_ratio: "盈亏比",
  profit_factor: "盈利因子",
  average_win: "平均盈利",
  average_loss: "平均亏损",
  average_holding_days: "平均持仓天数",
  annualized_turnover: "年化换手率",
  commission: "佣金",
  stamp_tax: "印花税",
  transfer_fee: "过户费",
  slippage_cost: "滑点成本",
  total_transaction_cost: "总交易成本",
  transaction_cost_to_initial_cash: "成本/初始资金",
  traded_notional: "成交金额",
  realized_gross_pnl: "已实现毛盈亏",
  realized_net_pnl: "已实现净盈亏",
  average_position_count: "平均持仓数",
  max_position_count: "最大持仓数",
  average_exposure: "平均仓位",
  max_exposure: "最大仓位",
  average_cash_ratio: "平均现金比例",
  minimum_cash_ratio: "最低现金比例",
  time_in_market_ratio: "在场时间比例",
  max_single_position_weight: "单股最大权重",
  average_concentration_hhi: "平均集中度 HHI",
  max_concentration_hhi: "最大集中度 HHI",
  date: "日期",
  trade_date: "交易日期",
  symbol: "证券代码",
  name: "名称",
  equity: "账户权益",
  cash: "现金",
  drawdown: "回撤",
  benchmark_nav: "基准净值",
  strategy_nav: "策略净值",
  quantity: "数量",
  price: "成交价",
  side: "方向",
  status: "状态",
  run_id: "运行编号",
  strategy_id: "策略编号",
  strategy_plugin: "策略",
  created_at: "创建时间",
  start_date: "开始日期",
  end_date: "结束日期",
  error: "失败原因",
  risk_events: "风险事件",
  positions: "持仓",
  signals: "信号",
  target_positions: "目标仓位",
  corporate_actions: "公司行为",
  ic_mean: "平均 IC",
  rank_ic_mean: "平均 Rank IC",
  ic_ir: "IC IR",
  rank_ic_ir: "Rank IC IR",
  long_short_mean: "多空收益差",
  turnover_mean: "成员更替率",
  coverage: "覆盖率",
  formula: "公式",
  description: "说明",
  version: "版本",
  direction: "方向",
  min_history: "最少历史天数",
  required_fields: "所需字段",
  source: "来源",
  category: "类别",
  metrics_reliable: "绩效可用",
  monthly_returns: "月度收益",
  validity: "有效性",
  summary: "指标汇总",
  daily_ic: "逐日 IC",
  annual_summary: "年度分析",
  significance: "显著性",
  horizon_decay: "持有期衰减",
  notes: "备注",
  reports: "分析报告",
  debate: "多空辩论",
  proposal: "交易员提案",
  risk: "风险评估",
  decision: "经理决策",
  fill: "模拟成交",
  rationale_chain: "理由链",
  rejection_reason: "拒绝原因",
  final_action: "最终动作",
  final_position_pct: "最终仓位",
  score: "评分",
  warning: "提示",
  warnings: "提示",
  errors: "非致命错误",
  trace_log: "过程回放",
  search: "参数搜索证据",
  assumptions: "执行假设",
  dimensions: "六维审计",
  issues: "问题明细",
};
const percentKeys = new Set(
  "cumulative_return annual_return max_drawdown annual_volatility downside_volatility best_day_return worst_day_return positive_day_ratio positive_month_ratio tracking_error regression_alpha order_fill_rate trade_win_rate annualized_turnover transaction_cost_to_initial_cash average_exposure max_exposure average_cash_ratio minimum_cash_ratio time_in_market_ratio max_single_position_weight long_short_mean final_position_pct".split(
    " ",
  ),
);
export function format(value: unknown, key = ""): string {
  if (
    value === null ||
    value === undefined ||
    (typeof value === "number" && !Number.isFinite(value))
  )
    return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "number")
    return percentKeys.has(key)
      ? `${(value * 100).toFixed(2)}%`
      : value.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
  return statusLabel[String(value)] || String(value);
}
export function PageHead({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <header className="page-head">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="actions">{actions}</div>
    </header>
  );
}
export function Card({
  title,
  children,
  className = "",
  action,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <section className={"card " + className}>
      {title && (
        <div className="card-title">
          <h2>{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {Children.map(children, (child) =>
        isValidElement(child)
          ? cloneElement(child as React.ReactElement<any>, {
              id,
              "aria-describedby": hint ? id + "-hint" : undefined,
            })
          : child,
      )}
      {hint && <small id={id + "-hint"}>{hint}</small>}
    </div>
  );
}
export function CheckBox({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="check">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      {label}
    </label>
  );
}
export function Note({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <div className={"note " + tone}>
      <AlertCircle size={16} />
      <div>{children}</div>
    </div>
  );
}
export function ErrorBox({ error }: { error?: Error }) {
  if (!error) return null;
  return (
    <div role="alert">
      <Note tone="error">{error.message}</Note>
      {error instanceof ApiError && error.details != null && (
        <details>
          <summary>查看具体原因</summary>
          <Report value={error.details} />
        </details>
      )}
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading">
      <LoaderCircle size={18} className="spin" />
      正在读取本地数据…
    </div>
  );
}
export function Empty({ children = "暂无数据。" }: { children?: ReactNode }) {
  return (
    <div className="empty">
      <span>◇</span>
      <p>{children}</p>
    </div>
  );
}
export function Badge({ value }: { value: string }) {
  return (
    <span className={"badge " + value.toLowerCase()}>
      {statusLabel[value] || value}
    </span>
  );
}
export function Tabs({
  items,
  value,
  onChange,
}: {
  items: (string | [string, string])[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item) => {
        const [id, label] = typeof item === "string" ? [item, item] : item;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={id === value}
            className={id === value ? "active" : ""}
            onClick={() => onChange(id)}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
export function MetricGrid({ values, keys }: { values: Obj; keys?: string[] }) {
  return (
    <div className="metrics">
      {(keys || Object.keys(values)).map((key) => (
        <div className="metric" key={key}>
          <span title={key}>{labels[key] || key}</span>
          <strong>{format(values[key], key)}</strong>
        </div>
      ))}
    </div>
  );
}
export function DataTable({
  data,
  columnLabels = {},
  onRow,
  selected,
}: {
  data: TableData | Obj[] | undefined;
  columnLabels?: Obj;
  onRow?: (row: Obj) => void;
  selected?: (row: Obj) => boolean;
}) {
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [data]);
  if (!data) return <Empty />;
  const rows = Array.isArray(data) ? data : data.rows;
  const columns = Array.isArray(data)
    ? [...new Set(data.flatMap((row) => Object.keys(row)))]
    : data.columns;
  if (!rows?.length) return <Empty />;
  const displayed = rows.slice(page * 50, (page + 1) * 50);
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((key) => (
                <th key={key} title={key}>
                  {columnLabels[key] || labels[key] || key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayed.map((row, i) => (
              <tr
                key={i}
                className={
                  (onRow ? "clickable " : "") +
                  (selected?.(row) ? "selected" : "")
                }
                onClick={() => onRow?.(row)}
              >
                {columns.map((key) => (
                  <td key={key}>
                    {onRow && key === columns[0] ? (
                      <button
                        className="text-button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onRow(row);
                        }}
                      >
                        {format(row[key], key)}
                      </button>
                    ) : (
                      format(row[key], key)
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > 50 && (
        <div className="pagination">
          <span>
            {rows.length} 条已载入记录 · 第 {page + 1} 页
          </span>
          <button
            disabled={page === 0}
            onClick={() => setPage((x) => x - 1)}
            aria-label="上一页"
          >
            <ArrowLeft size={15} />
          </button>
          <button
            disabled={(page + 1) * 50 >= rows.length}
            onClick={() => setPage((x) => x + 1)}
            aria-label="下一页"
          >
            <ArrowRight size={15} />
          </button>
        </div>
      )}
    </>
  );
}
export function RemoteTable({
  path,
  exportPath,
  columnLabels,
}: {
  path: string;
  exportPath?: string;
  columnLabels?: Obj;
}) {
  const [offset, setOffset] = useState(0);
  useEffect(() => setOffset(0), [path]);
  const separator = path.includes("?") ? "&" : "?";
  const resource = useResource<TableData>(
    `${path}${separator}offset=${offset}&limit=200`,
  );
  return (
    <>
      <div className="table-toolbar">
        <span>
          {resource.data
            ? `${resource.data.total.toLocaleString()} 条记录`
            : "完整记录"}
        </span>
        <div className="actions">
          <button onClick={resource.refresh}>
            <RotateCw size={14} />
            刷新
          </button>
          {exportPath && (
            <a className="button" href={"/api/v1" + exportPath}>
              <ArrowDownToLine size={14} />
              下载全部 CSV
            </a>
          )}
        </div>
      </div>
      <ErrorBox error={resource.error} />
      {resource.loading ? (
        <Loading />
      ) : (
        <DataTable data={resource.data} columnLabels={columnLabels} />
      )}
      <div className="pagination">
        <span>服务端分页 · 每次 200 条</span>
        <button
          disabled={offset === 0}
          onClick={() => setOffset((x) => Math.max(0, x - 200))}
        >
          上一批
        </button>
        <button
          disabled={!resource.data || offset + 200 >= resource.data.total}
          onClick={() => setOffset((x) => x + 200)}
        >
          下一批
        </button>
      </div>
    </>
  );
}
const LazyChart = lazy(() =>
  import("./Charts").then((module) => ({ default: module.Chart })),
);
export function Chart(props: ComponentProps<typeof import("./Charts").Chart>) {
  return (
    <Suspense fallback={<Loading />}>
      <LazyChart {...props} />
    </Suspense>
  );
}
export function Report({ value, depth = 0 }: { value: any; depth?: number }) {
  if (value == null) return <span className="muted">未记录</span>;
  if (value.columns && Array.isArray(value.rows))
    return <DataTable data={value} />;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="muted">无</span>;
    if (value.every((x) => x && typeof x === "object" && !Array.isArray(x)))
      return <DataTable data={value} />;
    return (
      <ul className="report-list">
        {value.map((item, i) => (
          <li key={i}>
            <Report value={item} depth={depth + 1} />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value !== "object")
    return <span className="report-text">{format(value)}</span>;
  if (value.index && value.values)
    return (
      <DataTable
        data={value.index.map((index: unknown, i: number) => ({
          index,
          value: value.values[i],
        }))}
      />
    );
  const entries = Object.entries(value);
  const scalar = Object.fromEntries(
    entries.filter(([, v]) => v === null || typeof v !== "object"),
  );
  const nested = entries.filter(([, v]) => v && typeof v === "object");
  return (
    <div className="report">
      {Object.keys(scalar).length > 0 && (
        <dl className="key-values">
          {Object.entries(scalar).map(([key, v]) => (
            <div key={key}>
              <dt title={key}>{labels[key] || key}</dt>
              <dd>{format(v, key)}</dd>
            </div>
          ))}
        </dl>
      )}
      {nested.map(([key, v]) => (
        <details key={key} open={depth < 1}>
          <summary>
            {labels[key] || key}
            <ChevronDown size={14} />
          </summary>
          <Report value={v} depth={depth + 1} />
        </details>
      ))}
    </div>
  );
}
const LazyBars = lazy(() =>
  import("./Charts").then((module) => ({ default: module.Bars })),
);
export function Bars(props: ComponentProps<typeof import("./Charts").Bars>) {
  return (
    <Suspense fallback={<Loading />}>
      <LazyBars {...props} />
    </Suspense>
  );
}
export function JobPanel({
  job,
  showResult = true,
}: {
  job: Job;
  showResult?: boolean;
}) {
  return (
    <>
      <ErrorBox error={job.error} />
      {job.task && (
        <Card
          className="task-card"
          title="后台任务"
          action={<Badge value={job.task.status} />}
        >
          <div className="task-meta">
            <code>{job.task.id}</code>
            <span>{job.task.progress.stage}</span>
          </div>
          {job.task.progress.total != null && job.task.progress.total > 0 ? (
            <progress
              max={job.task.progress.total}
              value={job.task.progress.completed}
            />
          ) : (
            <p className="muted">等待阶段进度 · 关闭页面后任务继续</p>
          )}
          <div className="actions">
            {![
              "SUCCESS",
              "PARTIAL",
              "FAILED",
              "CANCELLED",
              "INTERRUPTED",
            ].includes(job.task.status) && (
              <button
                onClick={job.cancel}
                disabled={job.task.status === "CANCEL_REQUESTED"}
              >
                请求取消
              </button>
            )}
            {["FAILED", "PARTIAL", "CANCELLED", "INTERRUPTED"].includes(
              job.task.status,
            ) && <button onClick={job.retry}>按原参数重试</button>}
            <Link className="text-button" to="/app/operations/jobs">
              全部任务 <ArrowRight size={14} />
            </Link>
          </div>
          {job.task.error && <Note tone="error">{job.task.error.message}</Note>}
          <details>
            <summary>进度与事件日志（{job.events.length}）</summary>
            <div className="event-log">
              {job.events.map((e, i) => (
                <div key={i}>
                  <time>{e.created_at.slice(11, 19)}</time>
                  <span>{e.stage}</span>
                  <span>
                    {e.message ||
                      (e.total != null
                        ? `${e.completed ?? ""} / ${e.total}`
                        : "")}
                  </span>
                </div>
              ))}
            </div>
          </details>
        </Card>
      )}
      {showResult && job.result && (
        <Card title="任务结果">
          <Report value={job.result} />
        </Card>
      )}
    </>
  );
}
export function JsonEditor({
  label,
  value,
  onChange,
  rows = 8,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <Field label={label}>
      <textarea
        className="code-input"
        rows={rows}
        spellCheck={false}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}
