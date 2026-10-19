<script setup>
// 因子库表格：一行一个因子，长的说明和公式只显示一行，全文在“详情”里。每页 20 个；手机上改成卡片。
import { computed, ref, watch } from 'vue'
import { ALPHA101_NOTE, directionText, directionTone, factorSummary, historyText } from '../factorPresentation.js'

const props = defineProps({
  factors: { type: Array, default: () => [] },
  empty: { type: String, default: '暂无因子' },
})
const emit = defineEmits(['detail'])

const PAGE_SIZE = 20
const page = ref(1)
const pages = computed(() => Math.max(1, Math.ceil(props.factors.length / PAGE_SIZE)))
const shown = computed(() => props.factors.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE)
  .map((factor) => ({ factor, summary: factorSummary(factor) })))
const hasAlpha101 = computed(() => props.factors.some((factor) => factor.source === 'Alpha101'))
// 筛选条件变了就回到第一页。
watch(() => props.factors, () => { page.value = 1 })
</script>

<template>
  <div>
    <p v-if="hasAlpha101" class="mb-3 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-xs leading-relaxed text-slate-400">{{ ALPHA101_NOTE }}</p>

    <div v-if="!factors.length" class="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-slate-500">{{ empty }}</div>
    <template v-else>
      <!-- 宽屏：表格 -->
      <div class="hidden overflow-x-auto md:block">
        <table class="w-full min-w-[760px] table-fixed text-left text-sm">
          <colgroup>
            <col class="w-[30%]" /><col class="w-[14%]" /><col /><col class="w-[4.5rem]" /><col class="w-[5.5rem]" /><col class="w-[4.5rem]" />
          </colgroup>
          <thead>
            <tr class="text-xs text-slate-500">
              <th class="pb-3 pr-4 font-medium">因子</th>
              <th class="pb-3 pr-4 font-medium">类型</th>
              <th class="pb-3 pr-4 font-medium">说明</th>
              <th class="pb-3 pr-4 font-medium">方向</th>
              <th class="pb-3 pr-4 text-right font-medium">最小历史</th>
              <th class="pb-3 text-right font-medium"><span class="sr-only">操作</span></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/5">
            <tr v-for="{ factor, summary } in shown" :key="factor.name" class="text-slate-300 transition hover:bg-white/5">
              <td class="py-2.5 pr-4">
                <div class="flex min-w-0 items-center gap-2">
                  <span class="truncate font-medium text-slate-100" :title="factor.display_name">{{ factor.display_name || factor.name }}</span>
                  <span v-if="factor.source && factor.source !== '内置'" class="shrink-0 rounded-full border border-white/10 px-1.5 py-px text-[10px] text-slate-400">{{ factor.source }}</span>
                </div>
                <p class="mt-0.5 truncate font-mono text-[11px] text-slate-500">{{ factor.name }}</p>
              </td>
              <td class="py-2.5 pr-4"><span class="block truncate text-xs text-slate-400" :title="factor.logical_category">{{ factor.logical_category || factor.category || '—' }}</span></td>
              <td class="py-2.5 pr-4">
                <p class="truncate" :class="summary.formula ? 'font-mono text-xs text-slate-400' : 'text-slate-300'" :title="summary.text">{{ summary.text }}</p>
              </td>
              <td class="whitespace-nowrap py-2.5 pr-4 text-xs" :class="directionTone(factor.direction)">{{ directionText(factor.direction) }}</td>
              <td class="whitespace-nowrap py-2.5 pr-4 text-right text-xs text-slate-400">{{ historyText(factor.min_history) }}</td>
              <td class="py-2.5 text-right">
                <button type="button" class="whitespace-nowrap rounded-lg border border-indigo-400/20 bg-indigo-500/10 px-2.5 py-1 text-xs text-indigo-300 transition hover:bg-indigo-400/20" @click="emit('detail', factor)">详情</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 手机：卡片 -->
      <ul class="space-y-2 md:hidden">
        <li v-for="{ factor, summary } in shown" :key="factor.name">
          <button type="button" class="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-left transition hover:bg-white/10" @click="emit('detail', factor)">
            <div class="flex items-start justify-between gap-3">
              <span class="min-w-0 font-medium text-slate-100">{{ factor.display_name || factor.name }}</span>
              <span class="shrink-0 text-xs" :class="directionTone(factor.direction)">{{ directionText(factor.direction) }}</span>
            </div>
            <p class="mt-0.5 font-mono text-[11px] text-slate-500">{{ factor.name }} · {{ factor.logical_category || factor.category }} · {{ historyText(factor.min_history) }}</p>
            <p class="mt-1.5 line-clamp-2 text-xs" :class="summary.formula ? 'font-mono text-slate-500' : 'text-slate-400'">{{ summary.text }}</p>
          </button>
        </li>
      </ul>

      <div v-if="pages > 1" class="mt-4 flex items-center justify-between text-xs text-slate-400">
        <span>共 {{ factors.length }} 个 · 第 {{ page }} / {{ pages }} 页</span>
        <div class="flex gap-2">
          <button type="button" :disabled="page === 1" class="rounded-full border border-white/10 px-3 py-1 hover:bg-white/5 disabled:opacity-40" @click="page -= 1">上一页</button>
          <button type="button" :disabled="page === pages" class="rounded-full border border-white/10 px-3 py-1 hover:bg-white/5 disabled:opacity-40" @click="page += 1">下一页</button>
        </div>
      </div>
    </template>
  </div>
</template>
