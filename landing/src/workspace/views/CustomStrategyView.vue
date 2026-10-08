<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  previewUserStrategy,
  saveUserStrategy,
  listUserStrategies,
  deleteUserStrategy,
} from '../../api.js'
import DataTable from '../ui/DataTable.vue'
import SectionCard from '../ui/SectionCard.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const DEFAULT_CODE = `from fellowquant.strategy import register_strategy


@register_strategy(
    name="双均线策略",
    description="短期均线上穿长期均线时买入，下穿时卖出",
)
class DualMovingAverage:
    def __init__(self, fast=5, slow=20):
        self.fast = fast
        self.slow = slow

    def on_bar(self, ctx, bar):
        fast_ma = ctx.sma(self.fast)
        slow_ma = ctx.sma(self.slow)
        if fast_ma > slow_ma and ctx.position == 0:
            ctx.buy()
        elif fast_ma < slow_ma and ctx.position > 0:
            ctx.sell()`

const tab = ref('editor') // editor | mine

// ---------- 编写策略 ----------
const code = ref(DEFAULT_CODE)
const displayName = ref('')
const description = ref('')
const riskAck = ref(false)
const saving = ref(false)
const warnings = ref([])

const sourceLabel = { editor: '编辑器', upload: '上传', nl: '自然语言' }

async function onSave() {
  if (!displayName.value.trim()) return props.notify('请输入策略显示名')
  if (!riskAck.value) return props.notify('请先勾选风险确认')

  saving.value = true
  warnings.value = []
  try {
    const payload = {
      code: code.value,
      display_name: displayName.value.trim(),
      description: description.value,
      source: 'editor',
      risk_acknowledged: riskAck.value,
    }
    const preview = await previewUserStrategy(payload)
    if (preview?.safety_report?.blocked) {
      const blockers = preview.safety_report.blockers || []
      const msg = blockers.map((b) => b.message || '存在安全风险').join('\n')
      return props.notify(msg || '代码未通过安全校验')
    }
    warnings.value = preview?.safety_report?.warnings || []
    await saveUserStrategy(payload)
    props.notify('已保存')
    displayName.value = ''
    description.value = ''
    riskAck.value = false
    loadMine()
  } catch (e) {
    props.notify(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// ---------- 我的策略 ----------
const myStrategies = ref([])
const listLoading = ref(false)

const columns = computed(() => [
  { key: 'display_name', label: '显示名' },
  { key: 'plugin_name', label: '插件名' },
  { key: 'source', label: '来源' },
  { key: 'updated_at', label: '更新时间' },
  { key: 'action', label: '操作' },
])

async function loadMine() {
  listLoading.value = true
  try {
    const data = await listUserStrategies()
    myStrategies.value = data?.strategies || []
  } catch (e) {
    props.notify(e.message || '加载策略失败')
  } finally {
    listLoading.value = false
  }
}

async function onDelete(s) {
  if (!confirm(`确定删除策略「${s.display_name}」？`)) return
  try {
    await deleteUserStrategy(s.plugin_name)
    myStrategies.value = myStrategies.value.filter((x) => x.plugin_name !== s.plugin_name)
    props.notify('已删除')
  } catch (e) {
    props.notify(e.message || '删除失败')
  }
}

onMounted(loadMine)
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div>
      <h1 class="text-xl font-bold text-white">自定义策略（Python）</h1>
      <p class="mt-1 text-sm text-slate-400">在网页编写 Python 策略，平台自动生成参数表单并回测</p>
    </div>

    <!-- 高级模式警告 -->
    <div class="rounded-2xl border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-200">
      高级模式：会运行你自己编写的 Python 代码
    </div>

    <!-- Tab 分段按钮 -->
    <div class="flex w-fit rounded-full border border-white/10 bg-white/5 p-0.5 text-xs">
      <button
        class="rounded-full px-3 py-1 transition"
        :class="tab === 'editor' ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'"
        @click="tab = 'editor'"
      >
        编写策略
      </button>
      <button
        class="rounded-full px-3 py-1 transition"
        :class="tab === 'mine' ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'text-slate-400 hover:text-slate-200'"
        @click="tab = 'mine'"
      >
        我的策略
      </button>
    </div>

    <!-- 编写策略 -->
    <section v-if="tab === 'editor'" class="glass rounded-2xl p-5">
      <h2 class="text-sm font-semibold text-white">编写策略</h2>
      <p class="mt-0.5 text-xs text-slate-500">在下方编辑 Python 代码，保存后平台自动解析参数并生成表单。</p>

      <div class="mt-4 space-y-4">
        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">策略代码</span>
          <textarea
            v-model="code"
            rows="16"
            spellcheck="false"
            class="w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 font-mono text-xs leading-relaxed text-indigo-100 outline-none focus:border-indigo-400/40"
          ></textarea>
        </label>

        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">策略显示名</span>
          <input
            v-model="displayName"
            placeholder="如：双均线策略"
            class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
          />
        </label>

        <label class="block">
          <span class="mb-1 block text-xs text-slate-400">策略说明</span>
          <textarea
            v-model="description"
            rows="3"
            placeholder="简要说明策略逻辑、适用市场与风险"
            class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
          ></textarea>
        </label>

        <label class="flex items-start gap-2.5">
          <input
            v-model="riskAck"
            type="checkbox"
            class="mt-0.5 h-4 w-4 rounded border-white/20 bg-white/5 accent-indigo-500"
          />
          <span class="text-sm text-slate-300">我已阅读并确认：该代码将在平台沙箱中运行，我对其行为负责。</span>
        </label>

        <div v-if="warnings.length" class="rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-xs text-amber-200">
          <p v-for="(w, i) in warnings" :key="i">{{ w.message || w }}</p>
        </div>

        <button
          @click="onSave"
          :disabled="saving"
          class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"
        >
          {{ saving ? '校验并保存中…' : '注册并保存' }}
        </button>
      </div>
    </section>

    <!-- 我的策略 -->
    <SectionCard v-else title="我的策略" hint="已保存的自定义策略，删除前请确认不再需要。">
      <div v-if="listLoading" class="text-sm text-slate-400">加载中…</div>
      <DataTable
        v-else
        :columns="columns"
        :rows="myStrategies"
        empty="暂无自定义策略，去「编写策略」创建一个。"
      >
        <template #cell-source="{ row }">
          <span class="text-slate-400">{{ sourceLabel[row.source] || row.source || '—' }}</span>
        </template>
        <template #cell-updated_at="{ row }">
          <span class="text-slate-400">{{ row.updated_at || row.created_at || '—' }}</span>
        </template>
        <template #cell-action="{ row }">
          <button
            @click="onDelete(row)"
            class="rounded-lg border border-rose-400/20 px-2.5 py-1 text-xs text-rose-300 transition hover:bg-rose-400/10"
          >
            删除
          </button>
        </template>
      </DataTable>
    </SectionCard>

    <!-- 安全边界说明 -->
    <p class="text-xs text-slate-500">
      安全边界：自定义代码在隔离沙箱内运行，无法访问您的账户与密钥；平台会基于 <code class="font-mono text-slate-400">@register_strategy</code> 装饰器与 <code class="font-mono text-slate-400">__init__</code> 参数自动生成策略表单，请勿在代码中写入敏感信息。
    </p>
  </div>
</template>
