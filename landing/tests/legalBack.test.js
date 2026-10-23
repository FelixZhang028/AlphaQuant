import test from 'node:test'
import assert from 'node:assert/strict'
import { backLink } from '../src/legal/legalBack.js'

const ORIGIN = 'https://prismind.example.test'

test('条款页的返回：回到本站来的那个页面', () => {
  assert.deepEqual(backLink(`${ORIGIN}/app.html?view=points`, ORIGIN), { href: `${ORIGIN}/app.html?view=points`, label: '返回功能台' })
  assert.deepEqual(backLink(`${ORIGIN}/auth.html`, ORIGIN), { href: `${ORIGIN}/auth.html`, label: '返回登录' })
  assert.deepEqual(backLink(`${ORIGIN}/community.html`, ORIGIN), { href: `${ORIGIN}/community.html`, label: '返回' })
})

test('条款页的返回：直接打开、从别的网站来、从条款页自己来，都回首页', () => {
  for (const referrer of ['', 'https://other.example.test/app.html', `${ORIGIN}/legal.html#privacy`]) {
    assert.deepEqual(backLink(referrer, ORIGIN), { href: '/', label: '返回首页' })
  }
})
