<script setup>
// 条件选股：自己设条件（或从我的策略导入），在本地最新一个交易日筛出符合条件的股票。
// 和回测用同一套计算；只描述数据，条件是用户自己设的，不是推荐。
import { computed, onActivated, onMounted, ref } from 'vue'
import { listPackages, studioOptions } from '../../api.js'
import { openResearch } from '../researchNavigation.js'
import { blankForm, definitionFromForm, formFromDefinition } from '../ruleForm.js'
import { handOffRules, takeHandedRules } from '../ruleHandoff.js'
import FormField from '../ui/FormField.vue'
import RuleConditions from '../ui/RuleConditions.vue'
import SectionCard from '../ui/SectionCard.vue'
import TodayScreen from '../ui/TodayScreen.vue'

const props = defineProps({ notify: { type: Function, default: () => {} } })

const options = ref(null)
const loadError = ref('')
const form = ref(null)
const packages = ref([])
const picked = ref('')
const from = ref('')        // 条件是从哪里来的，显示在表单上面

const packageOptions = computed(() => [{ value: '', label: '选一个我的策略' }, ...packages.value.map((p) => ({ value: p.package_id, label: p.name }))])

function useDefinition(definition, label) {
  form.value = formFromDefinition(definition, { top_n: 5, rebalance: 'weekly' }, options.value)
  from.value = label
}

// 从新建规则策略带过来的条件
function takeHandOff() {
  const handed = options.value && takeHandedRules()
  if (handed) useDefinition(handed, `来自新建规则策略${handed.name ? `：${handed.name}` : ''}`)
}

function importPackage() {
  const item = packages.value.find((p) => p.package_id === picked.value)
  if (!item) return
  useDefinition(item.definition, `来自我的策略：${item.name}`)
  props.notify(`已导入“${item.name}”的条件`)
}

function reset() {
  form.value = blankForm(options.value)
  from.value = ''
  picked.value = ''
}

function backtest() {
  handOffRules(definitionFromForm(form.value))
  openResearch('strategy-studio')
}

onMounted(async () => {
  try {
    options.value = await studioOptions()
    form.value = blankForm(options.value)
    takeHandOff()
  } catch (e) {
    loadError.value = e.message || '加载选项失败'
  }
  try { packages.value = (await listPackages()).items || [] } catch { packages.value = [] }
})
onActivated(() => {
  takeHandOff()
  listPackages().then((data) => { packages.value = data.items || [] }).catch(() => {})
})
</script>

<template>
  <div class="space-y-6">
    <section class="glass glass-sheen rounded-2xl p-6">
      <h2 class="text-lg font-semibold text-white">条件选股</h2>
      <p class="mt-2 text-sm leading-relaxed text-slate-300">按你自己设的条件，从本地最新一个交易日的数据里筛出股票，再按你选的指标排序。条件和回测用的是同一套计算，筛好以后可以直接拿去回测，看这组条件在历史上的表现。</p>
      <p class="mt-2 text-xs text-slate-500">结果只是按条件从数据里筛出来的，不是推荐，也不代表以后的走势。</p>
    </section>

    <p v-if="loadError" role="alert" class="rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{{ loadError }}</p>

    <template v-if="form && options">
      <SectionCard title="条件" :hint="from || '自己填，或者从我的策略导入'">
        <div class="mb-5 flex flex-wrap items-end gap-3 border-b border-white/10 pb-5">
          <div class="w-64 max-w-full"><FormField label="从我的策略导入" type="select" v-model="picked" :options="packageOptions" /></div>
          <button type="button" :disabled="!picked" class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300 hover:border-white/25 disabled:opacity-40" @click="importPackage">导入条件</button>
          <button type="button" class="rounded-full px-3 py-2 text-sm text-slate-400 hover:text-white" @click="reset">清空重填</button>
          <p v-if="!packages.length" class="text-xs text-slate-500">还没有保存的策略，可以直接在下面填条件。</p>
        </div>
        <RuleConditions :form="form" :options="options" />
      </SectionCard>

      <TodayScreen :form="form" :notify="notify" />

      <div class="flex flex-wrap items-center gap-3">
        <button type="button" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5" @click="backtest">用这些条件做回测 →</button>
        <span class="text-xs text-slate-500">带着这组条件去“新建规则策略”，设好持股数量和调仓频率就能保存、回测。</span>
      </div>
    </template>
  </div>
</template>
