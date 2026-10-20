<script setup>
import { computed, nextTick, onActivated, onMounted, ref, watch } from 'vue'
import { aiStatus, askBrief, createBrief, decideBrief, deleteBrief, getBrief, getPreferences, listBriefs, readBrief, universeSearch } from '../../api.js'
import SectionCard from '../ui/SectionCard.vue'
import PriorKnowledgeView from './PriorKnowledgeView.vue'
import JevStockReport from '../ui/JevStockReport.vue'
import StockDataReport from '../ui/StockDataReport.vue'
import { openResearch } from '../researchNavigation.js'
import { setFocus } from '../chatFocus.js'
import { encodePreset, statesFromFacts } from '../eventStudy.js'
import {
  evidenceText, factGroups, laterText, modelText, pickSuggestion, pointSections, remainingText, signedPercent, TILT_NOTE, tiltLabel, tiltTone,
} from '../aiPresentation.js'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
  routeContext: { type: Object, default: () => ({}) },
})

const status = ref(null)
const query = ref('')
const picked = ref(null) // { symbol, name }
const suggestions = ref([])
const highlighted = ref(-1)
const tradeDate = ref('')
const useExperience = ref(true)
const step = ref('') // '' | 'data' | 'decision' | 'reading'
const loadingRecord = ref(false)
const error = ref('')
const record = ref(null)
const history = ref([])
const question = ref('')
const asking = ref(false)
const chatBox = ref(null)
const upgradingReport = ref(false)
const refreshing = ref(false)

// 因子画像还在后台计算时，重新打开这次分析：算好了就会补上。
async function refreshRecord() {
  if (!record.value) return
  refreshing.value = true
  try { record.value = await getBrief(record.value.id) } catch (e) { props.notify(e.message || '刷新失败') } finally { refreshing.value = false }
}

const facts = computed(() => record.value?.facts || null)
const groups = computed(() => factGroups(facts.value?.facts))
// 这只股票现在的几个状态：每个都可以去事件研究里看全市场历史上的情况（这里不显示任何“之后涨跌”的数字）。
const states = computed(() => statesFromFacts(facts.value?.facts))
function studyState(state) { openResearch('event-study', { preset: encodePreset(state.conditions) }) }
const brief = computed(() => record.value?.brief || null)
const odds = computed(() => record.value?.odds || brief.value?.odds || null)
const busy = computed(() => step.value !== '' || upgradingReport.value)
const canAsk = computed(() => Boolean(brief.value && status.value?.ai?.available))
const questionsLeft = computed(() => remainingText(status.value?.usage?.question, '追问'))

async function loadStatus() {
  try { status.value = await aiStatus() } catch (e) { props.notify(e.message || '读取 AI 模型状态失败') }
}
async function loadHistory() {
  try { history.value = (await listBriefs()).items || [] } catch (e) { props.notify(e.message || '读取以前的分析失败') }
}

// ---------- 选股票：代码或名称 ----------
let searchTimer = null
let searchSeq = 0
watch(query, (text) => {
  if (picked.value && text === `${picked.value.symbol} ${picked.value.name}`) return
  picked.value = null
  clearTimeout(searchTimer)
  const term = text.trim()
  if (!term) { suggestions.value = []; return }
  searchTimer = setTimeout(async () => {
    const seq = ++searchSeq
    try {
      const found = (await universeSearch(term)).results || []
      if (seq === searchSeq) { suggestions.value = found.slice(0, 8); highlighted.value = found.length ? 0 : -1 }
    } catch { if (seq === searchSeq) suggestions.value = [] }
  }, 250)
})
function choose(item) {
  picked.value = item
  query.value = `${item.symbol} ${item.name}`
  suggestions.value = []
}
function closeSuggestions() {
  setTimeout(() => { suggestions.value = [] }, 150)
}
function onSearchKey(event) {
  if (!suggestions.value.length) return
  if (event.key === 'ArrowDown') { event.preventDefault(); highlighted.value = (highlighted.value + 1) % suggestions.value.length }
  else if (event.key === 'ArrowUp') { event.preventDefault(); highlighted.value = (highlighted.value - 1 + suggestions.value.length) % suggestions.value.length }
  else if (event.key === 'Escape') suggestions.value = []
  else if (event.key === 'Enter' && highlighted.value >= 0) { event.preventDefault(); choose(suggestions.value[highlighted.value]) }
}

