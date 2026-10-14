<script setup>
import { computed, nextTick, onActivated, onMounted, ref, watch } from 'vue'
import { aiStatus, askBrief, createBrief, getBrief } from '../../api.js'
import SectionCard from '../ui/SectionCard.vue'
import FormField from '../ui/FormField.vue'
import { openResearch } from '../researchNavigation.js'
import { evidenceText, factGroups, modelText, pointSections, remainingText, tiltTone } from '../aiPresentation.js'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
  routeContext: { type: Object, default: () => ({}) },
})

const status = ref(null)
const symbol = ref('')
const tradeDate = ref('')
const useExperience = ref(true)
const running = ref(false)
const loadingRecord = ref(false)
const error = ref('')
const record = ref(null)
const question = ref('')
const asking = ref(false)
const chatBox = ref(null)

const facts = computed(() => record.value?.facts || null)
const groups = computed(() => factGroups(facts.value?.facts))
const brief = computed(() => record.value?.brief || null)
const canAsk = computed(() => Boolean(brief.value && status.value?.ai?.available))
const questionsLeft = computed(() => remainingText(status.value?.usage?.question, '追问'))

async function loadStatus() {
  try { status.value = await aiStatus() } catch (e) { props.notify(e.message || '读取 AI 模型状态失败') }
}

async function openRecord(id) {
  if (!id || record.value?.id === id) return
  loadingRecord.value = true
  error.value = ''
  try {
    record.value = await getBrief(id)
    symbol.value = record.value.symbol
    tradeDate.value = record.value.trade_date
  } catch (e) {
    error.value = e.message || '打开这次分析失败'
  } finally {
    loadingRecord.value = false
  }
}

onMounted(() => {
  loadStatus()
  openRecord(props.routeContext.brief)
})
onActivated(loadStatus)
watch(() => props.routeContext.brief, (id) => openRecord(id))

async function run() {
  if (!symbol.value.trim()) return props.notify('请输入股票代码')
  running.value = true
  error.value = ''
  try {
    const data = await createBrief({ symbol: symbol.value.trim(), trade_date: tradeDate.value, use_experience: useExperience.value })
    record.value = data
    openResearch('agent-lab', { brief: data.id })
  } catch (e) {
    error.value = e.message || '分析失败'
  } finally {
    running.value = false
    loadStatus()
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
</script>

<template>
  <div class="space-y-6">
    <div class="glass glass-sheen relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-violet-500/20 blur-3xl" />
      <h2 class="text-xl font-bold text-white">AI研究员</h2>
      <p class="mt-1 text-sm text-slate-400">输入一只股票，先看本地数据整理出的走势、估值和风险，再看 AI 根据这些数据写的解读。</p>
      <p class="mt-1 text-xs text-slate-500">仅供研究，不构成投资建议。</p>
    </div>

    <SectionCard title="分析一只股票" hint="日期留空表示本地最近一个交易日">
      <template #actions>
        <button :disabled="running" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white transition hover:-translate-y-0.5 disabled:opacity-60" @click="run">
          {{ running ? '分析中…' : '开始分析' }}
        </button>
      </template>
      <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="run">
        <FormField label="股票代码" v-model="symbol" placeholder="如 600519" />
        <FormField label="分析日期" type="date" v-model="tradeDate" />
      </form>
      <div class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-slate-300">
        <label class="flex items-center gap-2">
          <input v-model="useExperience" type="checkbox" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
          参考我的研究经验（{{ status?.experience_count ?? 0 }} 条）
        </label>
        <button type="button" class="text-indigo-300 hover:text-indigo-200" @click="openResearch('knowledge-base', { mode: 'experience' })">管理研究经验</button>
      </div>
      <p class="mt-3 text-sm" :class="status && !status.ai?.available ? 'text-amber-200' : 'text-slate-400'">{{ modelText(status) }}</p>
      <p v-if="running" class="mt-2 text-sm text-slate-400">正在整理本地数据并等待 AI 解读，通常需要十几秒到一分钟。</p>
      <p v-if="error" role="alert" class="mt-3 text-sm text-rose-300">{{ error }}</p>
    </SectionCard>

    <p v-if="loadingRecord" class="text-sm text-slate-400">正在打开这次分析…</p>

    <template v-if="record && facts">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-lg font-semibold text-white">{{ record.name }} <span class="text-sm font-normal text-slate-400">{{ record.symbol }}</span></h2>
        <p class="text-xs text-slate-500">数据截至 {{ record.trade_date }} · 分析于 {{ localTime(record.created_at) }}</p>
      </div>
      <p v-for="note in facts.notes" :key="note" class="text-sm text-amber-200">{{ note }}</p>

      <SectionCard v-if="brief" title="AI 解读" :hint="`只根据下面的数据写成，每条后面是它引用的数据 · 模型 ${record.model}`">
        <div class="flex flex-wrap items-center gap-3">
          <span class="rounded-full border px-4 py-1.5 text-base font-semibold" :class="tiltTone(brief.tilt)">{{ brief.tilt }}</span>
          <span class="text-sm text-slate-400">信心：{{ brief.confidence }}</span>
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
      <div v-else-if="record.ai_note" class="rounded-xl border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-amber-100">{{ record.ai_note }}</div>

      <SectionCard title="数据摘要" hint="全部来自本地数据，只用分析日当天及以前已知的信息；涨跌幅按复权价格计算">
        <div class="grid gap-4 md:grid-cols-2">
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
        <div v-if="facts.missing.length" class="mt-4 rounded-xl border border-white/10 bg-white/5 p-4">
          <h3 class="text-xs font-semibold text-slate-300">本地缺少的数据（没有用到，也没有让 AI 猜）</h3>
          <ul class="mt-2 space-y-1 text-sm text-slate-400">
            <li v-for="item in facts.missing" :key="item.group"><span class="text-slate-300">{{ item.group }}</span>：{{ item.reason }}</li>
          </ul>
          <button type="button" class="mt-3 text-sm text-indigo-300 hover:text-indigo-200" @click="openResearch('data-update')">去数据更新 →</button>
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
  </div>
</template>
