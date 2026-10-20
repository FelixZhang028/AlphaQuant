// 右下角 AI 问答：按页面推荐的问题、发给后端的“正在看什么”、数据表里能点的股票、次数的说法。

// 每个页面推荐的问题；看着一只股票或一次回测时，换成和它有关的问题。
const PAGE_SUGGESTIONS = {
  'market-lookup': ['沪深300里市盈率最低的 10 只是哪些？', '平台的财务数据从哪天开始？'],
  'market-chart': ['上证50里近 60 个交易日涨幅最大的是哪些？', '什么是 RSI？'],
  'agent-lab': ['比较一下招商银行和平安银行的净资产收益率和负债率', '白酒行业毛利率最高的有哪些？'],
  'factor-lab': ['动量类因子有哪些？', '市净率因子是怎么算的？'],
  'backtest-review': ['我最近几次回测的结果怎么样？', '什么是夏普比率？'],
  research: ['我最近几次回测的结果怎么样？', '什么是样本外检验？'],
  'run-library': ['我最近几次回测的结果怎么样？', '最大回撤是什么意思？'],
  'data-guide': ['平台有哪些数据，各从哪天开始？', '估值与换手率的数据覆盖多少只股票？'],
}
const DEFAULT_SUGGESTIONS = ['沪深300里市盈率最低的 10 只是哪些？', '银行股里净资产收益率最高的有哪些？', '平台有哪些数据？']

export function suggestionsFor(view, focus) {
  if (focus?.symbol) {
    const who = focus.name || focus.symbol
    return [`${who}最近四个季度的利润怎么变的？`, `${who}的估值在同行里是什么位置？`, `${who}和同行业市值最大的几家比一比`]
  }
  if (focus?.backtest) return ['这次回测的最大回撤发生在什么时候？', '这次回测收益最好和最差的是哪几个月？', '这次回测和沪深300比怎么样？']
  return PAGE_SUGGESTIONS[view] || DEFAULT_SUGGESTIONS
}

export function focusText(focus) {
  if (focus?.symbol) return focus.name ? `${focus.name}（${focus.symbol}）` : focus.symbol
  if (focus?.backtest) return `第 ${focus.backtest} 号回测`
  return ''
}

// 发给后端的“正在看什么”；用户点了“不带上”时只带页面名称。
export function chatContext(label, focus, include = true) {
  const context = label ? { page: label } : {}
  if (include && focus?.symbol) context.symbol = String(focus.symbol)
  if (include && focus?.backtest) context.backtest = String(focus.backtest)
  return context
}

// 数据表里“代码”那一列可以点：打开这只股票。
export function codeColumn(block) {
  return (block?.columns || []).indexOf('代码')
}
// 每个数据块下面的跳转：股票数据和财报可以去股票查询或分析这只股票；回测可以打开那次回测。
export function blockLinks(block) {
  if (!block || block.error) return []
  if ((block.kind === 'stock' || block.kind === 'financials') && block.symbols?.length) {
    const symbol = block.symbols[0]
    const lookup = block.kind === 'financials'
      ? { label: '看全部历期财报', view: 'market-lookup', context: { symbol, mode: 'financials' } }
      : { label: '在股票查询里打开', view: 'market-lookup', context: { symbol } }
    return [lookup, { label: '分析这只股票', view: 'agent-lab', context: { symbol } }]
  }
  if (block.kind === 'backtest' && block.backtest) return [{ label: '打开这次回测', view: 'backtest-review', context: { run: block.backtest } }]
  return []
}

export function usageText(usage) {
  if (!usage) return ''
  if (usage.limit === null || usage.limit === undefined) return '管理员不限次数'
  return usage.remaining > 0 ? `今天还能问 ${usage.remaining} 次（每天 ${usage.limit} 次）` : `今天的 ${usage.limit} 次已经用完，明天再来`
}

// “用到的数据（2 项，1 项没有查到）”
export function dataSummary(turn) {
  const blocks = turn?.data || []
  const missing = blocks.filter((block) => block.error).length
  const found = blocks.length - missing
  if (!found) return `查过的数据（${missing} 项没有查到）`
  return `用到的数据（${found} 项${missing ? `，${missing} 项没有查到` : ''}）`
}

