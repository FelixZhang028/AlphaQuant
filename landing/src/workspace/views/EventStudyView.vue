<script setup>
// 事件研究：选几个条件，看全市场历史上满足条件以后通常怎么样，并和平时、和同一天的全部股票对照。
// 只是历史统计：不针对任何一只股票，也不是买卖建议。
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { eventStudyOptions, runEventStudy } from '../../api.js'
import { openResearch } from '../researchNavigation.js'
import {
  OP_WORDS, SHORT_NAMES, bigNumbers, compareRows, decodePreset, defaultCondition, diffText, histogramBars, pathChart,
  pct, reading, sentenceParts, signedPct, tone, yearChart,
} from '../eventStudy.js'
import SectionCard from '../ui/SectionCard.vue'

const props = defineProps({
  notify: { type: Function, default: () => {} },
  routeContext: { type: Object, default: () => ({}) },
})

const options = ref(null)
const loadError = ref('')
const form = reactive({ conditions: [], scope: 'all', industry: '', start: '', end: '', cooldown: 20, keep_st: false })
const running = ref(false)
const error = ref('')
const result = ref(null)
const horizon = ref('20')
const fromPreset = ref(false)
const activePreset = ref('')
const resultsEl = ref(null)
const hoverDay = ref(null)

const kinds = computed(() => options.value?.conditions || [])
const kindOf = (type) => kinds.value.find((k) => k.type === type)
const groups = computed(() => [...new Set(kinds.value.map((k) => k.group))].map((group) => ({ group, items: kinds.value.filter((k) => k.group === group) })))
const current = computed(() => result.value?.horizons?.[horizon.value])
const numbers = computed(() => bigNumbers(horizon.value, current.value))
const readingText = computed(() => reading(result.value, horizon.value))
const rows = computed(() => compareRows(current.value))
const bars = computed(() => histogramBars(result.value?.histogram))
// 图按容器的实际宽度画（不是整张缩放），手机上字也不会变小。
const chartBox = ref(null)
const chartWidth = ref(640)
let observer = null
watch(chartBox, (el) => { observer?.disconnect(); if (el && observer) observer.observe(el) })
onUnmounted(() => observer?.disconnect())
const chart = computed(() => pathChart(result.value?.path, { width: chartWidth.value }))
const years = computed(() => yearChart(result.value?.by_year, { width: chartWidth.value }))
const dayLabels = computed(() => (chartWidth.value < 800 ? [0, 20, 40, 60] : [0, 5, 20, 40, 60]))
const dayLabel = (d) => (chartWidth.value < 480 ? (d ? `${d} 天` : '当天') : d ? `第 ${d} 天` : '出现当天')
const marked = computed(() => hoverDay.value ?? Number(horizon.value))
const settingsText = computed(() => {
  const scope = options.value?.scopes?.find((s) => s.value === form.scope)?.label || '全市场'
  const parts = [scope + (form.industry.trim() ? `里的“${form.industry.trim()}”行业` : ''), `${form.start || '…'} 至 ${form.end || '…'}`,
    form.cooldown ? `同一只股票 ${form.cooldown} 个交易日内只算一次` : '每天都算', form.keep_st ? '包括 ST' : '不含 ST']
  return parts.join(' · ')
})
const LINES = [
  { key: 'events', label: '满足条件以后', stroke: '#818cf8', dash: '', width: 2.5 },
  { key: 'market', label: '同一天的全部股票', stroke: '#cbd5e1', dash: '6 4', width: 1.5 },
  { key: 'all', label: '平时（全部交易日）', stroke: '#64748b', dash: '2 4', width: 1.5 },
]

function applyConditions(list) {
  form.conditions = list.map((c) => ({ ...defaultCondition(kindOf(c.type)), ...c }))
}
function applyLink(text) {
  const decoded = decodePreset(text, kinds.value)
  if (!decoded.length) return false
  applyConditions(decoded)
  fromPreset.value = true
  activePreset.value = ''
  result.value = null
  return true
}
onMounted(async () => {
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(([entry]) => { chartWidth.value = Math.max(280, Math.round(entry.contentRect.width)) })
    if (chartBox.value) observer.observe(chartBox.value)
  }
  try {
    options.value = await eventStudyOptions()
    form.start = options.value.default_start || ''
    form.end = options.value.bounds?.end || ''
    const linked = props.routeContext.preset && applyLink(props.routeContext.preset)
    if (!form.conditions.length) applyConditions(options.value.presets?.[0]?.conditions || [defaultCondition(kindOf('ret'))])
    if (linked) run()                    // 从 AI研究员点过来：直接给结果
  } catch (e) { loadError.value = e.message || '加载失败' }
})
watch(() => props.routeContext.preset, (text) => { if (text && options.value && applyLink(text)) run() })

