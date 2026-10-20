// 系统设置页：服务商预设、每一项的来源、表单里改了哪些、AI 用量图的高度。

// 选一个服务商，自动填好接口地址和常用的模型名称（还要点保存才生效）。
export const PROVIDERS = [
  { key: 'openrouter', label: 'OpenRouter', base: '', model: 'deepseek/deepseek-v4-pro', note: '填上面的 OpenRouter 密钥即可，文本模型和 Jev 共用。' },
  { key: 'deepseek', label: 'DeepSeek', base: 'https://api.deepseek.com/v1', model: 'deepseek-chat', note: '在“文本模型密钥”里填 DeepSeek 的密钥。' },
  { key: 'qwen', label: '通义千问', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', note: '在“文本模型密钥”里填阿里云百炼的密钥。' },
  { key: 'custom', label: '其他 OpenAI 兼容服务', base: null, model: null, note: '自己填接口地址、模型名称和密钥。' },
]

// 根据现在的接口地址认出是哪个服务商。
export function providerOf(baseUrl) {
  const base = String(baseUrl || '').replace(/\/+$/, '')
  if (!base || base === 'https://openrouter.ai/api/v1') return 'openrouter'
  return PROVIDERS.find((p) => p.base && p.base === base)?.key || 'custom'
}

export const SOURCE_LABELS = { admin: '后台设置', env: '来自 .env', default: '默认' }
export function sourceText(item) {
  if (item.unreadable) return '后台设置（解不开）'
  if (item.source === 'default') return item.configured || item.default ? '默认' : '未设置'
  return SOURCE_LABELS[item.source] || item.source
}

// 表单的初始值：密钥永远是空的（留空表示不修改），其他项是现在的值。
export function initialForm(groups) {
  const form = {}
  for (const group of groups || []) for (const item of group.items) form[item.name] = item.kind === 'secret' ? '' : String(item.value ?? '')
  return form
}

// 和初始值不一样的项（密钥只要填了就算），以及要改回用 .env 的项。
export function pendingChanges(groups, form, clear = []) {
  const values = {}
  for (const group of groups || []) {
    for (const item of group.items) {
      if (clear.includes(item.name)) continue
      const now = String(form[item.name] ?? '').trim()
      if (item.kind === 'secret' ? now !== '' : now !== String(item.value ?? '').trim() && now !== '') values[item.name] = now
    }
  }
  return { values, clear: [...clear], count: Object.keys(values).length + clear.length }
}

export function secretPlaceholder(item) {
  if (item.unreadable) return '保存时用的 APP_SECRET 变了，解不开，请重新填写'
  return item.configured ? `已设置 ${item.masked}，留空表示不修改` : '还没有设置'
}

// AI 用量图：每天的柱子高度（相对最高的那天），没有用量时为 0。
export function barHeights(days) {
  const top = Math.max(0, ...(days || []).map((d) => d.total))
  return (days || []).map((d) => (top ? Math.round((d.total / top) * 100) : 0))
}
export function tokensText(tokens) {
  if (!tokens) return '没有记录'
  return tokens >= 10000 ? `${(tokens / 10000).toFixed(1)} 万` : String(tokens)
}
