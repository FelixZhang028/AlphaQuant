// 全局主题基础设施：light / dark 双主题
// - 首次访问跟随系统 prefers-color-scheme，用户手动切换后持久化到 localStorage
// - 主题通过 <html data-theme="light|dark"> 应用（HTML 内联脚本已在首屏前设置，避免闪烁）
import { ref } from 'vue'

const STORAGE_KEY = 'fq-theme'

function preferredTheme() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

const theme = ref(preferredTheme())

function applyTheme(t) {
  document.documentElement.dataset.theme = t
}

// 模块加载时同步一次（与 HTML 内联脚本结果一致，保证 Vue 状态与 DOM 同步）
applyTheme(theme.value)

export function useTheme() {
  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    localStorage.setItem(STORAGE_KEY, theme.value)
    applyTheme(theme.value)
  }
  return { theme, toggle }
}
