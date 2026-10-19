<script setup>
import { computed } from 'vue'
import { openResearch } from '../researchNavigation.js'
import { evidenceText, oddsDisagree, TILT_NOTE, tiltLabel, tiltTone } from '../aiPresentation.js'
import { assessmentTone, confidenceLabel, distributionRows, isDetailedReport, probabilityLabel, reportSummary } from '../jevReportPresentation.js'

const props = defineProps({
  report: { type: Object, required: true },
  tradeDate: { type: String, default: '' },
  textTilt: { type: String, default: '' },
  upgrading: { type: Boolean, default: false },
  canUpgrade: { type: Boolean, default: false },
  remaining: { type: Number, default: null },
})
defineEmits(['upgrade'])
const detailed = computed(() => isDetailedReport(props.report))
const rows = computed(() => distributionRows(Object.fromEntries(['偏多', '中性', '偏空'].map(label => [label, props.report.probabilities?.[label]]))))
const date = computed(() => props.report.as_of || props.tradeDate)
const disagree = computed(() => oddsDisagree(props.report, props.textTilt))
</script>

<template>
  <section class="overflow-hidden rounded-2xl border border-indigo-400/20 bg-gradient-to-br from-indigo-500/[0.07] via-white/[0.03] to-transparent" aria-label="Jev 分析报告">
    <header class="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4 sm:px-6">
      <div>
        <h3 class="text-base font-semibold text-white">Jev 分析报告</h3>
        <p class="mt-1 text-xs text-slate-400">数据截至 {{ date }}<span v-if="report.model"> · {{ report.model }}</span> · 基于本次保存的数据</p>
      </div>
      <span class="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-400">{{ detailed ? '分项报告' : '历史简版' }}</span>
    </header>

    <div class="space-y-6 p-5 sm:p-6">
      <div class="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div class="min-w-0">
          <p class="text-xs font-medium text-slate-400">综合判断</p>
          <div class="mt-3 flex flex-wrap items-center gap-3">
            <span class="rounded-xl border px-4 py-2 text-xl font-semibold" :class="tiltTone(report.choice)">{{ tiltLabel(report.choice) }}</span>
            <div class="text-sm text-slate-300">
              <p>模型置信度 <span class="font-semibold text-white">{{ confidenceLabel(report.confidence) }}</span> · {{ probabilityLabel(report.confidence) }}</p>
              <p class="mt-0.5 text-xs text-slate-500">反映模型对分类的把握程度</p>
            </div>
          </div>
          <p class="mt-2 text-xs text-slate-500">{{ TILT_NOTE }}</p>
          <p class="mt-4 text-base leading-relaxed text-slate-200">{{ reportSummary(report) }}</p>
          <p v-if="disagree" class="mt-2 text-sm text-amber-200">Jev 与文字解读的倾向不同，说明对同一份数据的判断存在分歧。</p>
          <p class="mt-3 text-xs leading-relaxed text-slate-500">概率表示对三类倾向的判断，不是未来涨跌幅或获利概率。说明文字由结构化结果整理，不是模型生成的推理过程。</p>
        </div>

        <div class="rounded-xl border border-white/10 bg-black/10 p-4">
          <h4 class="text-sm font-medium text-slate-300">三种倾向的概率</h4>
          <ul class="mt-4 space-y-4">
            <li v-for="row in rows" :key="row.label">
              <div class="mb-1.5 flex justify-between text-sm"><span class="text-slate-300">{{ tiltLabel(row.label) }}<span v-if="row.label === report.choice" class="ml-2 text-xs text-slate-500">本次判断</span></span><span class="font-medium text-white">{{ row.text }}</span></div>
              <div class="h-2 overflow-hidden rounded-full bg-white/10" aria-hidden="true"><div class="h-full rounded-full bg-indigo-400" :style="{ width: row.width }" /></div>
            </li>
          </ul>
        </div>
      </div>

      <div v-if="!detailed" class="rounded-xl border border-indigo-400/20 bg-indigo-500/5 p-4">
        <p class="text-sm text-slate-300">这是一条历史简版判断，尚未评估各个维度。可以使用当时保存的数据补全报告。</p>
        <button v-if="canUpgrade" type="button" :disabled="upgrading || remaining === 0" class="mt-3 rounded-full border border-indigo-400/40 bg-indigo-500/10 px-4 py-2 text-sm text-indigo-200 disabled:opacity-50" @click="$emit('upgrade')">
          {{ upgrading ? '正在补全报告…' : remaining === 0 ? '今天的评估额度已用完' : '补全分项报告 · 使用 1 次评估' }}
        </button>
        <p v-else class="mt-2 text-xs text-slate-500">平台配置 Jev 后可以补全；当前保存的判断仍可查看。</p>
      </div>

      <template v-else>
        <div class="grid gap-3 sm:grid-cols-3">
          <div class="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p class="text-xs text-slate-400">本次可评估的维度</p>
            <p class="mt-2 text-xl font-semibold text-white">{{ report.coverage.evaluated }} <span class="text-sm font-normal text-slate-500">/ {{ report.coverage.total }}</span></p>
            <p class="mt-1 text-xs text-slate-500">缺少必要依据时不作判断</p>
          </div>
          <div class="rounded-xl border border-emerald-400/10 bg-emerald-500/[0.03] p-4">
            <p class="text-xs text-slate-400">相对有利的线索</p>
            <p class="mt-2 text-sm leading-relaxed text-emerald-200">{{ report.supports.length ? report.supports.join('、') : '本次没有分项被判断为“支持”' }}</p>
          </div>
          <div class="rounded-xl border border-amber-400/10 bg-amber-500/[0.03] p-4">
            <p class="text-xs text-slate-400">需要优先留意</p>
            <p class="mt-2 text-sm leading-relaxed text-amber-200">{{ report.concerns.length ? report.concerns.join('、') : '已评估分项中未标出需留意项；其余维度仍可能存在风险' }}</p>
          </div>
        </div>

        <div>
          <div class="flex flex-wrap items-baseline justify-between gap-2"><h4 class="text-sm font-semibold text-white">分项判断与数据依据</h4><p class="text-xs text-slate-500">依据展示输入事实，不代表综合结论的因果解释</p></div>
          <div class="mt-3 grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
            <article v-for="item in report.dimensions" :key="item.key" class="min-w-0 rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div class="flex items-start justify-between gap-2"><h5 class="text-sm font-semibold text-slate-200">{{ item.title }}</h5><span class="shrink-0 rounded-full border px-2 py-0.5 text-xs" :class="assessmentTone(item.assessment)">{{ item.assessment }}</span></div>
              <p class="mt-1 text-xs text-slate-500">{{ item.description }}</p>
              <p class="mt-3 text-sm leading-relaxed text-slate-300">{{ item.interpretation }}</p>
              <p v-if="item.confidence != null" class="mt-2 text-xs text-slate-500">模型置信度 {{ probabilityLabel(item.confidence) }}（{{ confidenceLabel(item.confidence) }}）</p>
              <ul v-if="item.evidence.length" class="mt-3 space-y-1.5 border-t border-white/10 pt-3">
                <li v-for="fact in item.evidence.slice(0, 3)" :key="fact.key" class="break-words text-xs leading-relaxed text-slate-400">{{ evidenceText(fact, date) }}</li>
              </ul>
              <p v-else class="mt-3 text-xs text-slate-500">本次没有可用的对应数据。</p>
              <details v-if="item.evidence.length > 3 || Object.keys(item.probabilities).length" class="mt-3 text-xs text-slate-400">
                <summary class="w-fit cursor-pointer text-indigo-300">查看完整依据与概率</summary>
                <ul class="mt-2 space-y-1.5"><li v-for="fact in item.evidence.slice(3)" :key="fact.key">{{ evidenceText(fact, date) }}</li></ul>
                <div v-for="row in distributionRows(item.probabilities)" :key="row.label" class="mt-1.5 flex justify-between gap-3"><span>{{ row.label }}</span><span>{{ row.text }}</span></div>
              </details>
            </article>
          </div>
        </div>

        <div class="grid gap-4 lg:grid-cols-2">
          <div class="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h4 class="text-sm font-semibold text-white">当前可见的风险线索</h4>
            <template v-if="report.risk">
              <p class="mt-2 text-lg font-semibold text-slate-200">{{ report.risk.level }}</p>
              <p class="mt-1 text-xs text-slate-500">依据已有波动、回撤等线索评级，缺失的财务或估值风险不在判断范围内。</p>
              <details class="mt-3 text-xs text-slate-400"><summary class="w-fit cursor-pointer text-indigo-300">查看风险等级分布</summary><div v-for="row in distributionRows(report.risk.probabilities)" :key="row.label" class="mt-2 flex justify-between gap-3"><span>{{ row.label }}</span><span>{{ row.text }}</span></div></details>
            </template>
            <p v-else class="mt-2 text-sm text-slate-400">缺少波动或回撤数据，暂不给出风险等级。</p>
          </div>
          <div class="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h4 class="text-sm font-semibold text-white">接下来核查什么</h4>
            <ol class="mt-3 space-y-3"><li v-for="(item, index) in report.followups" :key="item.title" class="flex gap-3"><span class="mt-0.5 text-xs text-indigo-300">{{ index + 1 }}.</span><div><p class="text-sm text-slate-200">{{ item.title }}</p><p class="mt-1 text-xs leading-relaxed text-slate-400">{{ item.text }}</p><button v-if="item.action === 'data-update'" type="button" class="mt-1 text-xs text-indigo-300 hover:text-indigo-200" @click="openResearch('data-guide')">看平台有哪些数据 →</button></div></li></ol>
          </div>
        </div>

        <details v-if="report.coverage.missing.length || report.coverage.notes.length" class="rounded-xl border border-amber-400/15 bg-amber-500/[0.03] p-4">
          <summary class="cursor-pointer text-sm text-amber-200">数据缺口与适用范围<span v-if="report.coverage.missing.length"> · {{ report.coverage.missing.length }} 项数据缺口</span></summary>
          <ul class="mt-3 space-y-2 text-xs leading-relaxed text-slate-400"><li v-for="item in report.coverage.missing" :key="item.group + item.reason"><span class="text-slate-300">{{ item.group }}：</span>{{ item.reason }}</li><li v-for="note in report.coverage.notes" :key="note">{{ note }}</li></ul>
        </details>
        <p class="text-xs text-slate-500">以上结果基于历史数据，仅供研究参考。</p>
      </template>
    </div>
  </section>
</template>
