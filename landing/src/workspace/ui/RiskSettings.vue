<script setup>
import { computed, onActivated, reactive, ref } from 'vue'
import { getRisk, saveRisk } from '../../api.js'
import SectionCard from './SectionCard.vue'
import FormField from './FormField.vue'

// 风控设置只在回测表单里出现这一处。
const props = defineProps({
  notify: { type: Function, default: () => {} },
})

const form = reactive({
  enabled: false,
  max_total_weight: 0.8,
  max_single_weight: 0.2,
  // 不在这里编辑：回测时使用表单里的“最大持仓”，这里只是原样存回。
  max_positions: 10,
  minimum_cash_ratio: 0.05,
  max_drawdown: 0.2,
  daily_position_limits: false,
  drawdown_action: 'stop_new',
  drawdown_target_weight: 0.4,
})

const actionOptions = [
  { value: 'stop_new', label: '停止新开仓' },
  { value: 'reduce', label: '自动降低仓位' },
  { value: 'liquidate', label: '自动清仓' },
]

const loadingRisk = ref(false)
const saving = ref(false)
const savedSnapshot = ref('')
const loadError = ref('')
const dirty = computed(() => !!savedSnapshot.value && savedSnapshot.value !== JSON.stringify(form))
const ready = computed(() => !!savedSnapshot.value && !loadingRisk.value && !loadError.value && !saving.value)
defineExpose({ dirty, ready })

async function loadRisk() {
  loadingRisk.value = true
  loadError.value = ''
  try {
    const data = await getRisk()
    Object.assign(form, {
      enabled: !!data.enabled,
      max_total_weight: data.max_total_weight,
      max_single_weight: data.max_single_weight,
      max_positions: data.max_positions,
      minimum_cash_ratio: data.minimum_cash_ratio,
      max_drawdown: data.max_drawdown,
      daily_position_limits: !!data.daily_position_limits,
      drawdown_action: data.drawdown_action,
      drawdown_target_weight: data.drawdown_target_weight,
    })
    savedSnapshot.value = JSON.stringify(form)
  } catch (e) {
    loadError.value = e.message || '风控配置加载失败'
    props.notify(e.message || '加载失败')
  } finally {
    loadingRisk.value = false
  }
}

async function onSubmit() {
  const submittedSnapshot = JSON.stringify(form)
  saving.value = true
  try {
    await saveRisk({
      enabled: !!form.enabled,
      max_total_weight: Number(form.max_total_weight),
      max_single_weight: Number(form.max_single_weight),
      max_positions: Math.round(Number(form.max_positions)),
      minimum_cash_ratio: Number(form.minimum_cash_ratio),
      max_drawdown: Number(form.max_drawdown),
      daily_position_limits: !!form.daily_position_limits,
      drawdown_action: form.drawdown_action,
      drawdown_target_weight: Number(form.drawdown_target_weight),
    })
    savedSnapshot.value = submittedSnapshot
    props.notify('已保存')
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onActivated(() => {
  if (!dirty.value) loadRisk()
})
</script>

<template>
  <SectionCard title="风控配置" hint="保存后应用到新回测；最大持股数量使用上方的“最大持仓”。">
    <p v-if="loadError" role="alert" class="mb-3 text-sm text-rose-300">{{ loadError }} <button class="underline" @click="loadRisk">重试</button></p>
    <div v-if="loadingRisk" class="text-sm text-slate-400">加载中…</div>
    <div v-else>
      <div class="grid gap-5 sm:grid-cols-2">
        <div class="space-y-4">
          <FormField label="" type="checkbox" v-model="form.enabled" hint="启用风控" />
          <FormField label="最大总仓位" type="number" v-model="form.max_total_weight" :min="0" :max="1" :step="0.05" />
          <FormField label="单只股票最大权重" type="number" v-model="form.max_single_weight" :min="0" :max="1" :step="0.05" />
          <div>
            <FormField label="" type="checkbox" v-model="form.daily_position_limits" hint="每日检查实际持仓并自动纠偏" />
            <p class="mt-1 pl-6 text-xs text-slate-500">持仓上涨导致单股、总仓位或持股数量超限时，下一交易日自动减仓。</p>
          </div>
        </div>
        <div class="space-y-4">
          <FormField label="最低现金比例" type="number" v-model="form.minimum_cash_ratio" :min="0" :max="1" :step="0.05" />
          <FormField label="最大回撤停止线" type="number" v-model="form.max_drawdown" :min="0" :max="1" :step="0.05" />
          <FormField label="达到回撤线后的处理" type="select" v-model="form.drawdown_action" :options="actionOptions" />
          <FormField label="降仓后的最大总仓位" type="number" v-model="form.drawdown_target_weight" :min="0" :max="1" :step="0.05" :disabled="form.drawdown_action !== 'reduce'" />
          <p class="text-xs text-slate-500">风控在每日收盘后检查实际持仓，纠偏订单在下一交易日开盘执行。</p>
        </div>
      </div>

      <div class="mt-6">
        <button
          @click="onSubmit"
          :disabled="saving || !ready"
          class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
        >
          {{ saving ? '保存中…' : '保存风控配置' }}
        </button>
      </div>
    </div>
  </SectionCard>
</template>
