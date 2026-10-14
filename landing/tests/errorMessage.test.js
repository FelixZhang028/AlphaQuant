import assert from 'node:assert/strict'
import test from 'node:test'
import { sanitizeError } from '../src/errorMessage.js'

const GENERIC = '请求失败，请稍后重试'

test('全中文的提示原样显示，不被当成空消息', () => {
  for (const message of [
    '本地还没有行业分类，请先在「数据更新」里下载后再使用。',
    '本地还没有估值与换手率数据，请先在「数据更新」里补全后再使用。',
    '股票池是空的，请先在股票池管理里添加股票',
    '回测不存在',
  ]) assert.equal(sanitizeError(message), message)
})

test('技术细节被去掉，只留下给人看的那句话', () => {
  assert.equal(sanitizeError('ValueError: 评估区间内没有行情数据'), '评估区间内没有行情数据')
  assert.equal(sanitizeError('MISSING_CORPORATE_ACTION: 复权因子变化缺少公司行为'), '复权因子变化缺少公司行为')
  assert.equal(sanitizeError('Traceback (most recent call last):\n  File "a.py", line 3, in f\nKeyError: 股票不存在'), '股票不存在')
  assert.equal(sanitizeError('BaoStock 暂时连不上。请稍后重试。'), 'BaoStock 暂时连不上。请稍后重试。')
})

test('空的或只剩符号的消息换成通用提示', () => {
  for (const message of ['', null, undefined, ' ', '。', '——', '!!!']) assert.equal(sanitizeError(message), GENERIC)
})
