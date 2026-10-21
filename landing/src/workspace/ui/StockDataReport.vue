<script setup>
// AI 研究员的数据报告：不用 AI，全部来自分析日当天及以前的本地数据。
// 依次是：每节一句话小结、需要留意的清单、和上次分析对比、价格走势、估值位置、财务趋势、同行对比、因子画像。
import { computed, ref } from 'vue'
import { openResearch } from '../researchNavigation.js'
import {
  CHECK_LABELS, EVENT_LABELS, FINANCE_ROWS, PEER_COLUMNS, checkCounts, eventMarkers,
  priceSeries, signedPct, sortedChecks, trendSeries, trendTone, valuationSeries,
} from '../researchReport.js'
import { aspectSummary, aspectsFrom } from '../factorProfile.js'
import FactorProfile from './FactorProfile.vue'
import ReportChart from './ReportChart.vue'
import SectionCard from './SectionCard.vue'

const props = defineProps({
  symbol: { type: String, default: '' },
  report: { type: Object, required: true },
  previous: { type: Object, default: null },
  tradeDate: { type: String, default: '' },
  refreshing: { type: Boolean, default: false },
})
const emit = defineEmits(['refresh'])

const checks = computed(() => sortedChecks(props.report.checks))
const counts = computed(() => checkCounts(props.report.checks))
const showAllChecks = ref(false)
const shownChecks = computed(() => (showAllChecks.value ? checks.value : checks.value.filter((item) => item.state !== 'ok')))

const price = computed(() => priceSeries(props.report.charts?.prices))
const markers = computed(() => eventMarkers(price.value.labels, props.report.charts?.events))
const events = computed(() => [...(props.report.charts?.events || [])].reverse())
const valuationKey = ref('pe_ttm')
const valuation = computed(() => valuationSeries(props.report.charts?.valuation, valuationKey.value))
const trend = computed(() => props.report.financial_trend)
const trendChart = computed(() => trendSeries(trend.value))
const peers = computed(() => props.report.peers)
const factors = computed(() => props.report.factors)
// 因子画像那一句换成按方面说的人话（旧的写法列的是因子名字，看不懂）。
const summaries = computed(() => {
  const text = aspectSummary(aspectsFrom(factors.value?.items || []))
  return (props.report.summaries || []).map((item) => (item.key === 'factors' && text ? { ...item, text } : item))
})
const changes = computed(() => props.previous?.changes || [])
// 上一次是同一天的数据、关键数字也没变时，不显示这一块。
const showPrevious = computed(() => Boolean(props.previous) && (changes.value.length > 0 || props.previous.trade_date !== props.tradeDate))

const priceFormat = (v) => (Number.isFinite(v) ? v.toFixed(2) : '—')
const ratioFormat = (v) => (Number.isFinite(v) ? v.toFixed(valuationKey.value === 'pb_mrq' ? 2 : 1) : '—')
const growthFormat = (v) => signedPct(v)
const stateTone = { warn: 'border-amber-400/30 bg-amber-500/10 text-amber-100', unknown: 'border-white/10 bg-white/5 text-slate-300', ok: 'border-emerald-400/20 bg-emerald-500/5 text-slate-300' }
const stateMark = { warn: '!', unknown: '?', ok: '✓' }
</script>

