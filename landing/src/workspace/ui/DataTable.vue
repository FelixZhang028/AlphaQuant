<script setup>
defineProps({
  columns: { type: Array, default: () => [] }, // [{ key, label }]
  rows: { type: Array, default: () => [] }, // array of objects
  empty: { type: String, default: '暂无数据' },
})
</script>

<template>
  <div v-if="!rows.length" class="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-slate-500">
    {{ empty }}
  </div>
  <div v-else class="overflow-x-auto">
    <table class="w-full min-w-[560px] text-left text-sm">
      <thead>
        <tr class="text-xs text-slate-500">
          <th v-for="c in columns" :key="c.key" class="pb-3 font-medium whitespace-nowrap" :class="c.align === 'right' ? 'text-right' : ''">{{ c.label }}</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-white/5">
        <tr v-for="(r, i) in rows" :key="i" class="text-slate-300 transition hover:bg-white/5">
          <td v-for="c in columns" :key="c.key" class="py-2.5" :class="c.align === 'right' ? 'text-right' : ''">
            <slot :name="`cell-${c.key}`" :row="r" :value="r[c.key]">{{ r[c.key] }}</slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
