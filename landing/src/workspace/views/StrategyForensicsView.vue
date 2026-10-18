<script setup>
// 外部成交核查（迁移自 AlphaQuant forensics + external_audit）
import { computed, ref } from 'vue'
import { forensicsCheck, forensicsPreview, forensicsTemplateUrl } from '../../api.js'
import SectionCard from '../ui/SectionCard.vue'
import DataTable from '../ui/DataTable.vue'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

const TEMPLATE = '日期,股票代码,买卖方向,数量（股）,成交价（未复权）\n2024-03-01,000001.SZ,买入,1000,10.50\n'

// ---------- 输入与预览 ----------
const content = ref('')
const previewing = ref(false)
const preview = ref(null) // { total, columns, preview, mapping, missing, inferred_unit, inferred_raw, labels }

// ---------- 手动列映射 ----------
const manualMapping = ref({}) // field -> column name

// ---------- 单位与价格口径 ----------
const unit = ref('股')
const basis = ref('未复权')

// ---------- 核查结果 ----------
const checking = ref(false)
const result = ref(null) // { verdict, findings, counts, covered, total, duplicates, errors, status }

const ORDER = ['发现明确矛盾', '存在疑点', '证据不足', '未发现异常']
const VERDICT_TONE = {
  '发现明确矛盾': 'text-rose-300',
  '存在疑点': 'text-amber-300',
  '证据不足': 'text-slate-400',
  '未发现异常': 'text-emerald-300',
}

const hasContent = computed(() => content.value.trim().length > 0)

const mappingComplete = computed(() => {
  if (!preview.value) return false
  const fields = ['date', 'symbol', 'side', 'quantity', 'price']
  return fields.every((f) => effectiveMapping.value[f])
})

const effectiveMapping = computed(() => {
  if (!preview.value) return {}
  return { ...preview.value.mapping, ...manualMapping.value }
})

const findingCols = [
  { key: '表格行', label: '行' },
  { key: '日期', label: '日期' },
  { key: '股票', label: '股票' },
  { key: '核查项', label: '核查项' },
  { key: '结论', label: '结论' },
  { key: '声称值', label: '声称值' },
  { key: '证据或限制', label: '证据或限制' },
  { key: '数据来源', label: '数据来源' },
]

const errorCols = [
  { key: '表格行', label: '行' },
  { key: '字段', label: '字段' },
  { key: '原值', label: '原值' },
  { key: '问题', label: '问题' },
]

const filteredFindings = computed(() => {
  if (!result.value?.findings) return []
  return result.value.findings.map((f) => {
    const row = {}
    for (const c of findingCols) row[c.key] = String(f[c.key] ?? '')
    return row
  })
})

// ---------- 操作 ----------
async function doPreview() {
  if (!hasContent.value) return
  previewing.value = true
  preview.value = null
  manualMapping.value = {}
  try {
    preview.value = await forensicsPreview(content.value)
    // 应用推断的单位和价格口径
    if (preview.value.inferred_unit) unit.value = preview.value.inferred_unit
    if (preview.value.inferred_raw) basis.value = '未复权'
    else basis.value = '复权或不确定'
  } catch (e) {
    props.notify(e.message || '解析失败')
  } finally {
    previewing.value = false
  }
}

async function doCheck() {
  if (!mappingComplete.value) {
    props.notify('请先补全字段映射')
    return
  }
  checking.value = true
  result.value = null
  try {
    result.value = await forensicsCheck({
      content: content.value,
      mapping: effectiveMapping.value,
      unit: unit.value,
      basis: basis.value,
    })
    if (result.value.status === 'errors') {
      props.notify('成交记录有解析错误，请先修正')
    } else if (result.value.duplicates?.length) {
      props.notify(`检测到 ${result.value.duplicates.length} 条重复记录，结果可能放大占比`)
    }
  } catch (e) {
    props.notify(e.message || '核查失败')
  } finally {
    checking.value = false
  }
}

function downloadTemplate() {
  const url = forensicsTemplateUrl()
  const a = document.createElement('a')
  a.href = url
  a.download = '成交记录模板.csv'
  a.click()
}