// ---------- 打开、运行 ----------
async function openRecord(id) {
  if (!id || record.value?.id === id) return
  loadingRecord.value = true
  error.value = ''
  try {
    record.value = await getBrief(id)
    choose({ symbol: record.value.symbol, name: record.value.name })
    tradeDate.value = record.value.trade_date
  } catch (e) {
    error.value = e.message || '打开这次分析失败'
  } finally {
    loadingRecord.value = false
  }
}

onMounted(() => {
  // “参考我的研究经验”默认按设置页的选择，这一次仍可以临时改。
  getPreferences().then((data) => { useExperience.value = data.preferences.use_experience }).catch(() => {})
  loadStatus()
  loadHistory()
  openRecord(props.routeContext.brief)
})
onActivated(loadStatus)
watch(() => props.routeContext.brief, (id) => openRecord(id))
watch(record, (value) => setFocus('agent-lab', value ? { symbol: String(value.symbol).split('.')[0], name: value.name } : null))
// 从 AI 问答等地方带着股票代码跳过来：先填好这只股票，用户点“开始分析”再分析。
// 右下角的 AI 问答：可以跨股票提问，例如排序、比较、问自己的回测。
function openChat() { window.dispatchEvent(new CustomEvent('fq-open-chat')) }
async function pickRouteSymbol(code) {
  if (!code || props.routeContext.brief) return
  const bare = String(code).split('.')[0]
  try {
    const found = ((await universeSearch(bare)).results || []).find((item) => String(item.symbol).startsWith(bare))
    choose(found || { symbol: bare, name: '' })
  } catch { choose({ symbol: bare, name: '' }) }
}
watch(() => props.routeContext.symbol, pickRouteSymbol, { immediate: true })

async function run() {
  const code = pickSuggestion(query.value, picked.value, suggestions.value)
  if (!code) return props.notify('请输入股票代码，或输入名称后从列表里选一只')
  suggestions.value = []
  error.value = ''
  step.value = 'data'
  try {
    let data = await createBrief({ symbol: code, trade_date: tradeDate.value, use_experience: useExperience.value })
    record.value = data
    openResearch('agent-lab', { brief: data.id })
    if (status.value?.decision?.available) {
      step.value = 'decision'
      try {
        data = await decideBrief(data.id)
        if (record.value?.id === data.id) record.value = data
      } catch (e) { props.notify(e.message || '决策模型暂时不可用') }
    }
    if (status.value?.ai?.available) {
      step.value = 'reading'
      data = await readBrief(data.id)
      if (record.value?.id === data.id) record.value = data
    }
  } catch (e) {
    error.value = e.message || '分析失败'
  } finally {
    step.value = ''
    loadStatus()
    loadHistory()
  }
}

async function remove(item) {
  if (!confirm(`删除 ${item.name} ${item.trade_date} 的这次分析？`)) return
  try {
    await deleteBrief(item.id)
    if (record.value?.id === item.id) { record.value = null; openResearch('agent-lab') }
    await loadHistory()
  } catch (e) {
    props.notify(e.message || '删除失败')
  }
}

async function upgradeReport() {
  if (busy.value || !record.value) return
  const id = record.value.id
  upgradingReport.value = true
  try {
    const data = await decideBrief(id, { upgrade: true })
    if (record.value?.id === id) record.value = data
  } catch (e) {
    props.notify(e.message || '报告补全失败，已保留原判断')
  } finally {
    upgradingReport.value = false
    loadStatus()
    loadHistory()
  }
}

async function ask() {
  const text = question.value.trim()
  if (!text || asking.value || !record.value) return
  asking.value = true
  try {
    const data = await askBrief(record.value.id, text)
    record.value = { ...record.value, questions: data.questions }
    question.value = ''
    if (status.value) status.value = { ...status.value, usage: { ...status.value.usage, question: data.usage } }
    await nextTick()
    chatBox.value?.scrollTo({ top: chatBox.value.scrollHeight, behavior: 'smooth' })
  } catch (e) {
    props.notify(e.message || '追问失败')
  } finally {
    asking.value = false
  }
}

function localTime(value) {
  const time = new Date(value)
  return Number.isNaN(time.getTime()) ? '' : time.toLocaleString('zh-CN', { hour12: false })
}
function moveTone(value) {
  if (value == null) return 'text-slate-400'
  return value > 0 ? 'text-rose-300' : value < 0 ? 'text-emerald-300' : 'text-slate-300'
}
</script>

