<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { xtickCatalog, xtickRequest, xtickStatus, xtickSaveCredentials } from '../../api.js'
import DataTable from '../ui/DataTable.vue'
import EmptyState from '../ui/EmptyState.vue'
import FormField from '../ui/FormField.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const catalog = ref([])
const loading = ref(false)
const activeCatId = ref(null)

// 凭证状态
const status = reactive({ configured: false, base_url: '', message: '' })
const credForm = reactive({ token: '', base_url: '' })
const savingCred = ref(false)
const showCredForm = ref(false)

// 参数、结果、请求态均按 api.id 存（不同分类间 id 唯一）
const params = reactive({})
const results = reactive({})
const requesting = reactive({})
const showRaw = reactive({})

const activeCategory = computed(
  () => catalog.value.find((c) => c.id === activeCatId.value) || catalog.value[0] || null
)
const activeApis = computed(() => (activeCategory.value ? activeCategory.value.apis : []))

function initValue(input) {
  if (input.type === 'select') {
    if (input.default !== undefined && input.default !== null && input.default !== '') return String(input.default)
    return input.options?.[0] ? input.options[0].value : ''
  }
  return input.default ?? ''
}

function tableColumns(apiId) {
  const first = results[apiId]?.rows?.[0]
  if (!first) return []
  return Object.keys(first).map((k) => ({ key: k, label: k }))
}

async function loadStatus() {
  try {
    const data = await xtickStatus()
    Object.assign(status, data)
    credForm.base_url = data.base_url || 'http://api.xtick.top'
    showCredForm.value = !data.configured
  } catch (e) {
    /* 状态加载失败不阻塞目录展示 */
  }
}

async function saveCredentials() {
  if (!credForm.token.trim()) {
    props.notify('请填写 XTick Token')
    return
  }
  savingCred.value = true
  try {
    await xtickSaveCredentials({ token: credForm.token.trim(), base_url: credForm.base_url.trim() })
    await loadStatus()
    showCredForm.value = false
    props.notify('XTick 凭证已保存')
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    savingCred.value = false
  }
}

async function loadCatalog() {
  loading.value = true
  try {
    const data = await xtickCatalog()
    catalog.value = data.catalog || []
    if (catalog.value.length && activeCatId.value === null) activeCatId.value = catalog.value[0].id
    // 初始化每个 api 的表单参数
    for (const cat of catalog.value) {
      for (const api of cat.apis || []) {
        const p = {}
        for (const inp of api.inputs || []) p[inp.name] = initValue(inp)
        params[api.id] = p
      }
    }
  } catch (e) {
    props.notify(e.message || '加载接口目录失败')
  } finally {
    loading.value = false
  }
}

async function onRequest(api) {
  requesting[api.id] = true
  try {
    const data = await xtickRequest({
      url: api.url,
      params: { ...params[api.id] },
      outputs: api.outputs || [],
    })
    results[api.id] = data
  } catch (e) {
    props.notify(e.message || '请求失败')
  } finally {
    requesting[api.id] = false
  }
}

// Excel 友好的 CSV 导出（UTF-8 BOM）
function exportCsv(api) {
  const result = results[api.id]
  if (!result?.rows?.length) return
  const columns = Object.keys(result.rows[0])
  const escape = (v) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [
    columns.map(escape).join(','),
    ...result.rows.map((row) => columns.map((c) => escape(row[c])).join(',')),
  ].join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `xtick_${String(api.id).replace(/[^\w-]/g, '_')}.csv`
  link.click()
  URL.revokeObjectURL(link.href)
}

