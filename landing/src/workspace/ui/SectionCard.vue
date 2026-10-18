<script setup>
defineProps({
  title: { type: String, default: '' },
  hint: { type: String, default: '' },
  subtitle: { type: String, default: '' },
})
</script>

<template>
  <section class="glass rounded-2xl p-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold text-white">{{ title }}</h2>
        <p v-if="hint || subtitle" class="mt-0.5 text-xs text-slate-500">{{ hint || subtitle }}</p>
      </div>
      <div class="flex items-center gap-2">
        <slot name="actions" />
      </div>
    </div>
    <div class="mt-4">
      <slot />
    </div>
  </section>
</template>
