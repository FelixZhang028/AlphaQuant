<script setup>
// 设置：外观、研究默认值、今天的 AI 次数、我的数据（含导出）、账户、关于；管理员另外能配置平台的知识库服务。
import { computed, onActivated, reactive, ref } from 'vue'
import { exportMyData, getPreferences, getRisk, getUniverse, savePreferences, todayUsage } from '../../api.js'
import { useTheme } from '../../theme.js'
import { CONTACT_EMAIL } from '../../legal/legalContent.js'
import { PERIOD_OPTIONS, REBALANCE_OPTIONS } from '../preferences.js'
import SectionCard from '../ui/SectionCard.vue'
import KnowledgeBaseView from './KnowledgeBaseView.vue'

const props = defineProps({ user: { type: Object, default: null }, notify: { type: Function, default: () => {} } })

const VERSION = '1.0.0'
const GITHUB = 'https://github.com/FelixZhang028/Prismind'
const contactEmail = CONTACT_EMAIL.startsWith('【') ? '' : CONTACT_EMAIL   // 法律文件里还没填时不显示

function navigate(key) {
  window.dispatchEvent(new CustomEvent('fq-navigate', { detail: key }))
}

// ---------- 外观 ----------
const { mode, setMode } = useTheme()
const themes = [
  { value: 'system', label: '跟随系统' },
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
]
function openTour() {
  window.dispatchEvent(new CustomEvent('fq-open-tour'))
}

