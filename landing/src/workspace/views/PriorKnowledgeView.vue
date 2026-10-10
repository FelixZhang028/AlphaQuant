<script setup>
import { onActivated, ref } from 'vue'
import { agentConfig, addPriorKnowledge, deletePriorKnowledge } from '../../api.js'
import SectionCard from '../ui/SectionCard.vue'
const props = defineProps({ embedded: Boolean, notify: { type: Function, default: () => {} } })
const entries = ref([])
const content = ref('')
const source = ref('')
const busy = ref(false)
async function load() { entries.value = (await agentConfig()).prior_knowledge || [] }
onActivated(async () => { try { await load() } catch (e) { props.notify(e.message) } })
async function save() {
  if (content.value.trim().length < 2) return props.notify('请填写至少两个字的经验内容')
  busy.value = true
  try {
    await addPriorKnowledge({ content: content.value.trim(), source: source.value.trim() })
    content.value = ''; source.value = ''
    await load(); props.notify('研究经验已保存')
  } catch (e) { props.notify(e.message) } finally { busy.value = false }
}
async function remove(id) {
  busy.value = true
  try { await deletePriorKnowledge(id); await load() } catch (e) { props.notify(e.message) }
  finally { busy.value = false }
}
</script>
<template>
  <div class="space-y-5">
    <p class="text-sm text-slate-400">记录投资规则、研究经验及来源，可在 AI研究员的高级设置中选择引用。这里的记录不会自动成为文档问答的检索材料。</p>
    <SectionCard title="添加研究经验">
      <form class="space-y-3" @submit.prevent="save">
        <textarea v-model="content" aria-label="知识内容" maxlength="2000" rows="4" placeholder="填写投资规则、研究经验或已验证的事实" class="w-full rounded-lg border border-white/10 bg-ink/60 p-3 text-sm text-white" />
        <input v-model="source" aria-label="知识来源" placeholder="知识来源（可选）" class="w-full rounded-lg border border-white/10 bg-ink/60 p-3 text-sm text-white" />
        <button :disabled="busy" class="rounded-lg bg-indigo-500 px-4 py-2 text-sm text-white disabled:opacity-50">保存经验</button>
      </form>
    </SectionCard>
    <SectionCard title="我的研究经验">
      <p v-if="!entries.length" class="text-sm text-slate-400">暂无研究经验，添加后可供 AI研究员引用。</p>
      <div v-for="entry in entries" :key="entry.id" class="mb-3 rounded-xl border border-white/10 p-4">
        <p class="whitespace-pre-wrap text-sm text-slate-200">{{ entry.content }}</p>
        <div class="mt-3 flex items-center justify-between gap-3 text-xs text-slate-400">
          <span>{{ entry.source || '未填写来源' }}</span>
          <button :disabled="busy" class="text-rose-300 disabled:opacity-50" @click="remove(entry.id)">删除</button>
        </div>
      </div>
    </SectionCard>
  </div>
</template>
