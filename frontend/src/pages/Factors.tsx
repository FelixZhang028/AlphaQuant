import { useEffect, useState } from "react";
import { ArrowRight, Plus } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  api,
  csv,
  download,
  type Obj,
  post,
  remove,
  useAction,
  useJob,
  useResource,
  useSticky,
} from "../api";
import {
  Bars,
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
} from "../components";

const factorTabs = [
  ["library", "因子库"],
  ["evaluation", "因子评估"],
  ["combinations", "因子组合"],
  ["custom", "自定义因子"],
];
const defaultCombination = {
  factor_names: [] as string[],
  train_start: "",
  train_end: "",
  test_start: "",
  test_end: "",
  mode: "equal",
  custom_weights: {} as Obj,
  clip: true,
  missing: "drop",
  horizon: 5,
  n_groups: 5,
};
export function FactorLab({ tab = "library" }: { tab?: string }) {
  return (
    <>
      <PageHead
        title="因子实验室"
        description="从公式与数据出发，研究信号的有效性和互补性。"
      />
      <div className="subnav">
        {factorTabs.map(([id, label]) => (
          <Link
            key={id}
            className={id === tab ? "active" : ""}
            to={"/app/factors/" + id}
          >
            {label}
          </Link>
        ))}
      </div>
      {tab === "library" ? (
        <FactorLibrary />
      ) : tab === "evaluation" ? (
        <FactorEvaluation />
      ) : tab === "combinations" ? (
        <FactorCombination />
      ) : (
        <CustomFactors />
      )}
    </>
  );
}
function FactorLibrary() {
  const resource = useResource("/factors/catalog"),
    navigate = useNavigate();
  const [filter, setFilter] = useSticky("factor-library-filter", {
    q: "",
    category: "",
    source: "",
    intents: [] as string[],
  });
  const [selected, setSelected] = useState<string>(),
    [, setCombination] = useSticky("combination-draft", defaultCombination);
  const items = (resource.data?.items || []).filter(
    (f: Obj) =>
      (!filter.category || f.classification.category === filter.category) &&
      (!filter.source || f.source === filter.source) &&
      (!filter.intents.length ||
        filter.intents.some((v) => f.classification.intents.includes(v))) &&
      `${f.name} ${f.display_name} ${f.description} ${f.formula}`
        .toLowerCase()
        .includes(filter.q.toLowerCase()),
  );
  const detail = items.find((f: Obj) => f.name === selected);
  useEffect(() => {
    if (selected && !items.some((f: Obj) => f.name === selected))
      setSelected(undefined);
  }, [JSON.stringify(filter), resource.data]);
  return (
    <>
      <Card title="因子目录">
        <div className="form-grid">
          <Field label="关键词 / 编号">
            <input
              value={filter.q}
              onChange={(e) => setFilter({ ...filter, q: e.target.value })}
              placeholder="搜索名称、Alpha 编号或公式"
            />
          </Field>
          <Field label="类别">
            <select
              value={filter.category}
              onChange={(e) =>
                setFilter({ ...filter, category: e.target.value })
              }
            >
              <option value="">全部类别</option>
              {[
                ...new Set<string>(
                  resource.data?.items.map(
                    (f: Obj) => f.classification.category,
                  ) || [],
                ),
              ].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
          <Field label="来源">
            <select
              value={filter.source}
              onChange={(e) => setFilter({ ...filter, source: e.target.value })}
            >
              <option value="">全部来源</option>
              {[
                ...new Set<string>(
                  resource.data?.items.map((f: Obj) => f.source) || [],
                ),
              ].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
        </div>
        <div className="intent-chips">
          {Object.keys(resource.data?.intents || {}).map((intent) => (
            <button
              className={filter.intents.includes(intent) ? "chosen" : ""}
              key={intent}
              onClick={() =>
                setFilter({
                  ...filter,
                  intents: filter.intents.includes(intent)
                    ? filter.intents.filter((v) => v !== intent)
                    : [...filter.intents, intent],
                })
              }
            >
              {intent}
            </button>
          ))}
        </div>
        <p className="muted">
          匹配 {items.length} / {resource.data?.items.length ?? "—"} 个因子 ·
          多个研究意图按“或”匹配
        </p>
        <ErrorBox error={resource.error} />
        {resource.loading ? (
          <Loading />
        ) : (
          <DataTable
            data={items.map((f: Obj) => ({
              name: f.name,
              display_name: f.display_name,
              category: f.classification.category,
              source: f.source,
              direction: f.direction,
              min_history: f.min_history,
              version: f.version,
            }))}
            onRow={(row) =>
              setSelected(row.name === selected ? undefined : row.name)
            }
            selected={(row) => row.name === selected}
          />
        )}
      </Card>
      {detail && (
        <Card title={detail.display_name}>
          <Report value={detail} />
          {detail.source_url && (
            <a
              className="text-button"
              target="_blank"
              rel="noreferrer"
              href={detail.source_url}
            >
              查看原始来源 ↗
            </a>
          )}
          <div className="actions">
            <button
              className="primary"
              onClick={() =>
                navigate("/app/factors/evaluation?factor=" + detail.name)
              }
            >
              用于因子评估 <ArrowRight size={14} />
            </button>
            <button
              onClick={() => {
                setCombination((previous) => ({
                  ...previous,
                  factor_names: [
                    ...new Set([...previous.factor_names, detail.name]),
                  ],
                }));
                navigate("/app/factors/combinations");
              }}
            >
              <Plus size={14} />
              加入因子组合
            </button>
          </div>
        </Card>
      )}
    </>
  );
}
function FactorEvaluation() {
  const factors = useResource("/factors/catalog"),
    defaults = useResource("/backtests/defaults"),
    [search] = useSearchParams();
  const [draft, setDraft] = useSticky("factor-evaluation", {
    factor_name: search.get("factor") || "momentum_20",
    start_date: "",
    end_date: "",
    horizon: 5,
    n_groups: 5,
    neutralization: "none",
  });
  const job = useJob("factor-evaluation");
  useEffect(() => {
    if (search.get("factor"))
      setDraft((previous) => ({
        ...previous,
        factor_name: search.get("factor")!,
      }));
  }, [search]);
  useEffect(() => {
    if (!draft.start_date && defaults.data)
      setDraft((previous) => ({
        ...previous,
        start_date: defaults.data!.start_date,
        end_date: defaults.data!.end_date,
      }));
  }, [defaults.data]);
  const change = (key: string, value: any) =>
    setDraft({ ...draft, [key]: value });
  const [submitted, setSubmitted] = useSticky(
    "factor-evaluation-signature",
    "",
  );
  const result = job.result;
  return (
    <>
      <Card title="单因子研究参数">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (await job.submit("factor_evaluation", draft))
              setSubmitted(JSON.stringify(draft));
          }}
        >
          <div className="form-grid">
            <Field label="因子">
              <select
                value={draft.factor_name}
                onChange={(e) => change("factor_name", e.target.value)}
              >
                {factors.data?.items.map((f: Obj) => (
                  <option key={f.name} value={f.name}>
                    {f.display_name} · {f.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="中性化">
              <select
                value={draft.neutralization}
                onChange={(e) => change("neutralization", e.target.value)}
              >
                {[
                  ["none", "不做中性化"],
                  ["industry", "行业"],
                  ["size", "市值"],
                  ["both", "行业与市值"],
                ].map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <DateFields draft={draft} change={change} />
            <HorizonFields draft={draft} change={change} />
          </div>
          <Note>
            t 日信号对应 t+1 日收盘买入、t+N+1
            日收盘卖出的收益。中性化需要当时的暴露数据，缺失时明确失败。
          </Note>
          <button className="primary" type="submit" disabled={job.active}>
            开始因子评估
          </button>
        </form>
        <ErrorBox error={factors.error || defaults.error} />
      </Card>
      <JobPanel job={job} showResult={false} />
      {result && (
        <Card title={result.display_name || "因子报告"}>
          {submitted !== JSON.stringify(draft) && (
            <Note>参数已修改，当前显示上次提交的报告。</Note>
          )}
          <FactorReport value={result} />
        </Card>
      )}
    </>
  );
}
function DateFields({
  draft,
  change,
  keys = ["start_date", "end_date"],
}: {
  draft: Obj;
  change: (key: string, value: any) => void;
  keys?: string[];
}) {
  const titles: Obj = {
    start_date: "开始日期",
    end_date: "结束日期",
    train_start: "训练开始",
    train_end: "训练结束",
    test_start: "测试开始",
    test_end: "测试结束",
  };
  return (
    <>
      {keys.map((key) => (
        <Field key={key} label={titles[key]}>
          <input
            type="date"
            required
            value={draft[key]}
            onChange={(e) => change(key, e.target.value)}
          />
        </Field>
      ))}
    </>
  );
}
function HorizonFields({
  draft,
  change,
}: {
  draft: Obj;
  change: (key: string, value: any) => void;
}) {
  return (
    <>
      <Field label="持有期（交易日）">
        <select
          value={draft.horizon}
          onChange={(e) => change("horizon", Number(e.target.value))}
        >
          {[1, 5, 10, 20].map((n) => (
            <option key={n} value={n}>
              {n} 日
            </option>
          ))}
        </select>
      </Field>
      <Field label="分组数">
        <select
          value={draft.n_groups}
          onChange={(e) => change("n_groups", Number(e.target.value))}
        >
          <option value={5}>5 组</option>
          <option value={10}>10 组</option>
        </select>
      </Field>
    </>
  );
}
function FactorReport({ value }: { value: Obj }) {
  const groups = value.group_mean_returns;
  const rows =
    groups?.index?.map((group: any, i: number) => ({
      group,
      return: groups.values[i],
    })) || [];
  return (
    <>
      <MetricGrid
        values={value}
        keys={[
          "ic_mean",
          "rank_ic_mean",
          "rank_ic_ir",
          "long_short_mean",
          "turnover_mean",
        ]}
      />
      <Chart rows={value.daily_ic?.rows || []} series={["rank_ic", "ic"]} />
      {rows.length > 0 && <Bars rows={rows} x="group" y="return" />}
      <Report value={value} />
    </>
  );
}
function FactorCombination() {
  const factors = useResource("/factors/catalog"),
    defaults = useResource("/backtests/defaults"),
    action = useAction(),
    navigate = useNavigate();
  const [draft, setDraft] = useSticky("combination-draft", defaultCombination),
    [submitted, setSubmitted] = useSticky("combination-signature", "");
  const job = useJob("factor-combination");
  useEffect(() => {
    if (!draft.train_start && defaults.data) {
      const start = new Date(defaults.data.start_date + "T00:00:00Z"),
        end = new Date(defaults.data.end_date + "T00:00:00Z");
      const middle = new Date((+start + +end) / 2);
      const next = new Date(+middle + 86400000);
      setDraft({
        ...draft,
        train_start: defaults.data.start_date,
        train_end: middle.toISOString().slice(0, 10),
        test_start: next.toISOString().slice(0, 10),
        test_end: defaults.data.end_date,
      });
    }
  }, [defaults.data]);
  const change = (key: string, value: any) =>
    setDraft({ ...draft, [key]: value });
  const result = job.result,
    current = submitted === JSON.stringify(draft);
  const prepare = () =>
    action.run(
      () => post("/factors/combinations/prepare", { task_id: job.id }),
      (value) => {
        sessionStorage.setItem(
          "alphaquant:prepared-request",
          JSON.stringify(value.request),
        );
        navigate("/app/backtests/new");
      },
    );
  return (
    <>
      <Card title="组合与训练 / 测试隔离">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (await job.submit("factor_combination", draft))
              setSubmitted(JSON.stringify(draft));
          }}
        >
          <Field label="选择至少两个因子（可多选）">
            <select
              multiple
              size={8}
              value={draft.factor_names}
              onChange={(e) =>
                change(
                  "factor_names",
                  Array.from(
                    e.target.selectedOptions,
                    (option) => option.value,
                  ),
                )
              }
            >
              {factors.data?.items.map((f: Obj) => (
                <option key={f.name} value={f.name}>
                  {f.display_name} · {f.name}
                </option>
              ))}
            </select>
          </Field>
          <div className="form-grid">
            <Field label="权重方式">
              <select
                value={draft.mode}
                onChange={(e) => change("mode", e.target.value)}
              >
                <option value="equal">等权</option>
                <option value="manual">手动权重</option>
                <option value="ic">仅训练期 IC 权重</option>
              </select>
            </Field>
            <Field label="缺失值处理">
              <select
                value={draft.missing}
                onChange={(e) => change("missing", e.target.value)}
              >
                <option value="drop">剔除缺失</option>
                <option value="median">中位数填充</option>
              </select>
            </Field>
            <DateFields
              draft={draft}
              change={change}
              keys={["train_start", "train_end", "test_start", "test_end"]}
            />
            <HorizonFields draft={draft} change={change} />
            {draft.mode === "manual" &&
              draft.factor_names.map((name) => (
                <Field key={name} label={name + " 权重"}>
                  <input
                    type="number"
                    min={0}
                    step="any"
                    value={draft.custom_weights[name] || 0}
                    onChange={(e) =>
                      change("custom_weights", {
                        ...draft.custom_weights,
                        [name]: Number(e.target.value),
                      })
                    }
                  />
                </Field>
              ))}
          </div>
          <CheckBox
            label="使用 MAD 缩尾清洗"
            checked={draft.clip}
            onChange={(value) => change("clip", value)}
          />
          <button
            className="primary"
            disabled={job.active || draft.factor_names.length < 2}
          >
            训练权重并在测试期验证
          </button>
        </form>
        <ErrorBox error={factors.error || defaults.error || action.error} />
      </Card>
      <JobPanel job={job} showResult={false} />
      {result && (
        <Card title="组合研究报告">
          {!current && (
            <Note>
              配置已修改，旧报告不能作为当前组合带入回测，请重新验证。
            </Note>
          )}
          <Report value={result} />
          {result.correlation?.rows.some((row: Obj, i: number) =>
            Object.values(row).some(
              (value, j) =>
                j !== i && typeof value === "number" && Math.abs(value) >= 0.7,
            ),
          ) && <Note>成分相关性较高，请留意重复暴露。</Note>}
          <div className="actions">
            <button onClick={() => download(result, "factor_research.json")}>
              下载完整研究 JSON
            </button>
            <button
              className="primary"
              disabled={
                !current || action.busy || job.task?.status !== "SUCCESS"
              }
              onClick={prepare}
            >
              使用验证过的组合回测 <ArrowRight size={15} />
            </button>
          </div>
        </Card>
      )}
    </>
  );
}
function CustomFactors() {
  const editor = useResource("/factors/editor"),
    action = useAction();
  const [draft, setDraft] = useSticky("custom-factor", {
    name: "",
    display_name: "",
    field: "adjusted_close",
    operator: "momentum",
    window: 20,
    window2: 60,
    direction: 1,
    description: "",
  });
  const change = (key: string, value: any) =>
    setDraft({ ...draft, [key]: value });
  return (
    <>
      <Card title="定义一个自定义因子">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(
              () =>
                post("/factors/custom", {
                  ...draft,
                  window2: editor.data?.operators[draft.operator]?.window2
                    ? draft.window2
                    : null,
                }),
              () => {
                editor.refresh();
                action.setMessage("因子已保存，可用于评价与组合。");
              },
            );
          }}
        >
          <div className="form-grid">
            <Field label="英文标识">
              <input
                required
                pattern="[a-zA-Z][a-zA-Z0-9_]*"
                value={draft.name}
                onChange={(e) => change("name", e.target.value)}
              />
            </Field>
            <Field label="中文名称">
              <input
                value={draft.display_name}
                onChange={(e) => change("display_name", e.target.value)}
              />
            </Field>
            <Field label="行情字段">
              <select
                value={draft.field}
                onChange={(e) => change("field", e.target.value)}
              >
                {Object.entries(editor.data?.fields || {}).map(
                  ([key, label]) => (
                    <option key={key} value={key}>
                      {String(label)}
                    </option>
                  ),
                )}
              </select>
            </Field>
            <Field label="算子">
              <select
                value={draft.operator}
                onChange={(e) => change("operator", e.target.value)}
              >
                {Object.entries(editor.data?.operators || {}).map(
                  ([key, value]) => (
                    <option key={key} value={key}>
                      {(value as Obj).label}
                    </option>
                  ),
                )}
              </select>
            </Field>
            <Field label="窗口 N">
              <input
                type="number"
                required
                min={1}
                max={500}
                value={draft.window}
                onChange={(e) => change("window", Number(e.target.value))}
              />
            </Field>
            {editor.data?.operators[draft.operator]?.window2 && (
              <Field label="窗口 N2">
                <input
                  type="number"
                  required
                  min={1}
                  max={500}
                  value={draft.window2}
                  onChange={(e) => change("window2", Number(e.target.value))}
                />
              </Field>
            )}
            <Field label="方向">
              <select
                value={draft.direction}
                onChange={(e) => change("direction", Number(e.target.value))}
              >
                <option value={1}>值越大越好</option>
                <option value={-1}>值越小越好</option>
              </select>
            </Field>
            <Field label="说明">
              <input
                value={draft.description}
                onChange={(e) => change("description", e.target.value)}
              />
            </Field>
          </div>
          <button className="primary" disabled={action.busy}>
            保存因子
          </button>
        </form>
        <ErrorBox error={editor.error || action.error} />
        {action.message && <Note tone="success">{action.message}</Note>}
      </Card>
      <Card title="已保存的自定义因子">
        {editor.data?.items.length ? (
          editor.data.items.map((factor: Obj) => (
            <div className="item-row" key={factor.name}>
              <div>
                <strong>{factor.display_name || factor.name}</strong>
                <small>
                  {factor.name} · {factor.operator} · N={factor.window}
                </small>
              </div>
              <Link to={"/app/factors/evaluation?factor=" + factor.name}>
                评估
              </Link>
              <button
                className="danger"
                onClick={() =>
                  action.run(
                    () => remove(`/factors/custom/${factor.name}`),
                    editor.refresh,
                  )
                }
              >
                删除该因子
              </button>
            </div>
          ))
        ) : (
          <Empty>还没有自定义因子。</Empty>
        )}
      </Card>
    </>
  );
}