<template>
  <div class="space-y-5">
    <!-- 每节一句话 -->
    <SectionCard title="数据小结" hint="按固定规则从本地数据整理，只描述数据，不代表买卖判断">
      <dl class="space-y-2.5">
        <div v-for="item in summaries" :key="item.key" class="grid gap-1 sm:grid-cols-[6rem_1fr]">
          <dt class="text-xs font-semibold text-slate-400 sm:pt-0.5">{{ item.title }}</dt>
          <dd class="text-sm leading-relaxed text-slate-200">{{ item.text }}</dd>
        </div>
      </dl>
    </SectionCard>

    <!-- 需要留意 -->
    <SectionCard title="需要留意的地方" :hint="`逐条按规则检查：需要留意 ${counts.warn || 0} 项 · 数据不足 ${counts.unknown || 0} 项 · 没有发现 ${counts.ok || 0} 项`">
      <ul class="grid gap-2 md:grid-cols-2">
        <li v-for="item in shownChecks" :key="item.key" class="flex gap-3 rounded-xl border p-3 text-sm" :class="stateTone[item.state]">
          <span class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-current text-[11px] font-bold" :aria-label="CHECK_LABELS[item.state]">{{ stateMark[item.state] }}</span>
          <div class="min-w-0">
            <p class="font-medium">{{ item.label }} · {{ item.text }}</p>
            <p class="mt-0.5 text-xs text-slate-500">规则：{{ item.rule }}</p>
          </div>
        </li>
      </ul>
      <p v-if="!shownChecks.length" class="text-sm text-slate-400">按这些规则检查，没有发现需要留意的地方。</p>
      <button v-if="counts.ok" type="button" class="mt-3 text-xs text-indigo-300 hover:text-indigo-200" @click="showAllChecks = !showAllChecks">
        {{ showAllChecks ? '只看需要留意和数据不足的' : `也看没有发现问题的 ${counts.ok} 项` }}
      </button>
    </SectionCard>

    <!-- 和上次对比 -->
    <SectionCard v-if="showPrevious" title="和上次分析对比" :hint="`上次分析的数据截至 ${previous.trade_date}`">
      <p v-if="!changes.length" class="text-sm text-slate-400">关键数字和上次一样。</p>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[420px] text-left text-sm">
          <thead><tr class="text-xs text-slate-500"><th class="pb-2 font-medium">指标</th><th class="pb-2 font-medium">上次</th><th class="pb-2 font-medium">这次</th></tr></thead>
          <tbody class="divide-y divide-white/5">
            <tr v-for="c in changes" :key="c.key" class="text-slate-300">
              <td class="py-2 pr-4 text-slate-400">{{ c.label }}</td>
              <td class="py-2 pr-4">{{ c.before }}</td>
              <td class="py-2 text-white">{{ c.after }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </SectionCard>

    <!-- 价格走势 -->
    <SectionCard v-if="price.labels.length" title="近一年价格走势" hint="复权收盘价和 20 日、60 日均线；圆点是事件，鼠标移上去可以看到">
      <ReportChart :labels="price.labels" :series="price.series" :markers="markers" :format="priceFormat" :height="220" />
      <details v-if="events.length" class="mt-3">
        <summary class="cursor-pointer text-xs text-slate-400">这段时间的事件（{{ events.length }} 个）</summary>
        <ul class="mt-2 space-y-1 text-xs text-slate-400">
          <li v-for="e in events" :key="e.date + e.text"><span class="text-slate-500">{{ e.date }}</span> · {{ EVENT_LABELS[e.kind] || e.kind }} · <span class="text-slate-300">{{ e.text }}</span></li>
        </ul>
      </details>
    </SectionCard>

    <!-- 估值位置 -->
    <SectionCard v-if="report.charts?.valuation" title="估值的位置" :hint="`${report.charts.valuation.start || ''} 以来（最多近 3 年）的估值走势，虚线是这段时间的 20% 分位、中位数和 80% 分位`">
      <div class="mb-3 flex gap-2" role="group" aria-label="估值指标">
        <button v-for="k in [{ key: 'pe_ttm', label: '市盈率' }, { key: 'pb_mrq', label: '市净率' }]" :key="k.key" type="button"
          class="rounded-full border px-3 py-1 text-xs" :aria-pressed="valuationKey === k.key"
          :class="valuationKey === k.key ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 text-slate-400'" @click="valuationKey = k.key">{{ k.label }}</button>
      </div>
      <ReportChart :labels="valuation.labels" :series="valuation.series" :bands="valuation.bands" :format="ratioFormat" :height="180" />
      <p v-if="valuation.band?.share != null" class="mt-2 text-sm text-slate-300">现在是 {{ ratioFormat(valuation.band.current) }}，高于 {{ report.charts.valuation.start }} 以来 {{ Math.round(valuation.band.share * 100) }}% 的交易日。</p>
      <p v-else class="mt-2 text-sm text-slate-400">这段时间里{{ valuationKey === 'pb_mrq' ? '市净率' : '市盈率' }}为负（亏损）或数据太少，不计算位置。</p>
    </SectionCard>

    <!-- 财务趋势 -->
    <SectionCard v-if="trend" title="最近几个季度的财务" hint="按财报公布日期，只包括分析日以前已经公布的；“走向”看最近四份">
      <ReportChart :labels="trendChart.labels" :series="trendChart.series" :format="growthFormat" :height="150" zero-line />
      <div class="mt-4 overflow-x-auto">
        <table class="w-full min-w-[720px] text-left text-sm">
          <thead>
            <tr class="text-xs text-slate-500">
              <th class="pb-2 pr-3 font-medium">指标</th>
              <th v-for="row in trend.rows" :key="row.stat_date" class="whitespace-nowrap pb-2 pr-3 text-right font-medium" :title="`${row.pub_date} 公布`">{{ row.period }}</th>
              <th class="whitespace-nowrap pb-2 text-right font-medium">走向</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/5">
            <tr v-for="metric in FINANCE_ROWS" :key="metric.key" class="text-slate-300">
              <td class="whitespace-nowrap py-2 pr-3 text-slate-400" :title="metric.note || ''">{{ metric.label }}</td>
              <td v-for="row in trend.rows" :key="row.stat_date" class="whitespace-nowrap py-2 pr-3 text-right">{{ metric.format(row[metric.key]) }}</td>
              <td class="whitespace-nowrap py-2 text-right text-xs" :class="trendTone(trend.trends[metric.key])">{{ trend.trends[metric.key] || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <button v-if="symbol" type="button" class="mt-3 text-xs text-indigo-300 hover:text-indigo-200" @click="openResearch('market-lookup', { symbol, mode: 'financials' })">在股票查询里看全部历期财报 →</button>
    </SectionCard>

    <!-- 同行对比 -->
    <SectionCard v-if="peers" title="同行对比" :hint="`${peers.industry} · 同行业 ${peers.count} 只，下表是市值最接近的几家和行业中位数`">
      <div class="overflow-x-auto">
        <table class="w-full min-w-[760px] text-left text-sm">
          <thead>
            <tr class="text-xs text-slate-500">
              <th class="pb-2 pr-3 font-medium">股票</th>
              <th v-for="col in PEER_COLUMNS" :key="col.key" class="whitespace-nowrap pb-2 pr-3 text-right font-medium">{{ col.label }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/5">
            <tr v-for="row in peers.rows" :key="row.symbol" :class="row.self ? 'bg-indigo-500/10 text-white' : 'text-slate-300'">
              <td class="whitespace-nowrap py-2 pr-3">{{ row.name }} <span class="text-xs text-slate-500">{{ row.symbol }}</span><span v-if="row.self" class="ml-1 text-xs text-indigo-300">这只</span></td>
              <td v-for="col in PEER_COLUMNS" :key="col.key" class="whitespace-nowrap py-2 pr-3 text-right">{{ col.format(row[col.key]) }}</td>
            </tr>
            <tr class="text-slate-400">
              <td class="py-2 pr-3 text-xs">行业中位数</td>
              <td v-for="col in PEER_COLUMNS" :key="col.key" class="whitespace-nowrap py-2 pr-3 text-right">{{ col.format(peers.median[col.key]) }}</td>
            </tr>
            <tr class="text-xs text-slate-500">
              <td class="py-2 pr-3">在同行中的位置</td>
              <td v-for="col in PEER_COLUMNS" :key="col.key" class="whitespace-nowrap py-2 pr-3 text-right">{{ peers.ranks[col.key] != null ? `高于 ${Math.round(peers.ranks[col.key] * 100)}%` : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </SectionCard>

    <!-- 因子画像 -->
    <SectionCard v-if="factors" title="因子画像" hint="这只股票当天在全市场和同行业里处在什么位置，分成几个方面说；点一个方面看具体每一项">
      <p v-if="factors.unavailable" class="text-sm text-slate-400">{{ factors.unavailable }}</p>
      <div v-else-if="factors.pending" class="flex flex-wrap items-center gap-3 text-sm text-slate-300">
        <span>正在计算这一天全市场的因子值（第一次大约半分钟），算好后点刷新就能看到。</span>
        <button type="button" :disabled="refreshing" class="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300 hover:text-white disabled:opacity-50" @click="emit('refresh')">{{ refreshing ? '刷新中…' : '刷新' }}</button>
      </div>
      <template v-else>
        <FactorProfile :items="factors.items" />
        <p v-if="factors.missing?.length" class="mt-2 text-xs text-slate-500">没有数据、所以没算的因子：{{ factors.missing.join('、') }}。</p>
      </template>
    </SectionCard>
  </div>
</template>
