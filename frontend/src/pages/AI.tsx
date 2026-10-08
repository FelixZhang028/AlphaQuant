import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type Obj,
  post,
  query,
  remove,
  useAction,
  useJob,
  useResource,
  useSticky,
} from "../api";
import {
  Card,
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

export function Knowledge() {
  const [search, setSearch] = useState(""),
    [source, setSource] = useState(""),
    [offset, setOffset] = useState(0),
    resource = useResource(
      "/knowledge" + query({ q: search, source, offset, limit: 100 }),
    );
  useEffect(() => setOffset(0), [search, source]);
  const [draft, setDraft] = useSticky("knowledge-new", {
      content: "",
      source: "我的观点",
    }),
    action = useAction();
  return (
    <>
      <PageHead
        title="先验知识库"
        description="保存研究观点与来源，AI 分析会读取全部知识，不受当前列表筛选影响。"
      />
      <Card title="添加研究知识">
        <Field label="内容">
          <textarea
            rows={4}
            value={draft.content}
            onChange={(e) => setDraft({ ...draft, content: e.target.value })}
          />
        </Field>
        <Field label="来源">
          <input
            value={draft.source}
            onChange={(e) => setDraft({ ...draft, source: e.target.value })}
          />
        </Field>
        <button
          className="primary"
          disabled={!draft.content.trim() || action.busy}
          onClick={() =>
            action.run(
              () => post("/knowledge", draft),
              () => {
                setDraft({ ...draft, content: "" });
                resource.refresh();
              },
            )
          }
        >
          保存知识
        </button>
        <ErrorBox error={action.error || resource.error} />
      </Card>
      <Card title="已保存知识">
        <MetricGrid
          values={{
            全部条目: resource.data?.all_count,
            来源数量: resource.data?.sources.length,
            最近更新: resource.data?.latest_update,
          }}
        />
        <div className="form-grid">
          <Field label="搜索内容或来源">
            <input value={search} onChange={(e) => setSearch(e.target.value)} />
          </Field>
          <Field label="来源过滤">
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">全部来源</option>
              {resource.data?.sources.map((s: string) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
        </div>
        {resource.loading ? (
          <Loading />
        ) : resource.data?.items.length ? (
          resource.data.items.map((item: Obj) => (
            <article className="knowledge-item" key={item.id}>
              <div>
                <span className="badge">{item.source}</span>
                <small>{item.created_at}</small>
                <p>{item.content}</p>
              </div>
              <button
                className="danger"
                disabled={action.busy}
                onClick={() =>
                  action.run(
                    () => remove("/knowledge/" + item.id),
                    resource.refresh,
                  )
                }
              >
                删除此条
              </button>
            </article>
          ))
        ) : (
          <Empty>没有匹配的知识条目。</Empty>
        )}
        <div className="pagination">
          <span>共 {resource.data?.total || 0} 条 · 每页 100 条</span>
          <button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 100))}
          >
            上一页
          </button>
          <button
            disabled={!resource.data || offset + 100 >= resource.data.total}
            onClick={() => setOffset(offset + 100)}
          >
            下一页
          </button>
        </div>
      </Card>
    </>
  );
}
export function AIResearch() {
  const settings = useResource("/settings"),
    [symbolSearch, setSymbolSearch] = useState(""),
    securities = useResource(
      symbolSearch ? "/universe/search" + query({ q: symbolSearch }) : null,
    );
  const [draft, setDraft] = useSticky("ai-draft", {
    symbol: "000001",
    trade_date: new Date().toISOString().slice(0, 10),
    lookback_days: 120,
    debate_rounds: 1,
    use_cache: true,
    provider: "",
    stock_source: "local",
    news_sources: [] as string[],
  });
  const [intervention, setIntervention] = useSticky("ai-intervention", false),
    [message, setMessage] = useState(""),
    [chatAnalysis, setChatAnalysis] = useSticky<string | null>(
      "chat-analysis",
      null,
    );
  const analysis = useJob("ai-analysis"),
    chat = useJob("ai-chat"),
    [failedMessage, setFailedMessage] = useSticky(
      "ai-chat-pending-message",
      "",
    );
  const [signature, setSignature] = useSticky("ai-submitted-signature", "");
  const [completedChat, setCompletedChat] = useSticky<{
    analysisId: string; taskId: string;
  } | null>("ai-completed-chat", null);
  const previousChat = useResource(
    completedChat?.analysisId === analysis.id
      ? `/tasks/${completedChat.taskId}/result` : null,
  );
  const change = (key: string, value: any) =>
    setDraft({ ...draft, [key]: value });
  const submit = async () => {
    const next = await analysis.submit("ai_analysis", {
      ...draft,
      provider: draft.provider || null,
    });
    if (next) {
      setSignature(JSON.stringify(draft));
      chat.setId(null);
      setChatAnalysis(next.id);
      setCompletedChat(null);
      setFailedMessage("");
    }
  };
  const send = async () => {
    const text = message.trim();
    if (!text || !analysis.id) return;
    setFailedMessage(text);
    setMessage("");
    const next = await chat.submit("ai_chat", {
      analysis_task_id: analysis.id,
      message: text,
      previous_task_id:
        chat.task?.status === "SUCCESS" && chatAnalysis === analysis.id
          ? chat.id
          : completedChat?.analysisId === analysis.id ? completedChat.taskId : null,
    });
    if (next) setChatAnalysis(analysis.id);
  };
  useEffect(() => {
    if (chat.task?.status === "SUCCESS" && chat.result && chat.id &&
      chatAnalysis === analysis.id && analysis.id) {
      setFailedMessage("");
      setCompletedChat({ analysisId: analysis.id, taskId: chat.id });
    }
  }, [chat.task?.status, chat.result, chat.id, chatAnalysis, analysis.id]);
  const result = analysis.result,
    current = signature === JSON.stringify(draft),
    messages = chatAnalysis === analysis.id
      ? chat.result?.messages || previousChat.data?.messages || [] : [];
  return (
    <>
      <PageHead
        title="AI 研究员"
        description="多智能体分别分析、讨论与评估，保留过程和最终决策。"
        actions={
          <>
            <Link className="button" to="/app/knowledge">
              先验知识库
            </Link>
            <Link className="button" to="/app/settings">
              模型设置
            </Link>
          </>
        }
      />
      <Card title="研究对象与数据来源">
        <Field label="按证券名称搜索（或直接填写代码）">
          <input
            value={symbolSearch}
            onChange={(e) => setSymbolSearch(e.target.value)}
            placeholder="搜索证券名称"
          />
        </Field>
        {symbolSearch && (
          <DataTable
            data={securities.data as any}
            onRow={(row) => {
              change("symbol", row.symbol || row["证券代码"]);
              setSymbolSearch("");
            }}
          />
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <div className="form-grid">
            <Field label="股票代码">
              <input
                required
                value={draft.symbol}
                onChange={(e) => change("symbol", e.target.value)}
              />
            </Field>
            <Field label="分析日期">
              <input
                type="date"
                required
                value={draft.trade_date}
                onChange={(e) => change("trade_date", e.target.value)}
              />
            </Field>
            <Field label="模型提供方">
              <select
                value={draft.provider}
                onChange={(e) => change("provider", e.target.value)}
              >
                <option value="">
                  全局默认（{settings.data?.default_provider || "—"}）
                </option>
                {settings.data?.providers.map((p: Obj) => (
                  <option key={p.key} value={p.key}>
                    {p.display_name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="行情来源">
              <select
                value={draft.stock_source}
                onChange={(e) => change("stock_source", e.target.value)}
              >
                {Object.entries(
                  settings.data?.stock_sources || { local: "本地行情" },
                ).map(([key, label]) => (
                  <option key={key} value={key}>
                    {String(label)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="回看天数">
              <input
                type="number"
                required
                min={20}
                max={250}
                value={draft.lookback_days}
                onChange={(e) =>
                  change("lookback_days", Number(e.target.value))
                }
              />
            </Field>
            <Field label="辩论轮数">
              <input
                type="number"
                required
                min={0}
                max={4}
                value={draft.debate_rounds}
                onChange={(e) =>
                  change("debate_rounds", Number(e.target.value))
                }
              />
            </Field>
          </div>
          <div className="checks">
            {Object.entries(settings.data?.news_sources || {}).map(
              ([key, label]) => (
                <CheckBox
                  key={key}
                  label={String(label)}
                  checked={draft.news_sources.includes(key)}
                  onChange={(value) =>
                    change(
                      "news_sources",
                      value
                        ? [...draft.news_sources, key]
                        : draft.news_sources.filter((v) => v !== key),
                    )
                  }
                />
              ),
            )}
            <button
              type="button"
              className="text-button"
              onClick={() =>
                change(
                  "news_sources",
                  Object.keys(settings.data?.news_sources || {}),
                )
              }
            >
              全选新闻源
            </button>
          </div>
          <CheckBox
            label="允许使用缓存的最终决策"
            checked={draft.use_cache}
            onChange={(value) => change("use_cache", value)}
          />
          <CheckBox
            label="分析后启用人为介入对话"
            checked={intervention}
            onChange={setIntervention}
          />
          <button className="primary" disabled={analysis.active}>
            开始 AI 分析
          </button>
        </form>
        <p className="muted">
          多来源会增加耗时；新闻失败可降级。本地行情只读取分析日期及之前的数据。
        </p>
        <ErrorBox error={settings.error || securities.error} />
      </Card>
      <JobPanel job={analysis} showResult={false} />
      {result && (
        <>
          <Card title="决策与研究证据">
            {!current && (
              <Note>研究参数已修改，以下为上次已提交任务的结果。</Note>
            )}
            {result.mode === "cache_enabled" && (
              <Note>
                启用了缓存：只提供最终决策，未提供的中间报告不会补造。
              </Note>
            )}
            <Report value={result.decision} />
          </Card>
          {result.state && (
            <Card title="完整分析与过程回放">
              <Report value={result.state} />
            </Card>
          )}
          {intervention && (
            <Card title="人为介入 · 与本次研究对话">
              <ErrorBox error={previousChat.error} />
              <div className="chat-history">
                {messages.map((item: Obj, index: number) => (
                  <article key={index} className={item.role}>
                    <strong>
                      {item.role === "user" ? "你的观点" : "AI 研究员"}
                    </strong>
                    <p>{item.content}</p>
                  </article>
                ))}
                {failedMessage && (
                  <article className="user">
                    <strong>已提交的观点</strong>
                    <p>{failedMessage}</p>
                  </article>
                )}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void send();
                }}
              >
                <Field label="提出问题、质疑或补充观点">
                  <textarea
                    rows={3}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                  />
                </Field>
                <button
                  className="primary"
                  disabled={
                    !message.trim() ||
                    chat.active ||
                    analysis.task?.status !== "SUCCESS"
                  }
                >
                  发送观点
                </button>
              </form>
              <JobPanel job={chat} showResult={false} />
            </Card>
          )}
        </>
      )}
    </>
  );
}
