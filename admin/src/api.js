// 管理后台 API 封装（FastAPI）
// 开发时（npm run dev）连 http://127.0.0.1:8000；打包后放在网站的 /admin/ 下，连自己所在的地址。
export const API_BASE = import.meta.env.VITE_API_BASE || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')
// 功能台的地址：开发时是官网的开发服务器，部署后和管理后台同一个网站。
export const SITE_BASE = import.meta.env.DEV ? import.meta.env.VITE_SITE_BASE || 'http://localhost:5273' : ''

const TOKEN_KEY = 'zt_admin_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}
export function setSession(token) {
  localStorage.setItem(TOKEN_KEY, token)
}
export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
}

async function request(path, { method = 'GET', body, auth = false } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth) {
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  let data = null
  try {
    data = await res.json()
  } catch {
    /* ignore */
  }
  if (!res.ok) {
    // 422 的 detail 是一组字段错误，直接显示会变成 [object Object]。
    const detail = data && (Array.isArray(data.detail) ? '填写的内容不符合要求' : data.detail || data.message)
    const msg = detail || `请求失败 (${res.status})`
    const err = new Error(msg)
    err.status = res.status
    throw err
  }
  return data
}

// 登录（复用 /auth/login），前端校验 is_admin
export async function login(email, password) {
  const data = await request('/api/v1/auth/login', { method: 'POST', body: { email, password } })
  if (!data.user || !data.user.is_admin) {
    throw new Error('该账户无管理员权限')
  }
  setSession(data.token)
  return data
}

export function me() {
  return request('/api/v1/auth/me', { auth: true })
}
// 退出登录：通知后端让这个账户的令牌全部失效（功能台上的登录也一起失效）。
export function logout() {
  const token = getToken()
  clearSession()
  if (token) {
    fetch(`${API_BASE}/api/v1/auth/logout`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } }).catch(() => {})
  }
}
export function adminUsers() {
  return request('/api/v1/admin/users', { auth: true })
}
export function adminStats() {
  return request('/api/v1/admin/stats', { auth: true })
}
export function setUserActive(id, active) {
  return request(`/api/v1/admin/users/${id}/active`, { method: 'POST', body: { active }, auth: true })
}

// 注册方式与邀请码
export function registrationSettings() {
  return request('/api/v1/admin/registration', { auth: true })
}
export function setRegistrationMode(mode) {
  return request('/api/v1/admin/registration', { method: 'PUT', body: { mode }, auth: true })
}
export function createInvite({ code = '', max_uses = null, note = '' }) {
  return request('/api/v1/admin/invites', { method: 'POST', body: { code, max_uses, note }, auth: true })
}
export function setInviteActive(code, active) {
  return request(`/api/v1/admin/invites/${encodeURIComponent(code)}/active`, { method: 'POST', body: { active }, auth: true })
}

// 数据更新（和功能台“数据更新”页用同一组接口）
export function dailyUpdateStatus() {
  return request('/api/v1/data-center/daily-update', { auth: true })
}
export function runDailyUpdate() {
  return request('/api/v1/data-center/daily-update/run', { method: 'POST', body: {}, auth: true })
}
export function dataJobs() {
  return request('/api/v1/data-center/jobs', { auth: true })
}
export function stopDataJob(id) {
  return request(`/api/v1/data-center/jobs/${encodeURIComponent(id)}/stop`, { method: 'POST', body: {}, auth: true })
}
export function startDataJob(payload) {
  return request('/api/v1/data-center/jobs/start', { method: 'POST', body: payload, auth: true })
}
export function dataJobLog(id) {
  return request(`/api/v1/data-center/jobs/${encodeURIComponent(id)}/log`, { auth: true })
}
export function closedLoopStatus() {
  return request('/api/v1/data-center/closed-loop', { auth: true })
}

// 服务器：磁盘空间、数据占用、备份、财务数据的自动更新
export function systemStatus() {
  return request('/api/v1/admin/system', { auth: true })
}
export function backupNow() {
  return request('/api/v1/admin/backup', { method: 'POST', body: {}, auth: true })
}

// 系统设置：保存要再输一次管理员密码；测试可以用还没保存的值
export function adminSettings() {
  return request('/api/v1/admin/settings', { auth: true })
}
export function saveAdminSettings({ password, values = {}, clear = [] }) {
  return request('/api/v1/admin/settings', { method: 'PUT', body: { password, values, clear }, auth: true })
}
export function testAdminSettings(target, values = {}) {
  return request('/api/v1/admin/settings/test', { method: 'POST', body: { target, values }, auth: true })
}
export function weknoraSettings() {
  return request('/api/v1/weknora/settings', { auth: true })
}
export function saveWeknoraSettings(payload) {
  return request('/api/v1/weknora/settings', { method: 'POST', body: payload, auth: true })
}

// 操作记录、AI 用量
export function adminAudit(kind = '', limit = 100) {
  return request(`/api/v1/admin/audit?${new URLSearchParams({ kind, limit })}`, { auth: true })
}
export function adminAiUsage(days = 30) {
  return request(`/api/v1/admin/ai-usage?${new URLSearchParams({ days })}`, { auth: true })
}