// ---------- 位置：按钮可以拖动，松手后贴到左边或右边 ----------
export const MARGIN = 20
export const DRAG_THRESHOLD = 5
// 默认在右下角。上下位置按比例记（0 最上面，1 最下面），浏览器窗口变大变小都还在屏幕里。
export const DEFAULT_DOCK = { side: 'right', ratio: 1 }

const clamp = (value, low, high) => Math.min(Math.max(value, low), Math.max(low, high))

// 只移动一点点算点击，超过几个像素才算拖动，拖完不会误打开窗口。
export function isDrag(start, point) {
  return Math.hypot(point.x - start.x, point.y - start.y) > DRAG_THRESHOLD
}
// 松手时按钮左上角的位置 -> 贴到离得近的那一边，记下上下的比例。
export function snapDock(point, viewport, size) {
  const side = point.x + size.width / 2 < viewport.width / 2 ? 'left' : 'right'
  const room = viewport.height - size.height - 2 * MARGIN
  const ratio = room > 0 ? clamp((point.y - MARGIN) / room, 0, 1) : 1
  return { side, ratio: Math.round(ratio * 10000) / 10000 }
}
// 贴边的按钮在屏幕上的位置（左上角）。
export function dockedBox(dock, viewport, size) {
  const room = Math.max(0, viewport.height - size.height - 2 * MARGIN)
  const ratio = Number.isFinite(dock?.ratio) ? clamp(dock.ratio, 0, 1) : 1
  return { left: dock?.side === 'left' ? MARGIN : Math.max(MARGIN, viewport.width - size.width - MARGIN), top: Math.round(MARGIN + room * ratio) }
}
// 任意位置放回屏幕里（拖动中的按钮、拖动过的窗口）。
export function clampBox(box, viewport, size) {
  return {
    left: clamp(box.left, MARGIN, viewport.width - size.width - MARGIN),
    top: clamp(box.top, MARGIN, viewport.height - size.height - MARGIN),
  }
}
// 窗口跟着按钮：按钮在哪一边就从哪一边弹出，底边和按钮底边对齐，整个窗口留在屏幕里。
export function panelBox(button, buttonSize, viewport, panelSize) {
  const left = button.left + buttonSize.width / 2 < viewport.width / 2 ? MARGIN : viewport.width - panelSize.width - MARGIN
  return clampBox({ left, top: button.top + buttonSize.height - panelSize.height }, viewport, panelSize)
}
// 气泡在按钮上面；按钮太靠上时放到下面。
export function bubbleBelow(button) {
  return button.top < 140
}

// ---------- 气泡：像在说话，提醒可以问 AI ----------
export const BUBBLE_DAILY_MAX = 3
export function bubbleFor(view, focus) {
  const question = suggestionsFor(view, focus)[0]
  if (focus?.symbol) {
    return { key: `stock:${focus.symbol}`, text: `要不要问问${focus.name || focus.symbol}最近四个季度的利润？`, question }
  }
  if (focus?.backtest) return { key: `backtest:${focus.backtest}`, text: '想知道这次回测的回撤发生在什么时候吗？', question }
  return { key: 'general', text: `有问题可以问我，比如：${question}`, question }
}
// 要不要弹出这个气泡：每天最多几次，同一个提示一天只说一次；
// 用户关掉过或者用过 AI 问答（quiet）以后，只在换到另一只股票、另一次回测时再提示。
export function nextBubble(memory, bubble, today) {
  const current = memory?.day === today ? memory : { day: today, count: 0, keys: [], quiet: Boolean(memory?.quiet) }
  const blocked = current.count >= BUBBLE_DAILY_MAX || current.keys.includes(bubble.key) || (current.quiet && bubble.key === 'general')
  if (blocked) return { show: false, memory: current }
  return { show: true, memory: { ...current, count: current.count + 1, keys: [...current.keys, bubble.key] } }
}

// 只记在这台电脑的浏览器里：窗口开着还是收起、正在看哪个对话、按钮和窗口的位置、气泡说过什么。
// 读写失败（隐私模式等）时当作没有。
const STORAGE_KEY = 'fq_ai_chat'
export function loadChatState() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {} } catch { return {} }
}
export function saveChatState(patch) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...loadChatState(), ...patch })) } catch { /* 存不了也不影响使用 */ }
}
