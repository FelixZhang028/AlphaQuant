<script setup>
import { onMounted, ref } from 'vue'
import NavBar from './NavBar.vue'
import FooterBar from './FooterBar.vue'
import DynamicBackground from './DynamicBackground.vue'
import { documents, EFFECTIVE_DATE } from '../legal/legalContent.js'

// 一个页面放三份文件，用地址里的 #terms / #privacy / #risk 跳到对应的一份。
const active = ref('terms')
function sync() {
  const id = window.location.hash.slice(1)
  if (documents.some((doc) => doc.id === id)) active.value = id
}
onMounted(() => {
  sync()
  window.addEventListener('hashchange', sync)
  if (window.location.hash) document.getElementById(active.value)?.scrollIntoView()
})
</script>

<template>
  <div class="min-h-screen text-slate-200">
    <DynamicBackground />
    <NavBar />

    <main class="mx-auto max-w-4xl px-5 pb-20 pt-28 lg:px-8">
      <div class="glass glass-sheen rounded-2xl p-8">
        <h1 class="text-2xl font-bold text-white sm:text-3xl">服务条款与政策</h1>
        <p class="mt-2 text-sm text-slate-400">生效日期：{{ EFFECTIVE_DATE }}</p>
        <nav class="mt-5 flex flex-wrap gap-2" aria-label="文件目录">
          <a
            v-for="doc in documents"
            :key="doc.id"
            :href="`#${doc.id}`"
            class="rounded-full border px-4 py-1.5 text-sm no-underline transition"
            :class="active === doc.id ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 text-slate-300 hover:border-indigo-400/40'"
          >{{ doc.title }}</a>
        </nav>
      </div>

      <article v-for="doc in documents" :id="doc.id" :key="doc.id" class="glass mt-6 scroll-mt-28 rounded-2xl p-8">
        <h2 class="text-xl font-bold text-white">{{ doc.title }}</h2>
        <p class="mt-3 text-sm leading-relaxed text-slate-300">{{ doc.intro }}</p>
        <section v-for="section in doc.sections" :key="section.heading" class="mt-6">
          <h3 class="text-base font-semibold text-white">{{ section.heading }}</h3>
          <p v-for="(text, i) in section.paragraphs" :key="i" class="mt-2 text-sm leading-relaxed text-slate-300">{{ text }}</p>
        </section>
      </article>
    </main>

    <FooterBar />
  </div>
</template>
