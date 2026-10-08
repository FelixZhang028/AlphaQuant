<script setup>
import { onActivated, reactive, ref } from 'vue'
import { backtestPackage, deletePackage, listPackages } from '../../api.js'
import EmptyState from '../ui/EmptyState.vue'
import SectionCard from '../ui/SectionCard.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 已保存策略包 ----------
const packages = ref([])
const loading = ref(false)
const backtestingId = ref(null)
const backtestResults = reactive({}) // package_id -> summary

function sourceLabel(source) {
  if (!source) return source
  if (source.startsWith('template:')) return '模板'
  if (source.startsWith('copy:')) return '副本'
  if (source === 'visual_builder') return '积木编辑器'
  if (source === 'nl_builder') return '自然语言'
  return source
}

function freqLabel(f) {
  const map = { daily: '每日', weekly: '每周', monthly: '每月' }
  return map[f] || f || '—'
}

function pct(v) {
  if (v === null || v === undefined) return '—'
  return `${Number(v).toFixed(2)}%`
}

function ratio(v) {
  if (v === null || v === undefined) return '—'
  return Number(v).toFixed(2)
}

async function loadPackages() {
  loading.value = true
  try {
    const data = await listPackages()
    packages.value = data.items || []
  } catch (e) {
    props.notify(e.message || '加载策略包失败')
  } finally {
    loading.value = false
  }
}

async function onBacktest(p) {
  backtestingId.value = p.package_id
  try {
    const data = await backtestPackage(p.package_id)
    const s = data.summary
    backtestResults[p.package_id] = s
    props.notify(`回测完成：总收益 ${pct(s.total_return)}，最大回撤 ${pct(s.max_drawdown)}`)
  } catch (e) {
    props.notify(e.message || '回测失败')
  } finally {
    backtestingId.value = null
  }
}

async function onDelete(p) {
  if (!confirm(`确定删除策略包「${p.name}」？`)) return
  try {
    await deletePackage(p.package_id)
    packages.value = packages.value.filter((x) => x.package_id !== p.package_id)
    delete backtestResults[p.package_id]
    props.notify('已删除')
  } catch (e) {
    props.notify(e.message || '删除失败')
  }
}

onActivated(loadPackages)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题区 -->
    <section class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <h2 class="text-xl font-bold text-white">策略管理</h2>
      <p class="mt-2 max-w-2xl text-sm text-slate-400">
        统一管理已保存策略。创建新策略时，从上方选择「模板与积木」「自然语言」或「Python 策略」。
      </p>
    </section>

    <!-- 已保存策略包 -->
    <SectionCard title="已保存策略包" hint="所有方式创建出的策略包统一在此登记、回测与删除">
      <template #actions>
        <button
          @click="loadPackages"
          :disabled="loading"
          class="rounded-full border border-white/10 px-4 py-1.5 text-xs text-slate-300 transition hover:bg-white/5 disabled:opacity-70"
        >
          {{ loading ? '加载中…' : '刷新' }}
        </button>
      </template>

      <div v-if="loading && !packages.length" class="text-sm text-slate-400">加载中…</div>

      <EmptyState v-else-if="!packages.length" text="暂无已保存的策略包，从上方四种方式开始创建。" />

      <div v-else class="grid gap-4">
        <div v-for="p in packages" :key="p.package_id" class="rounded-xl border border-white/10 bg-white/5 p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="text-sm font-semibold text-white">{{ p.name }}</h3>
                <span class="rounded-full border border-indigo-400/30 bg-indigo-400/10 px-2.5 py-0.5 text-xs text-indigo-300">{{ sourceLabel(p.source) }}</span>
              </div>
              <p class="mt-1.5 text-xs text-slate-500">
                持股 {{ p.top_n }} 只 · 调仓频率 {{ freqLabel(p.rebalance) }}
              </p>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <button
                @click="onBacktest(p)"
                :disabled="backtestingId === p.package_id"
                class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-1.5 text-xs font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:-translate-y-0.5 disabled:opacity-70"
              >
                {{ backtestingId === p.package_id ? '回测中…' : '去回测' }}
              </button>
              <button
                @click="onDelete(p)"
                class="rounded-lg border border-rose-400/20 px-3 py-1.5 text-xs text-rose-300 transition hover:bg-rose-400/10"
              >
                删除
              </button>
            </div>
          </div>

          <p v-if="p.describe_text" class="mt-3 text-xs leading-relaxed text-slate-400">{{ p.describe_text }}</p>

          <!-- 回测结果内联指标 -->
          <div v-if="backtestResults[p.package_id]" class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div class="rounded-lg border border-white/10 bg-white/5 p-3">
              <p class="text-xs text-slate-400">总收益</p>
              <p class="mt-1 text-base font-bold" :class="backtestResults[p.package_id].total_return >= 0 ? 'text-emerald-300' : 'text-rose-300'">{{ pct(backtestResults[p.package_id].total_return) }}</p>
            </div>
            <div class="rounded-lg border border-white/10 bg-white/5 p-3">
              <p class="text-xs text-slate-400">最大回撤</p>
              <p class="mt-1 text-base font-bold text-rose-300">{{ pct(backtestResults[p.package_id].max_drawdown) }}</p>
            </div>
            <div class="rounded-lg border border-white/10 bg-white/5 p-3">
              <p class="text-xs text-slate-400">夏普比率</p>
              <p class="mt-1 text-base font-bold text-white">{{ ratio(backtestResults[p.package_id].sharpe) }}</p>
            </div>
            <div class="rounded-lg border border-white/10 bg-white/5 p-3">
              <p class="text-xs text-slate-400">胜率</p>
              <p class="mt-1 text-base font-bold text-white">{{ pct(backtestResults[p.package_id].win_rate) }}</p>
            </div>
          </div>
        </div>
      </div>
    </SectionCard>
  </div>
</template>
