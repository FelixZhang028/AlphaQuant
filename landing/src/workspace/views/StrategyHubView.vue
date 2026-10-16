<script setup>
import { computed, onActivated, ref } from 'vue'
import { copyPackage, deletePackage, listPackages } from '../../api.js'
import { openResearch, strategyReference } from '../researchNavigation.js'
import { sourceLabel as ruleSourceLabel } from '../ruleForm.js'
import EmptyState from '../ui/EmptyState.vue'
import SectionCard from '../ui/SectionCard.vue'

const props = defineProps({ user: Object, routeContext: { type: Object, default: () => ({}) }, notify: { type: Function, default: () => {} } })
const assets = ref([])
const loading = ref(false)
const error = ref('')
const keyword = ref('')
const confirming = ref('')
const busy = ref('')
const methods = [
  { label: '新建规则策略', hint: '不用写代码：从模板开始、用一句话描述，或自己填写条件', view: 'strategy-studio' },
]
const visibleAssets = computed(() => assets.value.filter((asset) =>
  `${asset.name} ${asset.description || ''}`.toLowerCase().includes(keyword.value.trim().toLowerCase())))
const freqLabel = (value) => ({ daily: '每日', weekly: '每周', monthly: '每月' }[value] || '—')

async function loadAssets() {
  loading.value = true
  error.value = ''
  try {
    const packages = (await listPackages()).items || []
    assets.value = packages.map((a) => ({ ...a, reference: strategyReference(a) }))
      .sort((a, b) => String(b.updated_at || b.created_at).localeCompare(String(a.updated_at || a.created_at)))
  } catch (e) {
    error.value = e.message || '策略加载失败'
  }
  if (props.routeContext.strategy) {
    const target = assets.value.find((a) => a.reference === props.routeContext.strategy)
    if (target) keyword.value = target.name
    else error.value = [error.value, '原策略已删除或无法加载，历史结果仍保留在研究记录中。'].filter(Boolean).join('；')
  }
  loading.value = false
}
async function remove(asset) {
  busy.value = asset.reference
  try {
    await deletePackage(asset.package_id)
    assets.value = assets.value.filter((a) => a.reference !== asset.reference)
    confirming.value = ''
    props.notify('策略已删除')
  } catch (e) { props.notify(e.message || '删除失败') }
  finally { busy.value = '' }
}
async function copy(asset) {
  busy.value = asset.reference
  try {
    await copyPackage(asset.package_id)
    await loadAssets()
    props.notify('已复制为新策略')
  } catch (e) { props.notify(e.message || '复制失败') }
  finally { busy.value = '' }
}
onActivated(loadAssets)
</script>
<template>
  <div class="space-y-6">
    <section class="glass glass-sheen rounded-2xl p-6">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div><h2 class="text-xl font-bold text-white">我的策略</h2><p class="mt-2 text-sm text-slate-400">先创建策略，再配置回测，最后在研究记录中比较结果。</p></div>
      </div>
      <h3 class="mt-5 text-base font-semibold text-white">新建策略</h3>
      <div class="mt-3 grid gap-3 sm:grid-cols-2">
        <button v-for="method in methods" :key="method.label" class="glass glass-sheen rounded-xl border border-white/10 p-4 text-left transition hover:-translate-y-0.5 hover:border-indigo-400/40" @click="openResearch(method.view, { mode: method.mode || '' })">
          <span class="font-semibold text-white">{{ method.label }}</span><span class="mt-2 block text-sm text-slate-400">{{ method.hint }}</span>
        </button>
      </div>
    </section>
    <SectionCard title="策略列表" :hint="`共 ${assets.length} 个策略`">
      <template #actions><button class="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-white/5 disabled:opacity-50" :disabled="loading" @click="loadAssets">{{ loading ? '加载中…' : '刷新' }}</button></template>
      <label class="block max-w-md"><span class="mb-2 block text-sm text-slate-400">搜索策略</span><input v-model="keyword" type="search" placeholder="输入名称或描述" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-white outline-none focus:border-indigo-400/40" /></label>
      <p v-if="error" role="alert" class="mt-4 text-sm text-rose-300">{{ error }}</p>
      <EmptyState v-if="!loading && !visibleAssets.length" :text="keyword ? '没有匹配的策略' : '暂无策略，选择上方一种创建方式开始。'" />
      <div class="mt-5 grid gap-4">
        <article v-for="asset in visibleAssets" :key="asset.reference" class="rounded-xl border border-white/10 bg-white/5 p-4">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="min-w-0"><h3 class="font-semibold text-white">{{ asset.name }} <span class="ml-2 rounded-full border border-indigo-400/30 px-2 py-0.5 text-xs text-indigo-300">{{ ruleSourceLabel(asset.source) }}</span></h3><p class="mt-2 text-sm text-slate-400">默认持股 {{ asset.top_n }} 只 · {{ freqLabel(asset.rebalance) }}调仓</p></div>
            <div class="flex flex-wrap gap-2">
              <button class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm text-white transition hover:-translate-y-0.5" @click="openResearch('backtest-review', { strategy: asset.reference })">去回测</button>
              <button class="rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/5 disabled:opacity-50" :disabled="busy === asset.reference" @click="copy(asset)">复制</button>
              <button class="rounded-lg border border-rose-400/20 px-3 py-2 text-sm text-rose-300 hover:bg-rose-400/10" @click="confirming = confirming === asset.reference ? '' : asset.reference">删除</button>
            </div>
          </div>
          <p v-if="asset.describe_text" class="mt-3 text-sm leading-relaxed text-slate-400">{{ asset.describe_text }}</p>
          <div v-if="confirming === asset.reference" class="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-rose-400/20 p-3 text-sm text-slate-300">
            <span>删除「{{ asset.name }}」？历史研究记录仍保留。</span><button class="rounded-lg bg-rose-400/10 px-3 py-2 text-rose-300 disabled:opacity-50" :disabled="busy === asset.reference" @click="remove(asset)">确认删除</button><button @click="confirming = ''">取消</button>
          </div>
        </article>
      </div>
    </SectionCard>
  </div>
</template>
