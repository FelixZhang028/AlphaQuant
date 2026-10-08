<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  createStrategy,
  deleteStrategy,
  fetchSnapshot,
  listStrategies,
  submitBacktest,
  updateStrategyStatus,
} from '../../api.js'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const snapshot = ref(null)

// ---------- 我的策略 ----------
const strategies = ref([])
const stratFilter = ref('全部')
const stratLoading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const newStrategy = reactive({ name: '', type: '趋势跟随', market: '沪深300' })
const stratTypes = ['趋势跟随', '套利', '做市', '均值回归', '高频']
const stratMarkets = ['沪深300', '中证500', '纳指100', 'ETH/USDT', 'BTC/USDT', '黄金期货']

const filteredStrats = computed(() =>
  stratFilter.value === '全部' ? strategies.value : strategies.value.filter((s) => s.status === stratFilter.value)
)
const stratStatusClass = {
  运行中: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/30',
  已暂停: 'text-amber-300 bg-amber-400/10 border-amber-400/30',
  已停止: 'text-rose-300 bg-rose-400/10 border-rose-400/30',
}

async function loadStrategies() {
  stratLoading.value = true
  try {
    strategies.value = await listStrategies()
  } catch (e) {
    props.notify(e.message || '加载策略失败')
  } finally {
    stratLoading.value = false
  }
}

async function onToggleStatus(s) {
  const next = s.status === '运行中' ? '已暂停' : '运行中'
  try {
    await updateStrategyStatus(s.id, next)
    s.status = next
    props.notify(`已${next === '运行中' ? '启动' : '暂停'} ${s.name}`)
  } catch (e) {
    props.notify(e.message || '操作失败')
  }
}

async function onDelete(s) {
  if (!confirm(`确定删除策略「${s.name}」？`)) return
  try {
    await deleteStrategy(s.id)
    strategies.value = strategies.value.filter((x) => x.id !== s.id)
    props.notify('已删除')
  } catch (e) {
    props.notify(e.message || '删除失败')
  }
}

async function onSubmitStrategy() {
  if (!newStrategy.name.trim()) return props.notify('请输入策略名称')
  creating.value = true
  try {
    const created = await createStrategy({ ...newStrategy })
    strategies.value.unshift(created)
    showCreate.value = false
    newStrategy.name = ''
    props.notify('策略已创建')
  } catch (e) {
    props.notify(e.message || '创建失败')
  } finally {
    creating.value = false
  }
}

// ---------- 回测 ----------
const bt = reactive({ strategy: 'AlphaSeeker', market: '沪深300', from: '2025-01-01', to: '2026-01-01', running: false })
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

// ---------- KPI ----------
const kpis = computed(() => {
  const s = snapshot.value
  return [
    { label: '账户资产', value: '¥1,000,000', sub: '初始资金', up: null },
    { label: '今日盈亏', value: '+¥24,690', sub: '较昨日', up: true },
    { label: '运行策略', value: s ? s.overview.running_instances : '—', sub: '实例', up: true },
    { label: '今日成交', value: s ? s.overview.today_trades.toLocaleString() : '—', sub: '笔', up: true },
  ]
})

onMounted(async () => {
  loadStrategies()
  try {
    snapshot.value = await fetchSnapshot()
  } catch {
    /* 降级静态 */
  }
})
</script>

