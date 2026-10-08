import { defineAsyncComponent } from 'vue'

// 首页为默认入口
export const overviewKey = 'overview'

// 沿用 AlphaQuant 的用户旅程，保留 v4 的所有模块入口。
export const groups = [
  { label: 'AI 智能投研', items: [
    { key: 'agent-lab', label: 'AI研究员' },
    { key: 'prior-knowledge', label: '先验知识库' },
    { key: 'knowledge-base', label: '知识库问答 · WeKnora' },
    { key: 'decision-center', label: 'AI 决策中心 · Jev' },
  ] },
  { label: '策略研究', items: [
    { key: 'strategy-hub', label: '策略工作室', children: [
      { key: 'strategy-hub', label: '策略管理' },
      { key: 'strategy-studio', label: '模板与积木' },
      { key: 'nl-strategy', label: '自然语言' },
      { key: 'custom-strategy', label: 'Python 策略' },
    ] },
    { key: 'factor-lab', label: '因子实验室' },
    { key: 'backtest-review', label: '回测与验证', children: [
      { key: 'backtest-review', label: '单次回测' },
      { key: 'research', label: '参数优化' },
      { key: 'audit-report', label: '可信度审计' },
      { key: 'strategy-forensics', label: '成交核查' },
    ] },
    { key: 'run-library', label: '研究记录' },
  ] },
  { label: '数据管理', items: [
    { key: 'data-management', label: '数据资产' },
    { key: 'data-update', label: '数据更新' },
    { key: 'xtick-data', label: 'XTick 数据服务' },
    { key: 'risk-management', label: '风险管理' },
    { key: 'universe', label: '股票池管理' },
  ] },
  { label: '系统', items: [
    { key: 'account', label: '个人中心' },
    { key: 'settings', label: '设置' },
  ] },
]

// 完整路由注册表保留页内入口，兼容官网、新手引导及已有直达链接。
export const allItems = [{ key: overviewKey, label: '首页' }, ...groups.flatMap((g) =>
  g.items.flatMap((item) => item.children || [item]))]

export function navigationItem(key) {
  return groups.flatMap((group) => group.items).find((item) =>
    item.key === key || item.children?.some((child) => child.key === key))
}

export function itemLabel(key) {
  const found = allItems.find((i) => i.key === key)
  return found ? found.label : key
}

export const views = {
  [overviewKey]: defineAsyncComponent(() => import('./views/OverviewView.vue')),
  'strategy-hub': defineAsyncComponent(() => import('./views/StrategyHubView.vue')),
  'nl-strategy': defineAsyncComponent(() => import('./views/NlStrategyView.vue')),
  'strategy-studio': defineAsyncComponent(() => import('./views/StrategyStudioView.vue')),
  'custom-strategy': defineAsyncComponent(() => import('./views/CustomStrategyView.vue')),
  'factor-lab': defineAsyncComponent(() => import('./views/FactorLabView.vue')),
  'agent-lab': defineAsyncComponent(() => import('./views/AgentLabView.vue')),
  'decision-center': defineAsyncComponent(() => import('./views/DecisionCenterView.vue')),
  'knowledge-base': defineAsyncComponent(() => import('./views/KnowledgeBaseView.vue')),
  'backtest-review': defineAsyncComponent(() => import('./views/BacktestReviewView.vue')),
  'audit-report': defineAsyncComponent(() => import('./views/AuditReportView.vue')),
  'strategy-forensics': defineAsyncComponent(() => import('./views/StrategyForensicsView.vue')),
  research: defineAsyncComponent(() => import('./views/ResearchView.vue')),
  'run-library': defineAsyncComponent(() => import('./views/RunLibraryView.vue')),
  'data-update': defineAsyncComponent(() => import('./views/DataUpdateView.vue')),
  'data-management': defineAsyncComponent(() => import('./views/DataManagementView.vue')),
  'xtick-data': defineAsyncComponent(() => import('./views/XtickDataView.vue')),
  'risk-management': defineAsyncComponent(() => import('./views/RiskManagementView.vue')),
  universe: defineAsyncComponent(() => import('./views/UniverseView.vue')),
  'prior-knowledge': defineAsyncComponent(() => import('./views/PriorKnowledgeView.vue')),
  settings: defineAsyncComponent(() => import('./views/SettingsView.vue')),
  account: defineAsyncComponent(() => import('./views/AccountView.vue')),
}
