<script setup>
import { computed } from 'vue'
import { openResearch } from '../researchNavigation.js'
import PriorKnowledgeView from './PriorKnowledgeView.vue'
import KnowledgeBaseView from './KnowledgeBaseView.vue'

const props = defineProps({
  user: Object,
  notify: { type: Function, default: () => {} },
  routeContext: { type: Object, default: () => ({}) },
  researchMode: String,
})
// Existing document links retain their destination; the old prior route opens experience.
const activeTab = computed(() => props.researchMode === 'prior-knowledge' || props.routeContext.mode === 'experience' ? 'experience' : 'documents')
const tabs = [{ key: 'experience', label: '研究经验' }, { key: 'documents', label: '文档问答' }]
</script>

<template>
  <div class="space-y-6">
    <section class="glass glass-sheen rounded-2xl p-6">
      <h2 class="text-xl font-bold text-white">投研知识库</h2>
      <p class="mt-2 text-sm text-slate-400">管理研究经验，或从文档中查找有来源的答案。</p>
    </section>
    <div class="flex gap-1 rounded-xl border border-white/10 bg-white/5 p-1" aria-label="知识库内容">
      <button v-for="tab in tabs" :key="tab.key" :aria-pressed="activeTab === tab.key"
        class="flex-1 rounded-lg px-3 py-2 text-sm font-medium transition"
        :class="activeTab === tab.key ? 'bg-indigo-500/20 text-indigo-200' : 'text-slate-400 hover:text-slate-200'"
        @click="openResearch('knowledge-base', { mode: tab.key })">{{ tab.label }}</button>
    </div>
    <KeepAlive>
      <component :is="activeTab === 'experience' ? PriorKnowledgeView : KnowledgeBaseView" :user="user" :notify="notify" embedded />
    </KeepAlive>
  </div>
</template>