// ---------- 研究默认值 ----------
const form = reactive({ initial_capital: 1000000, max_positions: 10, rebalance: 'weekly', period_years: 1, use_experience: true })
const defaults = ref(null)
const saving = ref(false)
const formError = ref('')
function validate() {
  const capital = Number(form.initial_capital)
  if (!Number.isFinite(capital) || capital < 10000 || capital > 100000000) return '初始资金要在 1 万到 1 亿元之间'
  const positions = Number(form.max_positions)
  if (!Number.isInteger(positions) || positions < 1 || positions > 50) return '最多持仓要在 1 到 50 只之间'
  return ''
}
async function save() {
  formError.value = validate()
  if (formError.value) return
  saving.value = true
  try {
    const data = await savePreferences({ ...form, initial_capital: Number(form.initial_capital), max_positions: Number(form.max_positions) })
    Object.assign(form, data.preferences)
    props.notify('已保存，下次打开回测和 AI 研究员时生效')
  } catch (e) {
    formError.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}
function restoreDefaults() {
  if (defaults.value) Object.assign(form, defaults.value)
  formError.value = ''
}

// ---------- 今天的 AI 次数 ----------
const usage = ref(null)

// ---------- 我的数据 ----------
const universe = ref(null)
const risk = ref(null)
const exporting = ref(false)
const universeText = computed(() => {
  if (!universe.value) return '—'
  const f = universe.value.filters || {}
  const rules = [f.exclude_st && '排除 ST', f.exclude_suspended && '排除停牌', f.minimum_listing_days && `上市满 ${f.minimum_listing_days} 天`].filter(Boolean)
  return `${universe.value.symbols?.length ?? 0} 只股票${rules.length ? ` · ${rules.join('、')}` : ''}`
})
const riskText = computed(() => {
  const r = risk.value
  if (!r) return '—'
  if (!r.enabled) return '没有开启'
  return `单只最多 ${Math.round(r.max_single_weight * 100)}% · 最多 ${r.max_positions} 只 · 回撤超过 ${Math.round(r.max_drawdown * 100)}% 时${r.drawdown_action === 'reduce' ? '自动降低仓位' : '停止新开仓'}`
})
async function download() {
  exporting.value = true
  try {
    const { blob, name } = await exportMyData()
    const url = URL.createObjectURL(blob)
    const link = Object.assign(document.createElement('a'), { href: url, download: name })
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    props.notify('已开始下载')
  } catch (e) {
    props.notify(e.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

onActivated(async () => {
  const [p, u, uni, r] = await Promise.allSettled([getPreferences(), todayUsage(), getUniverse(), getRisk()])
  if (p.status === 'fulfilled') {
    Object.assign(form, p.value.preferences)
    defaults.value = p.value.defaults
  }
  if (u.status === 'fulfilled') usage.value = u.value
  if (uni.status === 'fulfilled') universe.value = uni.value
  if (r.status === 'fulfilled') risk.value = r.value
})

const inputClass = 'mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/50'
const pill = (active) => active ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 bg-white/5 text-slate-300 hover:border-white/25'
</script>

<template>
  <div class="space-y-6">
    <SectionCard title="外观">
      <div class="flex flex-wrap items-center gap-2" role="group" aria-label="主题">
        <span class="mr-2 text-sm text-slate-400">主题</span>
        <button v-for="t in themes" :key="t.value" type="button" class="rounded-full border px-4 py-1.5 text-sm transition" :class="pill(mode === t.value)"
          :aria-pressed="mode === t.value" @click="setMode(t.value)">{{ t.label }}</button>
      </div>
      <div class="mt-4 flex flex-wrap items-center gap-3">
        <span class="text-sm text-slate-400">新手引导</span>
        <button type="button" class="rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-sm text-slate-300 hover:border-white/25" @click="openTour">重新打开</button>
      </div>
    </SectionCard>

    <SectionCard title="研究默认值" hint="打开回测和 AI 研究员时自动填好，每次仍可以临时修改；保存在账户里，换电脑也在">
      <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
        <label class="text-xs text-slate-400">回测初始资金（元）<input v-model="form.initial_capital" type="number" min="10000" max="100000000" step="10000" :class="inputClass" /></label>
        <label class="text-xs text-slate-400">最多持仓（只）<input v-model="form.max_positions" type="number" min="1" max="50" step="1" :class="inputClass" /></label>
        <label class="text-xs text-slate-400">调仓频率
          <select v-model="form.rebalance" :class="inputClass"><option v-for="o in REBALANCE_OPTIONS" :key="o.value" :value="o.value" class="bg-ink">{{ o.label }}</option></select>
        </label>
        <label class="text-xs text-slate-400">回测区间
          <select v-model.number="form.period_years" :class="inputClass"><option v-for="o in PERIOD_OPTIONS" :key="o.value" :value="o.value" class="bg-ink">{{ o.label }}（截止到今天）</option></select>
        </label>
        <label class="flex items-center gap-2 text-sm text-slate-300 sm:col-span-2">
          <input v-model="form.use_experience" type="checkbox" class="h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500" />
          AI 研究员分析时默认参考我的研究经验
        </label>
        <p class="text-xs text-slate-500 sm:col-span-2">所选策略自带持仓数和调仓频率时，以策略为准。</p>
        <p v-if="formError" role="alert" class="text-sm text-rose-300 sm:col-span-2">{{ formError }}</p>
        <div class="flex flex-wrap gap-3 sm:col-span-2">
          <button type="submit" :disabled="saving" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white disabled:opacity-50">{{ saving ? '保存中…' : '保存' }}</button>
          <button type="button" class="rounded-full border border-white/10 px-5 py-2 text-sm text-slate-300 hover:border-white/25" @click="restoreDefaults">恢复平台默认</button>
        </div>
      </form>
    </SectionCard>

    <SectionCard title="今天的 AI 次数" :hint="usage?.unlimited ? '管理员不限次数' : '每天北京时间 0 点重置'">
      <ul v-if="usage" class="grid gap-3 sm:grid-cols-2">
        <li v-for="item in usage.items" :key="item.kind" class="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm">
          <span class="text-slate-300">{{ item.label }}</span>
          <span v-if="item.limit == null" class="text-slate-400">已用 {{ item.used }} · 不限</span>
          <span v-else :class="item.remaining ? 'text-white' : 'text-amber-300'">还剩 {{ item.remaining }} / {{ item.limit }}</span>
        </li>
      </ul>
      <p v-else class="text-sm text-slate-500">加载中…</p>
    </SectionCard>

    <SectionCard title="我的数据">
      <dl class="grid gap-4 text-sm sm:grid-cols-2">
        <div class="rounded-xl border border-white/10 bg-white/5 p-4">
          <dt class="text-xs text-slate-400">股票池</dt>
          <dd class="mt-1 text-slate-200">{{ universeText }}</dd>
          <button type="button" class="mt-2 text-xs text-indigo-300 hover:text-indigo-200" @click="navigate('universe')">去修改 →</button>
        </div>
        <div class="rounded-xl border border-white/10 bg-white/5 p-4">
          <dt class="text-xs text-slate-400">风控设置</dt>
          <dd class="mt-1 text-slate-200">{{ riskText }}</dd>
          <button type="button" class="mt-2 text-xs text-indigo-300 hover:text-indigo-200" @click="navigate('backtest-review')">在回测页修改 →</button>
        </div>
      </dl>
      <div class="mt-4 flex flex-wrap items-center gap-3 border-t border-white/10 pt-4">
        <button type="button" :disabled="exporting" class="rounded-full border border-indigo-400/40 bg-indigo-500/10 px-5 py-2 text-sm text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50" @click="download">{{ exporting ? '正在导出…' : '导出我的数据' }}</button>
        <p class="text-xs text-slate-500">下载一个 JSON 文件：账户信息、策略、回测记录、AI 分析、研究经验和各项设置。不包含密码。</p>
      </div>
    </SectionCard>

    <SectionCard title="账户">
      <p class="text-sm text-slate-400">修改密码、退出登录、注销账户在个人中心。</p>
      <button type="button" class="mt-3 rounded-full border border-white/10 px-4 py-1.5 text-sm text-slate-300 hover:border-white/25" @click="navigate('account')">打开个人中心</button>
    </SectionCard>

    <SectionCard title="关于">
      <ul class="space-y-2 text-sm text-slate-300">
        <li>镜思 Prismind 版本 {{ VERSION }}</li>
        <li class="flex flex-wrap gap-x-4 gap-y-1">
          <a href="/legal.html#terms" target="_blank" class="text-indigo-300 hover:text-indigo-200">服务条款</a>
          <a href="/legal.html#privacy" target="_blank" class="text-indigo-300 hover:text-indigo-200">隐私政策</a>
          <a href="/legal.html#risk" target="_blank" class="text-indigo-300 hover:text-indigo-200">风险提示</a>
        </li>
        <li v-if="contactEmail">联系我们：<a :href="`mailto:${contactEmail}`" class="text-indigo-300 hover:text-indigo-200">{{ contactEmail }}</a></li>
        <li>问题反馈：<a :href="`${GITHUB}/issues/new/choose`" target="_blank" rel="noopener noreferrer" class="text-indigo-300 hover:text-indigo-200">在 GitHub 上提交</a></li>
      </ul>
      <p class="mt-3 text-xs text-slate-500">平台提供的数据、回测与分析结果仅供研究参考，不构成任何投资建议。</p>
    </SectionCard>

    <template v-if="user?.is_admin">
      <SectionCard title="平台设置（管理员）" hint="这里的设置对整个平台生效">
        <a href="/admin/" class="text-sm text-indigo-300 hover:text-indigo-200">打开管理后台：用户、注册与邀请码、数据运维 →</a>
      </SectionCard>
      <KnowledgeBaseView :user="user" :notify="notify" settings-only />
    </template>
  </div>
</template>
