import { defineAsyncComponent } from 'vue'

// 首页为默认入口
export const overviewKey = 'overview'

// 沿用 AlphaQuant 的用户旅程，保留 v4 的所有模块入口。
export const groups = [
  { label: 'AI 智能投研', items: [
    { key: 'agent-lab', label: 'AI研究员' },
    { key: 'knowledge-base', label: '投研知识库' },
    { key: 'decision-center', label: '决策辅助' },
  ] },
  { label: '策略研究', items: [
    { key: 'strategy-hub', label: '我的策略' },
    { key: 'factor-lab', label: '因子研究' },
    { key: 'backtest-review', label: '回测与验证', children: [
      { key: 'backtest-review', label: '策略回测' },
      { key: 'research', label: '参数优化' },
      { key: 'walk-forward', label: '样本外验证' },
    ] },
    { key: 'run-library', label: '研究记录' },
  ] },
  { label: '数据管理', items: [
    { key: 'data-management', label: '数据概览' },
    { key: 'data-update', label: '数据更新' },
    { key: 'universe', label: '股票池管理' },
  ] },
  { label: '系统', items: [
    { key: 'account', label: '个人中心' },
    { key: 'settings', label: '设置' },
  ] },
]

// 完整路由注册表保留页内入口，兼容官网、新手引导及已有直达链接。
const utilityItems = [
  { key: 'prior-knowledge', label: '研究经验', parent: 'knowledge-base' },
  { key: 'xtick-data', label: 'XTick 数据服务', parent: 'data-management' },
  { key: 'strategy-studio', label: '模板与规则创建', parent: 'strategy-hub' },
  { key: 'nl-strategy', label: '自然语言创建', parent: 'strategy-hub' },
  { key: 'custom-strategy', label: 'Python 策略创建', parent: 'strategy-hub' },
  { key: 'audit-report', label: '可信度审计', parent: 'backtest-review' },
  { key: 'strategy-forensics', label: '成交核查', parent: 'backtest-review' },
  { key: 'risk-management', label: '风险管理', parent: 'backtest-review' },
]
export const allItems = [{ key: overviewKey, label: '首页' }, ...groups.flatMap((g) =>
  g.items.flatMap((item) => item.children || [item])), ...utilityItems]

export function navigationItem(key) {
  const parentKey = utilityItems.find((item) => item.key === key)?.parent || key
  return groups.flatMap((group) => group.items).find((item) =>
    item.key === parentKey || item.children?.some((child) => child.key === key))
}

export function itemLabel(key) {
  const found = allItems.find((i) => i.key === key)
  return found ? found.label : key
}

// 内容宽度与外壳独立：研究页为图表留空间，账户/设置保持紧凑。
const wideViews = new Set([
  'factor-lab', 'backtest-review', 'research', 'walk-forward', 'audit-report',
  'strategy-forensics', 'strategy-studio', 'run-library',
])
const compactViews = new Set(['account', 'settings'])

export function contentLayout(key) {
  if (compactViews.has(key)) return 'compact'
  return wideViews.has(key) ? 'wide' : 'standard'
}

const researchView = defineAsyncComponent(() => import('./views/ResearchView.vue'))
const investmentKnowledgeView = defineAsyncComponent(() => import('./views/InvestmentKnowledgeView.vue'))
export const views = {
  [overviewKey]: defineAsyncComponent(() => import('./views/OverviewView.vue')),
  'strategy-hub': defineAsyncComponent(() => import('./views/StrategyHubView.vue')),
  'nl-strategy': defineAsyncComponent(() => import('./views/NlStrategyView.vue')),
  'strategy-studio': defineAsyncComponent(() => import('./views/StrategyStudioView.vue')),
  'custom-strategy': defineAsyncComponent(() => import('./views/CustomStrategyView.vue')),
  'factor-lab': defineAsyncComponent(() => import('./views/FactorLabView.vue')),
  'agent-lab': defineAsyncComponent(() => import('./views/AgentLabView.vue')),
  'decision-center': defineAsyncComponent(() => import('./views/DecisionCenterView.vue')),
  'knowledge-base': investmentKnowledgeView,
  'backtest-review': defineAsyncComponent(() => import('./views/BacktestReviewView.vue')),
  'audit-report': defineAsyncComponent(() => import('./views/AuditReportView.vue')),
  'strategy-forensics': defineAsyncComponent(() => import('./views/StrategyForensicsView.vue')),
  research: researchView,
  'walk-forward': researchView,
  'run-library': defineAsyncComponent(() => import('./views/RunLibraryView.vue')),
  'data-update': defineAsyncComponent(() => import('./views/DataUpdateView.vue')),
  'data-management': defineAsyncComponent(() => import('./views/DataManagementView.vue')),
  'xtick-data': defineAsyncComponent(() => import('./views/XtickDataView.vue')),
  'risk-management': defineAsyncComponent(() => import('./views/RiskManagementView.vue')),
  universe: defineAsyncComponent(() => import('./views/UniverseView.vue')),
  'prior-knowledge': investmentKnowledgeView,
  settings: defineAsyncComponent(() => import('./views/SettingsView.vue')),
  account: defineAsyncComponent(() => import('./views/AccountView.vue')),
}
