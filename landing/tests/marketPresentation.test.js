import assert from 'node:assert/strict'
import test from 'node:test'
import { CURRENT_POOL, marketChoices, marketLabel, marketNote, usableMarket } from '../src/workspace/marketPresentation.js'

const markets = [
  { value: '当前股票池', label: '当前股票池', available: true },
  { value: '000300.SH', label: '沪深300历史成分股', available: true, start_date: '2015-01-05', end_date: '2026-10-12' },
  { value: '000905.SH', label: '中证500历史成分股', available: false, start_date: null, end_date: null },
]

test('没有下载成分股历史的指数不能选，并写明原因', () => {
  assert.deepEqual(marketChoices(markets), [
    { value: '当前股票池', label: '当前股票池', disabled: false },
    { value: '000300.SH', label: '沪深300历史成分股', disabled: false },
    { value: '000905.SH', label: '中证500历史成分股（未下载）', disabled: true },
  ])
  // 目录还没有加载出来时，只有自己的股票池。
  assert.deepEqual(marketChoices([]), [{ value: CURRENT_POOL, label: '当前股票池', disabled: false }])
  assert.deepEqual(marketChoices(undefined).map((item) => item.value), [CURRENT_POOL])
})

test('结果页显示范围的名称，不显示指数代码', () => {
  assert.equal(marketLabel('000300.SH', markets), '沪深300历史成分股')
  assert.equal(marketLabel('当前股票池', markets), '当前股票池')
  assert.equal(marketLabel('当前股票池', []), '当前股票池')
  assert.equal(marketLabel('399001.SZ', markets), '399001.SZ')
  assert.equal(marketLabel(undefined, markets), '')
})

test('选中指数时说明用的是当时的名单，以及名单覆盖的日期', () => {
  assert.equal(marketNote('当前股票池', markets), '')
  assert.equal(marketNote('000300.SH', markets),
    '每个调仓日只在当时的成分股里选股，不使用今天的名单。成分股历史从 2015-01-05 开始，核对到 2026-10-12；开始日期不能早于 2015-01-05。')
  assert.equal(marketNote('000905.SH', markets), '还没有下载中证500历史成分股，请先到「数据更新」下载指数成分股。')
  assert.equal(marketNote('000300.SH', []), '')
})

test('带入以前的配置时，范围已经不能选就回到自己的股票池', () => {
  assert.equal(usableMarket('000300.SH', markets), '000300.SH')
  assert.equal(usableMarket('000905.SH', markets), CURRENT_POOL)
  assert.equal(usableMarket(undefined, markets), CURRENT_POOL)
  assert.equal(usableMarket('000300.SH', []), CURRENT_POOL)
})

test('因子研究的范围说明，以及默认用哪个范围', async () => {
  const { factorUniverseNote, defaultFactorUniverse } = await import('../src/workspace/marketPresentation.js')
  assert.match(factorUniverseNote('当前股票池', markets), /股票很少时.*建议选择指数/)
  assert.equal(factorUniverseNote('000300.SH', markets),
    '每天只用那天在指数里的股票，不用今天的名单；Alpha101 的截面排名也只在当天的成分股之间进行。成分股历史从 2015-01-05 开始，开始日期不能早于这一天。')
  assert.equal(factorUniverseNote('000905.SH', markets), '还没有下载中证500历史成分股，请先到「数据更新」下载指数成分股。')
  assert.equal(factorUniverseNote('000300.SH', []), '')
  assert.equal(defaultFactorUniverse(markets, ''), '000300.SH')                 // 没用过：有沪深300 就用它
  assert.equal(defaultFactorUniverse(markets, '当前股票池'), '当前股票池')     // 用过的优先
  assert.equal(defaultFactorUniverse(markets, '000905.SH'), '000300.SH')       // 用过的现在不能选了
  assert.equal(defaultFactorUniverse([], ''), CURRENT_POOL)
})
