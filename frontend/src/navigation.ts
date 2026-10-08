import {
  Activity,
  BookOpen,
  Boxes,
  Braces,
  ChartNoAxesCombined,
  CircleHelp,
  Database,
  FlaskConical,
  FolderClock,
  LayoutDashboard,
  ListChecks,
  MessagesSquare,
  Network,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquareTerminal,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export type Tool = {
  title: string;
  path: string;
  description: string;
  group: string;
  icon: LucideIcon;
};
export const tools: Tool[] = [
  {
    title: "AI 研究员",
    path: "/app/research/ai",
    description: "多智能体分析、证据回放与研究对话",
    group: "策略研究",
    icon: Sparkles,
  },
  {
    title: "选股想法",
    path: "/app/strategies/ideas",
    description: "从想法出发，确认规则与数据条件",
    group: "策略研究",
    icon: FlaskConical,
  },
  {
    title: "可视化策略",
    path: "/app/strategies/visual",
    description: "模板、条件积木与版本管理",
    group: "策略研究",
    icon: Workflow,
  },
  {
    title: "自然语言策略",
    path: "/app/strategies/natural-language",
    description: "描述规则，生成并人工确认策略",
    group: "策略研究",
    icon: MessagesSquare,
  },
  {
    title: "Python 策略",
    path: "/app/strategies/python",
    description: "在线编写、上传和注册自己的策略",
    group: "策略研究",
    icon: Braces,
  },
  {
    title: "单次回测",
    path: "/app/backtests/new",
    description: "检查数据，运行策略，查看完整报告",
    group: "策略研究",
    icon: ChartNoAxesCombined,
  },
  {
    title: "参数优化与验证",
    path: "/app/experiments/optimization",
    description: "参数搜索、DSR 与滚动样本外验证",
    group: "策略研究",
    icon: Network,
  },
  {
    title: "因子实验室",
    path: "/app/factors/library",
    description: "因子库、评价、组合与自定义因子",
    group: "策略研究",
    icon: Boxes,
  },
  {
    title: "先验知识库",
    path: "/app/knowledge",
    description: "让研究观点与来源进入 AI 上下文",
    group: "策略研究",
    icon: BookOpen,
  },
  {
    title: "研究记录与对比",
    path: "/app/research/records",
    description: "查找历史回测，比较结果与参数",
    group: "我的研究",
    icon: FolderClock,
  },
  {
    title: "可信度审计",
    path: "/app/audits",
    description: "六维审计与原始证据链",
    group: "我的研究",
    icon: ShieldCheck,
  },
  {
    title: "检查外部策略",
    path: "/app/audits/external",
    description: "导入成交材料，核对本地市场证据",
    group: "我的研究",
    icon: ListChecks,
  },
  {
    title: "研究方案复用",
    path: "/app/research/plans",
    description: "保存执行快照，对比与恢复版本",
    group: "我的研究",
    icon: Workflow,
  },
  {
    title: "行情更新",
    path: "/app/data/update",
    description: "数据源、覆盖率、行情与版本明细",
    group: "数据与运行",
    icon: RefreshCw,
  },
  {
    title: "全市场回填",
    path: "/app/data/backfill",
    description: "断点回填、进度和闭环检查点",
    group: "数据与运行",
    icon: Database,
  },
  {
    title: "任务记录",
    path: "/app/operations/jobs",
    description: "任务状态、日志、取消和失败重试",
    group: "数据与运行",
    icon: Activity,
  },
  {
    title: "数据资产",
    path: "/app/data/sources",
    description: "比较来源能力与配置状态",
    group: "数据与运行",
    icon: Boxes,
  },
  {
    title: "XTick 接口",
    path: "/app/data/xtick",
    description: "完整动态目录、查询与结果下载",
    group: "数据与运行",
    icon: SquareTerminal,
  },
  {
    title: "股票池",
    path: "/app/data/universe",
    description: "搜索证券，维护范围与过滤规则",
    group: "数据与运行",
    icon: ListChecks,
  },
  {
    title: "风险规则与记录",
    path: "/app/risk",
    description: "仓位、回撤约束和历史风险事件",
    group: "策略研究",
    icon: ShieldCheck,
  },
  {
    title: "模型与数据源设置",
    path: "/app/settings",
    description: "AI 模型、数据凭证与存储诊断",
    group: "设置",
    icon: Settings2,
  },
  {
    title: "个人中心",
    path: "/app/account",
    description: "本机访问状态与账号迁移说明",
    group: "设置",
    icon: Users,
  },
  {
    title: "使用指南",
    path: "/",
    description: "了解五步研究流程与数据准备",
    group: "设置",
    icon: CircleHelp,
  },
];
export const workspaces = [
  { title: "首页", path: "/app", icon: LayoutDashboard },
  { title: "策略研究", path: "/app/strategies", icon: FlaskConical },
  { title: "我的研究", path: "/app/research/records", icon: FolderClock },
  { title: "数据与运行", path: "/app/operations", icon: Database },
  { title: "设置", path: "/app/settings", icon: Settings2 },
];
export function currentTool(path: string) {
  return tools
    .filter(
      (tool) =>
        path === tool.path ||
        (tool.path !== "/" && path.startsWith(tool.path + "/")),
    )
    .sort((a, b) => b.path.length - a.path.length)[0];
}
