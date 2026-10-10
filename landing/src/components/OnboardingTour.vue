<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  user: { type: Object, default: null },
})
const emit = defineEmits(['close'])

// 引导步骤：对应工作台核心使用流程
const steps = [
  {
    icon: '📊',
    title: '第 1 步 · 下载数据',
    text: '进入「数据更新」页面，点击「开始更新」下载 A 股日线行情与交易日历。回测和因子研究都依赖本地数据。',
    view: 'data-update',
    viewLabel: '去数据更新',
  },
  {
    icon: '🗂️',
    title: '第 2 步 · 设置股票池',
    text: '在「股票池管理」中挑选你关注的股票（支持按名称/代码搜索）。股票池决定了回测和因子评估的选股范围。',
    view: 'universe',
    viewLabel: '去股票池管理',
  },
  {
    icon: '🧪',
    title: '第 3 步 · 研究因子',
    text: '在「因子研究」了解因子、评估单因子，再用训练与测试区间研究组合。自定义因子从「新建因子」进入。',
    view: 'factor-lab',
    viewLabel: '去因子研究',
  },
  {
    icon: '🧩',
    title: '第 4 步 · 搭建策略',
    text: '进入「我的策略」，在「新建策略」区域选择模板、可视化规则、自然语言或 Python。保存后再去回测。',
    view: 'strategy-hub',
    viewLabel: '去我的策略',
  },
  {
    icon: '🚀',
    title: '第 5 步 · 回测验证',
    text: '在「回测与验证」提交回测，查看资金曲线、收益指标、成交明细与持仓分析，检验策略效果。',
    view: 'backtest-review',
    viewLabel: '去回测页面',
  },
  {
    icon: '💡',
    title: '更多能力',
    text: '「研究记录」可比较历史结果、继续研究。参数优化与样本外验证目前为模拟预览；审计位于回测结果，成交核查位于高级工具。顶栏 ? 可重新打开引导。',
    view: null,
    viewLabel: '',
  },
]

const current = ref(0)
const step = computed(() => steps[current.value])
const progress = computed(() => Math.round(((current.value + 1) / steps.length) * 100))

function next() {
  if (current.value < steps.length - 1) current.value += 1
  else emit('close')
}

function prev() {
  if (current.value > 0) current.value -= 1
}

function goto(view) {
  emit('close')
  // 通过 URL 参数让外壳切换视图（保持与落地页导航一致的机制）
  window.location.href = `/app.html?view=${view}`
}
</script>

<template>
  <div class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" @click.self="emit('close')">
    <div class="glass glass-sheen relative w-full max-w-lg overflow-hidden rounded-2xl">
      <!-- 步骤进度 -->
      <div class="h-1 w-full bg-white/5">
        <div class="h-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-300" :style="{ width: `${progress}%` }" />
      </div>

      <div class="p-6 sm:p-8">
        <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
          新手引导 · {{ current + 1 }} / {{ steps.length }}
        </p>

        <div class="mt-4 flex items-start gap-4">
          <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500/25 to-violet-500/15 text-2xl ring-1 ring-inset ring-white/10">{{ step.icon }}</span>
          <div>
            <h2 class="text-lg font-bold text-white">{{ step.title }}</h2>
            <p class="mt-2 text-sm leading-relaxed text-slate-400">{{ step.text }}</p>
          </div>
        </div>

        <div class="mt-7 flex items-center justify-between">
          <button
            class="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-400 transition hover:bg-white/5 hover:text-slate-200"
            @click="emit('close')"
          >跳过引导</button>

          <div class="flex items-center gap-2">
            <button
              v-if="current > 0"
              class="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/5"
              @click="prev"
            >上一步</button>
            <button
              v-if="step.view"
              class="rounded-full border border-indigo-400/30 bg-indigo-500/10 px-4 py-2 text-sm text-indigo-200 transition hover:bg-indigo-500/20"
              @click="goto(step.view)"
            >{{ step.viewLabel }}</button>
            <button
              class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5"
              @click="next"
            >{{ current === steps.length - 1 ? '开始使用' : '下一步' }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
