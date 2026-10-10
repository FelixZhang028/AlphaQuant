<script setup>
import { computed, nextTick, onActivated, onMounted, reactive, ref, watch } from 'vue'
import {
  agentConfig,
  battleAgent,
  runAgent,
  saveAgentConfig,
} from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import StatusPill from '../ui/StatusPill.vue'
import EmptyState from '../ui/EmptyState.vue'
import FormField from '../ui/FormField.vue'
import { openResearch } from '../researchNavigation.js'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 配置加载 ----------
const providers = ref([])
const stockSources = ref([])
const newsSources = ref([])
const priorEntries = ref([])
const configLoading = ref(false)

const form = reactive({
  provider: 'mock',
  symbol: '600519',
  trade_date: new Date().toISOString().slice(0, 10),
  lookback_days: 60,
  debate_rounds: 1,
  stock_source: 'local',
  news_sources: [],
  use_cache: true,
  prior_ids: [],
})

// 已选先验知识（null = 全部注入）
const selectedPriorIds = ref(null)

const providerOptions = computed(() =>
  providers.value.map((p) => ({
    value: p.key,
    label: `${p.display_name}${p.requires_key ? '' : '（无需 Key）'}`,
  }))
)

const currentProvider = computed(
  () => providers.value.find((p) => p.key === form.provider) || null
)

onMounted(async () => {
  configLoading.value = true
  try {
    const cfg = await agentConfig()
    providers.value = cfg.providers || []
    stockSources.value = cfg.stock_sources || []
    newsSources.value = cfg.news_sources || []
    priorEntries.value = cfg.prior_knowledge || []
    if (cfg.default_provider) form.provider = cfg.default_provider
    else if (providers.value.length) {
      const mock = providers.value.find((p) => p.key === 'mock')
      form.provider = mock ? mock.key : providers.value[0].key
    }
  } catch (e) {
    props.notify(e.message || '加载智能体配置失败')
  } finally {
    configLoading.value = false
  }
})

// 从独立知识库页面返回后刷新可选择的先验知识。
onActivated(async () => {
  try { priorEntries.value = (await agentConfig()).prior_knowledge || [] }
  catch (e) { props.notify(e.message) }
})

// ---------- LLM 提供商配置 ----------
const llmForm = reactive({ base_url: '', api_key: '', model: '' })
const llmSaving = ref(false)
const showLlmForm = ref(false)

// 切换 provider 时带出已保存配置（api_key 只回显是否已配置，不回传明文）
watch(currentProvider, (p) => {
  if (!p) return
  llmForm.base_url = p.base_url || p.default_base_url || ''
  llmForm.model = p.model || p.default_model || ''
  llmForm.api_key = ''
})

async function onSaveLlm() {
  llmSaving.value = true
  try {
    await saveAgentConfig({
      provider: form.provider,
      base_url: llmForm.base_url,
      api_key: llmForm.api_key,
      model: llmForm.model,
    })
    props.notify('模型配置已保存（仅保存在本机）')
    showLlmForm.value = false
    const cfg = await agentConfig()
    providers.value = cfg.providers || []
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    llmSaving.value = false
  }
}

// ---------- 先验知识库 ----------

const visiblePriors = computed(() =>
  selectedPriorIds.value === null
    ? priorEntries.value
    : priorEntries.value.filter((e) => selectedPriorIds.value.includes(e.id))
)

function togglePrior(id) {
  const ids = new Set(selectedPriorIds.value ?? priorEntries.value.map((e) => e.id))
  if (ids.has(id)) ids.delete(id)
  else ids.add(id)
  selectedPriorIds.value = [...ids]
}

function selectAllPrior() {
  selectedPriorIds.value = null
}

function isPriorSelected(id) {
  const ids = selectedPriorIds.value ?? priorEntries.value.map((e) => e.id)
  return ids.includes(id)
}

// ---------- 运行分析 ----------
const running = ref(false)
const runError = ref('')
const result = ref(null)
const resultProvider = ref('')

