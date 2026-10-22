<script setup>
// 条款弹窗：每个页面放一个。点到 /legal.html#… 的链接时在这里打开，不离开当前页面。
// 按 Esc、点“关闭”或点窗口外面关闭；打开时焦点在窗口里，关闭后回到原来点的地方。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { documents, EFFECTIVE_DATE } from '../legal/legalContent.js'
import { closeLegal, legalDialog, legalIdFromHref, openLegal, shouldOpenInDialog } from '../legal/legalDialog.js'
import LegalDocument from './LegalDocument.vue'

const panel = ref(null)
const body = ref(null)
const closeButton = ref(null)
const doc = computed(() => documents.find((item) => item.id === legalDialog.id) || documents[0])
let returnFocus = null

function onClick(event) {
  const link = event.target.closest?.('a[href]')
  if (!link || link.hasAttribute('data-legal-page') || !shouldOpenInDialog(event, window.location.pathname)) return
  const id = legalIdFromHref(link.getAttribute('href'), window.location.href)
  if (!id) return
  event.preventDefault()
  returnFocus = link
  openLegal(id)
}

function onKey(event) {
  if (!legalDialog.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeLegal()
  } else if (event.key === 'Tab') {
    // 焦点只在窗口里转，不跑到后面的页面上
    const items = [...(panel.value?.querySelectorAll('button, a[href]') || [])]
    if (!items.length) return
    const first = items[0]
    const last = items[items.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
}

function choose(id) {
  openLegal(id)
  nextTick(() => body.value?.scrollTo?.({ top: 0 }))
}

watch(() => legalDialog.open, async (open) => {
  document.documentElement.style.overflow = open ? 'hidden' : ''   // 弹窗打开时后面的页面不跟着滚
  if (open) {
    await nextTick()
    body.value?.scrollTo?.({ top: 0 })
    closeButton.value?.focus()
  } else {
    returnFocus?.focus?.()
    returnFocus = null
  }
})

onMounted(() => {
  document.addEventListener('click', onClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onClick)
  document.removeEventListener('keydown', onKey)
  document.documentElement.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div v-if="legalDialog.open" class="fixed inset-0 z-[100] flex items-stretch justify-center bg-black/60 backdrop-blur-sm sm:items-center sm:p-6"
      @click.self="closeLegal">
      <section ref="panel" role="dialog" aria-modal="true" aria-labelledby="legal-dialog-title"
        class="glass-strong flex h-full w-full max-w-3xl flex-col overflow-hidden text-slate-200 sm:h-auto sm:max-h-[86vh] sm:rounded-2xl">
        <header class="flex flex-wrap items-start justify-between gap-3 border-b border-white/10 px-5 py-4 sm:px-6">
          <div>
            <h2 id="legal-dialog-title" class="text-lg font-semibold text-white">{{ doc.title }}</h2>
            <p class="mt-0.5 text-xs text-slate-500">生效日期：{{ EFFECTIVE_DATE }}</p>
          </div>
          <button ref="closeButton" type="button" class="rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-sm text-slate-300 hover:border-white/25 hover:text-white"
            @click="closeLegal">关闭</button>
          <nav class="flex w-full flex-wrap gap-2" aria-label="切换文件">
            <button v-for="item in documents" :key="item.id" type="button" class="rounded-full border px-3 py-1 text-xs transition"
              :class="item.id === doc.id ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 text-slate-400 hover:border-white/25'"
              :aria-pressed="item.id === doc.id" @click="choose(item.id)">{{ item.title }}</button>
          </nav>
        </header>
        <div ref="body" class="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">
          <LegalDocument :doc="doc" />
        </div>
        <footer class="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 px-5 py-3 text-xs text-slate-500 sm:px-6">
          <span>按 Esc 或点窗口外面也可以关闭</span>
          <a :href="`/legal.html#${doc.id}`" target="_blank" rel="noopener" data-legal-page class="text-indigo-300 hover:text-indigo-200">在新页面打开</a>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
