import assert from 'node:assert/strict'
import test from 'node:test'
import { coverageText, lastText, progressText } from '../src/workspace/dailyUpdate.js'

test('数据覆盖：说明更新到哪一天、这天有多少只股票，不完整时提醒', () => {
  assert.equal(coverageText(null), '本地还没有行情数据')
  assert.equal(coverageText({ latest_date: '2026-10-15', stocks_on_latest: 5224, listed: 5320 }),
    '数据更新到 2026-10-15，这一天有 5,224 只股票的行情（在市 5,320 只）')
  assert.equal(coverageText({ latest_date: '2026-10-13', stocks_on_latest: 146, listed: 5320 }),
    '数据更新到 2026-10-13，这一天有 146 只股票的行情（在市 5,320 只）；这一天的行情还不完整')
  assert.equal(coverageText({ latest_date: '2026-10-13', stocks_on_latest: 146, listed: 0 }), '数据更新到 2026-10-13，这一天有 146 只股票的行情')
})

test('上次更新：结果、是不是交易日、是谁运行的', () => {
  assert.equal(lastText(null), '还没有运行过每日更新')
  assert.equal(lastText({ trade_date: '2026-10-15', status: 'SUCCESS', market: 'updated', summary: '更新了 5,300 只股票的行情', trigger: 'auto' }),
    '上次更新：2026-10-15 完成，更新了 5,300 只股票的行情')
  assert.equal(lastText({ trade_date: '2026-10-01', status: 'SUCCESS', market: 'closed', summary: '', trigger: 'auto' }),
    '上次更新：2026-10-01 不是交易日，没有更新')
  assert.equal(lastText({ trade_date: '2026-10-16', status: 'PARTIAL', market: 'updated', summary: '1 项没有完成', trigger: 'admin' }),
    '上次更新：2026-10-16 部分完成（管理员手动运行），1 项没有完成')
})

test('进度：正在做哪一步，下载行情时显示做到第几只', () => {
  assert.equal(progressText(null), '正在准备')
  assert.equal(progressText({ stage: 'daily_bars', done: 1200, total: 5320 }), '下载日线行情 1,200 / 5,320')
  assert.equal(progressText({ stage: 'industry', done: 0, total: 1 }), '更新行业分类')
})

test('后端给出的结果说明优先：没下载、先补前几天、被数据源拒绝', () => {
  assert.equal(lastText({ trade_date: '2026-10-20', status: 'SUCCESS', market: 'not_ready', outcome: '当天的行情还没有发布，先补到 2026-10-19', summary: '更新了 5,300 只股票的行情', trigger: 'admin' }),
    '上次更新：2026-10-20 当天的行情还没有发布，先补到 2026-10-19（管理员手动运行），更新了 5,300 只股票的行情')
  assert.equal(lastText({ trade_date: '2026-10-19', status: 'FAILED', outcome: '没有完成：数据源 BaoStock 暂时拒绝了这台服务器', blocked: true, summary: '', trigger: 'auto' }),
    '上次更新：2026-10-19 没有完成：数据源 BaoStock 暂时拒绝了这台服务器')
})
