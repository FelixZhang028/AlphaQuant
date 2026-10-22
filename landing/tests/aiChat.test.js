import test from 'node:test'
import assert from 'node:assert/strict'
import {
  BUBBLE_DAILY_MAX, DEFAULT_OFFSET, MARGIN, blockLinks, boxFromSpot, bubbleBelow, bubbleFor, chatContext, clampBox, codeColumn, dataSummary,
  focusText, isDrag, nextBubble, panelBox, spotFromBox, suggestionsFor, usageText,
} from '../src/workspace/aiChat.js'

test('推荐问题：看着一只股票或一次回测时换成和它有关的问题，否则按页面推荐', () => {
  assert.match(suggestionsFor('market-lookup', { symbol: '600519', name: '贵州茅台' })[0], /^贵州茅台最近四个季度/)
  assert.match(suggestionsFor('backtest-review', { backtest: 3 })[0], /这次回测的最大回撤/)
  assert.equal(suggestionsFor('factor-lab', null)[0], '动量类因子有哪些？')
  assert.equal(suggestionsFor('没有这个页面', null).length, 3)
})

test('正在看的内容：显示的说法和发给后端的内容；用户可以不带上', () => {
  const focus = { symbol: '600519', name: '贵州茅台' }
  assert.equal(focusText(focus), '贵州茅台（600519）')
  assert.equal(focusText({ backtest: 7 }), '第 7 号回测')
  assert.equal(focusText(null), '')
  assert.deepEqual(chatContext('股票查询', focus), { page: '股票查询', symbol: '600519' })
  assert.deepEqual(chatContext('股票查询', focus, false), { page: '股票查询' })
  assert.deepEqual(chatContext('策略回测', { backtest: 7 }), { page: '策略回测', backtest: '7' })
  assert.deepEqual(chatContext('', null), {})
})

test('数据表里的代码可以点；数据块下面的跳转', () => {
  assert.equal(codeColumn({ columns: ['排名', '股票', '代码'] }), 2)
  assert.equal(codeColumn({ columns: ['项目', '数值'] }), -1)
  const stock = blockLinks({ kind: 'stock', symbols: ['600519'] })
  assert.deepEqual(stock.map((link) => link.view), ['market-lookup', 'agent-lab'])
  assert.deepEqual(blockLinks({ kind: 'financials', symbols: ['600519'] })[0].context, { symbol: '600519', mode: 'financials' })
  assert.deepEqual(blockLinks({ kind: 'backtest', backtest: 3 }), [{ label: '打开这次回测', view: 'backtest-review', context: { run: 3 } }])
  assert.deepEqual(blockLinks({ kind: 'stock', error: '没有找到' }), [])
  assert.equal(dataSummary({ data: [{ title: 'a' }, { title: 'b', error: 'x' }] }), '用到的数据（1 项，1 项没有查到）')
  assert.equal(dataSummary({ data: [{ title: 'a' }] }), '用到的数据（1 项）')
  assert.equal(dataSummary({ data: [{ title: 'b', error: 'x' }] }), '查过的数据（1 项没有查到）')
})

test('次数的说法', () => {
  assert.equal(usageText({ limit: 20, used: 2, remaining: 18 }), '今天还能免费问 18 次（每天 20 次）')
  assert.equal(usageText({ limit: 20, used: 20, remaining: 0 }), '今天的 20 次免费已用完，明天再来')
  assert.equal(usageText({ limit: 10, used: 10, remaining: 0, cost: 2, points: 96 }), '今天的 10 次免费已用完，再问每次 2 积分（现有 96）')
  assert.equal(usageText({ limit: null, used: 5, remaining: null }), '管理员不限次数')
  assert.equal(usageText(null), '')
})

const screen = { width: 1400, height: 900 }
const pill = { width: 100, height: 48 }

test('拖动：移动几个像素以内算点击；松手就停在那里，按比例记，换了窗口大小也在屏幕里', () => {
  assert.equal(isDrag({ x: 10, y: 10 }, { x: 13, y: 13 }), false)
  assert.equal(isDrag({ x: 10, y: 10 }, { x: 20, y: 10 }), true)
  // 默认不贴角落：离右边、下边各留一段
  assert.deepEqual(boxFromSpot(null, screen, pill), { left: 1400 - 100 - DEFAULT_OFFSET.right, top: 900 - 48 - DEFAULT_OFFSET.bottom })
  // 拖到哪里就停在哪里（不吸附到两边）
  const spot = spotFromBox({ left: 700, top: 400 }, screen, pill)
  assert.deepEqual(boxFromSpot(spot, screen, pill), { left: 700, top: 400 })
  assert.deepEqual(spotFromBox({ left: -50, top: 5000 }, screen, pill), { x: 0, y: 1 })
  // 窗口变小以后还在屏幕里
  const small = boxFromSpot(spot, { width: 600, height: 500 }, pill)
  assert.ok(small.left >= MARGIN && small.left + pill.width <= 600 - MARGIN)
  assert.ok(small.top >= MARGIN && small.top + pill.height <= 500 - MARGIN)
  assert.deepEqual(boxFromSpot({ x: 'oops' }, screen, pill), boxFromSpot(null, screen, pill))
  assert.deepEqual(clampBox({ left: -40, top: 2000 }, screen, pill), { left: MARGIN, top: 900 - 48 - MARGIN })
})

test('窗口跟着按钮：右半边右对齐、左半边左对齐；下半边往上展开、上半边往下展开；整个留在屏幕里', () => {
  const panel = { width: 400, height: 640 }
  assert.deepEqual(panelBox({ left: 1000, top: 760 }, pill, screen, panel), { left: 1000 + 100 - 400, top: 760 + 48 - 640 })
  assert.deepEqual(panelBox({ left: 100, top: 60 }, pill, screen, panel), { left: 100, top: 60 })
  assert.deepEqual(panelBox({ left: 1280, top: 300 }, pill, screen, panel), { left: 1400 - 400 - MARGIN, top: 240 })
  assert.equal(bubbleBelow({ top: 60 }), true)
  assert.equal(bubbleBelow({ top: 700 }), false)
})

test('气泡：跟着页面说话；每天最多几次，同一句一天只说一次，关掉或用过以后只在换股票时再说', () => {
  const general = bubbleFor('market-lookup', null)
  assert.equal(general.key, 'general')
  assert.match(general.text, /^有问题可以问我，比如：/)
  const moutai = bubbleFor('market-lookup', { symbol: '600519', name: '贵州茅台' })
  assert.equal(moutai.text, '要不要问问贵州茅台最近四个季度的利润？')
  assert.match(moutai.question, /^贵州茅台最近四个季度/)
  assert.equal(bubbleFor('backtest-review', { backtest: 3 }).key, 'backtest:3')

  let step = nextBubble(null, general, '2026-10-20')
  assert.equal(step.show, true)
  step = nextBubble(step.memory, general, '2026-10-20')
  assert.equal(step.show, false)                                     // 同一句一天只说一次
  const quiet = { ...step.memory, quiet: true }
  assert.equal(nextBubble(quiet, general, '2026-10-21').show, false)  // 关掉过：第二天也不再说泛泛的话
  assert.equal(nextBubble(quiet, moutai, '2026-10-21').show, true)    // 换到一只股票时再说
  let memory = null
  const shown = [1, 2, 3, 4].map((i) => {
    const result = nextBubble(memory, { key: `stock:${i}` }, '2026-10-22')
    memory = result.memory
    return result.show
  })
  assert.deepEqual(shown, [true, true, true, false])
  assert.equal(BUBBLE_DAILY_MAX, 3)
})
