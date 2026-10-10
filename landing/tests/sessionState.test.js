import assert from 'node:assert/strict'
import test from 'node:test'
import { checkSavedSession } from '../src/sessionState.js'

function sessionFixture(fetchUser) {
  let token = 'saved-session'
  let clears = 0
  return {
    options: { readToken: () => token, fetchUser, clear: () => { token = null; clears += 1 } },
    token: () => token,
    clears: () => clears,
    replace: (value) => { token = value },
  }
}

test('有效会话恢复用户信息，不要求重新登录', async () => {
  const user = { id: 1, name: '测试账户' }
  const fixture = sessionFixture(async () => user)
  assert.deepEqual(await checkSavedSession(fixture.options), { status: 'authenticated', user })
  assert.equal(fixture.token(), 'saved-session')
  assert.equal(fixture.clears(), 0)
})

test('未登录时不调用用户接口', async () => {
  const fixture = sessionFixture(async () => { assert.fail('不应发送验证请求') })
  fixture.replace(null)
  assert.equal((await checkSavedSession(fixture.options)).status, 'anonymous')
  assert.equal(fixture.clears(), 0)
})

test('服务明确返回401时才清除失效会话', async () => {
  const fixture = sessionFixture(async () => { throw Object.assign(new Error('已过期'), { status: 401 }) })
  assert.equal((await checkSavedSession(fixture.options)).status, 'anonymous')
  assert.equal(fixture.token(), null)
  assert.equal(fixture.clears(), 1)
})

for (const status of [undefined, 403, 404, 500, 503]) {
  test(`连接异常或服务返回${status ?? '网络错误'}时保留登录，不误判过期`, async () => {
    const error = Object.assign(new Error('服务不可用'), { status })
    const fixture = sessionFixture(async () => { throw error })
    const result = await checkSavedSession(fixture.options)
    assert.equal(result.status, 'unavailable')
    assert.equal(result.error, error)
    assert.equal(fixture.token(), 'saved-session')
    assert.equal(fixture.clears(), 0)
  })
}

test('旧会话的401响应不能清除另一标签中新登录的会话', async () => {
  const fixture = sessionFixture(async () => {
    fixture.replace('new-session')
    throw Object.assign(new Error('旧登录已过期'), { status: 401 })
  })
  assert.equal((await checkSavedSession(fixture.options)).status, 'changed')
  assert.equal(fixture.token(), 'new-session')
  assert.equal(fixture.clears(), 0)
})

test('验证期间在另一标签退出，不恢复已退出账户的旧响应', async () => {
  const fixture = sessionFixture(async () => {
    fixture.replace(null)
    return { id: 1 }
  })
  assert.equal((await checkSavedSession(fixture.options)).status, 'changed')
  assert.equal((await checkSavedSession(fixture.options)).status, 'anonymous')
  assert.equal(fixture.token(), null)
})
