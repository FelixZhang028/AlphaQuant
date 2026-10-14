// 后端 API 封装（FastAPI，默认 http://127.0.0.1:8000）
// 可用环境变量 VITE_API_BASE 覆盖
import { checkSavedSession } from './sessionState.js'
import { sanitizeError } from './errorMessage.js'

export { sanitizeError }

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

const TOKEN_KEY = 'zt_token'
const USER_KEY = 'zt_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}
export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
}
export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
export function getLocalUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
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
    let msg = (data && (data.detail || data.message)) || `请求失败 (${res.status})`
    if (data && data.detail && typeof data.detail === 'object') {
      msg = data.detail.blockers ? data.detail.blockers.map((b) => b.message).join('；') : JSON.stringify(data.detail)
    }
    const err = new Error(sanitizeError(msg))
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

// ---- 认证 ----
export function register({ name, email, password }) {
  return request('/api/v1/auth/register', { method: 'POST', body: { name, email, password } })
}
export async function login({ email, password }) {
  const data = await request('/api/v1/auth/login', { method: 'POST', body: { email, password } })
  setSession(data.token, data.user)
  return data
}
export function me() {
  return request('/api/v1/auth/me', { auth: true })
}
export async function restoreSession() {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const session = await checkSavedSession({ readToken: getToken, fetchUser: me, clear: clearSession })
    if (session.status === 'changed') continue
    if (session.status === 'authenticated') localStorage.setItem(USER_KEY, JSON.stringify(session.user))
    return session
  }
  return { status: 'unavailable', user: null, error: new Error('登录状态正在变化，请重试') }
}
export function forgotRequest({ name, email }) {
  return request('/api/v1/auth/forgot/request', { method: 'POST', body: { name, email } })
}
export function forgotReset({ name, email, code, new_password }) {
  return request('/api/v1/auth/forgot/reset', { method: 'POST', body: { name, email, code, new_password } })
}
export function logout() {
  clearSession()
}

// ---- 策略（通用 CRUD，功能台概览页使用）----
export function listStrategies() {
  return request('/api/v1/strategies', { auth: true })
}
export function createStrategy(payload) {
  return request('/api/v1/strategies', { method: 'POST', body: payload, auth: true })
}
export function updateStrategyStatus(id, status) {
  return request(`/api/v1/strategies/${id}`, { method: 'PATCH', body: { status }, auth: true })
}
export function deleteStrategy(id) {
  return request(`/api/v1/strategies/${id}`, { method: 'DELETE', auth: true })
}

// ---- 回测 ----
export function submitBacktest(payload) {
  return request('/api/v1/backtests', { method: 'POST', body: payload, auth: true })
}
export function getBacktestBenchmark(id, symbol) {
  return request(`/api/v1/backtests/${id}/benchmark?${new URLSearchParams({ symbol })}`, { auth: true })
}
export function getBacktest(id) {
  return request(`/api/v1/backtests/${id}`, { auth: true })
}

// ---- 监控数据（公开）----
export function fetchSnapshot() {
  return request('/api/v1/stats/snapshot')
}

// ---- 策略包（策略创作中心 / 自然语言 / 零代码工作台）----
export function listPackages() {
  return request('/api/v1/packages', { auth: true })
}
export function createPackage(payload) {
  return request('/api/v1/packages', { method: 'POST', body: payload, auth: true })
}
export function getPackage(id) {
  return request(`/api/v1/packages/${id}`, { auth: true })
}
export function copyPackage(id, name) {
  return request(`/api/v1/packages/${id}/copy`, { method: 'POST', body: name ? { name } : {}, auth: true })
}
export function deletePackage(id) {
  return request(`/api/v1/packages/${id}`, { method: 'DELETE', auth: true })
}
export function preflightPackage(payload) {
  return request('/api/v1/packages/preflight', { method: 'POST', body: payload, auth: true })
}
export function packageRiskScore(id) {
  return request(`/api/v1/packages/${id}/risk-score`, { auth: true })
}
export function backtestPackage(id, payload) {
  return request(`/api/v1/packages/${id}/backtest`, { method: 'POST', body: payload || {}, auth: true })
}
export function studioOptions() {
  return request('/api/v1/studio/options', { auth: true })
}

// ---- 自然语言建策略 ----
export function nlStatus() {
  return request('/api/v1/nl/status', { auth: true })
}
export function nlGenerate(payload) {
  return request('/api/v1/nl/generate', { method: 'POST', body: payload, auth: true })
}

