<script setup>
import DecisionCenterView from './DecisionCenterView.vue'
import KnowledgeBaseView from './KnowledgeBaseView.vue'
defineProps({ user: { type: Object, default: null }, notify: { type: Function, default: () => {} } })
</script>
<template>
  <div class="space-y-8">
    <p class="text-sm text-slate-400">在下方配置当前账户的 Jev 决策模型和 WeKnora 知识库服务。</p>
    <DecisionCenterView :user="user" :notify="notify" settings-only />
    <KnowledgeBaseView :user="user" :notify="notify" settings-only />
  </div>
</template>
