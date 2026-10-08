import { useEffect, useState } from "react";
import { ArrowRight, Plus, Save, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import {
  api,
  type BacktestRequest,
  type Obj,
  post,
  remove,
  useAction,
  useJob,
  useResource,
  useSticky,
} from "../api";
import {
  Card,
  CheckBox,
  ErrorBox,
  Field,
  JobPanel,
  JsonEditor,
  Loading,
  Note,
  PageHead,
  Report,
  Tabs,
} from "../components";
import { RunForm } from "./Backtests";

export function Ideas() {
  const [draft, setDraft] = useSticky("idea", {
    idea: "趋势上涨",
    start_date: "",
    end_date: "",
    initial_cash: 1000000,
    top_n: 5,
    rebalance: "weekly",
  });
  const defaults = useResource<BacktestRequest>("/backtests/defaults"),
    ideas = useResource<Obj[]>("/research/ideas"),
    action = useAction();
  const [prepared, setPrepared] = useSticky<BacktestRequest | null>(
    "idea-prepared",
    null,
  );
  const [restored, setRestored] = useSticky<Obj | null>("idea-restored", null);
  useEffect(() => {
    const text = sessionStorage.getItem("alphaquant:guided-plan");
    if (text) {
      const result = JSON.parse(text);
      const { scope, ...inputs } = result.inputs;
      setDraft(inputs);
      setPrepared(result.request);
      setRestored(result.request);
      sessionStorage.removeItem("alphaquant:guided-plan");
    }
  }, []);
  useEffect(() => {
    if (!draft.start_date && defaults.data)
      setDraft((previous) =>
        previous.start_date
          ? previous
          : {
              ...previous,
              start_date: defaults.data!.start_date,
              end_date: defaults.data!.end_date,
            },
      );
  }, [defaults.data]);
  const change = (key: string, value: any) => {
    setDraft({ ...draft, [key]: value });
    setPrepared(null);
  };
  return (
    <>
      <PageHead
        title="从一个选股想法开始"
        description="选择想法，看看它将如何变成可以验证的规则。"
      />
      <Card title="想法与研究范围">
        <div className="choice-cards">
          {ideas.data?.map((idea: Obj) => (
            <button
              key={idea.name}
              className={draft.idea === idea.name ? "chosen" : ""}
              onClick={() => change("idea", idea.name)}
            >
              <strong>{idea.name}</strong>
              <small>{idea.description}</small>
            </button>
          ))}
        </div>
        <div className="form-grid">
          <Field label="开始日期">
            <input
              type="date"
              value={draft.start_date}
              onChange={(e) => change("start_date", e.target.value)}
            />
          </Field>
          <Field label="结束日期">
            <input
              type="date"
              value={draft.end_date}
              onChange={(e) => change("end_date", e.target.value)}
            />
          </Field>
          <Field label="初始资金（元）">
            <input
              type="number"
              min={1000}
              value={draft.initial_cash}
              onChange={(e) => change("initial_cash", Number(e.target.value))}
            />
          </Field>
          <Field label="持股数">
            <input
              type="number"
              min={1}
              max={100}
              value={draft.top_n}
              onChange={(e) => change("top_n", Number(e.target.value))}
            />
          </Field>
          <Frequency
            value={draft.rebalance}
            onChange={(value) => change("rebalance", value)}
          />
        </div>
        <button
          className="primary"
          disabled={action.busy}
          onClick={() =>
            action.run(
              () =>
                post<BacktestRequest>("/research/ideas/prepare", {
                  ...draft,
                  plan_id: restored?.plan_id,
                  plan_revision: restored?.plan_revision,
                }),
              setPrepared,
            )
          }
        >
          生成待检查的研究规则 <ArrowRight size={15} />
        </button>
        <ErrorBox error={ideas.error || defaults.error || action.error} />
      </Card>
      {prepared && (
        <RunForm
          key={JSON.stringify(prepared)}
          initial={prepared}
          scope="ideas"
          title="确认规则并验证数据"
          planInputs={{ scope: "guided", ...draft }}
        />
      )}
    </>
  );
}
export function Frequency({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Field label="调仓频率">
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="daily">每日</option>
        <option value="weekly">每周</option>
        <option value="monthly">每月</option>
      </select>
    </Field>
  );
}
function Indicator({
  value,
  onChange,
  indicators,
  title,
}: {
  value: Obj;
  onChange: (v: Obj) => void;
  indicators: Obj;
  title: string;
}) {
  return (
    <div className="indicator">
      <Field label={title}>
        <select
          value={value.name}
          onChange={(e) =>
            onChange(
              e.target.value === "close"
                ? { name: "close" }
                : { name: e.target.value, window: 20 },
            )
          }
        >
          {Object.entries(indicators).map(([key, label]) => (
            <option key={key} value={key}>
              {String(label)}
            </option>
          ))}
        </select>
      </Field>
      {value.name !== "close" && (
        <Field label="周期">
          <input
            type="number"
            min={
              value.name === "return" || value.name === "average_amount" ? 1 : 2
            }
            max={value.name === "rsi" ? 120 : 500}
            value={value.window ?? 20}
            onChange={(e) =>
              onChange({ ...value, window: Number(e.target.value) })
            }
          />
        </Field>
      )}
    </div>
  );
}
export function VisualStrategy() {
  const templates = useResource("/strategies/templates"),
    editor = useResource("/factors/editor"),
    packages = useResource("/strategies/packages");
  const [mode, setMode] = useState("templates"),
    [template, setTemplate] = useSticky("template-id", "momentum"),
    [style, setStyle] = useSticky("template-style", "balanced");
  const templateResource = useResource(
    mode === "templates" ? `/strategies/templates/${template}/${style}` : null,
  );
  const [draft, setDraft] = useSticky<Obj | null>("visual-strategy", null),
    [revision, setRevision] = useState<string | null>(null),
    [savedId, setSavedId] = useState("");
  const [validSignature, setValidSignature] = useState(""),
    [validation, setValidation] = useState<Obj>(),
    [request, setRequest] = useState<BacktestRequest>();
  const action = useAction();
  useEffect(() => {
    if (templateResource.data) {
      setDraft(templateResource.data);
      setValidSignature("");
      setRequest(undefined);
      setRevision(null);
    }
  }, [templateResource.data]);
  const signature = JSON.stringify(draft);
  const change = (value: Obj) => {
    setDraft(value);
    setRequest(undefined);
    setValidation(undefined);
    setValidSignature("");
  };
  const payload = () => ({
    definition: draft!.definition,
    top_n: Number(draft!.top_n),
    rebalance: draft!.rebalance,
    revision_of: revision,
  });
  const load = () =>
    action.run(
      () => api(`/strategies/packages/${savedId}`),
      (value) => {
        change(value);
        setRevision(value.package_id);
        setMode("custom");
      },
    );
  const validate = () =>
    action.run(
      () => post("/strategies/packages/validate", payload()),
      (value) => {
        setValidation(value);
        setValidSignature(signature);
      },
    );
  const prepare = () =>
    action.run(
      async () => {
        const value = {
          ...draft,
          package_version: 1,
          package_id: draft!.package_id || "draft",
          name: draft!.definition.name,
          source: "visual_builder",
          created_at: draft!.created_at || new Date().toISOString(),
        };
        return post("/strategies/packages/prepare", { package: value });
      },
      (value) => {
        setRequest(value.request);
        if (value.warnings.length) action.setMessage(value.warnings.join("；"));
      },
    );
  return (
    <>
      <PageHead
        title="可视化策略工作室"
        description="从模板开始，或用条件积木建立自己的选股规则。"
      />
      <Tabs
        items={[
          ["templates", "策略模板"],
          ["custom", "条件积木"],
          ["saved", "我的策略与版本"],
        ]}
        value={mode}
        onChange={setMode}
      />
      <ErrorBox
        error={
          templates.error || editor.error || packages.error || action.error
        }
      />
      {mode === "templates" && (
        <Card title="选择模板与风格">
          <div className="form-grid">
            <Field label="策略模板">
              <select
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
              >
                {templates.data?.items.map((t: Obj) => (
                  <option key={t.template_id} value={t.template_id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="研究风格">
              <select value={style} onChange={(e) => setStyle(e.target.value)}>
                {Object.entries(templates.data?.styles || {}).map(
                  ([key, label]) => (
                    <option key={key} value={key}>
                      {String(label)}
                    </option>
                  ),
                )}
              </select>
            </Field>
          </div>
          <p className="muted">
            {
              templates.data?.items.find((t: Obj) => t.template_id === template)
                ?.summary
            }
          </p>
          <ErrorBox error={templateResource.error} />
        </Card>
      )}
      {mode === "saved" && (
        <Card title="已保存策略">
          <Field label="选择策略版本">
            <select
              value={savedId}
              onChange={(e) => setSavedId(e.target.value)}
            >
              <option value="">选择已保存的策略</option>
              {packages.data?.items.map((p: Obj) => (
                <option key={p.package_id} value={p.package_id}>
                  {p.name} · {p.package_id}
                </option>
              ))}
            </select>
          </Field>
          <div className="actions">
            <button disabled={!savedId || action.busy} onClick={load}>
              载入积木编辑
            </button>
            <button
              disabled={!savedId || action.busy}
              onClick={() =>
                action.run(
                  () => post(`/strategies/packages/${savedId}/copy`, {}),
                  (value) => {
                    setDraft(value);
                    packages.refresh();
                    setMode("custom");
                    setRevision(null);
                    setValidSignature("");
                  },
                )
              }
            >
              复制为新策略
            </button>
            <button
              disabled={!savedId || action.busy}
              onClick={() =>
                action.run(
                  async () => {
                    const value = await api(`/strategies/packages/${savedId}`);
                    return post("/strategies/packages/prepare", {
                      package: value,
                    });
                  },
                  (value) => setRequest(value.request),
                )
              }
            >
              准备已保存策略回测
            </button>
          </div>
        </Card>
      )}
      {draft && editor.data && mode !== "saved" && (
        <Card title="规则编辑器">
          <div className="form-grid">
            <Field label="策略名称">
              <input
                value={draft.definition.name}
                onChange={(e) =>
                  change({
                    ...draft,
                    definition: { ...draft.definition, name: e.target.value },
                  })
                }
              />
            </Field>
            <Field label="英文标识">
              <input
                value={draft.definition.strategy_id}
                onChange={(e) =>
                  change({
                    ...draft,
                    definition: {
                      ...draft.definition,
                      strategy_id: e.target.value,
                    },
                  })
                }
              />
            </Field>
            <Field label="条件关系">
              <select
                value={draft.definition.entry_logic}
                onChange={(e) =>
                  change({
                    ...draft,
                    definition: {
                      ...draft.definition,
                      entry_logic: e.target.value,
                    },
                  })
                }
              >
                <option value="all">全部满足（AND）</option>
                <option value="any">任一满足（OR）</option>
              </select>
            </Field>
          </div>
          {draft.definition.entry_rules.map((rule: Obj, index: number) => {
            const update = (value: Obj) =>
              change({
                ...draft,
                definition: {
                  ...draft.definition,
                  entry_rules: draft.definition.entry_rules.map(
                    (r: Obj, i: number) => (i === index ? value : r),
                  ),
                },
              });
            return (
              <div className="rule-row" key={index}>
                <span className="rule-number">{index + 1}</span>
                <Indicator
                  title="左侧指标"
                  value={rule.left}
                  onChange={(left) => update({ ...rule, left })}
                  indicators={editor.data!.indicators}
                />
                <Field label="比较关系">
                  <select
                    value={rule.operator}
                    onChange={(e) =>
                      update({ ...rule, operator: e.target.value })
                    }
                  >
                    {Object.entries(editor.data!.comparisons).map(
                      ([key, label]) => (
                        <option key={key} value={key}>
                          {String(label)}
                        </option>
                      ),
                    )}
                  </select>
                </Field>
                <Field label="比较对象">
                  <select
                    value={rule.right ? "indicator" : "value"}
                    onChange={(e) =>
                      update(
                        e.target.value === "indicator"
                          ? {
                              ...rule,
                              right: { name: "moving_average", window: 60 },
                              value: null,
                            }
                          : { ...rule, right: null, value: 0 },
                      )
                    }
                  >
                    <option value="value">固定数值</option>
                    <option value="indicator">另一指标</option>
                  </select>
                </Field>
                {rule.right ? (
                  <Indicator
                    title="右侧指标"
                    value={rule.right}
                    onChange={(right) => update({ ...rule, right })}
                    indicators={editor.data!.indicators}
                  />
                ) : (
                  <Field label="阈值（比例使用小数）">
                    <input
                      type="number"
                      step="any"
                      value={rule.value ?? 0}
                      onChange={(e) =>
                        update({ ...rule, value: Number(e.target.value) })
                      }
                    />
                  </Field>
                )}
                <button
                  aria-label={`删除条件 ${index + 1}`}
                  disabled={draft.definition.entry_rules.length <= 1}
                  onClick={() =>
                    change({
                      ...draft,
                      definition: {
                        ...draft.definition,
                        entry_rules: draft.definition.entry_rules.filter(
                          (_: Obj, i: number) => i !== index,
                        ),
                      },
                    })
                  }
                >
                  <Trash2 size={15} />
                </button>
              </div>
            );
          })}
          <button
            disabled={draft.definition.entry_rules.length >= 6}
            onClick={() =>
              change({
                ...draft,
                definition: {
                  ...draft.definition,
                  entry_rules: [
                    ...draft.definition.entry_rules,
                    {
                      left: { name: "return", window: 20 },
                      operator: "greater_than",
                      value: 0,
                      right: null,
                    },
                  ],
                },
              })
            }
          >
            <Plus size={15} />
            添加条件
          </button>
          <div className="form-grid ranking">
            <Indicator
              title="排序指标"
              value={draft.definition.ranking.indicator}
              indicators={editor.data.indicators}
              onChange={(indicator) =>
                change({
                  ...draft,
                  definition: {
                    ...draft.definition,
                    ranking: { ...draft.definition.ranking, indicator },
                  },
                })
              }
            />
            <Field label="排序方向">
              <select
                value={draft.definition.ranking.direction}
                onChange={(e) =>
                  change({
                    ...draft,
                    definition: {
                      ...draft.definition,
                      ranking: {
                        ...draft.definition.ranking,
                        direction: e.target.value,
                      },
                    },
                  })
                }
              >
                <option value="descending">从高到低</option>
                <option value="ascending">从低到高</option>
              </select>
            </Field>
            <Field label="持股数">
              <input
                type="number"
                min={1}
                max={50}
                value={draft.top_n}
                onChange={(e) =>
                  change({ ...draft, top_n: Number(e.target.value) })
                }
              />
            </Field>
            <Frequency
              value={draft.rebalance}
              onChange={(rebalance) => change({ ...draft, rebalance })}
            />
          </div>
          <div className="actions">
            <button
              className="primary"
              onClick={validate}
              disabled={action.busy}
            >
              生成并检查策略
            </button>
            <button
              disabled={validSignature !== signature || action.busy}
              onClick={() =>
                action.run(
                  () => post("/strategies/packages", payload()),
                  (value) => {
                    action.setMessage("策略已保存：" + value.package_id);
                    packages.refresh();
                    setRevision(value.package_id);
                  },
                )
              }
            >
              <Save size={15} />
              {revision ? "保存为新版本" : "另存为我的策略"}
            </button>
            <button
              disabled={validSignature !== signature || action.busy}
              onClick={prepare}
            >
              准备回测
            </button>
          </div>
          {validation && (
            <details open>
              <summary>通过校验的规则</summary>
              <Report value={validation} />
            </details>
          )}
          {action.message && <Note>{action.message}</Note>}
        </Card>
      )}
      {request && (
        <RunForm
          initial={request}
          scope="visual"
          title="可视化策略回测范围与参数"
        />
      )}
    </>
  );
}
export function NaturalLanguage() {
  const [description, setDescription] = useSticky("nl-description", ""),
    [confirmed, setConfirmed] = useState(false),
    [saved, setSaved] = useState(""),
    [topN, setTopN] = useState(5),
    [rebalance, setRebalance] = useState("weekly");
  const settings = useResource("/settings"),
    job = useJob("nl"),
    action = useAction();
  const [submitted, setSubmitted] = useSticky("nl-submitted-description", "");
  const current = submitted === description;
  return (
    <>
      <PageHead
        title="用自然语言创建策略"
        description="描述想法，核对生成的结构化规则，确认后再保存。"
        actions={
          <Link className="button" to="/app/settings">
            模型设置
          </Link>
        }
      />
      <Card title="描述你的规则">
        <p className="muted">
          当前默认模型：{settings.data?.default_provider || "—"}
        </p>
        <Field label="策略描述">
          <textarea
            rows={5}
            value={description}
            placeholder="例如：5日均线高于20日均线且近5日平均成交额大于2000万，按20日涨幅排序。"
            onChange={(e) => {
              setDescription(e.target.value);
              setConfirmed(false);
              setSaved("");
            }}
          />
        </Field>
        <button
          className="text-button"
          onClick={() => {
            setDescription("5日均线高于20日均线，按20日涨幅从高到低排序");
            setConfirmed(false);
            setSaved("");
          }}
        >
          填入示例
        </button>
        <div className="form-grid">
          <Field label="持股数">
            <input
              type="number"
              min={1}
              max={50}
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
            />
          </Field>
          <Frequency value={rebalance} onChange={setRebalance} />
        </div>
        <button
          className="primary"
          disabled={job.active || !description.trim()}
          onClick={async () => {
            setConfirmed(false);
            setSaved("");
            const next = await job.submit("nl_strategy", { description });
            if (next) {
              setSubmitted(description);
              setConfirmed(false);
            }
          }}
        >
          生成策略草稿
        </button>
        <ErrorBox error={settings.error || action.error} />
      </Card>
      <JobPanel job={job} showResult={false} />
      {job.result?.definition && (
        <Card title="人工核对规则">
          {!current && (
            <Note>描述已修改，下面是上一次生成的草稿。请重新生成后保存。</Note>
          )}
          <p>{job.result.explanation}</p>
          <Report value={job.result.definition} />
          <CheckBox
            label="我已核对规则与原始描述一致"
            checked={confirmed}
            onChange={setConfirmed}
          />
          <div className="actions">
            <button
              className="primary"
              disabled={!confirmed || !current || action.busy}
              onClick={() =>
                action.run(
                  () =>
                    post("/strategies/packages", {
                      definition: job.result!.definition,
                      top_n: topN,
                      rebalance,
                    }),
                  (value) => setSaved(value.package_id),
                )
              }
            >
              确认并保存
            </button>
            <button
              onClick={() => {
                job.setId(null);
                setConfirmed(false);
                setSaved("");
              }}
            >
              放弃并重新描述
            </button>
            {saved && (
              <Link className="button" to="/app/strategies/visual">
                已保存 · 去策略工作室回测 <ArrowRight size={14} />
              </Link>
            )}
          </div>
        </Card>
      )}
    </>
  );
}
export function PythonStrategies() {
  const resource = useResource("/strategies/python"),
    action = useAction();
  const [draft, setDraft] = useSticky("python-editor", {
    code: "",
    display_name: "",
    description: "",
    source: "editor",
  });
  const [acknowledged, setAcknowledged] = useState(false),
    [report, setReport] = useState<Obj>(),
    [selected, setSelected] = useState(""),
    [request, setRequest] = useState<BacktestRequest>();
  const defaults = useResource<BacktestRequest>("/backtests/defaults");
  useEffect(() => {
    if (resource.data?.starter)
      setDraft((previous) =>
        previous.code
          ? previous
          : { ...previous, code: resource.data!.starter },
      );
  }, [resource.data]);
  const changeCode = (code: string, source = "editor") => {
    setDraft({ ...draft, code, source });
    setAcknowledged(false);
    setReport(undefined);
  };
  return (
    <>
      <PageHead
        title="Python 策略"
        description="编写或上传 .py 文件，检查后注册到同一策略目录。"
      />
      <Card title="策略编辑器">
        <div className="form-grid">
          <Field label="显示名称">
            <input
              value={draft.display_name}
              onChange={(e) =>
                setDraft({ ...draft, display_name: e.target.value })
              }
            />
          </Field>
          <Field label="说明">
            <input
              value={draft.description}
              onChange={(e) =>
                setDraft({ ...draft, description: e.target.value })
              }
            />
          </Field>
        </div>
        <Field label="上传 .py 文件（UTF-8）">
          <input
            type="file"
            accept=".py"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file)
                void action.run(async () => {
                  if (file.size > 300000) throw new Error("策略文件过大");
                  changeCode(
                    new TextDecoder("utf-8", { fatal: true }).decode(
                      await file.arrayBuffer(),
                    ),
                    "upload",
                  );
                });
            }}
          />
        </Field>
        <JsonEditor
          label="策略代码"
          value={draft.code}
          onChange={changeCode}
          rows={20}
        />
        <div className="actions">
          <button
            onClick={() =>
              action.run(
                () => post("/strategies/python/check", draft),
                setReport,
              )
            }
            disabled={action.busy}
          >
            检查代码风险
          </button>
          <button
            className="primary"
            onClick={() =>
              action.run(
                () =>
                  post("/strategies/python", {
                    ...draft,
                    risk_acknowledged: acknowledged,
                  }),
                (value) => {
                  action.setMessage("已注册：" + value.plugin_name);
                  resource.refresh();
                  setSelected(value.plugin_name);
                },
              )
            }
            disabled={action.busy}
          >
            检查并注册策略
          </button>
        </div>
        <CheckBox
          label="我已阅读检查结果，并了解提示的风险"
          checked={acknowledged}
          onChange={setAcknowledged}
        />
        <ErrorBox error={resource.error || action.error} />
        {report && <Report value={report} />}
        {action.message && <Note tone="success">{action.message}</Note>}
      </Card>
      <Card title="已保存的自定义策略">
        <Field label="选择策略">
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">选择已保存策略</option>
            {resource.data?.items.map((item: Obj) => (
              <option key={item.plugin_name} value={item.plugin_name}>
                {item.display_name}
              </option>
            ))}
          </select>
        </Field>
        <div className="actions">
          <button
            disabled={!selected}
            onClick={() => {
              const item = resource.data!.items.find(
                (v: Obj) => v.plugin_name === selected,
              );
              setDraft({
                code: item.code,
                description: item.description,
                display_name: item.display_name,
                source: "editor",
              });
              setAcknowledged(false);
              setReport(undefined);
            }}
          >
            载入源码
          </button>
          <button
            disabled={!selected || !defaults.data}
            onClick={() =>
              action.run(async () => {
                const strategies = await api("/strategies");
                const metadata = strategies.items.find(
                  (s: Obj) => s.plugin_name === selected,
                );
                if (!metadata) throw new Error("策略加载失败，请查看加载问题");
                setRequest({
                  ...defaults.data!,
                  strategy_plugin: selected,
                  strategy_id: selected,
                  strategy_parameters: Object.fromEntries(
                    metadata.parameters.map((p: Obj) => [p.name, p.default]),
                  ),
                });
              })
            }
          >
            准备该策略回测
          </button>
          <button
            className="danger"
            disabled={!selected || action.busy}
            onClick={() =>
              action.run(
                () => remove(`/strategies/python/${selected}`),
                () => {
                  resource.refresh();
                  setSelected("");
                  setRequest(undefined);
                },
              )
            }
          >
            删除所选策略
          </button>
        </div>
        {resource.data?.load_errors.length > 0 && (
          <details open>
            <summary>策略加载问题</summary>
            <Report value={resource.data?.load_errors} />
          </details>
        )}
      </Card>
      {request && <RunForm initial={request} scope="python" />}
    </>
  );
}
