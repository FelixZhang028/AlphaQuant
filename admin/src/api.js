// 管理后台 API 封装（FastAPI，默认 http://127.0.0.1:8000）
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

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
    const msg = (data && (data.detail || data.message)) || `请求失败 (${res.status})`
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
export function adminUsers() {
  return request('/api/v1/admin/users', { auth: true })
}
export function adminStrategies() {
  return request('/api/v1/admin/strategies', { auth: true })
}
export function adminStats() {
  return request('/api/v1/admin/stats', { auth: true })
}