// ---- 自定义策略（Python）----
export function previewUserStrategy(payload) {
  return request('/api/v1/user-strategies/preview', { method: 'POST', body: payload, auth: true })
}
export function saveUserStrategy(payload) {
  return request('/api/v1/user-strategies', { method: 'POST', body: payload, auth: true })
}
export function listUserStrategies() {
  return request('/api/v1/user-strategies', { auth: true })
}
export function deleteUserStrategy(name) {
  return request(`/api/v1/user-strategies/${name}`, { method: 'DELETE', auth: true })
}

// ---- 因子研究室 ----
export function listFactors() {
  return request('/api/v1/factors', { auth: true })
}
export function evaluateFactor(payload) {
  return request('/api/v1/factors/evaluate', { method: 'POST', body: payload, auth: true })
}
export function factorUniverses() {
  return request('/api/v1/factors/universes', { auth: true })
}
export function compositeFactors(payload) {
  return request('/api/v1/factors/composite', { method: 'POST', body: payload, auth: true })
}
export function researchFactors(payload) {
  return request('/api/v1/factors/research', { method: 'POST', body: payload, auth: true })
}
export function createCustomFactor(payload) {
  return request('/api/v1/factors/custom', { method: 'POST', body: payload, auth: true })
}
export function deleteCustomFactor(name) {
  return request(`/api/v1/factors/custom/${name}`, { method: 'DELETE', auth: true })
}

// ---- AI 研究员 ----
export function aiStatus() {
  return request('/api/v1/agent-lab/status', { auth: true })
}
export function createBrief(payload) {
  return request('/api/v1/agent-lab/briefs', { method: 'POST', body: payload, auth: true })
}
export function readBrief(id) {
  return request(`/api/v1/agent-lab/briefs/${id}/reading`, { method: 'POST', auth: true })
}
export function deleteBrief(id) {
  return request(`/api/v1/agent-lab/briefs/${id}`, { method: 'DELETE', auth: true })
}
export function getBrief(id) {
  return request(`/api/v1/agent-lab/briefs/${id}`, { auth: true })
}
export function listBriefs() {
  return request('/api/v1/agent-lab/briefs', { auth: true })
}
export function askBrief(id, message) {
  return request(`/api/v1/agent-lab/briefs/${id}/questions`, { method: 'POST', body: { message }, auth: true })
}
export function listPriorKnowledge() {
  return request('/api/v1/agent-lab/prior-knowledge', { auth: true })
}
export function addPriorKnowledge(payload) {
  return request('/api/v1/agent-lab/prior-knowledge', { method: 'POST', body: payload, auth: true })
}
export function deletePriorKnowledge(id) {
  return request(`/api/v1/agent-lab/prior-knowledge/${id}`, { method: 'DELETE', auth: true })
}

// ---- 参数优化与稳健性验证 ----
export function researchBaselines() {
  return request('/api/v1/research/baselines', { auth: true })
}
export function runOptimization(payload) {
  return request('/api/v1/research/optimize', { method: 'POST', body: payload, auth: true })
}
export function runWalkForward(payload) {
  return request('/api/v1/research/walk-forward', { method: 'POST', body: payload, auth: true })
}

// ---- 回测记录库 ----
export function listRuns(params = {}) {
  const q = new URLSearchParams(params).toString()
  return request(`/api/v1/runs${q ? `?${q}` : ''}`, { auth: true })
}
export function compareRuns(runIds) {
  return request('/api/v1/runs/compare', { method: 'POST', body: { run_ids: runIds }, auth: true })
}

