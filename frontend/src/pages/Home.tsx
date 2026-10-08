import { useState } from "react";
import {
  ArrowRight,
  BookOpen,
  ChartNoAxesCombined,
  CheckCheck,
  FlaskConical,
  Play,
  Plus,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";
import { type Obj, useResource, useSticky } from "../api";
import {
  Badge,
  Card,
  Empty,
  ErrorBox,
  format,
  Loading,
  MetricGrid,
  Note,
  PageHead,
  Report,
} from "../components";
import { tools } from "../navigation";

export function ToolGrid({
  group,
  search = "",
}: {
  group?: string;
  search?: string;
}) {
  const matches = tools.filter(
    (t) =>
      (!group || t.group === group) &&
      `${t.title} ${t.description}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return matches.length ? (
    <div className="tool-grid">
      {matches.map((tool) => (
        <Link className="tool-card" to={tool.path} key={tool.path}>
          <span className="tool-icon">
            <tool.icon size={20} />
          </span>
          <div>
            <h3>{tool.title}</h3>
            <p>{tool.description}</p>
          </div>
          <ArrowRight size={17} />
        </Link>
      ))}
    </div>
  ) : (
    <Empty>没有匹配的工具，请换个关键词。</Empty>
  );
}
export function Home() {
  const runs = useResource("/runs?limit=3"),
    overview = useResource("/data/overview"),
    strategies = useResource("/strategies");
  const [lastRun] = useSticky<string | null>("last-run", null);
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <PageHead
        title="让每一个想法，都有证据。"
        description="从策略研究到样本外验证，在一个工作台里完成。"
        eyebrow="YOUR RESEARCH WORKSPACE"
        actions={
          <Link className="button primary" to="/app/backtests/new">
            <Plus size={16} />
            新建回测
          </Link>
        }
      />
      <section className="hero">
        <div>
          <span className="hero-tag">
            <span className="live-dot" /> 本地量化研究工作台
          </span>
          <h2>
            研究有方向，
            <br />
            决策有依据。
          </h2>
          <p>
            建立规则 · 检查数据 · 验证结果
            <br />
            把研究过程留在可追溯的记录里。
          </p>
          <Link className="button light" to="/app/strategies/ideas">
            从一个想法开始 <ArrowRight size={16} />
          </Link>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit one" />
          <div className="orbit two" />
          <div className="orbit three" />
          <div className="hero-core">
            <ChartNoAxesCombined size={58} strokeWidth={1.1} />
          </div>
          <span className="art-label top">
            <FlaskConical size={14} />
            规则
          </span>
          <span className="art-label bottom">
            <ShieldCheck size={14} />
            证据
          </span>
        </div>
      </section>
      <div className="stat-row">
        <div>
          <span className="stat-icon">
            <FolderIcon />
          </span>
          <div>
            <small>成功回测</small>
            <strong>{runs.data?.total ?? "—"}</strong>
          </div>
        </div>
        <div>
          <span className="stat-icon purple">
            <FlaskConical size={19} />
          </span>
          <div>
            <small>可用策略</small>
            <strong>{strategies.data?.items.length ?? "—"}</strong>
          </div>
        </div>
        <div>
          <span className="stat-icon amber">
            <ChartNoAxesCombined size={19} />
          </span>
          <div>
            <small>配置股票</small>
            <strong>{overview.data?.configured_symbol_count ?? "—"}</strong>
          </div>
        </div>
        <div>
          <span className="stat-icon blue">
            <CheckCheck size={19} />
          </span>
          <div>
            <small>行情记录</small>
            <strong>
              {overview.data?.market?.rows?.toLocaleString() ?? "—"}
            </strong>
          </div>
        </div>
      </div>
      <ErrorBox error={runs.error || overview.error || strategies.error} />
      <div className="section-heading">
        <h2>今天，从哪里开始？</h2>
        <span>三个常用研究入口</span>
      </div>
      <div className="start-grid">
        {[
          {
            title: "验证策略想法",
            text: "把想法变成规则，用历史数据检验。",
            icon: FlaskConical,
            path: "/app/strategies/ideas",
            number: "01",
          },
          {
            title: "检查外部策略",
            text: "核对成交材料，看看证据是否充分。",
            icon: ShieldCheck,
            path: "/app/audits/external",
            number: "02",
          },
          {
            title: "查看研究结果",
            text: "回顾收益、风险和执行假设。",
            icon: ChartNoAxesCombined,
            path: "/app/research/records",
            number: "03",
          },
        ].map((item) => (
          <Link className="start-card" to={item.path} key={item.number}>
            <div className="start-card-top">
              <item.icon size={23} />
              <span>{item.number}</span>
            </div>
            <h3>{item.title}</h3>
            <p>{item.text}</p>
            <span className="text-button">
              开始研究 <ArrowRight size={15} />
            </span>
          </Link>
        ))}
      </div>
      <Card
        title="最近研究"
        action={
          <Link className="text-button" to="/app/research/records">
            全部记录 <ArrowRight size={14} />
          </Link>
        }
      >
        {runs.loading ? (
          <Loading />
        ) : runs.data?.items.length ? (
          <div className="recent-list">
            {runs.data.items.map((run: Obj) => (
              <Link to={"/app/backtests/" + run.run_id} key={run.run_id}>
                <span className="recent-icon">
                  <ChartNoAxesCombined size={19} />
                </span>
                <div>
                  <strong>{run.strategy_id}</strong>
                  <small>
                    {run.start_date} — {run.end_date} · {run.run_id.slice(0, 8)}
                  </small>
                </div>
                <Badge value={run.status} />
                <ArrowRight size={16} />
              </Link>
            ))}
          </div>
        ) : (
          <Empty>还没有成功回测。检查数据后，可以开始第一次研究。</Empty>
        )}
        {lastRun && (
          <Link className="button" to={"/app/backtests/" + lastRun}>
            继续上次研究 <ArrowRight size={14} />
          </Link>
        )}
      </Card>
      <button className="disclosure" onClick={() => setExpanded(!expanded)}>
        {expanded ? "收起全部工具" : "浏览全部 23 个工具"}{" "}
        <ArrowRight size={14} />
      </button>
      {expanded && <ToolGrid />}
    </>
  );
}
function FolderIcon() {
  return <BookOpen size={19} />;
}
export function Workspace({ group }: { group: string }) {
  const [search, setSearch] = useState("");
  return (
    <>
      <PageHead
        title={group}
        description={
          group === "策略研究"
            ? "选择一种创作方式，从规则开始，逐步验证。"
            : "维护数据、股票池与后台任务。"
        }
      />
      <input
        className="tool-search"
        aria-label="搜索工具"
        placeholder="搜索工具或功能…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <ToolGrid group={group} search={search} />
      {group === "数据与运行" && <Readiness />}
    </>
  );
}
export function Readiness({ en = false }: { en?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const resource = useResource(expanded ? "/readiness" : null);
  return (
    <Card
      title={en ? "Local readiness check" : "本机就绪检查"}
      action={
        <button onClick={() => setExpanded(!expanded)}>
          {expanded
            ? en
              ? "Collapse"
              : "收起"
            : en
              ? "Check environment"
              : "检查当前环境"}
        </button>
      }
    >
      {expanded && (
        <>
          <ErrorBox error={resource.error} />
          {resource.loading ? <Loading /> : <Report value={resource.data} />}
        </>
      )}
    </Card>
  );
}
export function Welcome() {
  const [language, setLanguage] = useSticky("welcome-language", "zh");
  const [preview, setPreview] = useState(0);
  const en = language === "en";
  const previews = en
    ? [
        [
          "Data",
          "Know what your research is built on",
          "Review source coverage, local tables and the stock universe.",
          "/app/data/update",
        ],
        [
          "Strategies",
          "Turn an idea into explicit rules",
          "Use templates, visual conditions, Python or natural language.",
          "/app/strategies",
        ],
        [
          "Backtests",
          "Follow every trade and assumption",
          "Inspect equity, costs, positions, risk events and execution evidence.",
          "/app/backtests/new",
        ],
        [
          "AI research",
          "Question and trace the reasoning",
          "Follow the analysis, then discuss its evidence and risks.",
          "/app/research/ai",
        ],
        [
          "Validation",
          "Test whether results hold up",
          "Compare parameter experiments and rolling out-of-sample windows.",
          "/app/experiments/optimization",
        ],
      ]
    : [
        [
          "数据",
          "先看清研究的数据基础",
          "核对来源、覆盖范围、本地数据表和股票池。",
          "/app/data/update",
        ],
        [
          "策略",
          "把投资想法变成明确规则",
          "从模板、可视化条件、Python 或自然语言开始。",
          "/app/strategies",
        ],
        [
          "回测",
          "每一笔交易都有据可查",
          "查看净值、成本、持仓、风险事件和完整执行证据。",
          "/app/backtests/new",
        ],
        [
          "智能分析",
          "沿着分析过程追问依据",
          "回放研究过程，并继续讨论结论、证据与风险。",
          "/app/research/ai",
        ],
        [
          "优化验证",
          "检验结果能否经得起变化",
          "对比参数实验，检查滚动样本外区间的表现。",
          "/app/experiments/optimization",
        ],
      ];
  return (
    <main className="welcome">
      <nav>
        <Link className="brand" to="/app">
          <span className="brand-mark">A</span>AlphaQuant
        </Link>
        <div className="actions">
          <button onClick={() => setLanguage(en ? "zh" : "en")}>
            {en ? "中文" : "English"}
          </button>
          <Link className="button primary" to="/app">
            {en ? "Open workspace" : "进入工作台"} <ArrowRight size={16} />
          </Link>
        </div>
      </nav>
      <section className="welcome-hero">
        <span className="eyebrow">BUILD · RESEARCH · VERIFY</span>
        <h1>
          {en ? (
            <>
              A clearer path
              <br />
              from ideas to evidence.
            </>
          ) : (
            <>
              让投资想法，
              <br />
              经得起数据检验。
            </>
          )}
        </h1>
        <p>
          {en
            ? "Your local workspace for strategies, backtests, AI research and validation."
            : "策略、回测、智能研究与验证。让每一步判断，都能回到事实。"}
        </p>
        <Link className="button primary large" to="/app">
          {en ? "Start your research" : "开始研究"} <ArrowRight size={17} />
        </Link>
        <a className="text-button" href="#workflow">
          {en ? "Explore the workflow" : "了解研究流程"} ↓
        </a>
      </section>
      <section aria-label={en ? "Feature preview" : "功能预览"}>
        <h2>
          {en ? "A connected research toolkit." : "从数据到验证，一处衔接。"}
        </h2>
        <div
          className="tabs"
          role="tablist"
          aria-label={en ? "Features" : "五类功能"}
        >
          {previews.map((item, i) => (
            <button
              key={item[0]}
              role="tab"
              aria-selected={preview === i}
              id={"preview-tab-" + i}
              aria-controls="preview-panel"
              onClick={() => setPreview(i)}
            >
              {item[0]}
            </button>
          ))}
        </div>
        <Card>
          <div
            role="tabpanel"
            id="preview-panel"
            aria-labelledby={"preview-tab-" + preview}
          >
            <span className="eyebrow">0{preview + 1} / 05</span>
            <h3>{previews[preview][1]}</h3>
            <p className="muted">{previews[preview][2]}</p>
            <Link className="text-button" to={previews[preview][3]}>
              {en ? "Open tool" : "打开工具"} →
            </Link>
          </div>
        </Card>
      </section>
      <section id="workflow">
        <h2>
          {en ? "Five steps. One research workspace." : "五步，把研究做扎实。"}
        </h2>
        <div className="workflow-grid">
          {(en
            ? [
                "Prepare data",
                "Build rules",
                "Run a backtest",
                "Review evidence",
                "Validate robustness",
              ]
            : ["准备数据", "建立规则", "运行回测", "核对证据", "稳健验证"]
          ).map((title, i) => (
            <article key={title}>
              <span>0{i + 1}</span>
              <h3>{title}</h3>
              <p>
                {
                  (en
                    ? [
                        "Check coverage and sources.",
                        "Choose templates, code or AI.",
                        "Keep assumptions and results.",
                        "Review trades, costs and risks.",
                        "Test unseen data and parameter bias.",
                      ]
                    : [
                        "核对来源、历史覆盖与股票池。",
                        "使用模板、积木、代码或自然语言。",
                        "保存参数、执行假设和完整结果。",
                        "查看交易、成本、风险与可信度。",
                        "研究参数偏差与样本外表现。",
                      ])[i]
                }
              </p>
            </article>
          ))}
        </div>
        <Readiness en={en} />
      </section>
      <footer>
        <span>
          AlphaQuant ·{" "}
          {en
            ? "Local research, traceable evidence."
            : "本地研究，证据可追溯。"}
        </span>
        <Link to="/app">{en ? "Open workspace" : "进入工作台"} →</Link>
      </footer>
    </main>
  );
}
export function Account() {
  const previous =
    sessionStorage.getItem("alphaquant:last-internal-page") || "/app";
  const back =
    previous === "/app" || previous.startsWith("/app/") ? previous : "/app";
  return (
    <>
      <PageHead title="个人中心" description="当前为本机访问模式。" />
      <Card title="访问状态">
        <Note>
          按当前迁移安排，登录与注册暂后接入。这里的研究记录属于本机共享工作区，尚未按账号隔离。
        </Note>
        <div className="actions">
          <Link className="button" to={back}>
            返回来源页
          </Link>
          <Link className="button" to="/app/settings">
            前往设置
          </Link>
          <Link className="button" to="/">
            使用指南
          </Link>
        </div>
      </Card>
      <Card title="账号功能">
        <p className="muted">
          资料编辑、修改密码、保存偏好、收藏与个人空间在旧版中也属于待开放功能。
        </p>
        <button disabled>资料编辑 · 尚未开放</button>
      </Card>
    </>
  );
}
