/**
 * Pinia 全局状态：仪表盘所有数据都集中在这里。
 * 数据来源由 services/dashboardService.js 推送进来（WebSocket 优先，HTTP 轮询兜底）。
 */
import { defineStore } from 'pinia'

// 六个核心模块的静态定义（key、名称、颜色、在 Mesh 图中的说明）
export const MODULES = [
  { key: 'strategy', name: '策略引擎', color: '#3b82f6', desc: '策略加载、信号计算与指令生成' },
  { key: 'data', name: '数据服务', color: '#22c55e', desc: '行情/因子数据清洗与分发' },
  { key: 'execution', name: '执行模块', color: '#f97316', desc: '订单路由与算法执行' },
  { key: 'risk', name: '风控模块', color: '#ef4444', desc: '实时风控检查与限额拦截' },
  { key: 'market', name: '行情网关', color: '#a855f7', desc: '交易所行情接入与推送' },
  { key: 'order', name: '订单管理', color: '#06b6d4', desc: '订单生命周期与成交回报' },
]

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    // ---- 顶部五个统计数字 ----
    overview: {
      active_strategies: 0,
      running_instances: 0,
      data_links: 0,
      pending_orders: 0,
      today_trades: 0,
    },
    // ---- 实时性能指标 ----
    performance: {
      process_rate: 0,
      throughput: 0,
      avg_latency: 0,
      pending_orders_count: 0,
    },
    // ---- 各模块负载 [{name, key, load, color}] ----
    moduleLoad: [],
    // ---- 吞吐/延迟历史 [{ts, throughput, latency}] ----
    history: [],
    // ---- 连接状态：'realtime' | 'polling' | 'disconnected' ----
    connection: 'disconnected',
    // ---- 是否暂停更新（空格键切换）----
    paused: false,
    // ---- 当前选中查看详情的节点 key ----
    selectedModule: null,
  }),

  getters: {
    /** 按 key 取模块负载（找不到返回 0） */
    loadOf: (state) => (key) => {
      const m = state.moduleLoad.find((m) => m.key === key)
      return m ? m.load : 0
    },
    /** 最忙模块（负载最高） */
    busiestModule(state) {
      if (!state.moduleLoad.length) return null
      return state.moduleLoad.reduce((a, b) => (a.load >= b.load ? a : b))
    },
    /** 底部分析文案 */
    analysisLine() {
      const busiest = this.busiestModule
      if (!busiest) return '等待数据接入…'
      if (busiest.load >= 90) {
        return `⚠ 检测到潜在瓶颈：${busiest.name}（${busiest.load.toFixed(0)}%）持续高负载，建议扩容或限流。`
      }
      return `没有明显瓶颈，最忙的是 ${busiest.name}（${busiest.load.toFixed(0)}%）。`
    },
  },

  actions: {
    /** 由 service 层调用：把一份完整快照写入 store */
    applySnapshot(snapshot) {
      if (this.paused) return // 暂停时丢弃更新
      this.overview = snapshot.overview
      this.performance = snapshot.performance
      this.moduleLoad = snapshot.module_load
      // 保留最近 120 个点，避免无限增长
      this.history = snapshot.history.slice(-120)
    },
    setConnection(status) {
      this.connection = status
    },
    togglePaused() {
      this.paused = !this.paused
    },
    selectModule(key) {
      this.selectedModule = this.selectedModule === key ? null : key
    },
  },
})