// ---- 可信度审计（迁移自 AlphaQuant audit_report）----
export function listAuditRuns() {
  return request('/api/v1/runs/audit', { auth: true })
}
export function runTradedSymbols(runId) {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/trades`, { auth: true })
}
export function runSymbolTrades(runId, symbol) {
  return request(`/api/v1/runs/${encodeURIComponent(runId)}/trades/${encodeURIComponent(symbol)}`, { auth: true })
}
export function getRunAudit(runId) {
  return request(`/api/v1/runs/${runId}/audit`, { auth: true })
}

// ---- 外部成交核查（迁移自 AlphaQuant forensics + external_audit）----
export function forensicsTemplateUrl() {
  return '/api/v1/forensics/template'
}
export function forensicsPreview(content) {
  return request('/api/v1/forensics/preview', { method: 'POST', body: { content }, auth: true })
}
export function forensicsCheck(payload) {
  return request('/api/v1/forensics/check', { method: 'POST', body: payload, auth: true })
}

// ---- 数据管理 ----
export function dataOverview() {
  return request('/api/v1/data-center/overview', { auth: true })
}
export function localMarketList(params = {}) {
  return request(`/api/v1/data-center/market?${new URLSearchParams(params)}`, { auth: true })
}
export function localMarketDetail(symbol) {
  return request(`/api/v1/data-center/market/${encodeURIComponent(symbol)}`, { auth: true })
}
export function localMarketBars(symbol, adjust = 'forward') {
  return request(`/api/v1/data-center/market/${encodeURIComponent(symbol)}/bars?${new URLSearchParams({ adjust })}`, { auth: true })
}
export function chartDrawings(symbol) {
  return request(`/api/v1/data-center/market/${encodeURIComponent(symbol)}/drawings`, { auth: true })
}
export function saveChartDrawings(symbol, drawings) {
  return request(`/api/v1/data-center/market/${encodeURIComponent(symbol)}/drawings`, { method: 'PUT', body: { drawings }, auth: true })
}
export function updateLocalStock(symbol, payload) {
  return request(`/api/v1/data-center/market/${encodeURIComponent(symbol)}/update`, { method: 'POST', body: payload, auth: true })
}
export function dataUpdate(payload) {
  return request('/api/v1/data-center/update', { method: 'POST', body: payload, auth: true })
}
export function dataJobs() {
  return request('/api/v1/data-center/jobs', { auth: true })
}
export function startDataJob(payload) {
  return request('/api/v1/data-center/jobs/start', { method: 'POST', body: payload, auth: true })
}
export function stopDataJob(jobId) {
  return request(`/api/v1/data-center/jobs/${jobId}/stop`, { method: 'POST', body: {}, auth: true })
}
export function dataJobLog(jobId) {
  return request(`/api/v1/data-center/jobs/${jobId}/log`, { auth: true })
}
export function closedLoopStatus() {
  return request('/api/v1/data-center/closed-loop', { auth: true })
}

// ---- XTick 数据服务 ----
export function xtickCatalog() {
  return request('/api/v1/xtick/catalog', { auth: true })
}
export function xtickStatus() {
  return request('/api/v1/xtick/status', { auth: true })
}
export function xtickSaveCredentials(payload) {
  return request('/api/v1/xtick/credentials', { method: 'POST', body: payload, auth: true })
}
export function xtickRequest(payload) {
  return request('/api/v1/xtick/request', { method: 'POST', body: payload, auth: true })
}

// ---- 风险管理 ----
export function getRisk() {
  return request('/api/v1/risk', { auth: true })
}
export function saveRisk(payload) {
  return request('/api/v1/risk', { method: 'PUT', body: payload, auth: true })
}

// ---- 股票池管理 ----
export function getUniverse() {
  return request('/api/v1/universe', { auth: true })
}
export function universeAdd(symbols) {
  return request('/api/v1/universe/add', { method: 'POST', body: { symbols }, auth: true })
}
export function universeRemove(symbols) {
  return request('/api/v1/universe/remove', { method: 'POST', body: { symbols }, auth: true })
}
export function universeSearch(q) {
  return request(`/api/v1/universe/search?q=${encodeURIComponent(q)}`, { auth: true })
}
export function universeSaveFilters(payload) {
  return request('/api/v1/universe/filters', { method: 'PUT', body: payload, auth: true })
}

// ---- Jev 结构化决策中心 ----
export function jevDecide(payload) {
  return request('/api/v1/jev/decide', { method: 'POST', body: payload, auth: true })
}

// ---- WeKnora 知识库问答 ----
export function weknoraSettings() {
  return request('/api/v1/weknora/settings', { auth: true })
}
export function weknoraSaveSettings(payload) {
  return request('/api/v1/weknora/settings', { method: 'POST', body: payload, auth: true })
}
export function weknoraKnowledgeBases() {
  return request('/api/v1/weknora/knowledge-bases', { auth: true })
}
export function weknoraChat(payload) {
  return request('/api/v1/weknora/chat', { method: 'POST', body: payload, auth: true })
}
export function weknoraQuery(payload) {
  return request('/api/v1/weknora/query', { method: 'POST', body: payload, auth: true })
}

export function jevSettings() { return request('/api/v1/jev/settings', { auth: true }) }
export function jevSaveSettings(payload) { return request('/api/v1/jev/settings', { method: 'POST', body: payload, auth: true }) }

export function getBacktestCatalog() {
  return request('/api/v1/backtests/catalog', { auth: true })
}
