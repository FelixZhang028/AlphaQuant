import test from 'node:test'
import assert from 'node:assert/strict'
import { barHeights, initialForm, pendingChanges, providerOf, secretPlaceholder, sourceText, tokensText } from '../src/settings.js'

const groups = [{
  key: 'ai', items: [
    { name: 'OPENROUTER_API_KEY', kind: 'secret', value: '', masked: 'sk-o…cdef', configured: true, source: 'admin' },
    { name: 'FELLOWQUANT_AI_MODEL', kind: 'text', value: 'deepseek/deepseek-v4-pro', source: 'env', configured: true },
    { name: 'FELLOWQUANT_AI_BASE_URL', kind: 'url', value: '', source: 'default', default: 'https://openrouter.ai/api/v1' },
  ],
}]

test('服务商：按接口地址认出来', () => {
  assert.equal(providerOf(''), 'openrouter')
  assert.equal(providerOf('https://openrouter.ai/api/v1/'), 'openrouter')
  assert.equal(providerOf('https://api.deepseek.com/v1'), 'deepseek')
  assert.equal(providerOf('http://127.0.0.1:11434/v1'), 'custom')
})

test('表单：密钥一开始是空的；只有改过的项和填了的密钥算修改；改回用 .env 单独算', () => {
  const form = initialForm(groups)
  assert.deepEqual(form, { OPENROUTER_API_KEY: '', FELLOWQUANT_AI_MODEL: 'deepseek/deepseek-v4-pro', FELLOWQUANT_AI_BASE_URL: '' })
  assert.equal(pendingChanges(groups, form).count, 0)
  form.FELLOWQUANT_AI_MODEL = ' qwen-plus '
  form.OPENROUTER_API_KEY = 'new-key'
  assert.deepEqual(pendingChanges(groups, form), { values: { FELLOWQUANT_AI_MODEL: 'qwen-plus', OPENROUTER_API_KEY: 'new-key' }, clear: [], count: 2 })
  assert.deepEqual(pendingChanges(groups, form, ['OPENROUTER_API_KEY']), { values: { FELLOWQUANT_AI_MODEL: 'qwen-plus' }, clear: ['OPENROUTER_API_KEY'], count: 2 })
})

test('每一项的来源和密钥的提示', () => {
  assert.equal(sourceText(groups[0].items[0]), '后台设置')
  assert.equal(sourceText(groups[0].items[1]), '来自 .env')
  assert.equal(sourceText(groups[0].items[2]), '默认')
  assert.equal(sourceText({ source: 'default', configured: false, default: '' }), '未设置')
  assert.equal(sourceText({ source: 'admin', unreadable: true }), '后台设置（解不开）')
  assert.equal(secretPlaceholder(groups[0].items[0]), '已设置 sk-o…cdef，留空表示不修改')
  assert.equal(secretPlaceholder({ configured: false }), '还没有设置')
  assert.match(secretPlaceholder({ unreadable: true }), /APP_SECRET/)
})

test('AI 用量图和 token 的说法', () => {
  assert.deepEqual(barHeights([{ total: 0 }, { total: 5 }, { total: 10 }]), [0, 50, 100])
  assert.deepEqual(barHeights([{ total: 0 }]), [0])
  assert.equal(tokensText(0), '没有记录')
  assert.equal(tokensText(8500), '8500')
  assert.equal(tokensText(123456), '12.3 万')
})
