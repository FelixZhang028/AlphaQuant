// 首屏前确定主题，避免闪烁：优先用户选择，其次跟随系统。
// 单独放成文件（不写在页面里），这样网站的内容安全策略可以只允许本站的脚本文件。
;(function () {
  var t = null
  try { t = localStorage.getItem('fq-theme') } catch (e) {}
  if (t !== 'light' && t !== 'dark') {
    t = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  }
  document.documentElement.dataset.theme = t
})()
