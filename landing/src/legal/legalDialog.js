// 服务条款、隐私政策、风险提示用弹窗显示，不离开当前页面（注册页填了一半的信息不会丢）。
// 页面上的链接照旧写 /legal.html#terms 这种地址：普通点击打开弹窗；
// 按住 Ctrl/⌘/Shift 点击或用鼠标中键时照常在新标签页打开；在条款页自己上不拦截。
import { reactive } from 'vue'

export const LEGAL_IDS = ['terms', 'privacy', 'risk']

export const legalDialog = reactive({ open: false, id: 'terms' })

export function openLegal(id = 'terms') {
  legalDialog.id = LEGAL_IDS.includes(id) ? id : 'terms'
  legalDialog.open = true
}

export function closeLegal() {
  legalDialog.open = false
}

// 链接地址是不是某一份条款："/legal.html#privacy" → "privacy"；别的地址返回空字符串。
export function legalIdFromHref(href, base = 'http://localhost/') {
  let url
  try {
    url = new URL(href, base)
  } catch {
    return ''
  }
  if (!/\/legal\.html$/.test(url.pathname)) return ''
  const id = url.hash.slice(1)
  return LEGAL_IDS.includes(id) ? id : 'terms'
}

// 这一次点击要不要换成弹窗：左键、没按修饰键、不是在条款页上。
export function shouldOpenInDialog(event, pathname) {
  if (event.defaultPrevented || event.button !== 0) return false
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return false
  return !/\/legal\.html$/.test(pathname)
}
