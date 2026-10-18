<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { aiStatus, dailyUpdateStatus, getBacktestCatalog, listPackages, listRuns, submitBacktest } from '../../api.js'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// 首页的四个数字都来自这个账户和本地数据，没有示例数字。
const marketData = ref(null)
const packageCount = ref(null)
const runSummary = ref(null)
const ai = ref(null)

function navigate(key) {
  window.dispatchEvent(new CustomEvent('fq-navigate', { detail: key }))
}

// ---------- 回测 ----------
const bt = reactive({ strategy: '', market: '当前股票池', from: '2025-01-01', to: '2026-01-01', running: false })
const btStrategies = ref([])
const btResult = ref(null)
const btError = ref('')

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
    const data = await submitBacktest({
      strategy: bt.strategy,
      market: bt.market,
      from_date: bt.from,
      to_date: bt.to,
    })
    btResult.value = data.result
  } catch (e) {
    btError.value = e.message || '回测失败'
  } finally {
    bt.running = false
  }
}

// ---------- 概况 ----------
const count = (value) => (value == null ? '—' : Number(value).toLocaleString())
const kpis = computed(() => {
  const data = marketData.value
  const brief = ai.value?.usage?.brief
  return [
    {
      label: '行情数据', view: 'data-management',
      value: data ? data.latest_date || '还没有数据' : '—',
      sub: data?.latest_date ? `${count(data.stocks_on_latest)} 只股票已更新到这一天` : '本地最新的交易日',
    },
    { label: '我的策略', view: 'strategy-hub', value: count(packageCount.value), sub: '保存的规则策略' },
    {
      label: '研究记录', view: 'run-library', value: count(runSummary.value?.total),
      sub: runSummary.value ? `成功 ${count(runSummary.value.stats?.success ?? 0)} 次` : '回测与验证的记录',
    },
    {
      label: '今天的 AI 解读', view: 'agent-lab',
      value: !ai.value ? '—' : !ai.value.ai?.available && !ai.value.decision?.available ? '暂不可用' : props.user?.is_admin ? '不限' : `${brief?.remaining ?? 0} / ${brief?.limit ?? 0}`,
      sub: ai.value && !ai.value.ai?.available && !ai.value.decision?.available ? '平台还没有配置 AI 模型' : '剩余次数，每天更新',
    },
  ]
})

onMounted(async () => {
  try { const c = await getBacktestCatalog(); btStrategies.value = c.items; bt.strategy = c.default }
  catch (e) { props.notify(e.message || '加载策略目录失败') }
  // 概况数字各自加载，某一项失败只显示 —，不影响其他。
  dailyUpdateStatus().then((d) => { marketData.value = d.data || {} }).catch(() => {})
  listPackages().then((d) => { packageCount.value = d.total ?? (d.items || []).length }).catch(() => {})
  listRuns({ limit: 1 }).then((d) => { runSummary.value = d }).catch(() => {})
  aiStatus().then((d) => { ai.value = d }).catch(() => {})
})
</script>

<template>
  <div class="space-y-6">
    <!-- 欢迎 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <p class="text-sm text-slate-400">欢迎回来</p>
      <p class="mt-1 text-2xl font-bold text-white">{{ user?.name }} <span class="font-serif italic text-indigo-300">，用数据检验每一个想法</span></p>
      <p class="mt-2 max-w-xl text-sm text-slate-400">这是你的量化研究工作台：更新行情数据、写策略规则、做历史回测和因子研究。所有结果仅供研究参考。</p>
    </div>

    <!-- KPI -->
    <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
      <button v-for="k in kpis" :key="k.label" type="button" class="glass glass-sheen rounded-2xl p-5 text-left transition hover:-translate-y-0.5" @click="navigate(k.view)">
        <p class="text-xs text-slate-400">{{ k.label }}</p>
        <p class="mt-2 text-2xl font-bold text-white">{{ k.value }}</p>
        <p class="mt-2 text-xs text-slate-500">{{ k.sub }}</p>
      </button>
    </section>

    <!-- 回测 -->
    <section class="glass rounded-2xl p-5">
      <h2 class="text-sm font-semibold text-white">快速回测</h2><p class="mt-2 text-xs text-slate-400">初始资金 100 万，最多 10 只，每周调仓；更多配置请进入回测与验证。</p>
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
            <span class="text-emerald-300">总收益 {{ btResult.total_return }}%</span>
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
          <div class="rounded-xl border border-white/10 bg-white/5 p-4">
            <p class="text-xs text-slate-400">总收益</p>
            <p class="mt-1 text-lg font-bold" :class="btResult.total_return >= 0 ? 'text-emerald-300' : 'text-rose-300'">{{ btResult.total_return }}%</p>
          </div>
          <div class="rounded-xl border border-white/10 bg-white/5 p-4">
            <p class="text-xs text-slate-400">最大回撤</p>
            <p class="mt-1 text-lg font-bold text-rose-300">{{ btResult.max_drawdown }}%</p>
          </div>
          <div class="rounded-xl border border-white/10 bg-white/5 p-4">
            <p class="text-xs text-slate-400">夏普比率</p>
            <p class="mt-1 text-lg font-bold text-white">{{ btResult.sharpe }}</p>
          </div>
          <div class="rounded-xl border border-white/10 bg-white/5 p-4">
            <p class="text-xs text-slate-400">胜率</p>
            <p class="mt-1 text-lg font-bold text-white">{{ btResult.win_rate }}%</p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
