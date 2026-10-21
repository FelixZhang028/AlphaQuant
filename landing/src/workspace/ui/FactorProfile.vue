<script setup>
// 因子画像：先用几张卡片说清这只股票在每个方面的样子，点一张卡片看这个方面的每一项。
// 每一项写真实数值、五档位置（实心点是全市场，空心点是同行业），点名字看它是什么。
import { computed, ref } from 'vue'
import { openResearch } from '../researchNavigation.js'
import { aspectsFrom } from '../factorProfile.js'

const props = defineProps({ items: { type: Array, default: () => [] } })

const aspects = computed(() => aspectsFrom(props.items))
const selected = ref('')
const current = computed(() => aspects.value.find((a) => a.key === selected.value) || aspects.value[0])
const explained = ref('')
const at = (share) => `${Math.min(97, Math.max(3, share * 100))}%`
</script>

<template>
  <div>
    <div class="grid grid-cols-2 gap-2 lg:grid-cols-4" role="tablist" aria-label="因子画像的几个方面">
      <button v-for="aspect in aspects" :key="aspect.key" type="button" role="tab" :aria-selected="current?.key === aspect.key"
        class="min-w-0 rounded-xl border p-3 text-left transition"
        :class="current?.key === aspect.key ? 'border-indigo-400/60 bg-indigo-500/10' : 'border-white/10 bg-white/[0.03] hover:border-white/20'"
        @click="selected = aspect.key">
        <span class="block text-xs text-slate-400">{{ aspect.title }}</span>
        <span class="mt-0.5 block text-sm font-semibold leading-snug text-white">{{ aspect.text }}</span>
        <span v-if="aspect.basis" class="mt-1 block text-xs leading-snug text-slate-500">{{ aspect.basis }}</span>
      </button>
    </div>

    <section v-if="current" class="mt-4 rounded-xl border border-white/10 bg-white/[0.02] p-4" role="tabpanel" :aria-label="current.title">
      <h4 class="text-sm font-semibold text-white">{{ current.title }} · {{ current.text }}</h4>
      <ul class="mt-3 space-y-5">
        <li v-for="row in current.rows" :key="row.name">
          <div class="flex items-baseline justify-between gap-3">
            <button type="button" class="min-w-0 text-left text-sm text-slate-200 hover:text-indigo-200" :aria-expanded="explained === row.name"
              @click="explained = explained === row.name ? '' : row.name">
              {{ row.label }}<span class="ml-1.5 text-xs text-slate-500">{{ row.original }}</span><span class="ml-1 text-xs text-indigo-300" aria-hidden="true">ⓘ</span>
            </button>
            <span class="shrink-0 text-sm font-semibold tabular-nums text-white">{{ row.value }}</span>
          </div>
          <div class="relative mt-2" :aria-label="`${row.levelWord}。${row.marketText}`" role="img">
            <div class="grid grid-cols-5 gap-1">
              <div v-for="i in 5" :key="i" class="h-2 rounded-full" :class="row.level === i - 1 ? 'bg-indigo-400/70' : 'bg-white/10'" />
            </div>
            <span v-if="row.industry != null" class="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-amber-300 bg-ink" :style="{ left: at(row.industry) }" />
            <span v-if="row.market != null" class="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-indigo-200 ring-2 ring-ink" :style="{ left: at(row.market) }" />
          </div>
          <div class="mt-1 flex justify-between text-[11px] text-slate-500"><span>{{ row.ends[0] }}</span><span>{{ row.ends[1] }}</span></div>
          <p class="text-xs leading-relaxed text-slate-400">
            <span class="font-medium text-slate-200">{{ row.levelWord }}</span><template v-if="row.marketText"> · {{ row.marketText }}</template><template v-if="row.industryText"> · {{ row.industryText }}</template>
          </p>
          <div v-if="explained === row.name" class="mt-2 rounded-lg bg-white/5 p-3 text-xs leading-relaxed text-slate-300">
            <p>{{ row.what }}</p>
            <p v-if="row.rule" class="mt-1 text-slate-400">{{ row.rule }}这是很多股票放在一起的统计规律，不代表这只股票以后会怎样。</p>
            <button type="button" class="mt-1 text-indigo-300 hover:text-indigo-200" @click="openResearch('factor-lab')">在因子研究里看这个因子 →</button>
          </div>
        </li>
      </ul>
    </section>
    <p class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
      <span class="flex items-center gap-1.5"><span class="h-3 w-3 rounded-full bg-indigo-200" />在全市场里的位置</span>
      <span class="flex items-center gap-1.5"><span class="h-3.5 w-3.5 rounded-full border-2 border-amber-300" />在同行业里的位置</span>
      <span>点指标的名字可以看它是什么</span>
    </p>
  </div>
</template>