<template>
  <div class="space-y-6">
    <div class="glass glass-sheen relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-violet-500/20 blur-3xl" />
      <h2 class="text-xl font-bold text-white">AI研究员</h2>
      <p class="mt-1 text-sm text-slate-400">输入一只股票，先看本地数据整理出的走势、估值和风险，再看 AI 根据这些数据写的解读。</p>
      <p class="mt-1 text-xs text-slate-500">分析依据本地数据生成，仅供研究参考。</p>
      <button type="button" class="relative mt-3 rounded-full border border-indigo-400/30 bg-indigo-500/10 px-4 py-1.5 text-sm text-indigo-200 transition hover:bg-indigo-500/20"
        @click="openChat">不只看一只股票？打开 AI 问答 →</button>
    </div>

    <SectionCard title="分析一只股票" hint="日期留空表示本地最近一个交易日">
      <form class="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] sm:items-end" @submit.prevent="run">
        <div class="relative">
          <label for="ai-stock" class="mb-1.5 block text-xs text-slate-400">股票代码或名称</label>
          <input id="ai-stock" v-model="query" autocomplete="off" placeholder="如 600519 或 茅台" role="combobox"
            :aria-expanded="suggestions.length > 0" aria-controls="ai-stock-list" @keydown="onSearchKey" @blur="closeSuggestions"
            class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          <ul v-if="suggestions.length" id="ai-stock-list" role="listbox"
            class="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-white/10 bg-ink/95 py-1 shadow-xl backdrop-blur">
            <li v-for="(item, i) in suggestions" :key="item.symbol" role="option" :aria-selected="i === highlighted"
              class="flex cursor-pointer justify-between gap-3 px-3 py-2 text-sm"
              :class="i === highlighted ? 'bg-indigo-500/20 text-white' : 'text-slate-300 hover:bg-white/5'"
              @mousedown.prevent="choose(item)">
              <span class="min-w-0 truncate">{{ item.name }}</span><span class="shrink-0 text-slate-500">{{ item.symbol }}</span>
            </li>
          </ul>
        </div>
        <div>
          <label for="ai-date" class="mb-1.5 block text-xs text-slate-400">分析日期</label>
          <input id="ai-date" v-model="tradeDate" type="date"
            class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
        </div>
        <button type="submit" :disabled="busy" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:-translate-y-0.5 disabled:opacity-60">
          {{ busy ? '分析中…' : '开始分析' }}
        </button>
      </form>
      <label class="mt-4 flex w-fit items-center gap-2 text-sm text-slate-300">
        <input v-model="useExperience" type="checkbox" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
        参考我的研究经验（{{ status?.experience_count ?? 0 }} 条）
      </label>
      <p class="mt-3 text-sm" :class="status && !status.ai?.available ? 'text-amber-200' : 'text-slate-400'">{{ modelText(status) }}</p>
      <p v-if="status?.decision?.available" class="mt-2 text-xs text-slate-400">Jev 决策模型已连接，可独立判断本地数据。{{ remainingText(status.usage?.decision, '个股判断') }}</p>
      <ol v-if="busy" class="mt-3 space-y-1 text-sm" aria-label="分析进度">
        <li :class="step === 'data' ? 'text-indigo-200' : 'text-slate-400'">{{ step === 'data' ? '…' : '✓' }} 整理本地数据（几秒）</li>
        <li v-if="status?.decision?.available" :class="step === 'decision' ? 'text-indigo-200' : 'text-slate-500'">{{ step === 'decision' ? '…' : '○' }} Jev 判断数据中的倾向</li>
        <li v-if="status?.ai?.available" :class="step === 'reading' ? 'text-indigo-200' : 'text-slate-500'">
          {{ step === 'reading' ? '…' : '○' }} AI 根据这些数据写解读（通常十几秒到一分钟，下面的数据可以先看）
        </li>
      </ol>
      <p v-if="error" role="alert" class="mt-3 text-sm text-rose-300">{{ error }}</p>
    </SectionCard>

    <p v-if="loadingRecord" class="text-sm text-slate-400">正在打开这次分析…</p>

    <template v-if="record && facts">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-lg font-semibold text-white">{{ record.name }} <span class="text-sm font-normal text-slate-400">{{ record.symbol }}</span></h2>
        <p class="text-xs text-slate-500">数据截至 {{ record.trade_date }} · 分析于 {{ localTime(record.created_at) }}</p>
      </div>
      <p v-for="note in facts.notes" :key="note" class="text-sm text-amber-200">{{ note }}</p>
      <p v-if="record.later" class="text-sm text-slate-300">{{ laterText(record.later) }}</p>

      <JevStockReport v-if="odds" :report="odds" :trade-date="record.trade_date" :text-tilt="brief?.tilt || ''"
        :upgrading="upgradingReport" :can-upgrade="Boolean(status?.decision?.available)"
        :remaining="status?.usage?.decision?.remaining ?? null" @upgrade="upgradeReport" />

      <SectionCard v-if="brief" title="AI 解读" :hint="`只根据下面的数据写成，每条后面是它引用的数据 · 模型 ${record.model}`">
        <div class="flex flex-wrap items-center gap-3">
          <span class="rounded-full border px-4 py-1.5 text-base font-semibold" :class="tiltTone(brief.tilt)">{{ tiltLabel(brief.tilt) }}</span>
          <span class="text-sm text-slate-400">信心：{{ brief.confidence }}</span>
          <span class="text-xs text-slate-500">{{ TILT_NOTE }}</span>
        </div>
        <p v-if="brief.summary" class="mt-4 text-sm leading-relaxed text-slate-200">{{ brief.summary }}</p>
        <div class="mt-5 grid gap-4 lg:grid-cols-3">
          <div v-for="section in pointSections" :key="section.key" class="min-w-0 rounded-xl border border-white/10 bg-white/5 p-4">
            <h3 class="text-xs font-semibold text-slate-300">{{ section.label }}</h3>
            <p v-if="!brief[section.key]?.length" class="mt-2 text-sm text-slate-500">没有</p>
            <ul v-else class="mt-2 space-y-3">
              <li v-for="(point, i) in brief[section.key]" :key="i">
                <p class="text-sm leading-relaxed text-slate-200">{{ point.text }}</p>
                <p v-for="fact in point.evidence" :key="fact.key" class="mt-1 text-xs text-slate-500">依据 · {{ evidenceText(fact, record.trade_date) }}</p>
              </li>
            </ul>
          </div>
        </div>
        <p v-if="brief.removed" class="mt-4 text-xs text-slate-500">已去掉 {{ brief.removed }} 条与数据对不上、没有依据或给出买卖建议的内容。</p>
      </SectionCard>
      <div v-else-if="step === 'reading'" class="rounded-xl border border-indigo-400/20 bg-indigo-500/5 p-4 text-sm text-indigo-100">AI 正在根据下面的数据写解读…</div>
      <div v-else-if="record.ai_note" class="rounded-xl border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-amber-100">{{ record.ai_note }}</div>

      <StockDataReport v-if="facts.report?.version" :symbol="record.symbol" :report="facts.report" :previous="record.previous" :trade-date="record.trade_date" :refreshing="refreshing" @refresh="refreshRecord" />

      <SectionCard v-if="states.length" title="这只股票现在的状态" hint="点一个状态，在事件研究里看全市场历史上出现这种情况以后通常怎么样；那是很多股票的统计，不是对这只股票的预测">
        <div class="flex flex-wrap gap-2">
          <button v-for="state in states" :key="state.text" type="button"
            class="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-200 transition hover:border-indigo-400/40 hover:text-white"
            @click="studyState(state)">{{ state.text }} <span class="text-xs text-indigo-300">看历史 →</span></button>
        </div>
      </SectionCard>

      <SectionCard :title="facts.report?.version ? '全部数据' : '数据摘要'" hint="全部来自本地数据，只用分析日当天及以前已知的信息；涨跌幅按复权价格计算">
        <details :open="!facts.report?.version">
        <summary v-if="facts.report?.version" class="cursor-pointer text-sm text-slate-400">展开全部 {{ facts.facts.length }} 项数据</summary>
        <div class="grid gap-4 md:grid-cols-2" :class="{ 'mt-3': facts.report?.version }">
          <div v-for="group in groups" :key="group.group" class="min-w-0 rounded-xl border border-white/10 bg-white/5 p-4">
            <h3 class="text-xs font-semibold text-slate-300">{{ group.group }}</h3>
            <dl class="mt-2 space-y-1.5">
              <div v-for="fact in group.items" :key="fact.key" class="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
                <dt class="min-w-0 text-slate-400">{{ fact.label }}</dt>
                <dd class="ml-auto min-w-0 text-right text-slate-200">{{ fact.text }}<span v-if="fact.as_of && fact.as_of !== record.trade_date" class="ml-1 text-xs text-slate-500">{{ fact.as_of }}</span></dd>
              </div>
            </dl>
          </div>
        </div>
        </details>
        <div v-if="facts.missing.length" class="mt-4 rounded-xl border border-white/10 bg-white/5 p-4">
          <h3 class="text-xs font-semibold text-slate-300">本地缺少的数据（没有用到，也没有让 AI 猜）</h3>
          <ul class="mt-2 space-y-1 text-sm text-slate-400">
            <li v-for="item in facts.missing" :key="item.group"><span class="text-slate-300">{{ item.group }}</span>：{{ item.reason }}</li>
          </ul>
          <button type="button" class="mt-3 text-sm text-indigo-300 hover:text-indigo-200" @click="openResearch('data-guide')">看平台有哪些数据 →</button>
        </div>
      </SectionCard>

      <SectionCard v-if="canAsk || record.questions.length" title="继续追问" :hint="`AI 只用上面的数据回答${questionsLeft ? ' · ' + questionsLeft : ''}`">
        <div ref="chatBox" class="max-h-96 space-y-3 overflow-y-auto">
          <p v-if="!record.questions.length" class="text-sm text-slate-500">例如：估值高不高？最大的风险是什么？</p>
          <div v-for="(turn, i) in record.questions" :key="i" class="space-y-2">
            <p class="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-indigo-500/80 px-4 py-2 text-sm text-white">{{ turn.question }}</p>
            <p class="w-fit max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-bl-md border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200">{{ turn.answer }}</p>
          </div>
        </div>
        <form v-if="canAsk" class="mt-3 flex gap-2" @submit.prevent="ask">
          <input v-model="question" maxlength="500" placeholder="输入你的问题" aria-label="追问"
            class="min-w-0 flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40" />
          <button :disabled="asking || !question.trim()" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-60">
            {{ asking ? '回答中…' : '发送' }}
          </button>
        </form>
      </SectionCard>
    </template>

    <SectionCard title="以前的分析" hint="“之后”是从分析日到本地最新行情的涨跌，和同期沪深300比较，可以用来看 AI 的判断靠不靠谱">
      <p v-if="!history.length" class="text-sm text-slate-500">还没有分析记录。</p>
      <ul v-else class="divide-y divide-white/5" aria-label="以前的分析">
        <li v-for="item in history" :key="item.id" class="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5 text-sm">
          <button type="button" class="min-w-0 text-left text-slate-200 hover:text-white" @click="openResearch('agent-lab', { brief: item.id })">
            {{ item.name }} <span class="text-xs text-slate-500">{{ item.symbol }} · {{ item.trade_date }}</span>
          </button>
          <span class="rounded-full border px-2 py-0.5 text-xs" :class="tiltTone(item.tilt)">{{ tiltLabel(item.tilt) || '只有数据' }}</span>
          <span class="ml-auto text-xs" :class="moveTone(item.later?.change)">
            <template v-if="item.later">之后 {{ signedPercent(item.later.change) }}<span class="text-slate-500">（{{ item.later.days }} 个交易日<template v-if="item.later.benchmark_change != null">，沪深300 {{ signedPercent(item.later.benchmark_change) }}</template>）</span></template>
            <span v-else class="text-slate-500">还没有之后的行情</span>
          </span>
          <button type="button" class="text-xs text-slate-500 hover:text-rose-300" @click="remove(item)">删除</button>
        </li>
      </ul>
    </SectionCard>

    <details class="glass rounded-2xl p-5">
      <summary class="cursor-pointer text-sm font-semibold text-white">我的研究经验（{{ status?.experience_count ?? 0 }} 条）<span class="ml-2 text-xs font-normal text-slate-500">记下你自己的投资规则，分析时让 AI 参考</span></summary>
      <div class="mt-4"><PriorKnowledgeView embedded :notify="notify" @changed="loadStatus" /></div>
    </details>
  </div>
</template>
