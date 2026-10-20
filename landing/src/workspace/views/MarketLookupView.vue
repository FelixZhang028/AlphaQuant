<script setup>
// 股票查询：查一只股票在平台上有哪段时间的行情、有哪几期财报，可以打开详情或加入自己的股票池。
import LocalMarketQuery from '../ui/LocalMarketQuery.vue'

defineProps({
  user: { type: Object, default: null }, notify: { type: Function, default: () => {} },
  routeContext: { type: Object, default: () => ({}) },
})
</script>

<template>
  <div class="space-y-6">
    <div class="glass glass-sheen rounded-2xl p-6">
      <h1 class="text-xl font-bold text-white">股票查询</h1>
      <p class="mt-1 text-sm text-slate-400">按名称或代码查找股票，看它的行情从哪天到哪天、历期财报；可以打开详情，或加入你的股票池。行情由平台每个交易日自动更新，财报在财报季定期更新。</p>
    </div>
    <LocalMarketQuery :notify="notify" :admin="!!user?.is_admin" :focus="routeContext" />
  </div>
</template>
