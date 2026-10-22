<script setup>
// 选股条件和排序的表单：新建规则策略和条件选股共用。直接改传进来的 form（同一份表单）。
import { computed } from 'vue'
import { blankRule, chooseIndicator } from '../ruleForm.js'
import FormField from './FormField.vue'

const props = defineProps({
  form: { type: Object, required: true },
  options: { type: Object, required: true },   // studioOptions()：指标、判断方式、周期范围
})

const MAX_RULES = 10
const dirOptions = [{ value: 'descending', label: '从高到低' }, { value: 'ascending', label: '从低到高' }]
const logicOptions = [{ value: 'all', label: '全部满足' }, { value: 'any', label: '满足任意一条' }]
const compareOptions = [{ value: 'value', label: '一个数值' }, { value: 'indicator', label: '另一个指标' }]
const select = (mapping) => Object.entries(mapping || {}).map(([value, label]) => ({ value, label }))
const indicatorOptions = computed(() => select(props.options.indicators))
const operatorOptions = computed(() => select(props.options.operators))
const windowLimits = (name) => props.options.indicator_windows[name]

function addRule() {
  if (props.form.rules.length < MAX_RULES) props.form.rules.push(blankRule(props.options))
}
function removeRule(index) {
  if (props.form.rules.length > 1) props.form.rules.splice(index, 1)
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h3 class="text-sm font-semibold text-white">选股条件</h3>
        <p class="mt-1 text-xs text-slate-500">涨跌幅、回撤、波动率用小数填写：0.05 表示 5%。成交额的单位是元。</p>
      </div>
      <div class="w-44"><FormField label="多条条件之间" type="select" v-model="form.entry_logic" :options="logicOptions" /></div>
    </div>
    <ol class="mt-3 space-y-3" aria-label="选股条件">
      <li v-for="(rule, index) in form.rules" :key="index" class="rounded-xl border border-white/10 bg-white/5 p-4">
        <div class="flex items-center justify-between">
          <span class="text-xs text-slate-400">条件 {{ index + 1 }}</span>
          <button type="button" class="text-xs text-rose-300 hover:underline disabled:opacity-40" :disabled="form.rules.length <= 1" @click="removeRule(index)">删除</button>
        </div>
        <!-- 只排出用得到的格子：没有周期的指标不留“周期”那一格，和数值比较时不留第二个周期 -->
        <div class="mt-3 flex flex-wrap gap-4">
          <FormField class="min-w-[11rem] flex-[2]" label="指标" type="select" :model-value="rule.left.name" :options="indicatorOptions" @update:model-value="chooseIndicator(rule.left, $event, options)" />
          <FormField v-if="rule.left.window != null" class="w-28 shrink-0" label="周期（日）" type="number" v-model="rule.left.window" :min="windowLimits(rule.left.name).minimum" :max="windowLimits(rule.left.name).maximum" :step="1" />
          <FormField class="min-w-[8rem] flex-1" label="判断" type="select" v-model="rule.operator" :options="operatorOptions" />
          <FormField class="min-w-[9rem] flex-1" label="和什么比较" type="select" v-model="rule.compare" :options="compareOptions" />
          <template v-if="rule.compare === 'indicator'">
            <FormField class="min-w-[11rem] flex-[2]" label="另一个指标" type="select" :model-value="rule.right.name" :options="indicatorOptions" @update:model-value="chooseIndicator(rule.right, $event, options)" />
            <FormField v-if="rule.right.window != null" class="w-28 shrink-0" label="周期（日）" type="number" v-model="rule.right.window" :min="windowLimits(rule.right.name).minimum" :max="windowLimits(rule.right.name).maximum" :step="1" />
          </template>
          <FormField v-else class="min-w-[9rem] flex-[2]" label="数值" type="number" v-model="rule.value" step="any" />
        </div>
      </li>
    </ol>
    <button type="button" class="mt-3 text-sm text-indigo-300 hover:underline disabled:opacity-40" :disabled="form.rules.length >= MAX_RULES" @click="addRule">+ 添加条件</button>

    <h3 class="mt-6 text-sm font-semibold text-white">排序</h3>
    <div class="mt-3 flex flex-wrap gap-4">
      <FormField class="min-w-[11rem] flex-[2]" label="排序指标" type="select" :model-value="form.ranking.name" :options="indicatorOptions" @update:model-value="chooseIndicator(form.ranking, $event, options)" />
      <FormField v-if="form.ranking.window != null" class="w-28 shrink-0" label="周期（日）" type="number" v-model="form.ranking.window" :min="windowLimits(form.ranking.name).minimum" :max="windowLimits(form.ranking.name).maximum" :step="1" />
      <FormField class="min-w-[9rem] flex-1" label="排序方向" type="select" v-model="form.ranking.direction" :options="dirOptions" />
    </div>
  </div>
</template>
