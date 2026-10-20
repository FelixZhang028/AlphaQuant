<script setup>
// 事件研究：选几个条件，看全市场历史上满足条件以后通常怎么样，并和全部交易日对照。
// 只是历史统计：不针对任何一只股票，也不是买卖建议。
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { eventStudyOptions, runEventStudy } from '../../api.js'
import { openResearch } from '../researchNavigation.js'
import { compareRows, decodePreset, defaultCondition, diffText, headline, histogramBars, pct, signedPct, tone } from '../eventStudy.js'
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

const kinds = computed(() => options.value?.conditions || [])
const kindOf = (type) => kinds.value.find((k) => k.type === type)
const groups = computed(() => [...new Set(kinds.value.map((k) => k.group))].map((group) => ({ group, items: kinds.value.filter((k) => k.group === group) })))
const current = computed(() => result.value?.horizons?.[horizon.value])
const rows = computed(() => compareRows(current.value))
const bars = computed(() => histogramBars(result.value?.histogram))

function applyPreset(text) {
  const decoded = decodePreset(text, kinds.value)
  if (!decoded.length) return
  form.conditions = decoded.map((c) => ({ ...defaultCondition(kindOf(c.type)), ...c }))
  fromPreset.value = true
  result.value = null
}
onMounted(async () => {
  try {
    options.value = await eventStudyOptions()
    form.start = options.value.default_start || ''
    form.end = options.value.bounds?.end || ''
    if (props.routeContext.preset) applyPreset(props.routeContext.preset)
    if (!form.conditions.length) form.conditions = [defaultCondition(kindOf('from_high'))]
  } catch (e) { loadError.value = e.message || '加载失败' }
})
watch(() => props.routeContext.preset, (text) => { if (text && options.value) applyPreset(text) })

function changeType(condition, type) {
  Object.keys(condition).forEach((key) => delete condition[key])
  Object.assign(condition, defaultCondition(kindOf(type)))
}
function addCondition() {
  if (form.conditions.length < (options.value?.max_conditions || 3)) form.conditions.push(defaultCondition(kindOf('ret')))
}
async function run() {
  if (running.value) return
  running.value = true
  error.value = ''
  try {
    result.value = await runEventStudy({ ...form, conditions: form.conditions.map((c) => ({ ...c })) })
    horizon.value = String(result.value.main_horizon)
  } catch (e) { error.value = e.message || '统计没有完成' }
  finally { running.value = false }
}

const input = 'rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/40'
</script>

