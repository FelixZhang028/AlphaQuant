<script setup>
// 股票查询 → 财务：一只股票的历期财报。最新一期和去年同期比，趋势图可以换指标，表格里每个空着的数字都说明原因。
// 只列数字，不评价好坏。
import { computed, ref, watch } from 'vue'
import { localMarketFinancials } from '../../api.js'
import { CHART_METRICS, STATEMENT_COLUMNS, chartSeries, column, coverageText, emptyText, latestCards } from '../stockFinancials.js'
import ReportChart from './ReportChart.vue'

const props = defineProps({ symbol: { type: String, required: true }, admin: { type: Boolean, default: false } })

const data = ref(null)
const loading = ref(false)
const error = ref('')
const chartKey = ref('profit_yoy')
let request = 0
async function load() {
  const current = ++request
  loading.value = true
  error.value = ''
  data.value = null
  try {
    const response = await localMarketFinancials(props.symbol)
    if (current === request) data.value = response
  } catch (e) {
    if (current === request) error.value = e.message || '读取财务数据失败'
  } finally {
    if (current === request) loading.value = false
  }
}
watch(() => props.symbol, load, { immediate: true })

const cards = computed(() => latestCards(data.value?.latest))
const chart = computed(() => chartSeries(data.value?.rows, chartKey.value))
const chartMetrics = CHART_METRICS.map(column)
</script>

<template>
  <div class="text-sm text-slate-300">
    <p v-if="loading" class="text-slate-400" role="status">正在读取这只股票的财报…</p>
    <p v-else-if="error" class="text-rose-300" role="alert">{{ error }} <button type="button" class="underline" @click="load">重试</button></p>
    <p v-else-if="data && !data.periods" class="text-slate-400">{{ emptyText(data, admin) }}</p>
    <div v-else-if="data" class="space-y-5">
      <div class="space-y-1 text-xs text-slate-400">
        <p>{{ coverageText(data) }}，按公布日期记录，数据来自 BaoStock。下面只列数字，不代表好坏。</p>
        <p v-if="data.next_report">下一份是 {{ data.next_report.period }}，最晚 {{ data.next_report.deadline }} 公布，公布后平台会自动更新。</p>
      </div>

      <!-- 最新一期 -->
      <section aria-label="最新一期财报">
        <h4 class="text-xs font-semibold text-slate-400">最新一期 · {{ data.latest.period }} · {{ data.latest.pub_date }} 公布</h4>
        <div class="mt-2 grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
          <div v-for="card in cards" :key="card.key" class="rounded-xl border border-white/10 bg-white/5 p-3">
            <p class="text-xs text-slate-400">{{ card.label }}</p>
            <p class="mt-1 text-base font-semibold text-white" :title="card.reason">{{ card.value }}</p>
            <p class="mt-1 text-xs" :class="card.tone" :title="card.changeReason">{{ card.changeLabel }} {{ card.arrow }} {{ card.changeText }}</p>
          </div>
        </div>
        <p class="mt-2 text-xs text-slate-500">营收、净利润和净资产收益率都是年初至报告期累计的，所以和去年同一期比较。箭头只表示比去年同期高还是低。
          <template v-if="!data.latest.last_year">本地还没有去年同一期的财报，所以除了财报自带的净利润同比，其余暂时不能和去年同期比较。</template></p>
      </section>

      <!-- 趋势图 -->
      <section aria-label="财务趋势图">
        <div class="flex flex-wrap gap-2" role="group" aria-label="趋势图指标">
          <button v-for="item in chartMetrics" :key="item.key" type="button" :aria-pressed="chartKey === item.key"
            class="rounded-full border px-3 py-1 text-xs transition"
            :class="chartKey === item.key ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 text-slate-400 hover:text-slate-200'"
            @click="chartKey = item.key">{{ item.label }}</button>
        </div>
        <div class="mt-3">
          <ReportChart v-if="chart.points >= 2" :labels="chart.labels" :series="chart.series" :format="chart.format" :zero-line="chart.zeroLine" :height="170" />
          <p v-else class="rounded-xl border border-dashed border-white/10 px-4 py-6 text-center text-xs text-slate-500">这一项本地只有 {{ chart.points }} 期数据，画不出走势。</p>
        </div>
        <p v-if="chart.note" class="mt-2 text-xs text-slate-500">{{ chart.note }}</p>
      </section>

      <!-- 历期财报 -->
      <section aria-label="历期财报">
        <h4 class="text-xs font-semibold text-slate-400">历期财报（从新到旧）</h4>
        <div class="mt-2 overflow-x-auto rounded-xl border border-white/10">
          <table class="w-full min-w-[1100px] text-left text-sm">
            <thead class="bg-white/5 text-xs text-slate-400">
              <tr>
                <th class="sticky left-0 z-10 whitespace-nowrap bg-ink px-3 py-2 font-medium">报告期</th>
                <th class="whitespace-nowrap px-3 py-2 font-medium">公布日期</th>
                <th v-for="col in STATEMENT_COLUMNS" :key="col.key" class="whitespace-nowrap px-3 py-2 text-right font-medium"
                  :title="col.cumulative ? '年初至报告期累计' : ''">{{ col.label }}<span v-if="col.cumulative" class="text-slate-500">*</span></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-white/5">
              <tr v-for="row in data.rows" :key="row.stat_date" class="hover:bg-white/5">
                <td class="sticky left-0 z-10 whitespace-nowrap bg-ink px-3 py-2 text-slate-200">{{ row.period }}</td>
                <td class="whitespace-nowrap px-3 py-2 text-slate-400">{{ row.pub_date }}</td>
                <td v-for="col in STATEMENT_COLUMNS" :key="col.key" class="whitespace-nowrap px-3 py-2 text-right">
                  <span v-if="row.missing?.[col.key]" class="cursor-help border-b border-dotted border-slate-600 text-slate-500" :title="row.missing[col.key]">—</span>
                  <template v-else>{{ col.format(row[col.key]) }}</template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="mt-2 text-xs text-slate-500">* 年初至报告期累计：半年报是前 6 个月的合计，年报是全年。“—”表示没有这项数据，鼠标移上去可以看到原因。资产负债率由权益乘数换算（1 − 1 / 权益乘数）。</p>
        <p class="mt-1 text-xs text-slate-500 sm:hidden">左右滑动表格可以看到全部指标。</p>
        <p v-if="data.empty_periods?.length" class="mt-1 text-xs text-slate-500">数据源确认没有财报的报告期：{{ data.empty_periods.join('、') }}。</p>
      </section>
    </div>
  </div>
</template>
