<script setup>
// 功能台首页：问候和数据状态、市场概况（指数和全市场涨跌分布）、我的股票池、新手任务、
// 最近的研究、今天的行业涨跌、数据日历，以及可以收起的快速回测。
// 数字都来自本地数据和这个账户自己的记录，一个请求拿到（/api/v1/home）。只列数据，不推荐股票。
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { getBacktestCatalog, submitBacktest, workspaceHome } from '../../api.js'
import { openResearch } from '../researchNavigation.js'
import {
  KIND_TONES, amountText, breadthShares, dailyText, greeting, industryQuestion, price, seasonShare, seasonText,
  signedPct, sortPool, stepsProgress, todayText, tone, whenText,
} from '../homePresentation.js'
import Sparkline from '../ui/Sparkline.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const home = ref(null)
const loading = ref(true)
const error = ref('')
async function load() {
  error.value = ''
  try { home.value = await workspaceHome() } catch (e) { error.value = e.message || '首页数据加载失败' }
  finally { loading.value = false }
}
onMounted(load)
onActivated(() => { if (home.value) load() })   // 从别的页面回来时刷新一下（例如刚跑完回测）

function go(view, context = {}) { openResearch(view, context) }
function openChat(detail = {}) { window.dispatchEvent(new CustomEvent('fq-open-chat', { detail })) }
function openRecent(item) {
  if (item.kind === 'chat') openChat({ chat: item.context.chat })
  else go(item.view, item.context)
}

const now = new Date()
const shares = computed(() => breadthShares(home.value?.breadth))
const progress = computed(() => stepsProgress(home.value?.steps))
const aiReady = computed(() => home.value?.ai?.available === true)

// ---------- 我的股票池 ----------
const poolSort = reactive({ key: '', descending: true })
const poolRows = computed(() => sortPool(home.value?.pool, poolSort.key, poolSort.descending))
function sortBy(key) {
  if (poolSort.key === key) poolSort.descending = !poolSort.descending
  else Object.assign(poolSort, { key, descending: true })
}
const sortMark = (key) => (poolSort.key !== key ? '' : poolSort.descending ? ' ↓' : ' ↑')