function changeType(condition, type) {
  Object.keys(condition).forEach((key) => delete condition[key])
  Object.assign(condition, defaultCondition(kindOf(type)))
  activePreset.value = ''
}
function addCondition() {
  if (form.conditions.length < (options.value?.max_conditions || 3)) form.conditions.push(defaultCondition(kindOf('ret')))
  activePreset.value = ''
}
function ask(preset) {
  applyConditions(preset.conditions)
  activePreset.value = preset.key
  fromPreset.value = false
  run()
}
async function run() {
  if (running.value) return
  running.value = true
  error.value = ''
  try {
    result.value = await runEventStudy({ ...form, conditions: form.conditions.map((c) => ({ ...c })) })
    horizon.value = String(result.value.main_horizon)
    await nextTick()
    resultsEl.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  } catch (e) { error.value = e.message || '统计没有完成' }
  finally { running.value = false }
}
function hover(event) {
  const c = chart.value
  if (!c) return
  const box = event.currentTarget.getBoundingClientRect()
  const x = ((event.clientX - box.left) / box.width) * c.width
  let best = 0
  c.xs.forEach((value, i) => { if (Math.abs(value - x) < Math.abs(c.xs[best] - x)) best = i })
  hoverDay.value = c.days[best] ?? null
}

const field = 'rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/40'
const inline = 'mx-0.5 max-w-full cursor-pointer rounded-md border-0 border-b-2 border-indigo-400/50 bg-transparent px-1 py-0.5 text-base text-indigo-200 outline-none hover:bg-white/5 focus:border-indigo-300'
</script>

