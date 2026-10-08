<script setup>
import { onActivated, reactive, ref } from 'vue'
import { weknoraChat, weknoraKnowledgeBases, weknoraQuery, weknoraSaveSettings, weknoraSettings } from '../../api.js'
import SectionCard from '../ui/SectionCard.vue'

const props = defineProps({
  settingsOnly: { type: Boolean, default: false },
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const bases = ref([])
const configured = ref(false)
const selectedBaseId = ref(null)
const loadingBases = ref(false)
const showConfig = ref(false)
const savingConfig = ref(false)

const config = reactive({
  base_url: '',
  api_key: '',
})

const mode = ref('chat') // chat | query
const question = ref('')
const queryText = ref('')
const topK = ref(5)
const loading = ref(false)

const chatResult = ref(null)
const queryResult = ref([])
const queryMock = ref(false)
const connectionError = ref('')

async function loadBases() {
  loadingBases.value = true
  try {
    connectionError.value = ''
    const data = await weknoraKnowledgeBases()
    bases.value = data.items || []
    configured.value = data.configured
    if (!bases.value.some((b) => b.id === selectedBaseId.value)) {
      selectedBaseId.value = bases.value[0]?.id || null
    }
  } catch (e) {
    connectionError.value = e.message || '加载知识库失败'
    bases.value = []; selectedBaseId.value = null
    props.notify(connectionError.value)
  } finally {
    loadingBases.value = false
  }
}

async function loadSettings() {
  try {
    const data = await weknoraSettings()
    config.base_url = data.base_url || ''
    configured.value = data.configured
  } catch (e) {
    props.notify(e.message)
  }
}

async function saveSettings() {
  savingConfig.value = true
  try {
    await weknoraSaveSettings({ base_url: config.base_url, api_key: config.api_key })
    props.notify('WeKnora 配置已保存')
    showConfig.value = false
    config.api_key = ''
    await loadBases()
  } catch (e) {
    props.notify(e.message || '保存配置失败')
  } finally {
    savingConfig.value = false
  }
}

onActivated(async () => {
  await loadSettings()
  if (!props.settingsOnly) await loadBases()
})

async function doChat() {
  if (!question.value.trim()) {
    props.notify('请输入问题')
    return
  }
  loading.value = true
  chatResult.value = null
  try {
    chatResult.value = await weknoraChat({
      question: question.value,
      knowledge_base_id: selectedBaseId.value || undefined,
    })
  } catch (e) {
    props.notify(e.message || '问答请求失败')
  } finally {
    loading.value = false
  }
}

async function doQuery() {
  if (!queryText.value.trim()) {
    props.notify('请输入检索词')
    return
  }
  loading.value = true
  queryResult.value = []
  try {
    const data = await weknoraQuery({
      query: queryText.value,
      knowledge_base_id: selectedBaseId.value || undefined,
      top_k: topK.value,
    })
    queryResult.value = data.items || []
    queryMock.value = data.mock
  } catch (e) {
    props.notify(e.message || '检索请求失败')
  } finally {
    loading.value = false
  }
}

</script>

<template>
  <div class="space-y-5">
    <div>
      <h1 class="text-2xl font-semibold text-white">知识库问答</h1>
      <p class="mt-1 text-sm text-slate-400">
        基于 WeKnora RAG 知识库的检索增强问答。未配置 WeKnora 服务时自动使用离线演示数据。
      </p>
    </div>

    <!-- Config status -->
    <div
      :class="[
        'flex items-center justify-between gap-2 rounded-lg border px-4 py-2.5 text-sm',
        configured
          ? 'border-emerald-400/20 bg-emerald-500/5 text-emerald-300'
          : 'border-amber-400/20 bg-amber-500/5 text-amber-300',
      ]"
    >
      <div class="flex items-center gap-2">
        <span class="inline-block h-2 w-2 rounded-full" :class="configured ? 'bg-emerald-400' : 'bg-amber-400'" />
        {{ connectionError ? '服务连接失败，请检查配置' : configured ? 'WeKnora 服务已配置' : '演示模式：未配置 WeKnora 服务地址' }}
      </div>
      <button
        @click="showConfig = !showConfig"
        class="rounded-md border border-white/10 px-2.5 py-1 text-xs text-slate-300 hover:bg-white/5"
      >
        {{ showConfig ? '收起' : '配置' }}
      </button>
    </div>

    <!-- Config panel -->
    <SectionCard v-if="showConfig || settingsOnly" title="WeKnora 服务配置">
      <div class="space-y-4">
        <div>
          <label class="mb-1.5 block text-xs font-medium text-slate-400">服务地址 (Base URL)</label>
          <input
            v-model="config.base_url"
            class="w-full rounded-lg border border-white/10 bg-ink/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400/50"
            placeholder="例如：http://127.0.0.1:8080"
          />
        </div>
        <div>
          <label class="mb-1.5 block text-xs font-medium text-slate-400">API Key（可选）</label>
          <input
            v-model="config.api_key"
            type="password"
            class="w-full rounded-lg border border-white/10 bg-ink/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400/50"
            placeholder="留空保留已保存的 API Key"
          />
        </div>
        <div class="flex items-center gap-3">
          <button
            @click="saveSettings"
            :disabled="savingConfig"
            class="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400 disabled:opacity-50"
          >
            {{ savingConfig ? '保存中…' : '保存配置' }}
          </button>
          <span class="text-xs text-slate-500">配置保存在当前账户的本机后端目录，调用服务时使用</span>
        </div>
      </div>
    </SectionCard>

    <p v-if="connectionError" role="alert" class="text-sm text-rose-300">{{ connectionError }}</p>
    <template v-if="!settingsOnly">
    <!-- Knowledge base list -->
    <SectionCard title="知识库" subtitle="选择要检索的知识库">
      <div v-if="loadingBases" class="py-4 text-center text-sm text-slate-400">加载中…</div>
      <div v-else-if="!bases.length" class="py-4 text-center text-sm text-slate-400">暂无知识库</div>
      <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <button
          v-for="b in bases"
          :key="b.id"
          @click="selectedBaseId = b.id"
          :class="[
            'rounded-lg border p-4 text-left transition',
            selectedBaseId === b.id
              ? 'border-indigo-400/50 bg-indigo-500/10'
              : 'border-white/10 bg-white/5 hover:border-white/20',
          ]"
        >
          <div class="font-medium text-slate-100">{{ b.name }}</div>
          <div class="mt-1 text-xs text-slate-400">{{ b.description }}</div>
          <div class="mt-2 text-xs text-slate-500">{{ b.document_count ?? b.knowledge_count ?? '—' }} 篇文档</div>
        </button>
      </div>
    </SectionCard>

    <!-- Mode tabs -->
    <div class="flex gap-1 rounded-xl border border-white/10 bg-white/5 p-1">
      <button
        @click="mode = 'chat'"
        :class="[
          'flex-1 rounded-lg px-3 py-2 text-sm font-medium transition',
          mode === 'chat' ? 'bg-indigo-500/20 text-indigo-200' : 'text-slate-400 hover:text-slate-200',
        ]"
      >
        智能问答
      </button>
      <button
        @click="mode = 'query'"
        :class="[
          'flex-1 rounded-lg px-3 py-2 text-sm font-medium transition',
          mode === 'query' ? 'bg-indigo-500/20 text-indigo-200' : 'text-slate-400 hover:text-slate-200',
        ]"
      >
        文档检索
      </button>
    </div>

    <!-- Chat mode -->
    <SectionCard v-if="mode === 'chat'" title="智能问答">
      <div class="space-y-4">
        <div>
          <label class="mb-1.5 block text-xs font-medium text-slate-400">你的问题</label>
          <textarea
            v-model="question"
            rows="3"
            class="w-full rounded-lg border border-white/10 bg-ink/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400/50"
            placeholder="输入你想从知识库中了解的问题，例如：什么是动量策略？"
          />
        </div>
        <button
          @click="doChat"
          :disabled="loading"
          class="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400 disabled:opacity-50"
        >
          {{ loading ? '思考中…' : '提问' }}
        </button>

        <div v-if="chatResult" class="space-y-4 rounded-lg border border-white/10 bg-white/5 p-4">
          <div class="flex items-center gap-2">
            <span
              :class="[
                'rounded-full px-2 py-0.5 text-xs font-medium',
                chatResult.mock ? 'bg-amber-500/15 text-amber-300' : 'bg-emerald-500/15 text-emerald-300',
              ]"
            >
              {{ chatResult.mock ? '演示回答' : '知识库回答' }}
            </span>
          </div>
          <p class="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">{{ chatResult.answer }}</p>
          <div v-if="chatResult.references && chatResult.references.length" class="border-t border-white/10 pt-3">
            <div class="mb-2 text-xs font-medium text-slate-400">引用来源</div>
            <ul class="space-y-1.5">
              <li v-for="(ref, i) in chatResult.references" :key="i" class="text-xs text-slate-400">
                <span class="text-slate-300">{{ ref.title }}</span>
                <span v-if="ref.page"> · 第 {{ ref.page }} 页</span>
                <div v-if="ref.snippet" class="mt-0.5 italic text-slate-500">「{{ ref.snippet }}」</div>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </SectionCard>

    <!-- Query mode -->
    <SectionCard v-if="mode === 'query'" title="文档检索">
      <div class="space-y-4">
        <div class="flex gap-3">
          <div class="flex-1">
            <label class="mb-1.5 block text-xs font-medium text-slate-400">检索词</label>
            <input
              v-model="queryText"
              class="w-full rounded-lg border border-white/10 bg-ink/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400/50"
              placeholder="输入关键词检索相关文档片段"
            />
          </div>
          <div class="w-28">
            <label class="mb-1.5 block text-xs font-medium text-slate-400">Top-K</label>
            <input
              v-model.number="topK"
              type="number"
              min="1"
              max="20"
              class="w-full rounded-lg border border-white/10 bg-ink/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400/50"
            />
          </div>
        </div>
        <button
          @click="doQuery"
          :disabled="loading"
          class="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400 disabled:opacity-50"
        >
          {{ loading ? '检索中…' : '检索' }}
        </button>

        <p v-if="queryResult.length && queryMock" class="text-xs text-amber-300">演示检索结果</p>
        <div v-if="queryResult.length" class="space-y-3">
          <div
            v-for="(item, i) in queryResult"
            :key="i"
            class="rounded-lg border border-white/10 bg-white/5 p-3"
          >
            <div class="text-sm font-medium text-slate-200">{{ item.title || `片段 ${i + 1}` }}</div>
            <div v-if="item.snippet" class="mt-1 text-xs text-slate-400">{{ item.snippet }}</div>
            <div v-if="item.page" class="mt-1 text-xs text-slate-500">第 {{ item.page }} 页</div>
          </div>
        </div>
        <div v-else-if="!loading" class="text-sm text-slate-500">
          输入检索词后点击「检索」查看相关文档片段。
        </div>
      </div>
    </SectionCard>
    </template>
  </div>
</template>
