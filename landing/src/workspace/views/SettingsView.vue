<script setup>
import KnowledgeBaseView from './KnowledgeBaseView.vue'
defineProps({ user: { type: Object, default: null }, notify: { type: Function, default: () => {} } })
</script>
<template>
  <div class="space-y-8">
    <p class="text-sm text-slate-400">AI 模型由平台统一提供，不需要在这里配置。下方是当前账户的 WeKnora 文档问答服务。</p>
    <KnowledgeBaseView :user="user" :notify="notify" settings-only />
  </div>
</template>