const decision = computed(() => result.value?.decision || {})
const state = computed(() => result.value?.state || {})
const analysts = computed(() => state.value.analysts || [])
const debate = computed(() => state.value.debate || [])
const proposal = computed(() => state.value.proposal || {})
const risk = computed(() => state.value.risk || {})
const fill = computed(() => state.value.fill || {})
const traceLog = computed(() => result.value?.trace_log || [])

function statusTone(status) {
  const s = String(status || '')
  if (['批准', '成功', 'SUCCESS', '买入', '通过', '完成'].includes(s)) return 'text-emerald-300'
  if (['拒绝', '失败', 'FAILED', '卖出'].includes(s)) return 'text-rose-300'
  if (['有条件批准', '警告', 'WARNING', '持有', '暂停'].includes(s)) return 'text-amber-300'
  return 'text-white'
}

function actionTone(action) {
  const a = String(action || '')
  if (['买入', 'BUY', '加仓', '看多'].includes(a)) return 'text-emerald-300'
  if (['卖出', 'SELL', '减仓', '看空'].includes(a)) return 'text-rose-300'
  if (['持有', 'HOLD', '观望', '中性'].includes(a)) return 'text-amber-300'
  return 'text-white'
}

function traceText(item) {
  if (typeof item === 'string') return item
  if (item == null) return ''
  if (typeof item === 'object') {
    if (item.message) return item.message
    if (item.text) return item.text
    if (item.content) return item.content
    if (item.step) return `${item.step}`
    return JSON.stringify(item)
  }
  return String(item)
}

async function onRun() {
  if (!form.symbol.trim()) return props.notify('请输入股票代码')
  running.value = true
  runError.value = ''
  result.value = null
  try {
    const provider = form.provider
    const data = await runAgent({
      symbol: form.symbol.trim(),
      trade_date: form.trade_date,
      lookback_days: Number(form.lookback_days),
      debate_rounds: Number(form.debate_rounds),
      provider: form.provider,
      stock_source: form.stock_source,
      news_sources: form.news_sources,
      prior_ids: selectedPriorIds.value,
      use_cache: form.use_cache,
    })
    result.value = data
    resultProvider.value = provider
    chat.value = [] // 新分析开始新的交锋
    props.notify('分析完成')
  } catch (e) {
    runError.value = e.message || '分析失败'
    props.notify(e.message || '分析失败')
  } finally {
    running.value = false
  }
}

// ---------- 与 AI 对话交锋 ----------
const chat = ref([])
const chatInput = ref('')
const battling = ref(false)
const chatBox = ref(null)