<template>
  <div class="space-y-6">
    <div class="glass glass-sheen rounded-2xl p-6">
      <h1 class="text-xl font-bold text-white">事件研究</h1>
      <p class="mt-1 text-sm text-slate-400">选几个条件，看全市场历史上满足条件以后，之后 5、20、60 个交易日通常怎么样，并和全部交易日对照。</p>
      <p class="mt-1 text-xs text-slate-500">这是历史统计，用来检验一个想法；它不针对任何一只股票，也不代表以后会怎样，不是买卖建议。</p>
    </div>

    <p v-if="loadError" role="alert" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{{ loadError }}</p>

    <SectionCard v-if="options" title="条件" hint="同时满足下面所有条件的那一天，算一次事件；最多 3 个条件">
      <p v-if="fromPreset" class="mb-3 text-xs text-indigo-200">已经填好了从 AI研究员 带来的条件，可以再调整，然后点“开始统计”。</p>
      <div class="space-y-3">
        <div v-for="(condition, i) in form.conditions" :key="i" class="flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
          <span class="text-xs text-slate-500">{{ i ? '并且' : '当' }}</span>
          <select :value="condition.type" :class="input" class="min-w-0 max-w-full" aria-label="条件" @change="changeType(condition, $event.target.value)">
            <optgroup v-for="g in groups" :key="g.group" :label="g.group">
              <option v-for="k in g.items" :key="k.type" :value="k.type" class="bg-ink">{{ k.label }}</option>
            </optgroup>
          </select>
          <select v-if="kindOf(condition.type)?.days.length" v-model.number="condition.days" :class="input" aria-label="天数">
            <option v-for="d in kindOf(condition.type).days" :key="d" :value="d" class="bg-ink">{{ d }} 日</option>
          </select>
          <select v-if="kindOf(condition.type)?.directions.length" v-model="condition.direction" :class="input" aria-label="方向">
            <option v-for="d in kindOf(condition.type).directions" :key="d.value" :value="d.value" class="bg-ink">{{ d.label }}</option>
          </select>
          <template v-if="kindOf(condition.type)?.compare">
            <select v-model="condition.op" :class="input" aria-label="比较">
              <option value="<=" class="bg-ink">≤</option>
              <option value=">=" class="bg-ink">≥</option>
            </select>
            <input v-model.number="condition.value" type="number" step="any" :class="input" class="w-28" aria-label="数值" />
            <span class="text-sm text-slate-400">{{ kindOf(condition.type).unit }}</span>
          </template>
          <span v-if="kindOf(condition.type)?.source !== 'price'" class="text-[11px] text-amber-200">{{ kindOf(condition.type).source === 'report' ? '财务数据只有最近几期' : '估值数据的历史比行情短' }}</span>
          <button v-if="form.conditions.length > 1" type="button" class="ml-auto text-xs text-slate-400 hover:text-rose-300" @click="form.conditions.splice(i, 1)">去掉</button>
        </div>
      </div>
      <button v-if="form.conditions.length < options.max_conditions" type="button" class="mt-3 text-sm text-indigo-300 hover:text-indigo-200" @click="addCondition">+ 再加一个条件</button>

      <div class="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <label class="block text-xs text-slate-400">股票范围
          <select v-model="form.scope" :class="input" class="mt-1 w-full"><option v-for="s in options.scopes" :key="s.value" :value="s.value" class="bg-ink">{{ s.label }}</option></select>
        </label>
        <label class="block text-xs text-slate-400">只看某个行业（可以不填）
          <input v-model="form.industry" :class="input" class="mt-1 w-full" placeholder="例如 银行、白酒、半导体" maxlength="30" />
        </label>
        <label class="block text-xs text-slate-400">开始日期<input v-model="form.start" type="date" :min="options.bounds?.start" :max="options.bounds?.end" :class="input" class="mt-1 w-full" /></label>
        <label class="block text-xs text-slate-400">结束日期<input v-model="form.end" type="date" :min="options.bounds?.start" :max="options.bounds?.end" :class="input" class="mt-1 w-full" /></label>
        <label class="block text-xs text-slate-400">同一只股票多久内不重复算
          <select v-model.number="form.cooldown" :class="input" class="mt-1 w-full">
            <option v-for="c in options.cooldowns" :key="c" :value="c" class="bg-ink">{{ c ? `${c} 个交易日` : '每天都算（不推荐）' }}</option>
          </select>
        </label>
      </div>
      <div class="mt-4 flex flex-wrap items-center gap-4">
        <label class="flex items-center gap-2 text-sm text-slate-300"><input v-model="form.keep_st" type="checkbox" class="h-4 w-4 accent-indigo-500" />包括 ST 股票</label>
        <button type="button" :disabled="running" class="ml-auto rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 transition hover:-translate-y-0.5 disabled:opacity-60" @click="run">{{ running ? '统计中…' : '开始统计' }}</button>
      </div>
      <p v-if="running" class="mt-3 text-xs text-slate-400" role="status">正在统计全市场的历史数据。每天第一次统计要先读取全部行情，大约 10～20 秒，之后几秒就好。</p>
      <p v-if="error" class="mt-3 text-sm text-rose-300" role="alert">{{ error }}</p>
    </SectionCard>

    <template v-if="result">
      <SectionCard title="结果" :hint="result.conditions.join(' 并且 ')">
        <p class="text-sm leading-relaxed text-slate-200">{{ headline(result) }}</p>
        <ul class="mt-2 space-y-1">
          <li v-for="item in result.coverage" :key="item.label" class="text-xs text-amber-200">“{{ item.label }}”要用到的数据，只覆盖了满足前面条件的股票交易日的 {{ pct(item.share, 0) }}{{ item.since ? `（${item.since} 年起才有）` : '' }}，结果主要来自有数据的那部分。</li>
          <li v-if="result.events < 30" class="text-xs text-amber-200">{{ result.notes[0] }}</li>
        </ul>

        <div v-if="result.events" class="mt-5">
          <div class="flex flex-wrap items-center gap-2" role="group" aria-label="看之后多少个交易日">
            <span class="text-xs text-slate-400">之后</span>
            <button v-for="h in Object.keys(result.horizons)" :key="h" type="button" :aria-pressed="horizon === h"
              class="rounded-full border px-3 py-1 text-xs" :class="horizon === h ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 text-slate-400'"
              @click="horizon = h">{{ h }} 个交易日</button>
          </div>
          <div class="mt-3 overflow-x-auto">
            <table class="w-full min-w-[520px] text-left text-sm">
              <thead class="text-xs text-slate-500"><tr><th class="pb-2 pr-4 font-medium" /><th class="pb-2 pr-4 text-right font-medium">满足条件以后</th><th class="pb-2 pr-4 text-right font-medium">全部交易日</th><th class="pb-2 text-right font-medium">差别</th></tr></thead>
              <tbody class="divide-y divide-white/5">
                <tr v-for="row in rows" :key="row.label" class="text-slate-300">
                  <td class="py-2 pr-4 text-slate-400">{{ row.label }}</td>
                  <td class="py-2 pr-4 text-right text-white">{{ row.event }}</td>
                  <td class="py-2 pr-4 text-right">{{ row.all }}</td>
                  <td class="py-2 text-right" :class="tone(row.diff)">{{ diffText(row) }}</td>
                </tr>
                <tr class="text-slate-300">
                  <td class="py-2 pr-4 text-slate-400">扣掉同一天全部股票的平均</td>
                  <td class="py-2 pr-4 text-right" :class="tone(current.excess.mean)">平均 {{ signedPct(current.excess.mean) }} · 中位数 {{ signedPct(current.excess.median) }}</td>
                  <td class="py-2 pr-4 text-right text-slate-500">—</td>
                  <td class="py-2 text-right text-xs text-slate-400">跑赢的比例 {{ pct(current.excess.up_share) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="mt-2 text-xs text-slate-500">计入 {{ current.events.count.toLocaleString('zh-CN') }} 次；还没满 {{ horizon }} 个交易日的 {{ current.not_yet }} 次、之后退市或长期停牌的 {{ current.left_market }} 次没有计入；全部交易日 {{ current.all.count?.toLocaleString('zh-CN') }} 个。</p>
        </div>
      </SectionCard>

      <div v-if="result.events" class="grid gap-6 lg:grid-cols-2">
        <SectionCard class="min-w-0" :title="`之后 ${result.main_horizon} 个交易日的涨跌分布`" hint="每一格是落在这个区间的比例">
          <div class="flex h-40 items-end gap-1.5" role="img" aria-label="满足条件和全部交易日的涨跌分布">
            <div v-for="bar in bars" :key="bar.label" class="flex h-full flex-1 items-end gap-0.5" :title="`${bar.label}：满足条件 ${pct(bar.event)}，全部交易日 ${pct(bar.all)}`">
              <div class="flex-1 rounded-t bg-indigo-400/80" :style="{ height: `${Math.max(bar.eventHeight, bar.event ? 2 : 0)}%` }" />
              <div class="flex-1 rounded-t bg-slate-400/40" :style="{ height: `${Math.max(bar.allHeight, bar.all ? 2 : 0)}%` }" />
            </div>
          </div>
          <div class="mt-1 flex justify-between text-[10px] text-slate-500"><span>{{ bars[0]?.label }}</span><span>{{ bars[bars.length - 1]?.label }}</span></div>
          <p class="mt-2 flex gap-4 text-xs text-slate-400"><span class="flex items-center gap-1.5"><span class="h-2 w-3 rounded bg-indigo-400/80" />满足条件以后</span><span class="flex items-center gap-1.5"><span class="h-2 w-3 rounded bg-slate-400/40" />全部交易日</span></p>
        </SectionCard>

        <SectionCard class="min-w-0" :title="`每一年分别怎么样（之后 ${result.main_horizon} 个交易日）`" hint="只在某一两年明显的结果，可能只是那段行情的特点">
          <div class="overflow-x-auto">
            <table class="w-full min-w-[420px] text-left text-sm">
              <thead class="text-xs text-slate-500"><tr><th class="pb-2 pr-3 font-medium">年份</th><th class="pb-2 pr-3 text-right font-medium">次数</th><th class="pb-2 pr-3 text-right font-medium">平均</th><th class="pb-2 pr-3 text-right font-medium">上涨比例</th><th class="pb-2 text-right font-medium">全部交易日平均</th></tr></thead>
              <tbody class="divide-y divide-white/5">
                <tr v-for="row in result.by_year" :key="row.year" class="text-slate-300">
                  <td class="py-1.5 pr-3">{{ row.year }}</td>
                  <td class="py-1.5 pr-3 text-right">{{ row.events.toLocaleString('zh-CN') }}</td>
                  <td class="py-1.5 pr-3 text-right" :class="tone(row.mean)">{{ signedPct(row.mean) }}</td>
                  <td class="py-1.5 pr-3 text-right">{{ pct(row.up_share) }}</td>
                  <td class="py-1.5 text-right text-slate-400">{{ signedPct(row.all_mean) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionCard>
      </div>

      <SectionCard v-if="result.recent.length" title="最近的几次（已经满 20 个交易日的）" hint="历史上的例子，用来核对统计对不对；点股票可以看它的行情">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[460px] text-left text-sm">
            <thead class="text-xs text-slate-500"><tr><th class="pb-2 pr-3 font-medium">日期</th><th class="pb-2 pr-3 font-medium">股票</th><th class="pb-2 pr-3 text-right font-medium">之后 {{ result.main_horizon }} 个交易日</th><th class="pb-2 text-right font-medium">扣掉全部股票平均</th></tr></thead>
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
      </SectionCard>

      <SectionCard title="怎么算的" hint="">
        <ul class="list-disc space-y-1 pl-5 text-xs leading-relaxed text-slate-400">
          <li v-for="note in result.notes" :key="note">{{ note }}</li>
          <li>只用当天和以前的数据：财报按公布日期，指数成分股按当时的名单。</li>
        </ul>
      </SectionCard>
    </template>
  </div>
</template>
