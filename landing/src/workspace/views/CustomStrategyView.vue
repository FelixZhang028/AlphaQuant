<script setup>
import { ref } from 'vue'
import {
  previewUserStrategy,
  saveUserStrategy,
} from '../../api.js'
import StrategySaved from '../ui/StrategySaved.vue'
import { openResearch } from '../researchNavigation.js'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const DEFAULT_CODE = "\"\"\"我的自定义策略（示例：双均线 + 动量排序）。\n\n使用说明：\n1. 继承 BaseStrategy，并用 @register_strategy(\"唯一英文标识\") 注册；\n2. 在 __init__ 里声明带默认值的参数，平台会自动生成网页参数表单；\n3. 重写 generate_signals，通过 context.history() 只读取截至当天的数据；\n4. 返回 Signal 列表，score 越大的股票越优先入选。\n\n常用行情字段（可在 required_fields 之外通过 context.history 使用）：\nadjusted_close（前复权收盘）、raw_close/raw_high/raw_low（未复权）、amount（成交额）、\nvolume（成交量）、up_limit/down_limit（涨跌停）、is_suspended、is_st 等。\n\"\"\"\n\nimport pandas as pd\n\nfrom quant_platform.signals.models import Signal\nfrom quant_platform.strategies.context import StrategyContext\nfrom quant_platform.user_strategies import BaseStrategy, register_strategy\n\n\n@register_strategy(\n    \"my_ma_momentum\",\n    display_name=\"我的双均线动量\",\n    description=\"价格站上快线且快线高于慢线时，按近期动量排序选股\",\n)\nclass MyStrategy(BaseStrategy):\n    # 策略需要哪些行情字段（平台会在运行前校验数据是否满足）\n    required_fields = frozenset({\"symbol\", \"trade_date\", \"adjusted_close\", \"amount\"})\n\n    # 可选：给参数更友好的网页标签、取值范围和说明\n    param_specs = {\n        \"fast\": {\"label\": \"快速均线（日）\", \"min\": 2, \"max\": 60},\n        \"slow\": {\"label\": \"慢速均线（日）\", \"min\": 5, \"max\": 250},\n        \"momentum\": {\"label\": \"动量窗口（日）\", \"min\": 2, \"max\": 120},\n    }\n\n    def __init__(self, fast: int = 5, slow: int = 20, momentum: int = 20):\n        self.fast = fast\n        self.slow = slow\n        self.momentum = momentum\n\n    def generate_signals(self, context: StrategyContext) -> list[Signal]:\n        history = context.history(\n            fields=[\"adjusted_close\", \"amount\"],\n            lookback=max(self.slow, self.momentum) + 1,\n        )\n        signals: list[Signal] = []\n        cutoff = pd.Timestamp(context.trade_date)\n        for symbol, group in history.groupby(\"symbol\"):\n            group = group.sort_values(\"trade_date\")\n            if group.empty or pd.Timestamp(group.iloc[-1][\"trade_date\"]) != cutoff:\n                continue\n            close = pd.to_numeric(group[\"adjusted_close\"], errors=\"coerce\").dropna()\n            if len(close) < self.slow + 1:\n                continue\n            fast_ma = float(close.tail(self.fast).mean())\n            slow_ma = float(close.tail(self.slow).mean())\n            current = float(close.iloc[-1])\n            if not (current > fast_ma > slow_ma):\n                continue\n            base = float(close.iloc[-self.momentum - 1])\n            if base <= 0:\n                continue\n            signals.append(\n                Signal(\n                    strategy_id=self.strategy_id,\n                    trade_date=context.trade_date,\n                    symbol=str(symbol),\n                    signal_type=\"MY_MA_MOMENTUM\",\n                    score=current / base - 1.0,\n                )\n            )\n        return sorted(signals, key=lambda signal: -signal.score)\n"
const savedAsset = ref(null)

// ---------- 编写策略 ----------
const code = ref(DEFAULT_CODE)
const displayName = ref('')
const description = ref('')
const riskAck = ref(false)
const saving = ref(false)
const warnings = ref([])


async function onSave() {
  if (!displayName.value.trim()) return props.notify('请输入策略显示名')
  if (!riskAck.value) return props.notify('请先勾选风险确认')

  saving.value = true
  warnings.value = []
  try {
    const payload = {
      code: code.value,
      display_name: displayName.value.trim(),
      description: description.value,
      source: 'editor',
      risk_acknowledged: riskAck.value,
    }
    const preview = await previewUserStrategy(payload)
    if (preview?.safety_report?.blocked) {
      const blockers = preview.safety_report.blockers || []
      const msg = blockers.map((b) => b.message || '存在安全风险').join('\n')
      return props.notify(msg || '代码未通过安全校验')
    }
    warnings.value = preview?.safety_report?.warnings || []
    savedAsset.value = await saveUserStrategy(payload)
    props.notify('已保存')
    displayName.value = ''
    description.value = ''
    riskAck.value = false
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass glass-sheen rounded-2xl p-6">
      <button class="mb-3 text-sm text-indigo-300" @click="openResearch('strategy-hub')">← 返回我的策略</button>
      <h1 class="text-xl font-bold text-white">自定义策略（Python）</h1>
      <p class="mt-1 text-sm text-slate-400">编写并校验策略代码，保存后到统一回测页配置与运行。</p>
    </div>

    <!-- 高级模式警告 -->
    <div class="rounded-2xl border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-200">
      高级模式：会运行你自己编写的 Python 代码
    </div>

    <StrategySaved v-if="savedAsset" :asset="savedAsset" />

    <!-- 编写策略 -->
    <section class="glass rounded-2xl p-5">
      <h2 class="text-sm font-semibold text-white">编写策略</h2>
      <p class="mt-0.5 text-xs text-slate-500">在下方编辑 Python 代码，保存后平台自动解析参数并生成表单。</p>

      <div class="mt-4 space-y-4">
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">策略代码</span>
          <textarea
            v-model="code"
            rows="16"
            spellcheck="false"
            class="w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 font-mono text-xs leading-relaxed text-indigo-100 outline-none focus:border-indigo-400/40"
          ></textarea>
        </label>

        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">策略显示名</span>
          <input
            v-model="displayName"
            placeholder="如：双均线策略"
            class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
          />
        </label>

        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">策略说明</span>
          <textarea
            v-model="description"
            rows="3"
            placeholder="简要说明策略逻辑、适用市场与风险"
            class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
          ></textarea>
        </label>

        <label class="flex items-start gap-2.5">
          <input
            v-model="riskAck"
            type="checkbox"
            class="mt-0.5 h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500"
          />
          <span class="text-sm text-slate-300">我已阅读并确认：该代码将在平台沙箱中运行，我对其行为负责。</span>
        </label>

        <div v-if="warnings.length" class="rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-xs text-amber-200">
          <p v-for="(w, i) in warnings" :key="i">{{ w.message || w }}</p>
        </div>

        <button
          @click="onSave"
          :disabled="saving"
          class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
        >
          {{ saving ? '校验并保存中…' : '注册并保存' }}
        </button>
      </div>
    </section>

    <!-- 安全边界说明 -->
    <p class="text-xs text-slate-500">
      安全边界：自定义代码在本地进程内运行，仅运行可信代码；平台会基于 <code class="font-mono text-slate-400">@register_strategy</code> 装饰器与 <code class="font-mono text-slate-400">__init__</code> 参数自动生成策略表单，请勿在代码中写入敏感信息。
    </p>
  </div>
</template>