// ---------- 快速回测（默认收起） ----------
const quickOpen = ref(false)
const bt = reactive({ strategy: '', market: '当前股票池', from: '2025-01-01', to: '2026-01-01', running: false })
const btStrategies = ref([])
const btResult = ref(null)
const btError = ref('')
let catalogLoaded = false
async function openQuick() {
  quickOpen.value = !quickOpen.value
  if (!quickOpen.value || catalogLoaded) return
  try {
    const catalog = await getBacktestCatalog()
    btStrategies.value = catalog.items
    bt.strategy = catalog.default
    catalogLoaded = true
  } catch (e) { props.notify(e.message || '加载策略目录失败') }
}
const equityPath = computed(() => {
  const arr = btResult.value?.equity || []
  if (!arr.length) return ''
  const w = 100, h = 40
  const max = Math.max(...arr), min = Math.min(...arr)
  const span = max - min || 1
  const step = w / (arr.length - 1)
  return arr.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(h - ((v - min) / span) * h).toFixed(1)}`).join(' ')
})
async function runBacktest() {
  bt.running = true
  btError.value = ''
  btResult.value = null
  try {
    const data = await submitBacktest({ strategy: bt.strategy, market: bt.market, from_date: bt.from, to_date: bt.to })
    btResult.value = data.result
    load()
  } catch (e) {
    btError.value = e.message || '回测失败'
  } finally {
    bt.running = false
  }
}

const card = 'glass rounded-2xl p-5'
const link = 'text-xs text-indigo-300 hover:text-indigo-200'
</script>

<template>
  <div class="space-y-6">
    <!-- 问候和数据状态 -->
    <section class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <div class="relative flex flex-wrap items-end justify-between gap-5">
        <div class="min-w-0">
          <p class="text-sm text-slate-400">{{ todayText(now) }}</p>
          <p class="mt-1 text-2xl font-bold text-white">{{ greeting(now) }}，{{ user?.name }}</p>
          <p class="mt-2 text-sm text-slate-400">{{ home ? dailyText(home.daily) : '正在读取数据…' }}</p>
          <p v-if="home && !aiReady" class="mt-1 text-xs text-amber-200">平台还没有配置 AI 模型，AI 解读和 AI 问答暂时不能用{{ user?.is_admin ? '；可以在管理后台的“系统设置”里配置' : '' }}。</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:-translate-y-0.5" @click="go('backtest-review')">新建回测</button>
          <button type="button" class="rounded-full border border-white/10 bg-white/5 px-5 py-2.5 text-sm text-slate-200 transition hover:bg-white/10" @click="go('agent-lab')">分析一只股票</button>
          <button type="button" class="rounded-full border border-white/10 bg-white/5 px-5 py-2.5 text-sm text-slate-200 transition hover:bg-white/10" @click="openChat()">问 AI</button>
        </div>
      </div>
    </section>

    <p v-if="error" role="alert" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{{ error }} <button type="button" class="underline" @click="load">重试</button></p>
    <p v-else-if="loading" class="text-sm text-slate-400" role="status">正在读取首页的数据…</p>

    <template v-if="home">
      <!-- 市场概况 -->
      <section aria-label="市场概况" class="space-y-3">
        <div class="flex flex-wrap items-baseline gap-2">
          <h2 class="text-sm font-semibold text-white">市场概况</h2>
          <span v-if="home.breadth" class="text-xs text-slate-500">{{ home.breadth.day }} 收盘</span>
        </div>
        <div class="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
          <button v-for="index in home.indexes" :key="index.symbol" type="button" class="glass glass-sheen rounded-2xl p-4 text-left transition hover:-translate-y-0.5"
            @click="go('market-chart')">
            <div class="flex items-baseline justify-between gap-2">
              <p class="text-xs text-slate-400">{{ index.name }}</p>
              <p class="text-xs font-semibold" :class="tone(index.change)">{{ signedPct(index.change) }}</p>
            </div>
            <p class="mt-1 text-lg font-bold text-white sm:text-xl">{{ price(index.close) }}</p>
            <Sparkline class="mt-2" :series="index.series" :rising="(index.series.at(-1) ?? 0) >= (index.series[0] ?? 0)" />
            <p class="mt-1 text-[10px] text-slate-500">近 {{ index.series.length }} 个交易日</p>
          </button>
          <p v-if="!home.indexes.length" class="col-span-2 text-sm text-slate-500 xl:col-span-4">本地还没有指数行情，管理员更新数据后就能看到。</p>
        </div>
        <div v-if="home.breadth && shares" :class="card">
          <div class="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <span class="text-rose-300">上涨 {{ home.breadth.up.toLocaleString() }} 只</span>
            <span class="text-slate-400">平盘 {{ home.breadth.flat.toLocaleString() }} 只</span>
            <span class="text-emerald-300">下跌 {{ home.breadth.down.toLocaleString() }} 只</span>
            <span class="text-slate-300">涨停 <b class="text-rose-300">{{ home.breadth.limit_up }}</b> · 跌停 <b class="text-emerald-300">{{ home.breadth.limit_down }}</b></span>
            <span class="text-slate-300">成交额 {{ amountText(home.breadth.amount) }}</span>
            <span v-if="home.breadth.suspended" class="text-xs text-slate-500">停牌 {{ home.breadth.suspended }} 只</span>
          </div>
          <div class="mt-3 flex h-2.5 overflow-hidden rounded-full bg-white/10" role="img" :aria-label="`上涨 ${shares.up}%，平盘 ${shares.flat}%，下跌 ${shares.down}%`">
            <div class="bg-rose-400/80" :style="{ width: `${shares.up}%` }" />
            <div class="bg-slate-400/50" :style="{ width: `${shares.flat}%` }" />
            <div class="bg-emerald-400/80" :style="{ width: `${shares.down}%` }" />
          </div>
          <p class="mt-2 text-[11px] text-slate-500">按交易所的昨收计算当天涨跌；停牌的股票不计入。</p>
        </div>
      </section>

      <!-- 同一行左右两边一样高：右边一列里最后一张卡片撑满剩下的高度，底边对齐 -->
      <div class="grid gap-6 lg:grid-cols-3">
        <!-- 我的股票池 -->
        <section :class="card" class="min-w-0 lg:col-span-2" aria-label="我的股票池">
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="text-sm font-semibold text-white">我的股票池</h2>
            <span class="text-xs text-slate-500">{{ home.pool.length }} 只</span>
            <button type="button" class="ml-auto" :class="link" @click="go('universe')">管理股票池 →</button>
          </div>
          <p v-if="!home.pool.length" class="mt-4 text-sm text-slate-400">股票池是空的。<button type="button" :class="link" @click="go('universe')">去添加股票</button>，回测和因子研究会用到它。</p>
          <!-- 全部直接显示；股票很多时在卡片里滚动，不把页面拉得太长 -->
          <div v-else class="mt-3 max-h-[36rem] overflow-auto">
            <table class="w-full min-w-[480px] text-left text-sm">
              <thead class="text-xs text-slate-500">
                <tr>
                  <th class="pb-2 pr-3 font-medium">股票</th>
                  <th class="pb-2 pr-3 text-right font-medium">最新价</th>
                  <th class="pb-2 pr-3 text-right font-medium"><button type="button" class="hover:text-slate-200" @click="sortBy('change')">当日{{ sortMark('change') }}</button></th>
                  <th class="pb-2 text-right font-medium"><button type="button" class="hover:text-slate-200" @click="sortBy('ret_20d')">近 20 日{{ sortMark('ret_20d') }}</button></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-white/5">
                <tr v-for="row in poolRows" :key="row.symbol" class="cursor-pointer hover:bg-white/5" @click="go('market-lookup', { symbol: row.symbol })">
                  <td class="py-2 pr-3"><span class="text-slate-200">{{ row.name }}</span> <span class="text-xs text-slate-500">{{ row.symbol }}</span>
                    <span v-if="row.st" class="ml-1 text-[10px] text-amber-300">ST</span><span v-if="row.suspended" class="ml-1 text-[10px] text-slate-500">停牌</span></td>
                  <td class="py-2 pr-3 text-right text-slate-200">{{ row.missing ? '没有最新行情' : price(row.close) }}</td>
                  <td class="py-2 pr-3 text-right" :class="tone(row.change)">{{ signedPct(row.change) }}</td>
                  <td class="py-2 text-right" :class="tone(row.ret_20d)">{{ signedPct(row.ret_20d) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- 新手任务 / 我的研究 + 数据日历 -->
        <div class="flex min-w-0 flex-col gap-6">
          <section v-if="!progress.finished" :class="card" aria-label="新手任务">
            <div class="flex items-baseline justify-between">
              <h2 class="text-sm font-semibold text-white">开始使用</h2>
              <span class="text-xs text-slate-400">已完成 {{ progress.done }}/{{ progress.total }}</span>
            </div>
            <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10"><div class="h-full rounded-full bg-indigo-400" :style="{ width: `${(progress.done / progress.total) * 100}%` }" /></div>
            <ol class="mt-4 space-y-2">
              <li v-for="(step, i) in home.steps" :key="step.key">
                <button type="button" class="flex w-full items-center gap-3 rounded-xl px-2 py-1.5 text-left text-sm transition hover:bg-white/5" @click="go(step.view)">
                  <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px]"
                    :class="step.done ? 'border-emerald-400/60 bg-emerald-500/20 text-emerald-200' : 'border-white/20 text-slate-400'">{{ step.done ? '✓' : i + 1 }}</span>
                  <span :class="step.done ? 'text-slate-500 line-through' : 'text-slate-200'">{{ step.label }}</span>
                  <span v-if="progress.next?.key === step.key" class="ml-auto text-xs text-indigo-300">去做 →</span>
                </button>
              </li>
            </ol>
          </section>
          <section v-else :class="card" aria-label="我的研究">
            <h2 class="text-sm font-semibold text-white">我的研究</h2>
            <dl class="mt-3 grid grid-cols-2 gap-3 text-sm">
              <button v-for="item in [['strategies', '保存的策略', 'strategy-hub'], ['backtests', '完成的回测', 'run-library'], ['briefs', 'AI 研究员分析', 'agent-lab'], ['chats', 'AI 问答对话', '']]"
                :key="item[0]" type="button" class="rounded-xl border border-white/10 bg-white/5 p-3 text-left hover:bg-white/10" @click="item[2] ? go(item[2]) : openChat()">
                <dt class="text-xs text-slate-400">{{ item[1] }}</dt><dd class="mt-1 text-lg font-bold text-white">{{ home.counts[item[0]] }}</dd>
              </button>
            </dl>
          </section>

          <section :class="card" class="flex flex-1 flex-col" aria-label="数据日历">
            <h2 class="text-sm font-semibold text-white">数据日历</h2>
            <p class="mt-3 text-sm text-slate-300">{{ dailyText(home.daily) }}</p>
            <div v-for="season in home.report_seasons" :key="season.period" class="mt-3">
              <p class="text-sm text-slate-300">{{ seasonText(season) }}</p>
              <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10" aria-hidden="true"><div class="h-full rounded-full bg-violet-400" :style="{ width: `${seasonShare(season)}%` }" /></div>
              <p class="mt-1 text-[11px] text-slate-500">平台在财报季定期下载新公布的财报</p>
            </div>
            <p v-if="!home.report_seasons.length" class="mt-2 text-xs text-slate-500">现在不是财报集中公布的时候。</p>
            <button type="button" class="mt-auto self-start pt-3" :class="link" @click="go('data-guide')">看平台有哪些数据 →</button>
          </section>
        </div>
      </div>

      <div class="grid gap-6 lg:grid-cols-3">
        <!-- 最近的研究 -->
        <section :class="card" class="min-w-0 lg:col-span-2" aria-label="最近的研究">
          <div class="flex items-center gap-3">
            <h2 class="text-sm font-semibold text-white">最近的研究</h2>
            <button type="button" class="ml-auto" :class="link" @click="go('run-library')">全部研究记录 →</button>
          </div>
          <p v-if="!home.recent.length" class="mt-4 text-sm text-slate-400">还没有研究记录。可以先<button type="button" :class="link" @click="go('backtest-review')">跑一次回测</button>，或者<button type="button" :class="link" @click="go('agent-lab')">分析一只股票</button>。</p>
          <ul v-else class="mt-3 divide-y divide-white/5">
            <li v-for="item in home.recent" :key="item.kind + item.at">
              <button type="button" class="flex w-full items-center gap-3 py-2.5 text-left transition hover:bg-white/5" @click="openRecent(item)">
                <span class="shrink-0 rounded-full px-2 py-0.5 text-[11px]" :class="KIND_TONES[item.kind]">{{ item.label }}</span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-sm text-slate-200">{{ item.title }}</span>
                  <span v-if="item.detail" class="block truncate text-xs" :class="item.value != null ? tone(item.value) : 'text-slate-500'">{{ item.detail }}</span>
                </span>
                <span class="shrink-0 text-xs text-slate-500">{{ whenText(item.at, now) }}</span>
              </button>
            </li>
          </ul>
        </section>

        <!-- 今天的行业涨跌 -->
        <section v-if="home.industries" :class="card" class="min-w-0" aria-label="今天的行业涨跌">
          <div class="flex items-baseline justify-between">
            <h2 class="text-sm font-semibold text-white">今天的行业涨跌</h2>
            <span class="text-xs text-slate-500">{{ home.industries.day }}</span>
          </div>
          <div v-for="part in [['up', '涨得多'], ['down', '跌得多']]" :key="part[0]" class="mt-3">
            <p class="text-xs text-slate-400">{{ part[1] }}</p>
            <ul class="mt-1.5 space-y-1">
              <li v-for="row in home.industries[part[0]]" :key="row.name">
                <button type="button" class="flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left text-sm hover:bg-white/5" :disabled="!aiReady"
                  @click="openChat({ question: industryQuestion(row.name) })">
                  <span class="min-w-0 flex-1 truncate text-slate-300">{{ row.name }}</span>
                  <span class="shrink-0 text-[11px] text-slate-500">{{ row.up }}/{{ row.count }} 涨</span>
                  <span class="w-16 shrink-0 text-right" :class="tone(row.change)">{{ signedPct(row.change) }}</span>
                </button>
              </li>
            </ul>
          </div>
          <p class="mt-3 text-[11px] text-slate-500">证监会行业分类，行业里股票当天涨跌的平均数（不含 ST 和停牌）。{{ aiReady ? '点一个行业，在 AI 问答里问它的估值和财务。' : '' }}只是数据，不代表买卖建议。</p>
        </section>
      </div>
    </template>

    <!-- 快速回测：默认收起 -->
    <section :class="card" aria-label="快速回测">
      <button type="button" class="flex w-full items-center gap-3 text-left" :aria-expanded="quickOpen" @click="openQuick">
        <h2 class="text-sm font-semibold text-white">快速回测</h2>
        <span class="text-xs text-slate-400">初始资金 100 万，最多 10 只，每周调仓；更多设置请进入回测与验证</span>
        <span class="ml-auto text-xs text-indigo-300">{{ quickOpen ? '收起' : '展开' }}</span>
      </button>
      <template v-if="quickOpen">
        <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">策略</span>
            <select v-model="bt.strategy" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white"><option v-for="s in btStrategies" :key="s.value" :value="s.value" class="bg-ink">{{ s.label }}</option></select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">市场</span>
            <select v-model="bt.market" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
              <option value="当前股票池" class="bg-ink">当前 A 股股票池</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">开始</span>
            <input v-model="bt.from" type="date" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs text-slate-400">结束</span>
            <input v-model="bt.to" type="date" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          </label>
          <div class="flex items-end">
            <button @click="runBacktest" :disabled="bt.running" class="w-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70">
              {{ bt.running ? '回测中…' : '开始回测' }}
            </button>
          </div>
        </div>
        <p v-if="btError" class="mt-4 text-sm text-rose-300">{{ btError }}</p>
        <div v-if="btResult" class="mt-6 grid gap-5 md:grid-cols-5">
          <div class="md:col-span-3">
            <div class="flex items-center justify-between text-xs text-slate-400">
              <span>资金曲线</span>
              <span :class="tone(btResult.total_return)">总收益 {{ btResult.total_return }}%</span>
            </div>
            <svg viewBox="0 0 100 40" class="mt-2 h-32 w-full" preserveAspectRatio="none">
              <defs>
                <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#6366f1" stop-opacity="0.35" />
                  <stop offset="100%" stop-color="#6366f1" stop-opacity="0" />
                </linearGradient>
              </defs>
              <path :d="`${equityPath} L100,40 L0,40 Z`" fill="url(#eq)" />
              <path :d="equityPath" fill="none" stroke="#818cf8" stroke-width="0.8" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </div>
          <div class="grid grid-cols-2 gap-3 md:col-span-2">
            <div class="rounded-xl border border-white/10 bg-white/5 p-4"><p class="text-xs text-slate-400">总收益</p><p class="mt-1 text-lg font-bold" :class="tone(btResult.total_return)">{{ btResult.total_return }}%</p></div>
            <div class="rounded-xl border border-white/10 bg-white/5 p-4"><p class="text-xs text-slate-400">最大回撤</p><p class="mt-1 text-lg font-bold text-white">{{ btResult.max_drawdown }}%</p></div>
            <div class="rounded-xl border border-white/10 bg-white/5 p-4"><p class="text-xs text-slate-400">夏普比率</p><p class="mt-1 text-lg font-bold text-white">{{ btResult.sharpe }}</p></div>
            <div class="rounded-xl border border-white/10 bg-white/5 p-4"><p class="text-xs text-slate-400">胜率</p><p class="mt-1 text-lg font-bold text-white">{{ btResult.win_rate }}%</p></div>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>
