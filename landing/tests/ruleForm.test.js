import assert from 'node:assert/strict'
import test from 'node:test'
import {
  blankForm, blankRule, chooseIndicator, definitionFromForm, formFromDefinition, packagePayload, sourceLabel,
} from '../src/workspace/ruleForm.js'

const options = {
  indicators: { close: '收盘价', return_1d: '区间涨跌幅', sma: '移动平均线' },
  operators: { gt: '大于', lt: '小于' },
  indicator_windows: {
    close: null,
    return_1d: { default: 20, minimum: 1, maximum: 500 },
    sma: { default: 20, minimum: 2, maximum: 500 },
  },
}

// 「均线趋势」模板的写法：既有“指标比指标”，也有自定义周期。
const template = {
  name: '均线趋势',
  entry_logic: 'all',
  entry_rules: [
    { left: { name: 'close' }, operator: 'gt', right: { name: 'sma', window: 60 } },
    { left: { name: 'return_1d', window: 5 }, operator: 'lt', value: -0.03 },
  ],
  ranking: { indicator: { name: 'return_1d', window: 20 }, direction: 'descending' },
}

test('模板里的规则填进表单后再取出来，内容不变', () => {
  const form = formFromDefinition(template, { top_n: 7, rebalance: 'monthly' }, options)
  assert.equal(form.rules[0].compare, 'indicator')
  assert.deepEqual(form.rules[0].left, { name: 'close', window: null })
  assert.deepEqual(form.rules[0].right, { name: 'sma', window: 60 })
  assert.equal(form.rules[1].compare, 'value')
  assert.equal(form.rules[1].value, -0.03)
  assert.deepEqual([form.top_n, form.rebalance], [7, 'monthly'])
  assert.deepEqual(definitionFromForm(form), template)
})

test('空白表单是一条可以直接保存的条件，换指标时周期回到默认值', () => {
  const form = blankForm(options)
  assert.equal(form.rules.length, 1)
  assert.deepEqual(definitionFromForm({ ...form, name: ' 我的策略 ' }), {
    name: '我的策略', entry_logic: 'all',
    entry_rules: [{ left: { name: 'close' }, operator: 'gt', value: 0 }],
    ranking: { indicator: { name: 'close' }, direction: 'descending' },
  })
  const rule = blankRule(options)
  chooseIndicator(rule.left, 'sma', options)
  assert.deepEqual(rule.left, { name: 'sma', window: 20 })
  rule.left.window = 60
  chooseIndicator(rule.left, 'close', options)
  assert.deepEqual(rule.left, { name: 'close', window: null })
})

test('切换成“和数值比较”后不会把另一个指标一起提交', () => {
  const form = formFromDefinition(template, { top_n: 5, rebalance: 'weekly' }, options)
  form.rules[0].compare = 'value'
  form.rules[0].value = '12.5'
  const [first] = definitionFromForm(form).entry_rules
  assert.deepEqual(first, { left: { name: 'close' }, operator: 'gt', value: 12.5 })
})

test('请求体如实记录表单是从哪里开始的', () => {
  const form = formFromDefinition(template, { top_n: 5, rebalance: 'weekly' }, options)
  assert.equal(packagePayload(form, null).source, 'visual_builder')
  assert.equal(packagePayload(form, { kind: 'describe' }).source, 'nl_builder')
  const fromTemplate = packagePayload(form, { kind: 'template', template_id: 'ma_trend', style: 'aggressive' })
  assert.deepEqual([fromTemplate.source, fromTemplate.style, fromTemplate.top_n], ['template:ma_trend', 'aggressive', 5])
})

test('来源标签区分原样的模板和改过的模板', () => {
  assert.equal(sourceLabel('template:momentum:balanced'), '模板')
  assert.equal(sourceLabel('template_modified:momentum:balanced'), '基于模板修改')
  assert.equal(sourceLabel('copy:abc'), '副本')
  assert.equal(sourceLabel('nl_builder'), '一句话生成')
  assert.equal(sourceLabel('visual_builder'), '自己填写')
  assert.equal(sourceLabel(undefined), '规则策略')
})
