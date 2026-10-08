import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Obj, post, useAction, useResource } from "../api";
import {
  Card,
  CheckBox,
  ErrorBox,
  Field,
  Loading,
  MetricGrid,
  Note,
  PageHead,
  RemoteTable,
  Report,
  Tabs,
} from "../components";

export function Settings() {
  const resource = useResource("/settings"),
    [tab, setTab] = useState("model"),
    system = useResource(tab === "system" ? "/settings/system" : null);
  const action = useAction(),
    [provider, setProvider] = useState(""),
    [model, setModel] = useState(""),
    [baseUrl, setBaseUrl] = useState(""),
    [key, setKey] = useState(""),
    [clearKey, setClearKey] = useState(false);
  const [dataSource, setDataSource] = useState("xtick"),
    [credentials, setCredentials] = useState<Obj>({}),
    [proxy, setProxy] = useState<Obj>();
  useEffect(() => {
    if (resource.data) {
      if (!provider) setProvider(resource.data.default_provider);
      setProxy(resource.data.proxy);
    }
  }, [resource.data]);
  const spec = resource.data?.providers.find((p: Obj) => p.key === provider);
  useEffect(() => {
    if (spec) {
      setModel(spec.model || "");
      setBaseUrl(spec.base_url || "");
      setKey("");
      setClearKey(false);
    }
  }, [provider, resource.data]);
  useEffect(() => {
    setCredentials({
      base_url: resource.data?.data_sources[dataSource]?.base_url || "",
    });
  }, [dataSource, resource.data]);
  const saveModel = (setDefault: boolean) =>
    action.run(
      () =>
        post("/settings/models/" + provider, {
          model,
          base_url: baseUrl,
          api_key: clearKey ? "" : key || null,
          set_default: setDefault,
        }),
      () => {
        setKey("");
        setClearKey(false);
        resource.refresh();
        action.setMessage(
          setDefault ? "配置已保存，并设为全局默认模型" : "模型配置已保存",
        );
      },
    );
  return (
    <>
      <PageHead
        title="研究设置"
        description="配置保存在本机。密钥只在提交保存时发送给本机后端。"
        actions={
          <>
            <Link className="button" to="/app/account">
              个人中心
            </Link>
            <Link className="button" to="/">
              使用指南
            </Link>
          </>
        }
      />
      <Tabs
        items={[
          ["model", "AI 模型"],
          ["data", "数据凭证"],
          ["proxy", "代理设置"],
          ["system", "系统与存储"],
        ]}
        value={tab}
        onChange={setTab}
      />
      <ErrorBox error={resource.error || action.error || system.error} />
      {action.message && <Note tone="success">{action.message}</Note>}
      {resource.loading ? (
        <Loading />
      ) : (
        <>
          {tab === "model" && (
            <Card title="AI 模型配置">
              <p className="muted">
                当前默认：{resource.data?.default_provider}
              </p>
              <div className="form-grid">
                <Field label="提供方">
                  <select
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                  >
                    {resource.data?.providers.map((p: Obj) => (
                      <option key={p.key} value={p.key}>
                        {p.display_name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="模型名称">
                  <input
                    list="models"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                  />
                  <datalist id="models">
                    {spec?.models?.map((m: string) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                </Field>
                <Field label="Base URL">
                  <input
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder={spec?.default_base_url}
                  />
                </Field>
                <Field
                  label="新的 API Key"
                  hint={
                    spec?.requires_key
                      ? spec.key_configured
                        ? "已有有效凭证；留空沿用。"
                        : "尚未配置凭证。"
                      : "该提供方无需凭证。"
                  }
                >
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                    disabled={!spec?.requires_key}
                  />
                </Field>
              </div>
              {spec?.requires_key && (
                <CheckBox
                  label="清除本地已保存 Key，改用环境变量回退"
                  checked={clearKey}
                  onChange={setClearKey}
                />
              )}
              <div className="actions">
                <button disabled={action.busy} onClick={() => saveModel(false)}>
                  仅保存配置
                </button>
                <button
                  className="primary"
                  disabled={action.busy}
                  onClick={() => saveModel(true)}
                >
                  保存并设为默认
                </button>
              </div>
            </Card>
          )}
          {tab === "data" && (
            <Card title="可选数据来源凭证">
              <Field label="数据来源">
                <select
                  value={dataSource}
                  onChange={(e) => setDataSource(e.target.value)}
                >
                  <option value="xtick">XTick</option>
                  <option value="ifind">iFinD</option>
                  <option value="tushare">Tushare</option>
                </select>
              </Field>
              <div className="form-grid">
                {(dataSource === "ifind"
                  ? ["username", "password"]
                  : ["token"]
                ).map((field) => (
                  <Field
                    key={field}
                    label={
                      field === "username"
                        ? "账号"
                        : field === "password"
                          ? "密码"
                          : "Token"
                    }
                    hint={
                      resource.data?.data_sources[dataSource]?.configured[field]
                        ? "已配置；留空沿用。"
                        : "尚未配置；支持已有环境变量。"
                    }
                  >
                    <input
                      type={field === "username" ? "text" : "password"}
                      autoComplete="new-password"
                      value={credentials[field] || ""}
                      onChange={(e) =>
                        setCredentials({
                          ...credentials,
                          [field]: e.target.value,
                        })
                      }
                    />
                  </Field>
                ))}
                {dataSource === "xtick" && (
                  <Field label="接口 Base URL">
                    <input
                      value={credentials.base_url || ""}
                      placeholder="http://api.xtick.top"
                      onChange={(e) =>
                        setCredentials({
                          ...credentials,
                          base_url: e.target.value,
                        })
                      }
                    />
                  </Field>
                )}
              </div>
              <button
                className="primary"
                disabled={action.busy}
                onClick={() =>
                  action.run(
                    () =>
                      post(
                        "/settings/data/" + dataSource,
                        Object.fromEntries(
                          Object.entries(credentials).filter(
                            ([, value]) => value !== "",
                          ),
                        ),
                      ),
                    () => {
                      setCredentials({});
                      resource.refresh();
                      action.setMessage("数据来源配置已保存");
                    },
                  )
                }
              >
                保存凭证
              </button>
              <Note>
                BaoStock 与 AkShare 无需在此填写凭证。iFinD 还需要在本机安装官方
                SDK。
              </Note>
            </Card>
          )}
          {tab === "proxy" && proxy && (
            <Card title="行情与新闻代理">
              <CheckBox
                label="对适用来源启用代理"
                checked={proxy.enabled}
                onChange={(enabled) => setProxy({ ...proxy, enabled })}
              />
              <Field label="代理地址">
                <input
                  value={proxy.address}
                  onChange={(e) =>
                    setProxy({ ...proxy, address: e.target.value })
                  }
                />
              </Field>
              <button
                className="primary"
                disabled={action.busy}
                onClick={() =>
                  action.run(
                    () => post("/settings/proxy", proxy),
                    () => {
                      resource.refresh();
                      action.setMessage("代理配置已保存");
                    },
                  )
                }
              >
                保存代理设置
              </button>
            </Card>
          )}
          {tab === "system" && (
            <Card title="系统与存储诊断">
              {system.loading ? <Loading /> : <Report value={system.data} />}
            </Card>
          )}
        </>
      )}
    </>
  );
}
export function Risk() {
  const resource = useResource("/risk"),
    action = useAction(),
    [draft, setDraft] = useState<Obj>(),
    runs = useResource("/runs?limit=500"),
    [runId, setRunId] = useState("");
  const recent = useResource("/risk/events?limit=1");
  useEffect(() => {
    if (resource.data) setDraft(resource.data);
  }, [resource.data]);
  const names: Obj = {
    max_total_weight: "最大总仓位",
    max_single_weight: "单股权重上限",
    max_positions: "最大持股数",
    minimum_cash_ratio: "最低现金比例",
    max_drawdown: "回撤阈值",
    drawdown_target_weight: "降仓目标权重",
    max_industry_weight: "行业权重上限",
    max_daily_loss: "单日亏损上限",
    max_rebalance_turnover: "调仓换手上限",
  };
  return (
    <>
      <PageHead
        title="风险规则与记录"
        description="设置新的回测默认限制；历史结果始终读取各自的执行快照。"
      />
      <ErrorBox error={resource.error || action.error} />
      {draft && (
        <Card title="默认风险约束">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(
                () => post("/risk", draft),
                () => {
                  resource.refresh();
                  action.setMessage("默认风险规则已保存");
                },
              );
            }}
          >
            <CheckBox
              label="启用风险检查"
              checked={draft.enabled}
              onChange={(enabled) => setDraft({ ...draft, enabled })}
            />
            <CheckBox
              label="每日检查持仓漂移"
              checked={draft.daily_position_limits}
              onChange={(daily_position_limits) =>
                setDraft({ ...draft, daily_position_limits })
              }
            />
            <div className="form-grid">
              {Object.entries(names).map(([key, label]) => (
                <Field
                  key={key}
                  label={String(label)}
                  hint={
                    key === "max_positions"
                      ? "整数"
                      : "使用小数，例如 0.2 表示 20%"
                  }
                >
                  <input
                    type="number"
                    required
                    min={key === "max_positions" ? 1 : 0}
                    max={
                      key === "max_positions"
                        ? undefined
                        : key === "max_rebalance_turnover"
                          ? 2
                          : 1
                    }
                    step={key === "max_positions" ? 1 : "any"}
                    value={draft[key]}
                    onChange={(e) =>
                      setDraft({ ...draft, [key]: Number(e.target.value) })
                    }
                  />
                </Field>
              ))}
              <Field label="回撤触线动作">
                <select
                  value={draft.drawdown_action}
                  onChange={(e) =>
                    setDraft({ ...draft, drawdown_action: e.target.value })
                  }
                >
                  <option value="stop_new">停止新开仓</option>
                  <option value="reduce">降仓</option>
                  <option value="liquidate">清仓</option>
                </select>
              </Field>
            </div>
            <button className="primary" disabled={action.busy}>
              保存默认风险规则
            </button>
          </form>
          {action.message && <Note tone="success">{action.message}</Note>}
        </Card>
      )}
      <Card title="最近风控记录 · 最近 10 次成功回测">
        <ErrorBox error={recent.error} />
        <MetricGrid values={recent.data?.counts || {}} />
        {!recent.loading && !recent.data?.total ? (
          <Note>尚无新版风控事件，请先运行回测。</Note>
        ) : (
          <RemoteTable
            path="/risk/events"
            exportPath="/risk/events/export.csv"
          />
        )}
      </Card>
      <Card title="查看单次运行风险事件">
        <Field label="运行">
          <select value={runId} onChange={(e) => setRunId(e.target.value)}>
            <option value="">选择运行</option>
            {runs.data?.items.map((run: Obj) => (
              <option key={run.run_id} value={run.run_id}>
                {run.strategy_id} · {run.run_id.slice(0, 8)}
              </option>
            ))}
          </select>
        </Field>
        {runId && (
          <RemoteTable
            key={runId}
            path={`/runs/${runId}/tables/risk_events`}
            exportPath={`/runs/${runId}/tables/risk_events/export.csv`}
          />
        )}
      </Card>
    </>
  );
}
