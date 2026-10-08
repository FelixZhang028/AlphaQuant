import {
  Component,
  Suspense,
  lazy,
  useEffect,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Link,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import {
  ArrowRight,
  CircleHelp,
  Code2,
  Menu,
  Search,
  Settings2,
  X,
} from "lucide-react";
import { useResource } from "./api";
import { Card, Empty, ErrorBox, Loading, PageHead } from "./components";
import { currentTool, tools, workspaces } from "./navigation";
import "./styles.css";

function page(loader: () => Promise<any>, name: string) {
  return lazy<ComponentType<any>>(async () => ({
    default: (await loader())[name],
  }));
}
const home = () => import("./pages/Home"),
  research = () => import("./pages/Research"),
  data = () => import("./pages/Data"),
  strategies = () => import("./pages/Strategies"),
  factors = () => import("./pages/Factors"),
  ai = () => import("./pages/AI"),
  settings = () => import("./pages/Settings"),
  backtests = () => import("./pages/Backtests");
const Home = page(home, "Home"),
  Workspace = page(home, "Workspace"),
  Welcome = page(home, "Welcome"),
  Account = page(home, "Account");
const BacktestPage = page(backtests, "BacktestPage"),
  RunReport = page(backtests, "RunReport"),
  Records = page(research, "Records"),
  Experiments = page(research, "Experiments"),
  Plans = page(research, "Plans"),
  Audit = page(research, "Audit"),
  ExternalAudit = page(research, "ExternalAudit");
const Ideas = page(strategies, "Ideas"),
  VisualStrategy = page(strategies, "VisualStrategy"),
  NaturalLanguage = page(strategies, "NaturalLanguage"),
  PythonStrategies = page(strategies, "PythonStrategies"),
  FactorLab = page(factors, "FactorLab");
const DataUpdate = page(data, "DataUpdate"),
  Universe = page(data, "Universe"),
  Jobs = page(data, "Jobs"),
  Backfill = page(data, "Backfill"),
  DataSources = page(data, "DataSources"),
  XTick = page(data, "XTick");
const Settings = page(settings, "Settings"),
  Risk = page(settings, "Risk"),
  Knowledge = page(ai, "Knowledge"),
  AIResearch = page(ai, "AIResearch");

class Boundary extends Component<{ children: ReactNode }, { error?: Error }> {
  state: { error?: Error } = {};
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    return this.state.error ? (
      <Card title="页面暂时无法显示">
        <ErrorBox error={this.state.error} />
        <button onClick={() => location.reload()}>重新载入页面</button>
      </Card>
    ) : (
      this.props.children
    );
  }
}
function Layout() {
  const location = useLocation(),
    tool = currentTool(location.pathname),
    [open, setOpen] = useState(false),
    [searching, setSearching] = useState(false),
    [search, setSearch] = useState("");
  const health = useResource("/health");
  const group =
    tool?.group ||
    (location.pathname.startsWith("/app/backtests/") ||
    location.pathname.startsWith("/app/experiments") ||
    location.pathname.startsWith("/app/factors")
      ? "策略研究"
      : location.pathname === "/app/operations"
        ? "数据与运行"
        : "首页");
  useEffect(() => {
    if (location.pathname !== "/app/account") {
      sessionStorage.setItem(
        "alphaquant:last-internal-page",
        location.pathname + location.search,
      );
    }
    setOpen(false);
    setSearching(false);
    window.scrollTo(0, 0);
  }, [location.pathname]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearching((value) => !value);
      }
      if (event.key === "Escape") {
        setSearching(false);
        setOpen(false);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const matches = tools.filter((t) =>
    `${t.title} ${t.description}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="app-shell">
      {open && (
        <button
          className="sidebar-backdrop"
          aria-label="关闭导航"
          onClick={() => setOpen(false)}
        />
      )}
      <aside className={"sidebar " + (open ? "open" : "")}>
        <Link className="brand" to="/app">
          <span className="brand-mark">A</span>
          <div>
            AlphaQuant<small>量化研究工作台</small>
          </div>
        </Link>
        <span className="nav-caption">WORKSPACE</span>
        <nav className="workspace-nav">
          {workspaces.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/app"}
              className={() => (group === item.title ? "active" : "")}
            >
              <item.icon size={18} />
              <span>{item.title}</span>
              {group === item.title && <span className="active-dot" />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-section">
          <span className="nav-caption">研究工具</span>
          <nav className="tool-nav">
            {tools
              .filter(
                (t) => t.group === (group === "首页" ? "策略研究" : group),
              )
              .map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === "/app/settings"}
                >
                  <item.icon size={15} />
                  <span>{item.title}</span>
                </NavLink>
              ))}
          </nav>
        </div>
        <div className="sidebar-bottom">
          <Link to="/">
            <CircleHelp size={16} />
            使用指南
          </Link>
          <a
            href="https://github.com/FelixZhang028/AlphaQuant"
            target="_blank"
            rel="noreferrer"
          >
            <Code2 size={16} />
            项目与反馈
          </a>
          <div className="local-status">
            <span className={"live-dot " + (health.error ? "offline" : "")} />
            <div>
              {health.data
                ? "本机服务已连接"
                : health.error
                  ? "后端未连接"
                  : "正在连接…"}
              <small>本地模式 · 暂不要求登录</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            aria-label="打开导航"
            onClick={() => setOpen(true)}
          >
            <Menu size={20} />
          </button>
          <div className="breadcrumb">
            <Link to="/app">工作台</Link>
            <span>/</span>
            <span>
              {tool?.title || (location.pathname === "/app" ? "首页" : group)}
            </span>
          </div>
          <div className="topbar-actions">
            <button
              className="search-trigger"
              onClick={() => setSearching(true)}
            >
              <Search size={15} />
              <span>搜索工具</span>
              <kbd>Ctrl K</kbd>
            </button>
            <Link
              className="icon-button"
              aria-label="打开设置"
              to="/app/settings"
            >
              <Settings2 size={18} />
            </Link>
            <Link className="avatar" aria-label="个人中心" to="/app/account">
              本机
            </Link>
          </div>
        </header>
        <main className="content">
          <Boundary key={location.pathname}>
            <Suspense fallback={<Loading />}>
              <Outlet />
            </Suspense>
          </Boundary>
          <footer className="workspace-footer">
            <span>AlphaQuant</span>
            <span>规则清晰 · 过程留痕 · 结果可复盘</span>
          </footer>
        </main>
      </div>
      {searching && (
        <div className="modal-backdrop" onClick={() => setSearching(false)}>
          <section
            className="search-modal"
            role="dialog"
            aria-modal="true"
            aria-label="搜索全部工具"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-search">
              <Search size={20} />
              <input
                autoFocus
                placeholder="搜索全部 23 个工具…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <button
                className="icon-button"
                aria-label="关闭搜索"
                onClick={() => setSearching(false)}
              >
                <X size={20} />
              </button>
            </div>
            <div className="search-results">
              {matches.map((item) => (
                <Link
                  to={item.path}
                  key={item.path}
                  onClick={() => setSearching(false)}
                >
                  <item.icon size={18} />
                  <div>
                    <strong>{item.title}</strong>
                    <small>
                      {item.group} · {item.description}
                    </small>
                  </div>
                  <ArrowRight size={15} />
                </Link>
              ))}
              {!matches.length && <Empty>没有匹配的工具。</Empty>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
function NotFound() {
  return (
    <>
      <PageHead
        title="这个页面没有找到"
        description="可以从全部工具中重新进入研究流程。"
      />
      <Link className="button primary" to="/app">
        返回工作台
      </Link>
    </>
  );
}
function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={<Welcome />} />
          <Route path="/app" element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="strategies" element={<Workspace group="策略研究" />} />
            <Route
              path="operations"
              element={<Workspace group="数据与运行" />}
            />
            <Route path="strategies/ideas" element={<Ideas />} />
            <Route path="strategies/visual" element={<VisualStrategy />} />
            <Route
              path="strategies/natural-language"
              element={<NaturalLanguage />}
            />
            <Route path="strategies/python" element={<PythonStrategies />} />
            <Route path="backtests/new" element={<BacktestPage />} />
            <Route path="backtests/:runId" element={<RunReport />} />
            <Route
              path="experiments/optimization"
              element={<Experiments key="optimization" />}
            />
            <Route
              path="experiments/walk-forward"
              element={<Experiments key="walk-forward" walkForward />}
            />
            <Route path="research/records" element={<Records />} />
            <Route path="research/plans" element={<Plans />} />
            <Route path="audits" element={<Audit />} />
            <Route path="audits/external" element={<ExternalAudit />} />
            <Route path="audits/:runId" element={<Audit />} />
            {["library", "evaluation", "combinations", "custom"].map((tab) => (
              <Route
                key={tab}
                path={"factors/" + tab}
                element={<FactorLab key={tab} tab={tab} />}
              />
            ))}
            <Route path="knowledge" element={<Knowledge />} />
            <Route path="research/ai" element={<AIResearch />} />
            <Route path="data/update" element={<DataUpdate />} />
            <Route path="data/universe" element={<Universe />} />
            <Route path="data/backfill" element={<Backfill />} />
            <Route path="data/sources" element={<DataSources />} />
            <Route path="data/xtick" element={<XTick />} />
            <Route path="operations/jobs" element={<Jobs />} />
            <Route path="settings" element={<Settings />} />
            <Route path="risk" element={<Risk />} />
            <Route path="account" element={<Account />} />
            <Route path="*" element={<NotFound />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
