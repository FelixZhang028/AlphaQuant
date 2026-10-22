import assert from 'node:assert/strict'
import test from 'node:test'
import { closeLegal, legalDialog, legalIdFromHref, openLegal, shouldOpenInDialog } from '../src/legal/legalDialog.js'

test('条款链接对应哪一份，别的链接不管', () => {
  assert.equal(legalIdFromHref('/legal.html#privacy'), 'privacy')
  assert.equal(legalIdFromHref('/legal.html#risk'), 'risk')
  assert.equal(legalIdFromHref('/legal.html'), 'terms')
  assert.equal(legalIdFromHref('https://prismind.example/legal.html#terms'), 'terms')
  assert.equal(legalIdFromHref('/app.html?view=points'), '')
  assert.equal(legalIdFromHref('/index.html#about'), '')
})

test('普通点击用弹窗；按住修饰键、中键、在条款页上照旧打开页面', () => {
  const click = { button: 0, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, defaultPrevented: false }
  assert.equal(shouldOpenInDialog(click, '/auth.html'), true)
  assert.equal(shouldOpenInDialog({ ...click, ctrlKey: true }, '/auth.html'), false)
  assert.equal(shouldOpenInDialog({ ...click, metaKey: true }, '/app.html'), false)
  assert.equal(shouldOpenInDialog({ ...click, button: 1 }, '/'), false)
  assert.equal(shouldOpenInDialog(click, '/legal.html'), false)
})

test('打开和关闭', () => {
  openLegal('risk')
  assert.deepEqual({ ...legalDialog }, { open: true, id: 'risk' })
  openLegal('nonsense')
  assert.equal(legalDialog.id, 'terms')
  closeLegal()
  assert.equal(legalDialog.open, false)
})