async function onBattle() {
  const text = chatInput.value.trim()
  if (!text || battling.value || running.value || !result.value) return
  chat.value.push({ role: 'user', text })
  chatInput.value = ''
  battling.value = true
  try {
    const history = chat.value.slice(0, -1).map((m) => ({ role: m.role, text: m.text }))
    const data = await battleAgent({ message: text, history })
    chat.value.push({ role: 'assistant', text: data.reply || '（无回复）' })
  } catch (e) {
    chat.value.push({ role: 'assistant', text: `出错了：${e.message || '未知错误'}`, error: true })
    props.notify(e.message || '对话失败')
  } finally {
    battling.value = false
    await nextTick()
    chatBox.value?.scrollTo({ top: chatBox.value.scrollHeight, behavior: 'smooth' })
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- 顶部标题 -->
    <div class="glass glass-sheen relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-violet-500/20 blur-3xl" />
      <h2 class="text-xl font-bold text-white">AI研究员</h2>
      <p class="mt-1 text-sm text-slate-400">输入股票和日期，查看分析结论、研究依据，再继续追问。</p>
      <p class="mt-1 text-xs text-slate-500">本页面仅供研究，不构成投资建议；默认 Mock 模型可离线运行，配置 API Key 后可接入真实大模型。</p>
    </div>

    <SectionCard title="开始研究" hint="选择研究标的和日期，其他选项可在高级设置中调整">
      <template #actions>
        <button @click="onRun" :disabled="running || battling || configLoading"
          class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white transition hover:-translate-y-0.5 disabled:opacity-60">
          {{ running ? '分析中…' : '开始分析' }}
        </button>
      </template>
      <div class="grid gap-4 sm:grid-cols-2">
        <FormField label="股票代码" v-model="form.symbol" placeholder="如 600519" />
        <FormField label="研究日期" type="date" v-model="form.trade_date" />
      </div>
      <p class="mt-4 text-sm text-slate-400">
        {{ currentProvider?.display_name || '正在加载模型' }} · {{ stockSources.find((source) => source.key === form.stock_source)?.label || '本地行情' }} · 引用 {{ visiblePriors.length }} 条研究经验
      </p>
      <p v-if="form.provider === 'mock'" class="mt-2 text-sm text-amber-300">当前为离线演示模型，分析内容仅用于体验流程。可在高级设置中切换模型。</p>
      <p v-if="configLoading" class="mt-3 text-sm text-slate-400">正在加载研究配置…</p>
      <p v-if="runError" role="alert" class="mt-3 text-sm text-rose-300">{{ runError }}</p>
    </SectionCard>

    <section class="glass rounded-2xl p-5">
      <h2 class="text-base font-semibold text-white">高级设置 <span class="ml-2 text-sm font-normal text-slate-400">模型、数据来源、研究经验与分析参数</span></h2>
      <div class="mt-5 space-y-5">
        <SectionCard title="模型、数据与研究经验" hint="按本次研究需要选择模型、数据来源与引用的经验">
          <div class="grid gap-4 lg:grid-cols-2">
            <!-- 模型与数据来源 -->
            <div class="space-y-4">
              <div class="rounded-xl border border-white/10 bg-white/5 p-4">
                <p class="text-xs font-semibold text-slate-300">模型与数据来源</p>
                <div class="mt-3 grid gap-3 sm:grid-cols-2">
                  <FormField
                    label="分析模型"
                    type="select"
                    v-model="form.provider"
                    :options="providerOptions"
                    :disabled="configLoading"
                    hint="Mock 离线可跑通全流程"
                  />
                  <FormField label="股票行情来源" type="select" v-model="form.stock_source"
                    :options="stockSources.map((s) => ({ value: s.key, label: s.label }))"
                    hint="本地行情离线稳定，其余需联网" />
                </div>
                <div class="mt-3">
                  <p class="mb-1.5 text-xs text-slate-400">新闻来源（可多选，抓取失败自动降级）</p>
                  <div class="flex flex-wrap gap-2">
                    <button
                      v-for="n in newsSources"
                      :key="n.key"
                      type="button"
                      class="rounded-full px-3 py-1 text-xs transition"
                      :class="form.news_sources.includes(n.key)
                        ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white'
                        : 'border border-white/10 text-slate-400 hover:text-slate-200'"
                      @click="form.news_sources.includes(n.key)
                        ? (form.news_sources = form.news_sources.filter((k) => k !== n.key))
                        : form.news_sources.push(n.key)"
                    >{{ n.label }}</button>
                  </div>
                </div>
                <div class="mt-3 flex items-center justify-between gap-3">
                  <p class="text-xs text-slate-500">
                    <template v-if="currentProvider">
                      {{ currentProvider.display_name }} ·
                      {{ currentProvider.api_key ? 'API Key 已配置' : (currentProvider.requires_key ? 'API Key 未配置' : '无需 API Key') }}
                    </template>
                  </p>
                  <button
                    class="rounded-full border border-white/10 px-3.5 py-1.5 text-xs text-slate-300 transition hover:border-indigo-400/40 hover:text-white"
                    @click="showLlmForm = !showLlmForm"
                  >{{ showLlmForm ? '收起' : '配置模型' }}</button>
                </div>
                <div v-if="showLlmForm" class="mt-3 space-y-3 border-t border-white/10 pt-3">
                  <label class="block">
                    <span class="mb-1 block text-xs text-slate-400">Base URL</span>
                    <input v-model="llmForm.base_url" placeholder="https://api.deepseek.com/v1"
                      class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/40" />
                  </label>
                  <label class="block">
                    <span class="mb-1 block text-xs text-slate-400">模型名称</span>
                    <input v-model="llmForm.model" placeholder="deepseek-chat"
                      class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/40" />
                  </label>
                  <label class="block">
                    <span class="mb-1 block text-xs text-slate-400">API Key（仅保存在本机，不会上传）</span>
                    <input v-model="llmForm.api_key" type="password" :placeholder="currentProvider?.api_key ? '已配置，留空表示不修改' : '未配置'"
                      class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/40" />
                  </label>
                  <div class="flex justify-end">
                    <button
                      class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-60"
                      :disabled="llmSaving"
                      @click="onSaveLlm"
                    >{{ llmSaving ? '保存中…' : '保存配置' }}</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 先验知识 -->
            <div class="rounded-xl border border-white/10 bg-white/5 p-4">
              <div class="flex items-center justify-between">
                <p class="text-xs font-semibold text-slate-300">研究经验（引用 {{ visiblePriors.length }} / {{ priorEntries.length }} 条）</p>
                <button
                  v-if="selectedPriorIds !== null && priorEntries.length"
                  class="text-xs text-indigo-300 transition hover:text-white"
                  @click="selectAllPrior"
                >全选</button>
              </div>
              <p v-if="!priorEntries.length" class="mt-3 text-xs text-slate-500">
                暂无研究经验，可前往投研知识库添加投资规则、经验及来源。
              </p>
              <ul v-else class="mt-3 max-h-48 space-y-2 overflow-y-auto pr-1">
                <li
                  v-for="entry in priorEntries"
                  :key="entry.id"
                  class="flex items-start gap-2.5 rounded-lg border border-white/5 bg-white/5 px-3 py-2"
                  :class="isPriorSelected(entry.id) ? 'border-indigo-400/30' : 'opacity-70'"
                >
                  <input
                    type="checkbox"
                    :checked="isPriorSelected(entry.id)"
                    class="mt-1 h-3.5 w-3.5 rounded border-white/20 bg-white/5 accent-indigo-500"
                    @change="togglePrior(entry.id)"
                  />
                  <div class="min-w-0 flex-1">
                    <p class="text-xs leading-relaxed text-slate-300">{{ entry.content }}</p>
                    <p class="mt-0.5 text-[10px] text-slate-500">{{ entry.source }}</p>
                  </div>

                </li>
              </ul>
              <button class="mt-3 rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-white/5"
                @click="openResearch('knowledge-base', { mode: 'experience' })">管理研究经验</button>
            </div>
          </div>
        </SectionCard>
        <SectionCard title="分析参数">
          <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <FormField
              label="回看天数"
              type="number"
              v-model="form.lookback_days"
              :min="20"
              :max="250"
            />
            <FormField
              label="辩论轮数"
              type="number"
              v-model="form.debate_rounds"
              :min="0"
              :max="4"
            />
            <label class="flex items-center gap-2.5 self-end pb-2.5">
              <input type="checkbox" v-model="form.use_cache" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
              <span class="text-sm text-slate-300">使用缓存</span>
              <span class="ml-auto text-[10px] text-slate-500">取消可查看完整过程</span>
            </label>
          </div>
        </SectionCard>
      </div>
    </section>

    <!-- 分析结果 -->
    <template v-if="result">
      <div v-if="result.cached" class="rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-slate-500">
        本次仅返回研究结论；在高级设置中取消「使用缓存」后重新分析，可查看完整研究过程。
      </div>

      <!-- 组合经理决策 -->
      <SectionCard
        :title="`研究结论${result.symbol ? ' · ' + result.symbol + ' ' + (result.name || '') : ''}`"
        hint="综合各分析维度的研究意见，下方列出依据与条件"
      >
        <p v-if="resultProvider === 'mock'" class="mb-4 text-sm text-amber-300">离线演示结果</p>
        <div class="grid gap-5 sm:grid-cols-3">
          <MetricCard label="审批状态" :value="decision.status || '—'" :tone="statusTone(decision.status)" />
          <MetricCard label="最终动作" :value="decision.final_action || '—'" :tone="actionTone(decision.final_action)" />
          <MetricCard label="目标仓位" :value="decision.final_position_pct != null ? decision.final_position_pct + '%' : '—'" tone="text-white" />
        </div>

        <div v-if="decision.confidence != null" class="mt-3 text-xs text-slate-500">
          决策置信度：<span class="text-slate-300">{{ decision.confidence }}</span>
        </div>

        <div v-if="decision.rejection_reason" class="mt-4 rounded-xl border border-rose-400/20 bg-rose-400/5 p-4">
          <p class="text-xs text-rose-300">拒绝原因</p>
          <p class="mt-1 text-sm text-rose-200">{{ decision.rejection_reason }}</p>
        </div>

        <div v-if="decision.conditions && decision.conditions.length" class="mt-4">
          <p class="text-xs text-slate-400">通过条件</p>
          <ul class="mt-2 space-y-1.5">
            <li v-for="(c, i) in decision.conditions" :key="i" class="flex items-start gap-2 text-sm text-slate-300">
              <span class="mt-0.5 text-emerald-300">✓</span>
              <span>{{ c }}</span>
            </li>
          </ul>
        </div>

        <div v-if="decision.rationale_chain && decision.rationale_chain.length" class="mt-4">
          <p class="text-xs text-slate-400">理由链</p>
          <ol class="mt-2 space-y-1.5">
            <li v-for="(r, i) in decision.rationale_chain" :key="i" class="flex items-start gap-2 text-sm text-slate-300">
              <span class="mt-0.5 font-mono text-xs text-indigo-300">{{ i + 1 }}.</span>
              <span>{{ r }}</span>
            </li>
          </ol>
        </div>
      </SectionCard>

      <details class="space-y-5">
        <summary class="glass cursor-pointer rounded-2xl p-5 text-base font-semibold text-white">查看研究过程 <span class="ml-2 text-sm font-normal text-slate-400">分析报告、多空辩论与过程日志</span></summary>
        <!-- 分析师报告 -->
        <SectionCard title="分析师报告" hint="各专职分析师围绕各自维度独立研判，给出评分与置信度">
          <EmptyState v-if="!analysts.length" text="暂无分析师报告" />
          <div v-else class="grid gap-4 lg:grid-cols-2">
            <div v-for="(a, i) in analysts" :key="i" class="rounded-xl border border-white/10 bg-white/5 p-4">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <p class="text-sm font-semibold text-white">{{ a.dimension || '分析师' }}</p>
                <div class="flex items-center gap-2 text-xs">
                  <span class="text-slate-400">评分</span>
                  <span class="font-bold text-indigo-300">{{ a.score ?? '—' }}</span>
                  <span class="text-slate-500">·</span>
                  <span class="text-slate-400">置信度</span>
                  <span class="font-bold text-slate-300">{{ a.confidence ?? '—' }}</span>
                </div>
              </div>
              <p v-if="a.summary" class="mt-2 text-sm text-slate-300">{{ a.summary }}</p>
              <div v-if="a.key_findings && a.key_findings.length" class="mt-3">
                <p class="text-xs text-slate-400">关键发现</p>
                <ul class="mt-1.5 space-y-1">
                  <li v-for="(k, j) in a.key_findings" :key="j" class="flex items-start gap-2 text-sm text-slate-300">
                    <span class="mt-0.5 text-indigo-300">•</span>
                    <span>{{ k }}</span>
                  </li>
                </ul>
              </div>
              <div v-if="a.risks && a.risks.length" class="mt-3">
                <p class="text-xs text-amber-300">风险</p>
                <ul class="mt-1.5 space-y-1">
                  <li v-for="(r, j) in a.risks" :key="j" class="flex items-start gap-2 text-sm text-slate-300">
                    <span class="mt-0.5 text-amber-300">⚠</span>
                    <span>{{ r }}</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </SectionCard>

        <!-- 多空辩论 -->
        <SectionCard title="多空辩论" hint="多方与空方智能体逐轮交锋，收敛分歧">
          <EmptyState v-if="!debate.length" text="本轮未开启辩论" />
          <div v-else class="space-y-4">
            <div v-for="(d, i) in debate" :key="i" class="rounded-xl border border-white/10 bg-white/5 p-4">
              <p class="mb-3 text-sm font-semibold text-white">第 {{ d.round ?? i + 1 }} 轮</p>
              <div class="grid gap-3 md:grid-cols-2">
                <div class="rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-3">
                  <p class="text-xs text-emerald-300">多方论点</p>
                  <p class="mt-1.5 text-sm text-slate-300">{{ d.bull || '—' }}</p>
                </div>
                <div class="rounded-xl border border-rose-400/20 bg-rose-400/5 p-3">
                  <p class="text-xs text-rose-300">空方论点</p>
                  <p class="mt-1.5 text-sm text-slate-300">{{ d.bear || '—' }}</p>
                </div>
              </div>
              <div v-if="d.bull_reply" class="mt-3 rounded-xl border border-indigo-400/20 bg-indigo-400/5 p-3">
                <p class="text-xs text-indigo-300">多方回应</p>
                <p class="mt-1.5 text-sm text-slate-300">{{ d.bull_reply }}</p>
              </div>
              <div v-if="d.bear_reply" class="mt-3 rounded-xl border border-indigo-400/20 bg-indigo-400/5 p-3">
                <p class="text-xs text-indigo-300">空方回应</p>
                <p class="mt-1.5 text-sm text-slate-300">{{ d.bear_reply }}</p>
              </div>
              <div v-if="d.bull_summary || d.bear_summary" class="mt-3 grid gap-3 md:grid-cols-2">
                <div v-if="d.bull_summary" class="text-sm">
                  <p class="text-xs text-emerald-300">多方总结</p>
                  <p class="mt-1 text-slate-300">{{ d.bull_summary }}</p>
                </div>
                <div v-if="d.bear_summary" class="text-sm">
                  <p class="text-xs text-rose-300">空方总结</p>
                  <p class="mt-1 text-slate-300">{{ d.bear_summary }}</p>
                </div>
              </div>
            </div>
          </div>
        </SectionCard>

        <!-- Trader 提案 / 风控评估 / 模拟成交 -->
        <div class="grid gap-5 lg:grid-cols-3">
          <SectionCard title="交易提案" hint="交易员给出的执行提案（止损/目标价仅供研究参考）">
            <dl class="space-y-2.5 text-sm">
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">动作</dt>
                <dd><StatusPill :value="proposal.action || '—'" /></dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">目标仓位</dt>
                <dd class="text-slate-300">{{ proposal.position_pct != null ? proposal.position_pct + '%' : '—' }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">置信度</dt>
                <dd class="text-slate-300">{{ proposal.confidence ?? '—' }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">止损价</dt>
                <dd class="text-slate-300">{{ proposal.stop_loss ?? '—' }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">目标价</dt>
                <dd class="text-slate-300">{{ proposal.target_price ?? '—' }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">持有期</dt>
                <dd class="text-slate-300">{{ proposal.holding_period ?? '—' }}</dd>
              </div>
            </dl>
            <p v-if="proposal.reason" class="mt-3 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-300">{{ proposal.reason }}</p>
          </SectionCard>

          <SectionCard title="风控评估" hint="风险管理智能体对提案的核查">
            <div class="mb-3 flex items-center justify-between">
              <span class="text-xs text-slate-400">是否否决</span>
              <StatusPill :value="risk.vetoed ? '拒绝' : (risk.vetoed === false ? '批准' : '—')" />
            </div>
            <dl class="space-y-2.5 text-sm">
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">波动率</dt>
                <dd class="text-slate-300">{{ risk.volatility ?? '—' }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">预估最大回撤</dt>
                <dd class="text-rose-300">{{ risk.est_max_drawdown ?? '—' }}</dd>
              </div>
            </dl>
            <div v-if="risk.veto_reason" class="mt-3 rounded-xl border border-rose-400/20 bg-rose-400/5 p-3">
              <p class="text-xs text-rose-300">否决原因</p>
              <p class="mt-1 text-sm text-rose-200">{{ risk.veto_reason }}</p>
            </div>
            <div v-if="risk.conditions && risk.conditions.length" class="mt-3">
              <p class="text-xs text-slate-400">风控条件</p>
              <ul class="mt-1.5 space-y-1">
                <li v-for="(c, i) in risk.conditions" :key="i" class="flex items-start gap-2 text-sm text-slate-300">
                  <span class="mt-0.5 text-slate-500">•</span>
                  <span>{{ c }}</span>
                </li>
              </ul>
            </div>
            <p v-if="risk.comment" class="mt-3 text-sm text-slate-400">{{ risk.comment }}</p>
          </SectionCard>

          <SectionCard title="模拟成交" hint="按提案撮合的模拟成交回报（T+1 语义，仅供核对）">
            <dl class="space-y-2.5 text-sm">
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">动作</dt>
                <dd><StatusPill :value="fill.action || '—'" /></dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">数量</dt>
                <dd class="text-slate-300">{{ fill.quantity ?? '—' }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">成交价</dt>
                <dd class="text-slate-300">{{ fill.price ?? '—' }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">基准价</dt>
                <dd class="text-slate-300">{{ fill.benchmark_price ?? '—' }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">手续费</dt>
                <dd class="text-slate-300">{{ fill.fee ?? '—' }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs text-slate-400">结算</dt>
                <dd class="text-slate-300">{{ fill.settle ?? '—' }}</dd>
              </div>
            </dl>
          </SectionCard>
        </div>

        <!-- 分析过程 -->
        <SectionCard title="分析过程" hint="多智能体协作的逐步日志">
          <EmptyState v-if="!traceLog.length" text="暂无过程日志" />
          <ul v-else class="max-h-80 space-y-2 overflow-y-auto pr-1">
            <li
              v-for="(t, i) in traceLog"
              :key="i"
              class="flex items-start gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-300"
              :class="String(traceText(t)).includes('失败') ? 'border-rose-400/30' : ''"
            >
              <span class="mt-0.5 font-mono text-xs text-indigo-300">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="whitespace-pre-wrap break-words">{{ traceText(t) }}</span>
            </li>
          </ul>
        </SectionCard>
      </details>
    </template>

    <!-- 与 AI 对话交锋 -->
    <SectionCard v-if="result" title="继续追问" hint="运行分析后，带着完整分析上下文向 AI 追问、提出观点或质疑它的结论">
      <div ref="chatBox" class="max-h-96 space-y-3 overflow-y-auto rounded-xl border border-white/10 bg-white/5 p-4">
        <div v-if="!chat.length" class="py-6 text-center text-sm text-slate-500">
          {{ result ? '开始一段对话，向 AI 提出你的疑问或挑战。' : '请先运行一次分析，交锋时 AI 会引用完整的分析上下文。' }}
        </div>
        <div v-for="(m, i) in chat" :key="i" class="flex" :class="m.role === 'user' ? 'justify-end' : 'justify-start'">
          <div
            class="max-w-[80%] rounded-2xl px-4 py-2.5 text-sm"
            :class="
              m.role === 'user'
                ? 'rounded-br-md bg-gradient-to-r from-indigo-500 to-violet-500 text-white'
                : m.error
                  ? 'rounded-bl-md border border-rose-400/20 bg-rose-400/10 text-rose-200'
                  : 'rounded-bl-md border border-white/10 bg-white/10 text-slate-200'
            "
          >
            <p class="mb-0.5 text-[10px] uppercase tracking-wide opacity-70">{{ m.role === 'user' ? '你' : 'AI' }}</p>
            <p class="whitespace-pre-wrap break-words">{{ m.text }}</p>
          </div>
        </div>
      </div>
      <div class="mt-3 flex gap-2">
        <input
          v-model="chatInput"
          @keyup.enter="onBattle"
          placeholder="输入你的观点或质疑…"
          class="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
        />
        <button
          @click="onBattle"
          :disabled="running || battling || !chatInput.trim()"
          class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
        >
          {{ battling ? '回复中…' : '发送' }}
        </button>
      </div>
    </SectionCard>
  </div>
</template>
