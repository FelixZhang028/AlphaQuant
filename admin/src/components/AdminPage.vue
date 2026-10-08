<script setup>
import { computed, onMounted, ref } from 'vue'
import { adminStats, adminUsers } from '../api.js'

const emit = defineEmits(['logout'])
const sidebarOpen = ref(false)
const activeNav = ref('概览')
const nav = [
  { k: '概览', i: 'M3 12l9-9 9 9M5 10v10h14V10' },
  { k: '策略管理', i: 'M4 6h16M4 12h16M4 18h10' },
  { k: '用户管理', i: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' },
  { k: '订单管理', i: 'M3 3h18v4H3zM3 11h18v4H3zM3 19h18v4H3z' },
  { k: '风控中心', i: 'M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-4z' },
  { k: '数据源', i: 'M4 4h16v16H4zM4 9h16M9 4v16' },
  { k: '系统设置', i: 'M10.5 13.5L4 20m6.5-6.5L20 4M10.5 13.5L4 20' },
]

// 真实监控数据
const overview = ref(null)
const performance = ref(null)
const users = ref([])
const dataError = ref('')

const kpis = computed(() => {
  const o = overview.value
  if (!o) return []
  return [
    { label: '活跃策略', value: o.active_strategies.toLocaleString(), sub: '在编策略总数', up: true },
    { label: '运行实例', value: o.running_instances.toLocaleString(), sub: '正在执行', up: true },
    { label: '数据链路', value: o.data_links.toLocaleString(), sub: '行情/交易连接', up: true },
    { label: '今日成交', value: o.today_trades.toLocaleString(), sub: '累计成交订单', up: true },
  ]
})

const perf = computed(() => {
  const p = performance.value
  if (!p) return []
  return [
    { label: '处理速率', value: p.process_rate.toFixed(1), unit: '笔/秒' },
    { label: '吞吐量', value: p.throughput.toFixed(1), unit: '笔/秒' },
    { label: '平均延迟', value: p.avg_latency.toFixed(1), unit: '毫秒' },
    { label: '挂起订单', value: p.pending_orders_count.toLocaleString(), unit: '笔' },
  ]
})

onMounted(async () => {
  try {
    const stats = await adminStats()
    overview.value = stats.overview
    performance.value = stats.performance
  } catch (e) {
    dataError.value = e.message || '监控数据加载失败'
  }
  try {
    users.value = await adminUsers()
  } catch {
    /* 用户列表加载失败不阻塞 */
  }
})

// 装饰数据（图表/地图/动态，后续可替换为真实接口）
const cities = [
  { x: 22, y: 38, n: '纽约', v: '¥3.2M' },
  { x: 47, y: 30, n: '伦敦', v: '¥2.8M' },
  { x: 64, y: 34, n: '迪拜', v: '¥1.4M' },
  { x: 55, y: 46, n: '上海', v: '¥5.6M' },
  { x: 71, y: 50, n: '香港', v: '¥2.1M' },
  { x: 80, y: 60, n: '新加坡', v: '¥1.8M' },
  { x: 30, y: 70, n: '圣保罗', v: '¥0.9M' },
]

const sources = [
  { label: '趋势跟随', pct: 41.2, c: '#6366f1' },
  { label: '套利', pct: 24.8, c: '#38bdf8' },
  { label: '做市', pct: 16.3, c: '#8b5cf6' },
  { label: '高频', pct: 11.4, c: '#2dd4bf' },
  { label: '其他', pct: 6.3, c: '#f59e0b' },
]
const R = 54
const C = 2 * Math.PI * R
let acc = 0
const segs = sources.map((s) => {
  const start = acc
  acc += s.pct
  return { ...s, dash: `${(s.pct / 100) * C} ${C}`, offset: -(start / 100) * C }
})

const ranges = { '30天': [3.2, 4.1, 3.8, 5.2, 4.6, 6.1, 5.4, 7.2, 6.8, 8.4, 7.9, 9.6], '90天': [8, 9, 7.5, 10, 11, 9.5, 12, 13, 11, 14, 13.5, 16], '12月': [22, 19, 26, 24, 30, 28, 34, 31, 38, 36, 42, 45] }
const range = ref('30天')
const bars = computed(() => {
  const arr = ranges[range.value]
  const max = Math.max(...arr)
  return arr.map((v) => ({ v, h: (v / max) * 100 }))
})
const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

const orderFilter = ref('全部')
const orders = [
  { id: 'QT-7420', user: '林安然', market: '沪深300', date: '2026-08-15', status: '挂单', total: '¥1,155' },
  { id: 'QT-7419', user: '陈若溪', market: 'ETH/USDT', date: '2026-08-15', status: '已成交', total: '¥1,750' },
  { id: 'QT-7418', user: '许思齐', market: '标普500', date: '2026-08-15', status: '挂单', total: '¥285' },
  { id: 'QT-7417', user: '宋承宇', market: '黄金期货', date: '2026-08-15', status: '已成交', total: '¥360' },
  { id: 'QT-7416', user: '谢书宁', market: '原油期货', date: '2026-08-15', status: '已撤', total: '¥1,835' },
  { id: 'QT-7415', user: '顾景行', market: '中证500', date: '2026-08-15', status: '已成交', total: '¥980' },
  { id: 'QT-7414', user: '唐清和', market: 'BTC/USDT', date: '2026-08-15', status: '挂单', total: '¥505' },
  { id: 'QT-7413', user: '谢书宁', market: '纳指100', date: '2026-08-14', status: '已成交', total: '¥940' },
]
const filteredOrders = computed(() =>
  orderFilter.value === '全部' ? orders : orders.filter((o) => o.status === orderFilter.value)
)
const statusClass = {
  已成交: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/30',
  挂单: 'text-amber-300 bg-amber-400/10 border-amber-400/30',
  已撤: 'text-rose-300 bg-rose-400/10 border-rose-400/30',
}

const feed = [
  { t: '策略停止', d: 'AlphaSeeker · 用户 林安然', time: '11 分钟', c: 'text-amber-300' },
  { t: '提现到账', d: '支付平台 · ¥18,430 至 ····4417', time: '1 小时', c: 'text-emerald-300' },
  { t: '风控触发', d: '回撤超限 · 自动平仓 ETH 合约', time: '2 小时', c: 'text-rose-300' },
  { t: '新增机构席位', d: '隼影资本 · 240 席位', time: '3 小时', c: 'text-indigo-300' },
  { t: '保证金不足', d: '原油期货 · 请追加保证金', time: '5 小时', c: 'text-amber-300' },
  { t: '套餐升级', d: '诺瓦工作室 → 专业版', time: '6 小时', c: 'text-sky-300' },
  { t: '行情重连', d: '数据源 orders.ticker · 重试 3 次', time: '8 小时', c: 'text-slate-300' },
]
</script>

<template>
  <div class="mx-auto flex max-w-[1600px]">
    <aside
      :class="[
        'fixed inset-y-0 left-0 z-40 w-60 transform border-r border-white/10 bg-ink/70 p-5 backdrop-blur-xl transition-transform duration-300 lg:static lg:translate-x-0',
        sidebarOpen ? 'translate-x-0' : '-translate-x-full',
      ]"
    >
      <a href="/" class="flex items-center gap-2.5">
        <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-base font-bold text-white shadow-lg shadow-indigo-500/40">智</span>
        <div class="leading-tight">
          <p class="text-sm font-semibold text-white">智投引擎</p>
          <p class="text-[10px] text-slate-500">管理后台</p>
        </div>
      </a>

      <nav class="mt-8 space-y-1">
        <button
          v-for="n in nav"
          :key="n.k"
          @click="activeNav = n.k"
          class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition"
          :class="activeNav === n.k ? 'bg-gradient-to-r from-indigo-500/25 to-violet-500/15 text-white ring-1 ring-inset ring-white/10' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'"
        >
          <svg class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
            <path stroke-linecap="round" stroke-linejoin="round" :d="n.i" />
          </svg>
          {{ n.k }}
        </button>
      </nav>

      <div class="absolute inset-x-5 bottom-5 rounded-xl border border-white/10 bg-white/5 p-3">
        <p class="text-xs text-slate-400">系统状态</p>
        <p class="mt-1 flex items-center gap-2 text-sm font-medium text-emerald-300">
          <span class="h-2 w-2 animate-pulse rounded-full bg-emerald-400" /> 运行正常
        </p>
      </div>
    </aside>

    <div class="min-w-0 flex-1">
      <header class="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-white/10 bg-ink/60 px-5 backdrop-blur-xl lg:px-8">
        <button class="rounded-lg p-2 text-slate-400 hover:bg-white/5 lg:hidden" @click="sidebarOpen = !sidebarOpen" aria-label="菜单">
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <h1 class="text-lg font-semibold text-white">{{ activeNav }}</h1>

        <div class="relative ml-auto hidden sm:block">
          <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7" /><path stroke-linecap="round" d="M21 21l-4-4" /></svg>
          <input placeholder="搜索订单、策略、用户…" class="w-64 rounded-full border border-white/10 bg-white/5 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-400/40 focus:ring-2 focus:ring-indigo-500/20" />
        </div>

        <button class="relative rounded-lg p-2 text-slate-400 hover:bg-white/5">
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2c0 .5-.2 1-.6 1.4L2 17h5m8 0a3 3 0 11-6 0" /></svg>
          <span class="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-rose-400" />
        </button>

        <div class="flex items-center gap-2.5 rounded-full border border-white/10 bg-white/5 py-1 pl-1 pr-3">
          <span class="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-xs font-bold text-white">管</span>
          <span class="hidden text-sm text-slate-300 sm:block">管理员</span>
        </div>
        <button @click="emit('logout')" class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 transition hover:border-white/25 hover:text-white">退出</button>
      </header>

      <main class="space-y-6 p-5 lg:p-8">
        <p v-if="dataError" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">监控数据连接失败：{{ dataError }}（其余为演示数据）</p>

        <!-- KPI（真实监控） -->
        <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="k in kpis" :key="k.label" class="glass glass-sheen rounded-2xl p-5">
            <p class="text-xs text-slate-400">{{ k.label }}</p>
            <p class="mt-2 text-3xl font-bold text-white">{{ k.value }}</p>
            <p class="mt-2 text-xs text-slate-500">{{ k.sub }}</p>
          </div>
        </section>

        <!-- 实时性能（真实监控） -->
        <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="p in perf" :key="p.label" class="glass rounded-2xl p-5">
            <p class="text-xs text-slate-400">{{ p.label }}</p>
            <p class="mt-2 text-2xl font-bold text-white">{{ p.value }} <span class="text-sm font-normal text-indigo-300">{{ p.unit }}</span></p>
          </div>
        </section>

        <!-- 用户管理（真实） -->
        <section class="glass rounded-2xl p-5">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-white">注册用户</h2>
            <span class="text-xs text-slate-500">共 {{ users.length }} 人</span>
          </div>
          <div class="mt-4 overflow-x-auto">
            <table class="w-full min-w-[560px] text-left text-sm">
              <thead>
                <tr class="text-xs text-slate-500">
                  <th class="pb-3 font-medium">ID</th>
                  <th class="pb-3 font-medium">用户名</th>
                  <th class="pb-3 font-medium">邮箱</th>
                  <th class="pb-3 font-medium">角色</th>
                  <th class="pb-3 font-medium">注册时间</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-white/5">
                <tr v-for="u in users" :key="u.id" class="text-slate-300 transition hover:bg-white/5">
                  <td class="py-3 font-mono text-xs text-indigo-300">{{ u.id }}</td>
                  <td class="py-3 font-medium text-white">{{ u.name }}</td>
                  <td class="py-3 text-slate-400">{{ u.email }}</td>
                  <td class="py-3">
                    <span class="rounded-full border px-2.5 py-0.5 text-xs" :class="u.is_admin ? 'border-violet-400/30 bg-violet-400/10 text-violet-300' : 'border-slate-400/20 bg-slate-400/10 text-slate-300'">{{ u.is_admin ? '管理员' : '用户' }}</span>
                  </td>
                  <td class="py-3 text-slate-400">{{ new Date(u.created_at).toLocaleString() }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- 全球成交 + 策略来源 -->
        <section class="grid gap-5 lg:grid-cols-3">
          <div class="glass rounded-2xl p-5 lg:col-span-2">
            <div class="flex items-center justify-between">
              <h2 class="text-sm font-semibold text-white">全球成交</h2>
              <span class="text-xs text-slate-500">点击城市筛选</span>
            </div>
            <div class="relative mt-4 aspect-[16/8] w-full overflow-hidden rounded-xl border border-white/5 bg-ink/40">
              <svg class="absolute inset-0 h-full w-full" viewBox="0 0 100 50" preserveAspectRatio="none">
                <defs>
                  <radialGradient id="glow" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stop-color="#6366f1" stop-opacity="0.18" />
                    <stop offset="100%" stop-color="#6366f1" stop-opacity="0" />
                  </radialGradient>
                </defs>
                <ellipse cx="50" cy="25" rx="48" ry="24" fill="url(#glow)" />
                <ellipse cx="50" cy="25" rx="48" ry="24" fill="none" stroke="rgba(148,163,184,0.12)" />
                <ellipse cx="50" cy="25" rx="32" ry="16" fill="none" stroke="rgba(148,163,184,0.1)" />
                <ellipse cx="50" cy="25" rx="16" ry="8" fill="none" stroke="rgba(148,163,184,0.08)" />
                <line v-for="y in [12,25,38]" :key="'h'+y" :x1="2" :y1="y" x2="98" :y2="y" stroke="rgba(148,163,184,0.07)" />
                <line v-for="x in [20,40,60,80]" :key="'v'+x" :x1="x" y1="1" :x2="x" y2="49" stroke="rgba(148,163,184,0.07)" />
              </svg>
              <button
                v-for="c in cities"
                :key="c.n"
                class="group absolute -translate-x-1/2 -translate-y-1/2"
                :style="{ left: c.x + '%', top: c.y + '%' }"
              >
                <span class="relative flex h-2.5 w-2.5">
                  <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-60" />
                  <span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-indigo-300 ring-2 ring-indigo-500/30" />
                </span>
                <span class="pointer-events-none absolute left-1/2 top-4 z-10 -translate-x-1/2 whitespace-nowrap rounded-md border border-white/10 bg-ink/90 px-2 py-1 text-[10px] text-slate-200 opacity-0 transition group-hover:opacity-100">
                  {{ c.n }} · {{ c.v }}
                </span>
              </button>
            </div>
          </div>

          <div class="glass rounded-2xl p-5">
            <h2 class="text-sm font-semibold text-white">策略来源</h2>
            <div class="relative mx-auto mt-3 h-40 w-40">
              <svg viewBox="0 0 140 140" class="h-full w-full -rotate-90">
                <circle cx="70" cy="70" :r="R" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="16" />
                <circle
                  v-for="s in segs"
                  :key="s.label"
                  cx="70" cy="70" :r="R" fill="none"
                  :stroke="s.c" stroke-width="16"
                  :stroke-dasharray="s.dash"
                  :stroke-dashoffset="s.offset"
                  stroke-linecap="butt"
                />
              </svg>
              <div class="absolute inset-0 flex flex-col items-center justify-center">
                <p class="text-2xl font-bold text-white">{{ overview ? overview.active_strategies : '—' }}</p>
                <p class="text-[10px] text-slate-500">活跃策略</p>
              </div>
            </div>
            <ul class="mt-4 space-y-2">
              <li v-for="s in sources" :key="s.label" class="flex items-center gap-2 text-xs">
                <span class="h-2 w-2 rounded-full" :style="{ background: s.c }" />
                <span class="text-slate-400">{{ s.label }}</span>
                <span class="ml-auto font-medium text-slate-200">{{ s.pct }}%</span>
              </li>
            </ul>
          </div>
        </section>

        <!-- 成交额趋势 + 动态 -->
        <section class="grid gap-5 lg:grid-cols-3">
          <div class="glass rounded-2xl p-5 lg:col-span-2">
            <div class="flex items-center justify-between">
              <h2 class="text-sm font-semibold text-white">成交额趋势</h2>
              <div class="flex rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
                <button
                  v-for="r in ['30天', '90天', '12月']"
                  :key="r"
                  @click="range = r"
                  class="rounded-full px-3 py-1 transition"
                  :class="range === r ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'"
                >{{ r }}</button>
              </div>
            </div>
            <div class="mt-6 flex h-52 items-end gap-2">
              <div v-for="(b, i) in bars" :key="i" class="group relative flex h-full flex-1 items-end justify-center">
                <div
                  class="w-full max-w-[26px] rounded-t-md bg-gradient-to-t from-indigo-600/60 to-violet-400/90 transition-all duration-500 ease-out-expo hover:from-indigo-500 hover:to-violet-300"
                  :style="{ height: b.h + '%' }"
                />
                <span class="pointer-events-none absolute -top-7 rounded bg-ink/90 px-1.5 py-0.5 text-[10px] text-slate-200 opacity-0 transition group-hover:opacity-100">{{ b.v }}M</span>
                <span class="absolute -bottom-6 text-[10px] text-slate-500">{{ months[i] }}</span>
              </div>
            </div>
          </div>

          <div class="glass rounded-2xl p-5">
            <h2 class="text-sm font-semibold text-white">系统动态</h2>
            <ul class="mt-4 space-y-4">
              <li v-for="(f, i) in feed" :key="i" class="relative pl-5">
                <span class="absolute left-0 top-1.5 h-2 w-2 rounded-full bg-indigo-400" />
                <span v-if="i < feed.length - 1" class="absolute left-[3px] top-3 h-[calc(100%-4px)] w-px bg-white/10" />
                <p class="text-sm font-medium text-white">{{ f.t }}</p>
                <p class="text-xs text-slate-400">{{ f.d }}</p>
                <p class="mt-0.5 text-[10px]" :class="f.c">{{ f.time }}</p>
              </li>
            </ul>
          </div>
        </section>

        <!-- 近期订单 -->
        <section class="glass rounded-2xl p-5">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <h2 class="text-sm font-semibold text-white">近期订单</h2>
            <div class="flex rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
              <button
                v-for="s in ['全部', '已成交', '挂单', '已撤']"
                :key="s"
                @click="orderFilter = s"
                class="rounded-full px-3 py-1 transition"
                :class="orderFilter === s ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'"
              >{{ s }}</button>
            </div>
          </div>

          <div class="mt-5 overflow-x-auto">
            <table class="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr class="text-xs text-slate-500">
                  <th class="pb-3 font-medium">订单</th>
                  <th class="pb-3 font-medium">客户</th>
                  <th class="pb-3 font-medium">市场</th>
                  <th class="pb-3 font-medium">日期</th>
                  <th class="pb-3 font-medium">状态</th>
                  <th class="pb-3 text-right font-medium">总额</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-white/5">
                <tr v-for="o in filteredOrders" :key="o.id" class="text-slate-300 transition hover:bg-white/5">
                  <td class="py-3 font-mono text-xs text-indigo-300">{{ o.id }}</td>
                  <td class="py-3">{{ o.user }}</td>
                  <td class="py-3 text-slate-400">{{ o.market }}</td>
                  <td class="py-3 text-slate-400">{{ o.date }}</td>
                  <td class="py-3">
                    <span class="rounded-full border px-2.5 py-0.5 text-xs" :class="statusClass[o.status]">{{ o.status }}</span>
                  </td>
                  <td class="py-3 text-right font-medium text-white">{{ o.total }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="mt-5 flex items-center justify-between text-xs text-slate-500">
            <span>1–{{ filteredOrders.length }} / 共 132</span>
            <div class="flex items-center gap-1">
              <button class="rounded-lg border border-white/10 px-2.5 py-1 hover:bg-white/5">‹</button>
              <button v-for="p in [1, 2, 3, '…', 16]" :key="p" class="rounded-lg px-2.5 py-1" :class="p === 1 ? 'bg-indigo-500/20 text-white ring-1 ring-inset ring-white/10' : 'border border-white/10 hover:bg-white/5'">{{ p }}</button>
              <button class="rounded-lg border border-white/10 px-2.5 py-1 hover:bg-white/5">›</button>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>

  <div v-if="sidebarOpen" class="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm lg:hidden" @click="sidebarOpen = false" />
</template>
