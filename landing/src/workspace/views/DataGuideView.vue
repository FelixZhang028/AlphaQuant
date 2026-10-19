<script setup>
// 数据说明：平台有哪些数据、从哪里来、多久更新一次、回测怎么用、有什么局限。所有人看到的一样，只读。
import { computed, onActivated, ref } from 'vue'
import { closedLoopStatus, dailyUpdateStatus } from '../../api.js'
import { BACKTEST_RULES, LIMITS, NOT_READY, SOURCES, guideRows, headline } from '../dataGuide.js'
import SectionCard from '../ui/SectionCard.vue'

const props = defineProps({ user: { type: Object, default: null }, notify: { type: Function, default: () => {} } })

const loop = ref(null)
const daily = ref(null)
const loading = ref(true)
const error = ref('')

onActivated(async () => {
  error.value = ''
  const [l, d] = await Promise.allSettled([closedLoopStatus(), dailyUpdateStatus()])
  if (l.status === 'fulfilled') loop.value = l.value
  if (d.status === 'fulfilled') daily.value = d.value
  if (l.status === 'rejected' && d.status === 'rejected') error.value = l.reason?.message || '读取数据情况失败'
  loading.value = false
})

const summary = computed(() => headline(loop.value, daily.value))
const rows = computed(() => guideRows(loop.value, daily.value))

function navigate(key) {
  window.dispatchEvent(new CustomEvent('fq-navigate', { detail: key }))
}
</script>

<template>
  <div class="space-y-6">
    <div class="glass glass-sheen rounded-2xl p-6">
      <h1 class="text-xl font-bold text-white">数据说明</h1>
      <p class="mt-1 text-sm text-slate-400">平台的数据由平台统一下载和更新，你不需要自己操作。这里介绍有哪些数据、从哪里来、回测怎么用它们。</p>
      <p class="mt-4 text-base font-medium text-white">{{ loading ? '正在读取…' : summary }}</p>
      <div class="mt-4 flex flex-wrap gap-3">
        <button type="button" class="rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-sm text-slate-300 hover:border-white/25" @click="navigate('market-lookup')">查一只股票有哪些数据</button>
        <button v-if="user?.is_admin" type="button" class="rounded-full border border-indigo-400/40 bg-indigo-500/10 px-4 py-1.5 text-sm text-indigo-200 hover:bg-indigo-500/20" @click="navigate('data-update')">去数据运维（管理员）</button>
      </div>
    </div>

    <p v-if="error" role="alert" class="text-sm text-rose-300">{{ error }}</p>

    <SectionCard title="有哪些数据" hint="“现在”一栏是平台此刻的情况">
      <!-- 宽屏：表格 -->
      <div class="hidden overflow-x-auto md:block">
        <table class="w-full min-w-[760px] table-fixed text-left text-sm">
          <colgroup><col class="w-[8rem]" /><col /><col class="w-[22%]" /><col class="w-[14%]" /><col class="w-[18%]" /></colgroup>
          <thead>
            <tr class="text-xs text-slate-500">
              <th class="pb-3 pr-4 font-medium">数据</th>
              <th class="pb-3 pr-4 font-medium">内容</th>
              <th class="pb-3 pr-4 font-medium">范围</th>
              <th class="pb-3 pr-4 font-medium">多久更新</th>
              <th class="pb-3 font-medium">现在</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/5 align-top">
            <tr v-for="row in rows" :key="row.key" class="text-slate-300">
              <td class="py-3 pr-4 font-medium text-white">{{ row.name }}</td>
              <td class="py-3 pr-4 leading-relaxed text-slate-400">{{ row.content }}</td>
              <td class="py-3 pr-4 text-slate-300">{{ row.range }}</td>
              <td class="py-3 pr-4 text-slate-400">{{ row.schedule }}</td>
              <td class="py-3" :class="row.now === NOT_READY ? 'text-amber-200' : 'text-slate-200'">{{ row.now }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <!-- 手机：卡片 -->
      <ul class="space-y-3 md:hidden">
        <li v-for="row in rows" :key="row.key" class="rounded-xl border border-white/10 bg-white/5 p-4 text-sm">
          <p class="font-medium text-white">{{ row.name }}</p>
          <p class="mt-1 text-xs leading-relaxed text-slate-400">{{ row.content }}</p>
          <dl class="mt-2 space-y-1 text-xs">
            <div class="flex gap-2"><dt class="w-14 shrink-0 text-slate-500">范围</dt><dd class="text-slate-300">{{ row.range }}</dd></div>
            <div class="flex gap-2"><dt class="w-14 shrink-0 text-slate-500">更新</dt><dd class="text-slate-300">{{ row.schedule }}</dd></div>
            <div class="flex gap-2"><dt class="w-14 shrink-0 text-slate-500">现在</dt><dd :class="row.now === NOT_READY ? 'text-amber-200' : 'text-slate-200'">{{ row.now }}</dd></div>
          </dl>
        </li>
      </ul>
    </SectionCard>

    <SectionCard title="数据从哪里来">
      <p class="text-sm leading-relaxed text-slate-300">{{ SOURCES }}</p>
    </SectionCard>

    <SectionCard title="回测怎么用这些数据" hint="这些做法是为了不让回测结果比实际交易好看">
      <ul class="grid gap-3 md:grid-cols-2">
        <li v-for="rule in BACKTEST_RULES" :key="rule.title" class="rounded-xl border border-white/10 bg-white/5 p-4">
          <p class="text-sm font-medium text-white">{{ rule.title }}</p>
          <p class="mt-1 text-sm leading-relaxed text-slate-400">{{ rule.text }}</p>
        </li>
      </ul>
    </SectionCard>

    <SectionCard title="数据的局限">
      <ul class="list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-300">
        <li v-for="item in LIMITS" :key="item">{{ item }}</li>
      </ul>
      <p class="mt-4 text-xs text-slate-500">发现数据有问题，可以在设置页的“关于”里反馈。平台提供的数据仅供研究参考，不构成任何投资建议。</p>
    </SectionCard>
  </div>
</template>