onMounted(() => {
  loadStatus()
  loadCatalog()
})
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <p class="text-2xl font-bold text-white">XTick 数据服务</p>
      <p class="mt-2 max-w-2xl text-sm text-slate-400">
        调用 XTick 金融行情数据 HTTP API，接口表单由官方 apidoc 动态生成；成功响应为 ZIP
        压缩包（内含 data.json），后端自动解包并附加股票名称。
      </p>
      <div class="mt-3 flex flex-wrap items-center gap-3">
        <span
          class="rounded-full px-3 py-1 text-xs"
          :class="status.configured ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'"
        >
          {{ status.configured ? '凭证已配置' : '未配置 Token' }}
        </span>
        <button
          class="text-xs text-indigo-300 underline-offset-2 hover:underline"
          @click="showCredForm = !showCredForm"
        >
          {{ showCredForm ? '收起凭证设置' : '凭证设置' }}
        </button>
      </div>
      <!-- 凭证表单 -->
      <div v-if="showCredForm" class="mt-4 grid gap-4 rounded-xl border border-white/10 bg-white/5 p-4 sm:grid-cols-2">
        <FormField v-model="credForm.token" label="XTick Token" type="text" placeholder="粘贴官方 Token" />
        <FormField v-model="credForm.base_url" label="接口 Base URL" type="text" placeholder="http://api.xtick.top" />
        <div class="sm:col-span-2">
          <button
            :disabled="savingCred"
            class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
            @click="saveCredentials"
          >
            {{ savingCred ? '保存中…' : '保存凭证' }}
          </button>
          <p class="mt-2 text-xs text-slate-500">保存到本机 data/runtime/data_source_settings.json；也可用环境变量 XTICK_TOKEN。</p>
        </div>
      </div>
    </div>

    <!-- 分类 Tab -->
    <div class="flex flex-wrap rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
      <button
        v-for="cat in catalog"
        :key="cat.id"
        class="rounded-full px-3 py-1 transition"
        :class="activeCatId === cat.id ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'"
        @click="activeCatId = cat.id"
      >
        {{ cat.name }}
      </button>
    </div>

    <!-- 内容 -->
    <div v-if="loading" class="text-sm text-slate-400">加载中…</div>

    <EmptyState v-else-if="!activeApis.length" text="该分类暂无可用接口" />

    <template v-else>
      <section v-for="api in activeApis" :key="api.id" class="glass rounded-2xl p-5">
        <div>
          <h2 class="text-sm font-semibold text-white">{{ api.name }}</h2>
          <p class="mt-1 font-mono text-xs text-indigo-300">{{ api.url }}</p>
          <p v-if="api.description" class="mt-1 text-xs text-slate-500">{{ api.description }}</p>
        </div>

        <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <FormField
            v-for="inp in api.inputs"
            :key="inp.name"
            :label="inp.label"
            :type="inp.type"
            v-model="params[api.id][inp.name]"
            :options="inp.options"
            :placeholder="inp.default ?? ''"
          />
        </div>

        <div class="mt-5 flex flex-wrap items-center gap-3">
          <button
            :disabled="requesting[api.id] || !status.configured"
            class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
            @click="onRequest(api)"
          >
            {{ requesting[api.id] ? '请求中…' : '请求数据' }}
          </button>
          <span v-if="!status.configured" class="text-xs text-amber-400">请先在上方保存 XTick Token</span>
        </div>

        <div v-if="results[api.id]" class="mt-5">
          <div class="mb-2 flex flex-wrap items-center gap-3">
            <p class="text-xs text-slate-400">
              返回 {{ results[api.id].count }} 行
              <template v-if="results[api.id].is_json">（JSON 结构）</template>
            </p>
            <button
              v-if="results[api.id].rows?.length"
              class="text-xs text-indigo-300 underline-offset-2 hover:underline"
              @click="exportCsv(api)"
            >
              下载 CSV
            </button>
            <button
              class="text-xs text-slate-400 underline-offset-2 hover:underline"
              @click="showRaw[api.id] = !showRaw[api.id]"
            >
              {{ showRaw[api.id] ? '隐藏原始 JSON' : '查看原始 JSON' }}
            </button>
          </div>
          <DataTable
            v-if="results[api.id].rows?.length"
            :columns="tableColumns(api.id)"
            :rows="results[api.id].rows"
            empty="暂无数据"
          />
          <pre
            v-if="showRaw[api.id]"
            class="mt-3 max-h-72 overflow-auto rounded-xl border border-white/10 bg-black/20 p-4 text-xs text-slate-300"
          >{{ JSON.stringify(results[api.id].rows, null, 2) }}</pre>
        </div>
      </section>
    </template>
  </div>
</template>