<template>
  <div class="space-y-6">
    <!-- 欢迎 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <p class="text-sm text-slate-400">欢迎回来</p>
      <p class="mt-1 text-2xl font-bold text-white">{{ user?.name }} <span class="font-serif italic text-indigo-300">，数据驱动决策</span></p>
      <p class="mt-2 max-w-xl text-sm text-slate-400">这是你的量化工作台。从这里启动策略、运行回测、监控实盘，让每一个交易思想落地为收益。</p>
    </div>

    <!-- KPI -->
    <section class="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
      <div v-for="k in kpis" :key="k.label" class="glass glass-sheen rounded-2xl p-5">
        <p class="text-xs text-slate-400">{{ k.label }}</p>
        <p class="mt-2 text-2xl font-bold text-white">{{ k.value }}</p>
        <p class="mt-2 flex items-center gap-1.5 text-xs">
          <span v-if="k.up !== null" :class="k.up ? 'text-emerald-300' : 'text-rose-300'">{{ k.up ? '↑' : '↓' }}</span>
          <span class="text-slate-500">{{ k.sub }}</span>
        </p>
      </div>
    </section>

    <!-- 回测 -->
    <section class="glass rounded-2xl p-5">
      <h2 class="text-sm font-semibold text-white">快速回测</h2>
      <div class="mt-4 grid gap-4 md:grid-cols-5">
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">策略</span>
          <input v-model="bt.strategy" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </label>
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">市场</span>
          <select v-model="bt.market" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
            <option v-for="m in stratMarkets" :key="m">{{ m }}</option>
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

    <!-- 我的策略 -->
    <section class="glass rounded-2xl p-5">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2 class="text-sm font-semibold text-white">我的策略</h2>
        <div class="flex items-center gap-3">
          <div class="flex rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
            <button v-for="s in ['全部', '运行中', '已暂停', '已停止']" :key="s" @click="stratFilter = s" class="rounded-full px-3 py-1 transition" :class="stratFilter === s ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'">{{ s }}</button>
          </div>
          <button @click="showCreate = true" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-1.5 text-xs font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:-translate-y-0.5">+ 新建策略</button>
        </div>
      </div>

      <div v-if="stratLoading" class="mt-6 text-sm text-slate-400">加载中…</div>
      <div v-else-if="!filteredStrats.length" class="mt-6 rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-slate-500">
        暂无策略，点击「新建策略」开始。
      </div>

      <div v-else class="mt-5 overflow-x-auto">
        <table class="w-full min-w-[680px] text-left text-sm">
          <thead>
            <tr class="text-xs text-slate-500">
              <th class="pb-3 font-medium">编号</th>
              <th class="pb-3 font-medium">名称</th>
              <th class="pb-3 font-medium">类型</th>
              <th class="pb-3 font-medium">市场</th>
              <th class="pb-3 font-medium">状态</th>
              <th class="pb-3 text-right font-medium">累计盈亏</th>
              <th class="pb-3 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/5">
            <tr v-for="s in filteredStrats" :key="s.id" class="text-slate-300 transition hover:bg-white/5">
              <td class="py-3 font-mono text-xs text-indigo-300">ST-{{ String(s.id).padStart(3, '0') }}</td>
              <td class="py-3 font-medium text-white">{{ s.name }}</td>
              <td class="py-3 text-slate-400">{{ s.type }}</td>
              <td class="py-3 text-slate-400">{{ s.market }}</td>
              <td class="py-3"><span class="rounded-full border px-2.5 py-0.5 text-xs" :class="stratStatusClass[s.status]">{{ s.status }}</span></td>
              <td class="py-3 text-right font-medium" :class="s.pnl >= 0 ? 'text-emerald-300' : 'text-rose-300'">{{ s.pnl >= 0 ? '+' : '' }}{{ s.pnl }}</td>
              <td class="py-3">
                <div class="flex items-center justify-end gap-2">
                  <button @click="onToggleStatus(s)" class="rounded-lg border border-white/10 px-2.5 py-1 text-xs text-slate-300 transition hover:bg-white/10 hover:text-white">
                    {{ s.status === '运行中' ? '暂停' : '启动' }}
                  </button>
                  <button @click="onDelete(s)" class="rounded-lg border border-rose-400/20 px-2.5 py-1 text-xs text-rose-300 transition hover:bg-rose-400/10">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 新建策略弹窗 -->
    <transition
      enter-active-class="transition duration-200"
      enter-from-class="opacity-0"
      leave-active-class="transition duration-200"
      leave-to-class="opacity-0"
    >
      <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" @click.self="showCreate = false">
        <div class="glass-strong w-full max-w-md rounded-2xl p-6">
          <h3 class="text-lg font-semibold text-white">新建策略</h3>
          <div class="mt-5 space-y-4">
            <div>
              <label class="mb-1.5 block text-xs text-slate-400">策略名称</label>
              <input v-model="newStrategy.name" placeholder="如 AlphaSeeker" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
            </div>
            <div>
              <label class="mb-1.5 block text-xs text-slate-400">策略类型</label>
              <select v-model="newStrategy.type" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
                <option v-for="t in stratTypes" :key="t">{{ t }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1.5 block text-xs text-slate-400">交易市场</label>
              <select v-model="newStrategy.market" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40">
                <option v-for="m in stratMarkets" :key="m">{{ m }}</option>
              </select>
            </div>
          </div>
          <div class="mt-6 flex gap-3">
            <button @click="showCreate = false" class="flex-1 rounded-full border border-white/10 py-2.5 text-sm text-slate-300 transition hover:bg-white/5">取消</button>
            <button @click="onSubmitStrategy" :disabled="creating" class="flex-1 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70">
              {{ creating ? '创建中…' : '创建' }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>