<template>
  <div class="space-y-6">
    <div class="glass glass-sheen rounded-2xl p-6">
      <h1 class="text-xl font-bold text-white">事件研究</h1>
      <p class="mt-1 text-sm text-slate-300">某种情况出现以后，股票之后通常怎么走？用全市场十年的历史算给你看，并和平时对照。</p>
      <p class="mt-1 text-xs text-slate-500">这是历史统计，用来检验一个想法；它不针对任何一只股票，也不代表以后会怎样，不是买卖建议。</p>
    </div>

    <p v-if="loadError" role="alert" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{{ loadError }}</p>

    <template v-if="options">
      <SectionCard title="先看几个常见问题" hint="点一下就出结果">
        <div class="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
          <button v-for="preset in options.presets" :key="preset.key" type="button" :disabled="running"
            class="min-w-0 rounded-xl border p-3 text-left transition hover:-translate-y-0.5 hover:border-indigo-400/40 disabled:opacity-60"
            :class="activePreset === preset.key ? 'border-indigo-400/60 bg-indigo-500/10' : 'border-white/10 bg-white/[0.03]'"
            :aria-pressed="activePreset === preset.key" @click="ask(preset)">
            <span class="block text-sm font-semibold text-white">{{ preset.question }}</span>
            <span class="mt-0.5 block text-xs text-slate-400">{{ preset.hint }}</span>
          </button>
        </div>
      </SectionCard>

      <SectionCard title="或者自己写一个" hint="点有下划线的地方可以改；同时满足所有条件的那一天，算出现一次">
        <p v-if="fromPreset" class="mb-3 text-xs text-indigo-200">已经填好了从 AI研究员 带来的条件，可以再调整。</p>
        <div class="text-base leading-[2.6] text-slate-200">
          <span>当一只股票的</span>
          <template v-for="(condition, i) in form.conditions" :key="i">
            <span v-if="i" class="text-slate-400">，并且</span>
            <span class="whitespace-normal">
              <select :value="condition.type" :class="inline" aria-label="条件" @change="changeType(condition, $event.target.value)">
                <optgroup v-for="g in groups" :key="g.group" :label="g.group" class="bg-ink">
                  <option v-for="k in g.items" :key="k.type" :value="k.type" class="bg-ink text-white">{{ SHORT_NAMES[k.type] || k.label }}</option>
                </optgroup>
              </select>
              <template v-for="(piece, j) in sentenceParts(kindOf(condition.type))" :key="j">
                <span v-if="piece.part === 'text'" class="mx-0.5">{{ piece.text }}</span>
                <select v-else-if="piece.part === 'days'" v-model.number="condition.days" :class="inline" aria-label="天数" @change="activePreset = ''">
                  <option v-for="d in kindOf(condition.type).days" :key="d" :value="d" class="bg-ink text-white">{{ d }}</option>
                </select>
                <select v-else-if="piece.part === 'direction'" v-model="condition.direction" :class="inline" aria-label="方向" @change="activePreset = ''">
                  <option v-for="d in kindOf(condition.type).directions" :key="d.value" :value="d.value" class="bg-ink text-white">{{ d.label }}</option>
                </select>
                <select v-else-if="piece.part === 'op'" v-model="condition.op" :class="inline" aria-label="比较" @change="activePreset = ''">
                  <option v-for="(word, op) in OP_WORDS" :key="op" :value="op" class="bg-ink text-white">{{ word }}</option>
                </select>
                <input v-else-if="piece.part === 'value'" v-model.number="condition.value" type="number" step="any" :class="inline" class="w-20 text-center"
                  aria-label="数值" @input="activePreset = ''" />
              </template>
              <button v-if="form.conditions.length > 1" type="button" class="ml-1 align-middle text-xs text-slate-500 hover:text-rose-300"
                :aria-label="`去掉第 ${i + 1} 个条件`" @click="form.conditions.splice(i, 1); activePreset = ''">✕</button>
            </span>
          </template>
          <span>的时候，之后通常怎么样？</span>
        </div>
        <p v-for="condition in form.conditions.filter((c) => kindOf(c.type)?.source !== 'price')" :key="condition.type" class="text-[11px] text-amber-200">
          {{ SHORT_NAMES[condition.type] }}：{{ kindOf(condition.type).source === 'report' ? '财务数据只有最近几期，能比的次数会少一些' : '估值数据的历史比行情短，能比的次数会少一些' }}
        </p>
        <button v-if="form.conditions.length < options.max_conditions" type="button" class="mt-1 text-sm text-indigo-300 hover:text-indigo-200" @click="addCondition">+ 再加一个条件</button>

        <details class="mt-4 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
          <summary class="cursor-pointer text-xs text-slate-400">更多设置：<span class="text-slate-300">{{ settingsText }}</span></summary>
          <div class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <label class="block text-xs text-slate-400">股票范围
              <select v-model="form.scope" :class="field" class="mt-1 w-full"><option v-for="s in options.scopes" :key="s.value" :value="s.value" class="bg-ink">{{ s.label }}</option></select>
            </label>
            <label class="block text-xs text-slate-400">只看某个行业（可以不填）
              <input v-model="form.industry" :class="field" class="mt-1 w-full" placeholder="例如 银行、白酒、半导体" maxlength="30" />
            </label>
            <label class="block text-xs text-slate-400">开始日期<input v-model="form.start" type="date" :min="options.bounds?.start" :max="options.bounds?.end" :class="field" class="mt-1 w-full" /></label>
            <label class="block text-xs text-slate-400">结束日期<input v-model="form.end" type="date" :min="options.bounds?.start" :max="options.bounds?.end" :class="field" class="mt-1 w-full" /></label>
            <label class="block text-xs text-slate-400">同一只股票多久内不重复算
              <select v-model.number="form.cooldown" :class="field" class="mt-1 w-full">
                <option v-for="c in options.cooldowns" :key="c" :value="c" class="bg-ink">{{ c ? `${c} 个交易日` : '每天都算（不推荐）' }}</option>
              </select>
            </label>
          </div>
          <label class="mt-4 flex items-center gap-2 text-sm text-slate-300"><input v-model="form.keep_st" type="checkbox" class="h-4 w-4 accent-indigo-500" />包括 ST 股票</label>
        </details>

        <div class="mt-4 flex flex-wrap items-center gap-3">
          <p v-if="running" class="text-xs text-slate-400" role="status">正在统计全市场的历史数据。数据更新后第一次要先读取全部行情，大约 10～20 秒，之后几秒就好。</p>
          <p v-if="error" class="text-sm text-rose-300" role="alert">{{ error }}</p>
          <button type="button" :disabled="running" class="ml-auto rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:-translate-y-0.5 disabled:opacity-60" @click="activePreset = ''; run()">{{ running ? '统计中…' : '看看历史上怎么样' }}</button>
        </div>
      </SectionCard>
    </template>

    <div v-if="result" ref="resultsEl" class="scroll-mt-20 space-y-6">
      <SectionCard title="结果" :hint="`${result.start} 至 ${result.end} · ${result.scope}${result.industries?.length ? '（' + result.industries.join('、') + '）' : ''}`">
        <p class="text-sm text-slate-300">当 <span class="text-white">{{ result.conditions.join('，并且 ') }}</span> 的时候</p>
        <template v-if="result.events && current?.events?.count">
          <div class="mt-4 flex flex-wrap items-center gap-2" role="group" aria-label="看之后多少个交易日">
            <span class="text-xs text-slate-400">看之后</span>
            <button v-for="h in Object.keys(result.horizons)" :key="h" type="button" :aria-pressed="horizon === h"
              class="rounded-full border px-3 py-1 text-xs" :class="horizon === h ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 text-slate-400'"
              @click="horizon = h">{{ h }} 个交易日</button>
          </div>
          <div class="mt-4 grid gap-3 sm:grid-cols-3">
            <div v-for="n in numbers" :key="n.label" class="rounded-xl bg-white/[0.04] p-4">
              <p class="text-xs text-slate-400">{{ n.label }}</p>
              <p class="mt-1 text-3xl font-semibold tabular-nums" :class="n.tone">{{ n.value }}</p>
              <p class="mt-1 text-xs text-slate-500">{{ n.note }}</p>
            </div>
          </div>
        </template>
        <p class="mt-4 border-l-2 border-indigo-400/60 pl-3 text-sm leading-relaxed text-slate-200">{{ readingText }}</p>
        <ul v-if="result.coverage.length" class="mt-2 space-y-1">
          <li v-for="item in result.coverage" :key="item.label" class="text-xs text-amber-200">“{{ item.label }}”要用到的数据，只覆盖了满足前面条件的股票交易日的 {{ pct(item.share, 0) }}{{ item.since ? `（${item.since} 年起才有）` : '' }}，结果主要来自有数据的那部分。</li>
        </ul>
      </SectionCard>

      <template v-if="result.events">
        <SectionCard v-if="chart" class="min-w-0" title="出现以后，平均每天走到哪里" hint="从出现那天的收盘价算起，之后每一天的平均累计涨跌；把鼠标放在图上看具体数字">
          <div class="mb-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
            <span v-for="line in LINES" :key="line.key" class="flex items-center gap-2">
              <svg width="22" height="6" aria-hidden="true"><line x1="0" y1="3" x2="22" y2="3" :stroke="line.stroke" :stroke-width="line.width" :stroke-dasharray="line.dash" /></svg>{{ line.label }}
            </span>
          </div>
          <div ref="chartBox" class="w-full" />
          <svg :viewBox="`0 0 ${chart.width} ${chart.height}`" :width="chart.width" :height="chart.height" class="max-w-full select-none" role="img" aria-label="出现以后之后每一天的平均累计涨跌"
            @pointermove="hover" @pointerleave="hoverDay = null">
            <g v-for="tick in chart.ticks" :key="tick.y">
              <line :x1="chart.left" :x2="chart.width - chart.right" :y1="tick.y" :y2="tick.y" :stroke="tick.zero ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.07)'" />
              <text :x="chart.left - 6" :y="tick.y + 4" text-anchor="end" class="fill-slate-500 text-[11px]">{{ tick.label }}</text>
            </g>
            <text v-for="d in dayLabels" :key="d" :x="chart.x(d)" :y="chart.height - 6" :text-anchor="d === 0 ? 'start' : d === 60 ? 'end' : 'middle'" class="fill-slate-500 text-[11px]">{{ dayLabel(d) }}</text>
            <line :x1="chart.x(marked)" :x2="chart.x(marked)" :y1="chart.top" :y2="chart.height - chart.bottom" stroke="rgba(129,140,248,0.35)" stroke-dasharray="3 3" />
            <path v-for="line in [...LINES].reverse()" :key="line.key" :d="chart.lines[line.key]" fill="none" :stroke="line.stroke" :stroke-width="line.width" :stroke-dasharray="line.dash" stroke-linejoin="round" stroke-linecap="round" />
            <template v-for="line in LINES" :key="`dot-${line.key}`">
              <circle v-if="chart.point(line.key, marked)" :cx="chart.point(line.key, marked).x" :cy="chart.point(line.key, marked).y" r="3.5" :fill="line.stroke" />
            </template>
          </svg>
          <p class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400" aria-live="polite">
            <span class="text-slate-300">{{ marked ? `第 ${marked} 个交易日` : '出现当天' }}</span>
            <span v-for="line in LINES" :key="`v-${line.key}`">{{ line.label }} <span :class="tone(chart.point(line.key, marked)?.value)">{{ signedPct(chart.point(line.key, marked)?.value) }}</span></span>
          </p>
        </SectionCard>

        <SectionCard v-if="years" class="min-w-0" :title="`每一年分别怎么样（之后 ${result.main_horizon} 个交易日的平均）`" hint="柱子是满足条件以后，横线是那一年的平时；只在某一两年明显的结果，可能只是那段行情的特点">
          <svg :viewBox="`0 0 ${years.width} ${years.height}`" :width="years.width" :height="years.height" class="max-w-full" role="img" aria-label="每一年满足条件以后和平时的平均涨跌">
            <line x1="0" :x2="years.width" :y1="years.zero" :y2="years.zero" stroke="rgba(255,255,255,0.25)" />
            <g v-for="bar in years.bars" :key="bar.year">
              <title>{{ bar.year }} 年：{{ bar.events }} 次，平均 {{ signedPct(bar.mean) }}，平时 {{ signedPct(bar.all_mean) }}</title>
              <rect :x="bar.x" :y="bar.y" :width="bar.w" :height="bar.h" rx="2" :class="bar.up ? 'fill-rose-400' : 'fill-emerald-400'" :fill-opacity="bar.few ? 0.3 : 0.85" />
              <line v-if="bar.allY !== null" :x1="bar.x - 2" :x2="bar.x + bar.w + 2" :y1="bar.allY" :y2="bar.allY" stroke="#cbd5e1" stroke-width="2" />
              <text :x="bar.center" :y="years.height - 6" text-anchor="middle" class="fill-slate-500 text-[11px]">{{ String(bar.year).slice(2) }}</text>
            </g>
          </svg>
          <p class="mt-2 text-xs text-slate-500">年份只写了后两位（16 = 2016 年）；颜色淡的年份不到 10 次，参考意义小。把鼠标放在柱子上看具体数字。</p>
        </SectionCard>

        <details class="glass rounded-2xl p-5">
          <summary class="cursor-pointer text-sm font-semibold text-white">更多细节 <span class="text-xs font-normal text-slate-400">完整对照表、涨跌分布、最近的例子、怎么算的</span></summary>
          <div class="mt-5 space-y-6">
            <div>
              <h3 class="text-sm font-semibold text-white">完整对照（之后 {{ horizon }} 个交易日）</h3>
              <div class="mt-3 overflow-x-auto">
                <table class="w-full min-w-[520px] text-left text-sm">
                  <thead class="text-xs text-slate-500"><tr><th class="pb-2 pr-4 font-medium" /><th class="pb-2 pr-4 text-right font-medium">满足条件以后</th><th class="pb-2 pr-4 text-right font-medium">平时</th><th class="pb-2 text-right font-medium">差别</th></tr></thead>
                  <tbody class="divide-y divide-white/5">
                    <tr v-for="row in rows" :key="row.label" class="text-slate-300">
                      <td class="py-2 pr-4 text-slate-400">{{ row.label }}</td>
                      <td class="py-2 pr-4 text-right text-white">{{ row.event }}</td>
                      <td class="py-2 pr-4 text-right">{{ row.all }}</td>
                      <td class="py-2 text-right" :class="tone(row.diff)">{{ diffText(row) }}</td>
                    </tr>
                    <tr class="text-slate-300">
                      <td class="py-2 pr-4 text-slate-400">和同一天的全部股票比</td>
                      <td class="py-2 pr-4 text-right" :class="tone(current.excess.mean)">平均 {{ signedPct(current.excess.mean) }} · 中位数 {{ signedPct(current.excess.median) }}</td>
                      <td class="py-2 pr-4 text-right text-slate-500">—</td>
                      <td class="py-2 text-right text-xs text-slate-400">跑赢的比例 {{ pct(current.excess.up_share) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p class="mt-2 text-xs text-slate-500">计入 {{ current.events.count.toLocaleString('zh-CN') }} 次；还没满 {{ horizon }} 个交易日的 {{ current.not_yet }} 次、之后退市或长期停牌的 {{ current.left_market }} 次没有计入；平时一共 {{ current.all.count?.toLocaleString('zh-CN') }} 个股票交易日。</p>
            </div>

            <div class="min-w-0">
              <h3 class="text-sm font-semibold text-white">之后 {{ result.main_horizon }} 个交易日的涨跌分布</h3>
              <p class="text-xs text-slate-500">每一格是落在这个区间的比例</p>
              <div class="mt-3 flex h-40 items-end gap-1.5" role="img" aria-label="满足条件和平时的涨跌分布">
                <div v-for="bar in bars" :key="bar.label" class="flex h-full flex-1 items-end gap-0.5" :title="`${bar.label}：满足条件 ${pct(bar.event)}，平时 ${pct(bar.all)}`">
                  <div class="flex-1 rounded-t bg-indigo-400/80" :style="{ height: `${Math.max(bar.eventHeight, bar.event ? 2 : 0)}%` }" />
                  <div class="flex-1 rounded-t bg-slate-400/40" :style="{ height: `${Math.max(bar.allHeight, bar.all ? 2 : 0)}%` }" />
                </div>
              </div>
              <div class="mt-1 flex justify-between text-[10px] text-slate-500"><span>{{ bars[0]?.label }}</span><span>{{ bars[bars.length - 1]?.label }}</span></div>
              <p class="mt-2 flex gap-4 text-xs text-slate-400"><span class="flex items-center gap-1.5"><span class="h-2 w-3 rounded bg-indigo-400/80" />满足条件以后</span><span class="flex items-center gap-1.5"><span class="h-2 w-3 rounded bg-slate-400/40" />平时</span></p>
            </div>

            <div v-if="result.recent.length">
              <h3 class="text-sm font-semibold text-white">最近的几次（已经满 {{ result.main_horizon }} 个交易日的）</h3>
              <p class="text-xs text-slate-500">历史上的例子，用来核对统计对不对；点股票可以看它的行情</p>
              <div class="mt-3 overflow-x-auto">
                <table class="w-full min-w-[460px] text-left text-sm">
                  <thead class="text-xs text-slate-500"><tr><th class="pb-2 pr-3 font-medium">日期</th><th class="pb-2 pr-3 font-medium">股票</th><th class="pb-2 pr-3 text-right font-medium">之后 {{ result.main_horizon }} 个交易日</th><th class="pb-2 text-right font-medium">和同一天全部股票比</th></tr></thead>
                  <tbody class="divide-y divide-white/5">
                    <tr v-for="row in result.recent" :key="row.date + row.symbol" class="text-slate-300">
                      <td class="py-1.5 pr-3 text-slate-400">{{ row.date }}</td>
                      <td class="py-1.5 pr-3"><button type="button" class="hover:text-indigo-200" @click="openResearch('market-chart', { symbol: row.symbol })">{{ row.name }} <span class="text-xs text-slate-500">{{ row.symbol }}</span></button></td>
                      <td class="py-1.5 pr-3 text-right" :class="tone(row.change)">{{ signedPct(row.change) }}</td>
                      <td class="py-1.5 text-right" :class="tone(row.excess)">{{ signedPct(row.excess) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div>
              <h3 class="text-sm font-semibold text-white">怎么算的</h3>
              <ul class="mt-2 list-disc space-y-1 pl-5 text-xs leading-relaxed text-slate-400">
                <li v-for="note in result.notes" :key="note">{{ note }}</li>
                <li>走势图上“平时”是从全部股票交易日里固定抽了 30 万个算的，第 5、20、60 天用的是全部数据的精确值。</li>
                <li>只用当天和以前的数据：财报按公布日期，指数成分股按当时的名单。</li>
              </ul>
            </div>
          </div>
        </details>
      </template>
    </div>
  </div>
</template>