function downloadReport() {
  if (!result.value?.findings) return
  const lines = ['# 外部成交材料检查', '', `结论：${result.value.verdict}`, '']
  for (const f of result.value.findings) {
    lines.push(`## 第${f['表格行']}行 · ${f['股票']} · ${f['日期']} · ${f['核查项']}`, '')
    for (const key of ['结论', '声称值', '证据或限制', '数据来源', '规则版本']) {
      lines.push(`${key}：${String(f[key] ?? '').replace(/\n/g, ' ')}  `)
    }
    lines.push('')
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = '外部成交检查.md'
  a.click()
}

function reset() {
  content.value = ''
  preview.value = null
  result.value = null
  manualMapping.value = {}
}
</script>

<template>
  <div class="space-y-6">
    <!-- 标题 -->
    <div class="glass relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <h1 class="text-xl font-bold text-white">外部成交核查</h1>
      <p class="mt-1 text-sm text-slate-400">
        上传成交明细或从 Excel 复制粘贴，检查上市时间、停牌、价格和成交占比。结论仅针对本次材料及可核查项目，不证明策略有效或原始材料真实。
      </p>
    </div>

    <!-- 输入区 -->
    <SectionCard title="成交记录" hint="支持粘贴表格或上传 CSV，仅限普通上市股票竞价成交">
      <div class="space-y-4">
        <div class="flex flex-wrap items-center gap-3">
          <button class="rounded-lg border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-slate-300 transition hover:border-white/25 hover:text-white" @click="downloadTemplate">
            下载示例模板
          </button>
          <button
            class="rounded-lg border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-slate-300 transition hover:border-white/25 hover:text-white"
            @click="content = TEMPLATE"
          >
            填入示例
          </button>
          <span class="text-xs text-slate-500">只需一份成交明细；净值、截图、委托单和策略描述暂不支持。</span>
        </div>
        <textarea
          v-model="content"
          class="h-40 w-full resize-y rounded-xl border border-white/10 bg-ink/60 px-4 py-3 text-sm text-slate-200 placeholder-slate-600 outline-none transition focus:border-indigo-400/40"
          placeholder="日期,股票代码,买卖方向,数量（股）,成交价（未复权）&#10;2024-03-01,000001.SZ,买入,1000,10.50"
        />
        <div class="flex items-center gap-3">
          <button
            class="rounded-lg bg-indigo-500 px-5 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="!hasContent || previewing"
            @click="doPreview"
          >
            {{ previewing ? '解析中…' : '解析并预览' }}
          </button>
          <button v-if="content" class="text-xs text-slate-500 transition hover:text-slate-300" @click="reset">
            清空
          </button>
        </div>
      </div>
    </SectionCard>

    <!-- 解析结果与列映射 -->
    <SectionCard v-if="preview" title="识别结果与预览" :hint="`共 ${preview.total} 条记录；下方报告行号含表头`">
      <div class="space-y-4">
        <!-- 预览表格 -->
        <div class="overflow-x-auto rounded-xl border border-white/10">
          <table class="w-full text-xs">
            <thead class="bg-white/5 text-slate-400">
              <tr>
                <th class="px-3 py-2 text-left">行号</th>
                <th v-for="col in preview.columns" :key="col" class="px-3 py-2 text-left">{{ col }}</th>
              </tr>
            </thead>
            <tbody class="text-slate-300">
              <tr v-for="(row, i) in preview.preview" :key="i" class="border-t border-white/5">
                <td class="px-3 py-2 text-slate-500">{{ row.__row__ }}</td>
                <td v-for="col in preview.columns" :key="col" class="px-3 py-2">{{ row[col] }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 列映射 -->
        <div v-if="preview.missing.length" class="space-y-3">
          <p class="text-sm text-amber-300">以下字段未自动识别，请手动指定：</p>
          <div v-for="field in preview.missing" :key="field" class="flex items-center gap-3">
            <span class="w-24 text-xs text-slate-400">{{ preview.labels[field] }}</span>
            <select
              v-model="manualMapping[field]"
              class="flex-1 rounded-lg border border-white/10 bg-ink/60 px-3 py-1.5 text-sm text-slate-200 outline-none focus:border-indigo-400/40"
            >
              <option :value="undefined">请选择</option>
              <option v-for="col in preview.columns" :key="col" :value="col">{{ col }}</option>
            </select>
          </div>
        </div>
        <div v-else>
          <p class="text-xs text-emerald-300">五个字段已全部自动识别。</p>
        </div>

        <!-- 已识别字段一览 -->
        <div class="flex flex-wrap gap-4 text-xs text-slate-400">
          <span v-for="(col, field) in effectiveMapping" :key="field">
            {{ preview.labels[field] }} ← <span class="text-slate-200">{{ col }}</span>
          </span>
        </div>

        <!-- 单位与价格口径 -->
        <div class="flex flex-wrap items-center gap-6">
          <label class="flex items-center gap-2 text-xs text-slate-400">
            数量单位
            <select v-model="unit" class="rounded-lg border border-white/10 bg-ink/60 px-3 py-1.5 text-sm text-slate-200 outline-none focus:border-indigo-400/40">
              <option value="股">股</option>
              <option value="手">手</option>
            </select>
          </label>
          <label class="flex items-center gap-2 text-xs text-slate-400">
            价格口径
            <select v-model="basis" class="rounded-lg border border-white/10 bg-ink/60 px-3 py-1.5 text-sm text-slate-200 outline-none focus:border-indigo-400/40">
              <option value="未复权">未复权</option>
              <option value="复权或不确定">复权或不确定</option>
            </select>
          </label>
        </div>
        <p v-if="basis !== '未复权'" class="text-xs text-slate-500">
          复权或不确定价格仍可检查时间线和数量；成交价格将标为证据不足。
        </p>

        <!-- 执行核查 -->
        <button
          class="rounded-lg bg-indigo-500 px-5 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!mappingComplete || checking"
          @click="doCheck"
        >
          {{ checking ? '核查中…' : '检查' }}
        </button>
      </div>
    </SectionCard>

    <!-- 解析错误 -->
    <SectionCard v-if="result?.status === 'errors'" title="解析错误" hint="请先修正以下问题，不会静默丢弃错误行">
      <DataTable :columns="errorCols" :rows="result.errors.map((e) => ({ 表格行: String(e['表格行']), 字段: String(e['字段']), 原值: String(e['原值']), 问题: String(e['问题']) }))" empty="无错误" />
    </SectionCard>

    <!-- 核查结果 -->
    <template v-if="result?.status === 'ok'">
      <!-- 结论横幅 -->
      <div class="glass rounded-2xl p-6">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-xs text-slate-500">总览</p>
            <p class="mt-1 text-2xl font-bold" :class="VERDICT_TONE[result.verdict] || 'text-white'">{{ result.verdict }}</p>
            <p class="mt-1 text-xs text-slate-500">结论仅针对本次材料及可核查项目，不证明策略有效或原始材料真实。</p>
          </div>
          <button class="rounded-lg border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-slate-300 transition hover:border-white/25 hover:text-white" @click="downloadReport">
            下载检查报告
          </button>
        </div>
        <!-- 统计 -->
        <div class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div v-for="label in ORDER" :key="label" class="rounded-xl border border-white/10 bg-white/5 p-4 text-center">
            <p class="text-2xl font-bold" :class="VERDICT_TONE[label]">{{ result.counts[label] || 0 }}</p>
            <p class="mt-1 text-xs text-slate-400">{{ label }}</p>
          </div>
        </div>
        <p class="mt-3 text-xs text-slate-500">证据齐备的成交记录：{{ result.covered }}/{{ result.total }}；上方数字按核查项统计。</p>
      </div>

      <!-- 核查明细 -->
      <SectionCard title="核查明细" hint="每条核查项的结论与证据">
        <DataTable :columns="findingCols" :rows="filteredFindings" empty="无核查发现">
          <template #cell-结论="{ row }">
            <span class="inline-flex rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap" :class="VERDICT_TONE[row['结论']] || 'text-slate-300 bg-white/5 border-white/10'">
              {{ row['结论'] }}
            </span>
          </template>
        </DataTable>
      </SectionCard>
    </template>
  </div>
</template>
