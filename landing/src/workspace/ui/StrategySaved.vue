<script setup>
import { openResearch, strategyReference } from '../researchNavigation.js'
defineProps({ asset: { type: Object, required: true } })
</script>
<template>
  <section class="glass glass-sheen rounded-2xl p-5" aria-live="polite">
    <h2 class="font-semibold text-emerald-300">策略已保存</h2>
    <p class="mt-2 text-sm text-slate-400">{{ asset.name || asset.display_name }} · 已加入「我的策略」。下一步确认回测配置。</p>
    <div class="mt-4 flex flex-wrap gap-3">
      <button class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white transition hover:-translate-y-0.5" @click="openResearch('backtest-review', { strategy: strategyReference(asset) })">去回测</button>
      <button class="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/5" @click="openResearch('strategy-hub')">返回我的策略</button>
    </div>
  </section>
</template>
