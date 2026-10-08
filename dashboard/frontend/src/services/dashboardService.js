/**
 * 数据接入服务：
 * 1. 优先建立 WebSocket（ws://localhost:8000/ws/dashboard，开发环境走 Vite 代理）
 * 2. WS 断开/不可用时自动降级为 HTTP 轮询（每 2.5s 请求 /api/v1/stats/snapshot）
 * 3. 轮询期间持续尝试重连 WS，恢复后切回实时模式
 */
import { useDashboardStore } from '../stores/dashboard'

const WS_URL =
  (location.protocol === 'https:' ? 'wss://' : 'ws://') +
  location.host +
  '/ws/dashboard'
const SNAPSHOT_URL = '/api/v1/stats/snapshot'

const POLL_INTERVAL = 2500 // 轮询间隔 ms
const RECONNECT_INTERVAL = 5000 // WS 重连间隔 ms

class DashboardService {
  constructor() {
    this.ws = null
    this.pollTimer = null
    this.reconnectTimer = null
    this.started = false
  }

  start() {
    if (this.started) return
    this.started = true
    this.connectWs()
  }

  stop() {
    this.started = false
    this.clearTimers()
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }
  }

  clearTimers() {
    if (this.pollTimer) clearInterval(this.pollTimer)
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.pollTimer = null
    this.reconnectTimer = null
  }

  connectWs() {
    const store = useDashboardStore()
    try {
      this.ws = new WebSocket(WS_URL)
    } catch {
      return this.fallbackToPolling()
    }

    this.ws.onopen = () => {
      // 连接成功：停掉轮询，进入实时模式
      if (this.pollTimer) {
        clearInterval(this.pollTimer)
        this.pollTimer = null
      }
      store.setConnection('realtime')
    }

    this.ws.onmessage = (event) => {
      try {
        const snapshot = JSON.parse(event.data)
        store.applySnapshot(snapshot)
      } catch (e) {
        console.error('快照解析失败', e)
      }
    }

    this.ws.onerror = () => {
      // 交给 onclose 统一处理
      this.ws?.close()
    }

    this.ws.onclose = () => {
      this.ws = null
      if (!this.started) return
      this.fallbackToPolling()
    }
  }

  /** 降级为 HTTP 轮询，并安排 WS 重连尝试 */
  fallbackToPolling() {
    const store = useDashboardStore()
    if (!this.pollTimer) {
      store.setConnection('polling')
      this.fetchSnapshot() // 立即拉一次，不等第一个周期
      this.pollTimer = setInterval(() => this.fetchSnapshot(), POLL_INTERVAL)
    }
    // 周期性尝试恢复 WebSocket
    if (!this.reconnectTimer) {
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = null
        if (this.started && !this.ws) this.connectWs()
      }, RECONNECT_INTERVAL)
    }
  }

  async fetchSnapshot() {
    const store = useDashboardStore()
    try {
      const resp = await fetch(SNAPSHOT_URL)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const snapshot = await resp.json()
      store.applySnapshot(snapshot)
      // 轮询正常则维持 polling 状态（除非已切回 realtime）
      if (store.connection !== 'realtime') store.setConnection('polling')
    } catch (e) {
      console.error('轮询快照失败', e)
      store.setConnection('disconnected')
    }
  }
}

export const dashboardService = new DashboardService()
