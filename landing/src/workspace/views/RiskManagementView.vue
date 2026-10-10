<script setup>
import { computed, onActivated, reactive, ref } from 'vue'
import { getRisk, saveRisk, riskEvents } from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
import DataTable from '../ui/DataTable.vue'
import StatusPill from '../ui/StatusPill.vue'
import EmptyState from '../ui/EmptyState.vue'
import FormField from '../ui/FormField.vue'

const props = defineProps({
  embedded: { type: Boolean, default: false },
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ---------- 风控配置 ----------
const form = reactive({
  enabled: false,
  max_total_weight: 0.8,
  max_single_weight: 0.2,
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

// ---------- 最近风控记录 ----------
const events = ref([])
const stats = reactive({ checks: 0, adjustments: 0, rejections: 0 })
const loadingEvents = ref(false)

const columns = [
  { key: 'trade_date', label: '日期' },
  { key: 'symbol', label: '代码' },
  { key: 'decision', label: '决策' },
  { key: 'reason', label: '原因' },
]

const decisionLabels = { PASS: '通过', ADJUST: '调整', REJECT: '拒绝' }
function decisionLabel(value) {
  return decisionLabels[value] || value || '—'
}

async function loadEvents() {
  loadingEvents.value = true
  try {
    const data = await riskEvents()
    events.value = data.events || []
    stats.checks = data.checks ?? events.value.length
    stats.adjustments = data.adjustments ?? 0
    stats.rejections = data.rejections ?? 0
  } catch (e) {
    props.notify(e.message || '加载失败')
  } finally {
    loadingEvents.value = false
  }
}

onActivated(() => {
  if (!dirty.value) loadRisk()
  if (!props.embedded) loadEvents()
})
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div v-if="!embedded">
      <h1 class="text-xl font-bold text-white">风险管理</h1>
      <p class="mt-1 text-sm text-slate-400">所有策略共用的组合级风控参数</p>
    </div>

    <!-- 风控配置 -->
    <SectionCard title="风控配置" :hint="embedded ? '保存后应用到新回测；最大持股数量沿用上方回测配置。' : '修改后会应用到新运行的回测和模拟账户。'">
      <p v-if="loadError" role="alert" class="mb-3 text-sm text-rose-300">{{ loadError }} <button class="underline" @click="loadRisk">重试</button></p>
      <div v-if="loadingRisk" class="text-sm text-slate-400">加载中…</div>
      <div v-else>
        <div class="grid gap-5 sm:grid-cols-2">
          <div class="space-y-4">
            <FormField label="" type="checkbox" v-model="form.enabled" hint="启用风控" />
            <FormField label="最大总仓位" type="number" v-model="form.max_total_weight" :min="0" :max="1" :step="0.05" />
            <FormField label="单只股票最大权重" type="number" v-model="form.max_single_weight" :min="0" :max="1" :step="0.05" />
            <FormField v-if="!embedded" label="最大持股数量" type="number" v-model="form.max_positions" :min="1" :step="1" />
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

    <!-- 最近风控记录 -->
    <SectionCard v-if="!embedded" title="最近风控记录" hint="每次回测与模拟账户运行产生的组合级风控检查结果。">
      <div v-if="loadingEvents" class="text-sm text-slate-400">加载中…</div>
      <div v-else>
        <div class="grid gap-5 sm:grid-cols-3">
          <MetricCard label="最近检查次数" :value="stats.checks.toLocaleString()" />
          <MetricCard label="自动调整次数" :value="stats.adjustments.toLocaleString()" tone="text-amber-300" />
          <MetricCard label="拒绝次数" :value="stats.rejections.toLocaleString()" tone="text-rose-300" />
        </div>

        <EmptyState v-if="!events.length" text="暂无风控记录，请先运行一次回测。" />
        <div v-else class="mt-5">
          <DataTable :columns="columns" :rows="events" empty="暂无数据">
            <template #cell-decision="{ value }">
              <StatusPill :value="decisionLabel(value)" />
            </template>
          </DataTable>
        </div>
      </div>
    </SectionCard>
  </div>
</template>
