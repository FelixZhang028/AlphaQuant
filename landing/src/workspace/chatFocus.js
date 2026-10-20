// 每个页面正在看的内容（一只股票、一次回测），给右下角的 AI 问答用：问“这只”“这次回测”时知道指的是什么。
// 按页面分开记：切到别的页面再回来，还是原来看的那只。只在这次打开功能台期间有效，不保存。
import { reactive } from 'vue'

export const pageFocus = reactive({})
// 盖住右侧的浮层（例如因子研究的因子详情抽屉）打开时，悬浮按钮先让开。
export const overlays = reactive({ drawer: false })

export function setFocus(view, focus) {
  pageFocus[view] = focus && (focus.symbol || focus.backtest) ? { ...focus } : null
}
