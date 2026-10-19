// 全局主题基础设施：light / dark 双主题
// - 首次访问跟随系统 prefers-color-scheme，用户手动切换后持久化到 localStorage
// - 设置页可以选“跟随系统”：清除保存的选择，系统切换深浅色时页面跟着变
// - 主题通过 <html data-theme="light|dark"> 应用（HTML 内联脚本已在首屏前设置，避免闪烁）
import { ref } from 'vue'

const STORAGE_KEY = 'fq-theme'

function preferredTheme() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

const theme = ref(preferredTheme())
// light / dark：用户选定；system：跟随系统
const mode = ref((() => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  } catch {
    return 'system'
  }
})())

function applyTheme(t) {
  document.documentElement.dataset.theme = t
}

const systemQuery = window.matchMedia?.('(prefers-color-scheme: light)')
systemQuery?.addEventListener?.('change', (event) => {
  if (mode.value !== 'system') return
  theme.value = event.matches ? 'light' : 'dark'
  applyTheme(theme.value)
})

// 模块加载时同步一次（与 HTML 内联脚本结果一致，保证 Vue 状态与 DOM 同步）
applyTheme(theme.value)

export function useTheme() {
  function setMode(next) {
    mode.value = next
    try {
      if (next === 'system') localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, next)
    } catch { /* 记不住也照样切换 */ }
    theme.value = next === 'system' ? (systemQuery?.matches ? 'light' : 'dark') : next
    applyTheme(theme.value)
  }
  function toggle() {
    setMode(theme.value === 'dark' ? 'light' : 'dark')
  }
  return { theme, mode, toggle, setMode }
}
