<script setup>
// 指数卡片上的小走势图：只有一条线和下面的浅色填充，涨就是红色，跌就是绿色。
import { computed } from 'vue'
import { sparkPath } from '../homePresentation.js'

const props = defineProps({
  series: { type: Array, default: () => [] },
  rising: { type: Boolean, default: true },
})
const path = computed(() => sparkPath(props.series))
const color = computed(() => (props.rising ? '#fb7185' : '#34d399'))
</script>

<template>
  <svg v-if="path" viewBox="0 0 100 30" preserveAspectRatio="none" class="h-10 w-full" aria-hidden="true">
    <path :d="`${path} L100,30 L0,30 Z`" :fill="color" fill-opacity="0.12" />
    <path :d="path" fill="none" :stroke="color" stroke-width="1.5" vector-effect="non-scaling-stroke" stroke-linejoin="round" />
  </svg>
</template>
