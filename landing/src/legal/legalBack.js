// 条款页的“返回”：从本站哪个页面来，就回到哪个页面；从别的网站来、新标签页打开、或者直接打开，就回首页。
// 不用 history.back()：页面里切换“服务条款 / 隐私政策 / 风险提示”会改地址里的 #，后退只会在这三份之间来回。
export function backLink(referrer, origin) {
  let from
  try {
    from = new URL(referrer)
  } catch {
    return { href: '/', label: '返回首页' }
  }
  if (from.origin !== origin || from.pathname.endsWith('/legal.html')) return { href: '/', label: '返回首页' }
  if (from.pathname.endsWith('/app.html')) return { href: from.href, label: '返回功能台' }
  if (from.pathname.endsWith('/auth.html')) return { href: from.href, label: '返回登录' }
  return { href: from.href, label: '返回' }
}
