import { useEffect, useState } from "react";
import { ArrowRight, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { useFullTable } from "./Backtests";
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
  RemoteTable,
  Report,
  Tabs,
} from "../components";

const split = (text: string) => text.split(/[\s,，;；]+/).filter(Boolean);
export function DataUpdate() {
  const [tab, setTab] = useState("update"),
    overview = useResource("/data/overview"),
    sources = useResource("/data/sources"),
    backfill = useResource("/data/backfill/jobs"),
    defaults = useResource("/backtests/defaults");
  const [benchmark, setBenchmark] = useState("");
  const backfillActive = backfill.data?.items.some((item: Obj) =>
    ["RUNNING", "STARTING", "RETRYING"].includes(item.status),
  );
  useEffect(() => {
    const timer = setInterval(backfill.refresh, 5000);
    return () => clearInterval(timer);
  }, []);
  const [draft, setDraft] = useSticky("data-update", {
    start_date: "",
    end_date: "",
    datasets: ["daily_bars", "benchmark_bars"],
    source: "",
    allow_market_fallback: true,
    benchmarks: "",
  });
  const [filter, setFilter] = useSticky("data-query", {
    symbols: "",
    start_date: "",
    end_date: "",
  });
  const job = useJob("data-update");
  useEffect(() => {
    if (!draft.start_date && defaults.data)
      setDraft({
        ...draft,
        start_date: defaults.data.start_date,
        end_date: defaults.data.end_date,
      });
  }, [defaults.data]);
  const change = (key: string, value: any) =>
    setDraft({ ...draft, [key]: value });
  const table = (
    {
      bars: "daily_bars",
      benchmark: "benchmark_bars",
      master: "security_master",
      versions: "data_manifests",
    } as Obj
  )[tab];
  const filtered = ["bars", "benchmark"].includes(tab)
    ? query({
        symbols: split(filter.symbols),
        start_date: filter.start_date,
        end_date: filter.end_date,
      })
    : "";
  const tableFilter = tab === "benchmark" && benchmark
    ? query({ symbols: [benchmark], start_date: filter.start_date, end_date: filter.end_date })
    : filtered;
  return (
    <>
      <PageHead
        title="行情与数据管理"
        description="检查覆盖率，选择本次数据来源，保留实际更新记录。"
        actions={
          <button
            onClick={() => {
              overview.refresh();
              sources.refresh();
              backfill.refresh();
            }}
          >
            <RefreshCw size={15} />
            刷新概览
          </button>
        }
      />
      <Card title="当前仓库">
        <ErrorBox error={overview.error || sources.error || backfill.error} />
        {overview.loading ? (
          <Loading />
        ) : (
          <>
            <MetricGrid
              values={{
                配置股票: overview.data?.configured_symbol_count,
                证券主表: overview.data?.security_count,
                行情记录: overview.data?.market?.rows,
                有行情股票: overview.data?.market?.symbol_count,
                未知状态行: overview.data?.market?.unknown_status_rows,
                覆盖率:
                  overview.data?.market?.coverage_ratio == null
                    ? null
                    : `${(overview.data.market.coverage_ratio * 100).toFixed(1)}%`,
              }}
            />
            <details>
              <summary>行情、基准与覆盖范围详情</summary>
              <Report value={overview.data} />
            </details>
            {overview.data?.market?.rows === 0 && <Empty>仓库暂无股票行情，请先选择数据集并更新。</Empty>}
          </>
        )}
      </Card>
      <Tabs
        items={[
          ["update", "日常更新"],
          ["coverage", "股票池覆盖"],
          ["bars", "股票行情"],
          ["benchmark", "基准行情"],
          ["master", "证券主表"],
          ["versions", "数据版本"],
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "update" && (
        <>
          <Card title="更新选择">
            <DataTable data={sources.data as any} />
            {backfillActive && <Note>全市场回填正在运行，请等待完成或安全停止后再进行日常更新。</Note>}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void job.submit("data_update", {
                  start_date: draft.start_date,
                  end_date: draft.end_date,
                  datasets: draft.datasets,
                  market_source_order: draft.source ? [draft.source] : null,
                  allow_market_fallback: draft.allow_market_fallback,
                  benchmark_symbols: draft.benchmarks
                    ? split(draft.benchmarks)
                    : null,
                });
              }}
            >
              <div className="form-grid">
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
                    max={new Date().toISOString().slice(0, 10)}
                    value={draft.end_date}
                    onChange={(e) => change("end_date", e.target.value)}
                  />
                </Field>
                <Field label="本次首选行情来源">
                  <select
                    value={draft.source}
                    onChange={(e) => change("source", e.target.value)}
                  >
                    <option value="">沿用默认路由</option>
                    {sources.data?.rows?.map((row: Obj) => (
                      <option key={row.provider} value={row.provider}>
                        {row.display_name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="基准代码（可多个，逗号分隔）">
                  <input
                    value={draft.benchmarks}
                    placeholder="留空使用配置基准"
                    onChange={(e) => change("benchmarks", e.target.value)}
                  />
                </Field>
              </div>
              <div className="checks">
                {[
                  ["security_master", "证券主表"],
                  ["daily_bars", "股票日线"],
                  ["corporate_actions", "分红送配"],
                  ["benchmark_bars", "基准行情"],
                ].map(([id, label]) => (
                  <CheckBox
                    key={id}
                    label={label}
                    checked={draft.datasets.includes(id)}
                    onChange={(value) =>
                      change(
                        "datasets",
                        value
                          ? [...draft.datasets, id]
                          : draft.datasets.filter((v) => v !== id),
                      )
                    }
                  />
                ))}
                <CheckBox
                  label="允许自动回退"
                  checked={draft.allow_market_fallback}
                  onChange={(value) => change("allow_market_fallback", value)}
                />
              </div>
              <button
                className="primary"
                type="submit"
                disabled={job.active || backfill.loading || !!backfill.error || backfillActive || !draft.datasets.length}
              >
                提交后台更新
              </button>
              <p className="muted">
                本次选源不修改默认配置；实际来源与失败明细在数据版本中记录。
              </p>
            </form>
          </Card>
          <JobPanel job={job} showResult={false} />
          {job.result && (
            <Card
              title="更新反馈"
              action={
                <button
                  onClick={() =>
                    csv(job.result!.results, "data_update_results.csv")
                  }
                >
                  下载全部更新结果
                </button>
              }
            >
              <DataTable data={job.result.results} />
              <button
                onClick={() => {
                  overview.refresh();
                  sources.refresh();
                }}
              >
                读取更新后的仓库
              </button>
            </Card>
          )}
        </>
      )}
      {tab === "coverage" && (
        <Card title="配置股票池覆盖率">
          <RemoteTable
            path="/data/coverage"
            exportPath="/data/coverage/export.csv"
          />
        </Card>
      )}
      {table && (
        <Card
          title={
            (
              {
                bars: "股票日线行情",
                benchmark: "基准行情",
                master: "证券主表",
                versions: "实际数据版本",
              } as Obj
            )[tab]
          }
        >
          {["bars", "benchmark"].includes(tab) && (
            <div className="form-grid">
              <Field label="证券代码（标准代码，逗号分隔）">
                <input
                  value={filter.symbols}
                  placeholder={
                    tab === "benchmark" ? "000300.SH" : "000001.SZ,600000.SH"
                  }
                  onChange={(e) =>
                    setFilter({ ...filter, symbols: e.target.value })
                  }
                />
              </Field>
              <Field label="开始日期">
                <input
                  type="date"
                  value={filter.start_date}
                  onChange={(e) =>
                    setFilter({ ...filter, start_date: e.target.value })
                  }
                />
              </Field>
              <Field label="结束日期">
                <input
                  type="date"
                  value={filter.end_date}
                  onChange={(e) =>
                    setFilter({ ...filter, end_date: e.target.value })
                  }
                />
              </Field>
            </div>
          )}
          {tab === "benchmark" && <BenchmarkChart filters={filtered} onSelect={setBenchmark} />}
          <RemoteTable
            key={table + tableFilter}
            path={`/data/tables/${table}${tableFilter}`}
            exportPath={`/data/tables/${table}/export.csv${tableFilter}`}
          />
        </Card>
      )}
    </>
  );
}
function BenchmarkChart({ filters, onSelect }: { filters: string; onSelect: (symbol: string) => void }) {
  const resource = useFullTable("/data/tables/benchmark_bars" + filters);
  const [selected, setSelected] = useState("");
  const rows = resource.data || [],
    symbols = [...new Set<string>(rows.map((r: Obj) => r.symbol))];
  const current = symbols.includes(selected) ? selected : symbols[0];
  useEffect(() => { onSelect(current || ""); }, [current, onSelect]);
  return (
    <>
      <Field label="绘图基准">
        <select
          value={current || ""}
          onChange={(e) => setSelected(e.target.value)}
        >
          {symbols.map((symbol) => (
            <option key={symbol}>{symbol}</option>
          ))}
        </select>
      </Field>
      {resource.loading ? (
        <Loading />
      ) : (
        current ? (
          <div>
            <h3>{current}</h3>
            <Chart
              rows={rows.filter((r: Obj) => r.symbol === current)}
              x="trade_date"
              series={[["raw_close", "收盘价"]]}
            />
          </div>
        ) : <Empty>当前范围没有基准行情。</Empty>
      )}
      <ErrorBox error={resource.error} />
    </>
  );
}
export function Universe() {
  const resource = useResource("/universe"),
    action = useAction();
  const [text, setText] = useState(""),
    [search, setSearch] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [removeConfirmed, setRemoveConfirmed] = useState(false),
    [filters, setFilters] = useState<Obj>();
  const results = useResource("/universe/search" + query({ q: search }));
  useEffect(() => {
    if (resource.data?.settings) {
      const { symbols, universe_id, ...rest } = resource.data.settings;
      setFilters(rest);
    }
  }, [resource.data]);
  const refresh = () => {
    resource.refresh();
    setSelected([]);
    setRemoveConfirmed(false);
  };
  return (
    <>
      <PageHead
        title="股票池"
        description="维护研究范围与过滤规则，移除股票不会删除已有行情。"
      />
      <Card title="添加与搜索证券">
        <Note>
          添加证券或修改过滤规则后，请到{" "}
          <Link to="/app/data/update">数据更新</Link>{" "}
          补齐当前股票池的行情，再运行研究。
        </Note>
        <div className="form-grid">
          <Field label="证券代码（多个可用逗号或换行分隔）">
            <textarea
              rows={2}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="000001,600000"
            />
          </Field>
          <Field label="按名称或代码搜索证券主表">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="平安 / 000001"
            />
          </Field>
        </div>
        <button
          className="primary"
          disabled={!text.trim() || action.busy}
          onClick={() =>
            action.run(
              () => post("/universe/symbols", { symbols: split(text) }),
              () => {
                refresh();
                setText("");
                action.setMessage("已添加并归一化证券代码");
              },
            )
          }
        >
          添加到股票池
        </button>
        {search && (
          <DataTable
            data={results.data as any}
            onRow={(row) =>
              setText((previous) =>
                (
                  previous +
                  "," +
                  (row.symbol || row["证券代码"] || "")
                ).replace(/^,/, ""),
              )
            }
          />
        )}
        {search && !results.loading && results.data?.total === 0 && (
          <Note>
            未找到匹配证券。请检查名称或代码；如果本机尚无证券主表，请先到{" "}
            <Link to="/app/data/update">数据更新</Link> 更新证券主表。
          </Note>
        )}
        <ErrorBox error={resource.error || results.error || action.error} />
        {action.message && <Note tone="success">{action.message}</Note>}
      </Card>
      <Card
        title={`当前股票池 · ${resource.data?.settings.symbols.length ?? "—"} 只`}
      >
        <p className="muted">点击记录勾选，再移除所选项。</p>
        <DataTable
          data={resource.data?.symbols}
          onRow={(row) => {
            setRemoveConfirmed(false);
            const symbol = row.symbol || row["证券代码"];
            setSelected((previous) =>
              previous.includes(symbol)
                ? previous.filter((v) => v !== symbol)
                : [...previous, symbol],
            );
          }}
          selected={(row) => selected.includes(row.symbol || row["证券代码"])}
        />
        <CheckBox
          label="确认从股票池移除所选证券"
          checked={removeConfirmed}
          onChange={setRemoveConfirmed}
        />
        <button
          className="danger"
          disabled={!selected.length || !removeConfirmed || action.busy}
          onClick={() =>
            action.run(
              () => post("/universe/symbols/remove", { symbols: selected }),
              refresh,
            )
          }
        >
          移除所选 {selected.length} 只股票
        </button>
      </Card>
      {filters && (
        <Card title="股票池过滤">
          <div className="form-grid">
            {[
              ["minimum_listing_days", "最少上市天数"],
              ["minimum_history_days", "最少行情天数"],
              ["minimum_average_amount", "最低平均成交额（元）"],
            ].map(([key, label]) => (
              <Field label={label} key={key}>
                <input
                  type="number"
                  min={key === "minimum_history_days" ? 1 : 0}
                  value={filters[key]}
                  onChange={(e) =>
                    setFilters({ ...filters, [key]: Number(e.target.value) })
                  }
                />
              </Field>
            ))}
          </div>
          <CheckBox
            label="排除 ST"
            checked={filters.exclude_st}
            onChange={(value) => setFilters({ ...filters, exclude_st: value })}
          />
          <CheckBox
            label="排除停牌证券"
            checked={filters.exclude_suspended}
            onChange={(value) =>
              setFilters({ ...filters, exclude_suspended: value })
            }
          />
          <button
            className="primary"
            disabled={action.busy}
            onClick={() =>
              action.run(
                () =>
                  api("/universe/filters", {
                    method: "PUT",
                    body: JSON.stringify(filters),
                  }),
                () => {
                  refresh();
                  action.setMessage("过滤规则已保存");
                },
              )
            }
          >
            保存过滤规则
          </button>
        </Card>
      )}
    </>
  );
}
export function Jobs() {
  const [status, setStatus] = useState(""),
    [kind, setKind] = useState(""),
    [offset, setOffset] = useState(0);
  const resource = useResource(
      "/tasks" + query({ status, kind, offset, limit: 50 }),
    ),
    job = useJob("task-browser");
  useEffect(() => {
    const timer = setInterval(resource.refresh, 5000);
    return () => clearInterval(timer);
  }, []);
  return (
    <>
      <PageHead
        title="后台任务"
        description="任务与浏览器页面独立，关闭页面后仍可从这里恢复查询。"
        actions={<button onClick={resource.refresh}>刷新任务</button>}
      />
      <Card title="任务记录">
        <div className="form-grid">
          <Field label="状态">
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">全部状态</option>
              {[
                "QUEUED",
                "RUNNING",
                "CANCEL_REQUESTED",
                "SUCCESS",
                "PARTIAL",
                "FAILED",
                "CANCELLED",
                "INTERRUPTED",
              ].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
          <Field label="类型">
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">全部类型</option>
              {[
                "backtest",
                "optimization",
                "walk_forward",
                "factor_evaluation",
                "factor_combination",
                "data_update",
                "ai_analysis",
                "ai_chat",
                "nl_strategy",
                "xtick_query",
              ].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
        </div>
        <ErrorBox error={resource.error} />
        <DataTable
          data={resource.data?.items}
          onRow={(row) => job.setId(row.id)}
          selected={(row) => row.id === job.id}
        />
        <div className="pagination">
          <button disabled={!offset} onClick={() => setOffset((x) => x - 50)}>
            上一批
          </button>
          <button
            disabled={!resource.data || offset + 50 >= resource.data.total}
            onClick={() => setOffset((x) => x + 50)}
          >
            下一批
          </button>
        </div>
      </Card>
      <JobPanel job={job} />
      {job.result?.run_id && (
        <Link
          className="button primary"
          to={"/app/backtests/" + job.result.run_id}
        >
          打开回测报告 <ArrowRight size={14} />
        </Link>
      )}
      <BackfillPanel compact />
    </>
  );
}
export function Backfill() {
  return (
    <>
      <PageHead
        title="全市场回填"
        description="沿用原有断点、互斥与重试机制，持续补齐全市场数据。"
      />
      <BackfillPanel />
      <ClosedLoop />
    </>
  );
}
function ClosedLoop() {
  const resource = useResource("/data/closed-loop");
  return (
    <Card title="全市场数据闭环">
      <ErrorBox error={resource.error} />
      <Report value={resource.data} />
      <Note>
        历史成分与退市结算中的部分记录是推导或近似值，请结合来源说明核对。
      </Note>
    </Card>
  );
}
export function BackfillPanel({ compact = false }: { compact?: boolean }) {
  const resource = useResource("/data/backfill/jobs"),
    action = useAction();
  const [selected, setSelected] = useSticky("backfill-selected", ""),
    [draft, setDraft] = useSticky("backfill", {
      start_date: "2019-01-01",
      end_date: new Date().toISOString().slice(0, 10),
      datasets: ["bars", "actions", "derived"],
    });
  const log = useResource(
    selected ? `/data/backfill/jobs/${selected}/log` : null,
  );
  useEffect(() => {
    const timer = setInterval(() => {
      resource.refresh();
      if (selected) log.refresh();
    }, 5000);
    return () => clearInterval(timer);
  }, [selected]);
  const record = resource.data?.items.find((item: Obj) => item.id === selected);
  return (
    <Card title={compact ? "全市场回填任务" : "回填配置与任务"}>
      {!compact && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(
              () => post("/data/backfill/jobs", draft),
              (value) => {
                setSelected(value.id);
                resource.refresh();
              },
            );
          }}
        >
          <div className="form-grid">
            <Field label="开始日期">
              <input
                type="date"
                required
                value={draft.start_date}
                onChange={(e) =>
                  setDraft({ ...draft, start_date: e.target.value })
                }
              />
            </Field>
            <Field label="结束日期">
              <input
                type="date"
                required
                min={draft.start_date}
                max={new Date().toISOString().slice(0, 10)}
                value={draft.end_date}
                onChange={(e) =>
                  setDraft({ ...draft, end_date: e.target.value })
                }
              />
            </Field>
          </div>
          <div className="checks">
            {[
              ["bars", "日线行情"],
              ["actions", "公司行为"],
              ["derived", "派生闭环数据"],
            ].map(([id, label]) => (
              <CheckBox
                key={id}
                label={label}
                checked={draft.datasets.includes(id)}
                onChange={(value) =>
                  setDraft({
                    ...draft,
                    datasets: value
                      ? [...draft.datasets, id]
                      : draft.datasets.filter((v) => v !== id),
                  })
                }
              />
            ))}
          </div>
          <button
            className="primary"
            disabled={
              action.busy ||
              !draft.datasets.length ||
              resource.data?.items.some((r: Obj) =>
                ["RUNNING", "STARTING", "RETRYING"].includes(r.status),
              )
            }
          >
            启动后台回填
          </button>
          <p className="muted">
            证券主表始终更新；相同区间跳过已完成检查点，自动重试最多 20 次。
          </p>
        </form>
      )}
      <ErrorBox error={resource.error || action.error} />
      <DataTable
        data={resource.data?.items}
        onRow={(row) => setSelected(row.id)}
        selected={(row) => row.id === selected}
      />
      {record && (
        <>
          <Report value={record} />
          <div className="actions">
            {["RUNNING", "STARTING", "RETRYING"].includes(record.status) && (
              <button
                disabled={action.busy || record.stopping}
                onClick={() =>
                  action.run(
                    () => post(`/data/backfill/jobs/${selected}/stop`),
                    resource.refresh,
                  )
                }
              >
                请求安全停止
              </button>
            )}
            {["FAILED", "PARTIAL", "STOPPED", "INTERRUPTED"].includes(
              record.status,
            ) && (
              <button
                disabled={action.busy || resource.data?.items.some((r: Obj) =>
                  ["RUNNING", "STARTING", "RETRYING"].includes(r.status),
                )}
                onClick={() =>
                  action.run(
                    () => post(`/data/backfill/jobs/${selected}/retry`),
                    (value) => {
                      setSelected(value.id);
                      resource.refresh();
                    },
                  )
                }
              >
                沿原范围继续回填
              </button>
            )}
          </div>
          <details open>
            <summary>最近日志（最多 32 KB）</summary>
            <pre className="log-output">{log.data?.text || "暂无日志"}</pre>
            <ErrorBox error={log.error} />
          </details>
        </>
      )}
    </Card>
  );
}
export function DataSources() {
  const resource = useResource("/data/sources"),
    settings = useResource("/settings");
  return (
    <>
      <PageHead
        title="数据资产与来源"
        description="配置状态和安装状态不等于网络连通或下载成功；实际成功来源请看数据版本。"
      />
      <Card title="当前行情路由">
        <ErrorBox error={resource.error || settings.error} />
        <DataTable data={resource.data as any} />
      </Card>
      <div className="tool-grid">
        {[
          ["XTick", "动态接口与量化因子，凭证配置后可专项查询。"],
          ["BaoStock", "免费历史行情、停牌与历史 ST 状态。"],
          ["AkShare", "公开证券主表、基准行情与备用日线来源。"],
          ["iFinD", "需要官方 SDK 与账号，用于首选行情路由。"],
          ["Tushare", "需要 Token，具体数据权限取决于服务账户。"],
        ].map(([name, text]) => (
          <Card title={name} key={name}>
            <p className="muted">{text}</p>
            <Link
              className="text-button"
              to={name === "XTick" ? "/app/data/xtick" : "/app/settings"}
            >
              {name === "XTick" ? "打开动态接口" : "查看配置"} →
            </Link>
          </Card>
        ))}
      </div>
      <Link className="button" to="/app/data/update">
        查看实际来源版本 →
      </Link>
    </>
  );
}
export function XTick() {
  const catalog = useResource("/data/xtick/catalog"),
    job = useJob("xtick"),
    [selection, setSelection] = useSticky("xtick-selection", {
      category: 1,
      api: 101,
    });
  const [values, setValues] = useSticky<Obj>("xtick-parameters", {}),
    [history, setHistory] = useSticky<Obj>("xtick-history", {});
  const category =
    catalog.data?.items.find((c: Obj) => c.id === selection.category) ||
    catalog.data?.items[0];
  const endpoint =
    category?.docApis.find((a: Obj) => a.id === selection.api) ||
    category?.docApis[0];
  const scope = `${category?.id}:${endpoint?.id}`,
    fields = endpoint?.inputParas || [],
    parameters = values[scope] || endpoint?.defaults || {};
  const signature = JSON.stringify({ scope, parameters }),
    current = history[scope]?.signature === signature;
  useEffect(() => {
    if (endpoint) job.setId(history[scope]?.id || null);
  }, [scope]);
  const set = (key: string, value: string) =>
    setValues({ ...values, [scope]: { ...parameters, [key]: value } });
  return (
    <>
      <PageHead
        title="XTick 动态接口"
        description="由完整接口目录生成表单，每个接口保留自己的参数与字段解释。"
        actions={
          <Link className="button" to="/app/settings">
            配置凭证
          </Link>
        }
      />
      <Card title="选择分类与接口">
        <ErrorBox error={catalog.error} />
        <div className="form-grid">
          <Field label="分类">
            <select
              value={category?.id || ""}
              disabled={job.submitting}
              onChange={(e) => {
                const c = catalog.data!.items.find(
                  (v: Obj) => v.id === Number(e.target.value),
                );
                setSelection({ category: c.id, api: c.docApis[0].id });
              }}
            >
              {catalog.data?.items.map((c: Obj) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {c.docApis.length} 个接口
                </option>
              ))}
            </select>
          </Field>
          <Field label="接口">
            <select
              value={endpoint?.id || ""}
              disabled={job.submitting}
              onChange={(e) =>
                setSelection({ ...selection, api: Number(e.target.value) })
              }
            >
              {category?.docApis.map((a: Obj) => (
                <option key={a.id} value={a.id}>
                  {a.id} · {a.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <p>{endpoint?.description}</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void (async () => {
              const input: Obj = {};
              for (const field of fields) {
                const name = field.name;
                const options = String(field.range || "")
                  .split(/[，,]/)
                  .filter(Boolean);
                input[name] =
                  parameters[name] ??
                  (options.length ? options[0].trim().split("-")[0] : "");
              }
              setHistory((previous) => {
                const next = { ...previous };
                delete next[scope];
                return next;
              });
              const task = await job.submit("xtick_query", {
                category_id: category.id,
                api_id: endpoint.id,
                parameters: input,
              });
              if (task)
                setHistory((previous) => ({
                  ...previous,
                  [scope]: { id: task.id, signature },
                }));
            })();
          }}
        >
          <div className="form-grid">
            {fields.map((field: Obj) => {
              const options = String(field.range || "")
                .split(/[，,]/)
                .map((v) => v.trim())
                .filter(Boolean);
              return (
                <Field
                  key={field.name}
                  label={field.name}
                  hint={field.description}
                >
                  {options.length ? (
                    <select
                      value={parameters[field.name] ?? options[0].split("-")[0]}
                      onChange={(e) => set(field.name, e.target.value)}
                    >
                      {options.map((value) => (
                        <option key={value} value={value.split("-")[0]}>
                          {value}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={parameters[field.name] || ""}
                      onChange={(e) => set(field.name, e.target.value)}
                      type={
                        /int|float|double/i.test(field.type) ? "number" : "text"
                      }
                      step={/int/i.test(field.type) ? 1 : "any"}
                      placeholder={
                        /Date$/i.test(field.name)
                          ? "YYYYMMDD 或 YYYY-MM-DD"
                          : field.type
                      }
                    />
                  )}
                </Field>
              );
            })}
          </div>
          <button className="primary" disabled={!endpoint || job.active}>
            查询此接口
          </button>
        </form>
      </Card>
      <JobPanel job={job} showResult={false} />
      {job.result && (
        <Card title="接口结果">
          {!current && <Note>接口或参数已切换，下方是上次查询的结果。</Note>}
          {job.result.table ? (
            <>
              <DataTable
                data={job.result.table}
                columnLabels={job.result.output_labels}
              />
              <button
                onClick={() =>
                  csv(
                    job.result!.table.rows.map((row: Obj) =>
                      Object.fromEntries(
                        Object.entries(row).map(([key, value]) => [
                          job.result!.output_labels[key]
                            ? `${job.result!.output_labels[key]}（${key}）`
                            : key,
                          value,
                        ]),
                      ),
                    ),
                    "xtick_" + job.task?.id + ".csv",
                  )
                }
              >
                下载完整 CSV
              </button>
            </>
          ) : (
            <Report value={job.result.raw} />
          )}
          <details>
            <summary>原始 JSON</summary>
            <pre className="log-output">
              {JSON.stringify(job.result.raw, null, 2)}
            </pre>
          </details>
          <button
            onClick={() => download(job.result!.raw, "xtick_result.json")}
          >
            下载原始 JSON
          </button>
        </Card>
      )}
    </>
  );
}
