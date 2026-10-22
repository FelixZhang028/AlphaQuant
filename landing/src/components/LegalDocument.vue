<script setup>
// 一份条款的正文：条款页和弹窗都用它，内容只在 legalContent.js 里写一次。
defineProps({ doc: { type: Object, required: true } })
</script>

<template>
  <div>
    <p class="text-sm leading-relaxed text-slate-300">{{ doc.intro }}</p>
    <section v-for="section in doc.sections" :key="section.heading" class="mt-6">
      <h3 class="text-base font-semibold text-white">{{ section.heading }}</h3>
      <p v-for="(text, i) in section.paragraphs" :key="i" class="mt-2 text-sm leading-relaxed text-slate-300">{{ text }}</p>
    </section>
  </div>
</template>
