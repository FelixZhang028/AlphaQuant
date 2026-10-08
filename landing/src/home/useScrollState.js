/* 原生滚动状态：滚动进度（平滑插值）+ 鼠标视差
 * 使用浏览器原生滚动（无 fake-scroll），平滑值仅供 WebGL 相机使用，
 * 杜绝与全局样式冲突导致的滚动失效问题。
 */
import { onBeforeUnmount, onMounted } from 'vue'

export function useScrollState() {
  const state = {
    target: 0, // 原生滚动位置
    smooth: 0, // 插值后的平滑位置（供场景相机）
    progress: 0, // 页面总进度 0..1
    maxScroll: 1,
    mouse: { x: 0, y: 0, sx: 0, sy: 0 }, // 原始 / 平滑鼠标
  }

  let lastTime = performance.now()

  function measure() {
    state.maxScroll = Math.max(1, document.documentElement.scrollHeight - window.innerHeight)
  }

  function onScroll() {
    state.target = window.scrollY || window.pageYOffset || 0
  }

  function onResize() {
    measure()
    onScroll()
  }

  function onMouseMove(e) {
    state.mouse.x = (e.clientX / window.innerWidth) * 2 - 1
    state.mouse.y = (e.clientY / window.innerHeight) * 2 - 1
  }

  onMounted(() => {
    measure()
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onResize, { passive: true })
    window.addEventListener('mousemove', onMouseMove, { passive: true })
    // 字体加载完成后高度可能变化
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(onResize)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('scroll', onScroll)
    window.removeEventListener('resize', onResize)
    window.removeEventListener('mousemove', onMouseMove)
  })

  // 每帧调用：平滑插值滚动进度与鼠标
  function update() {
    const now = performance.now()
    const dt = Math.min(0.05, Math.max(0.001, (now - lastTime) / 1000))
    lastTime = now

    state.smooth += (state.target - state.smooth) * Math.min(1, dt * 6)
    if (Math.abs(state.target - state.smooth) < 0.05) state.smooth = state.target
    state.progress = Math.min(1, Math.max(0, state.smooth / state.maxScroll))

    state.mouse.sx += (state.mouse.x - state.mouse.sx) * 0.05
    state.mouse.sy += (state.mouse.y - state.mouse.sy) * 0.05
  }

  // 锚点导航（原生滚动 + 平滑滚动行为）
  function scrollToSection(id) {
    const el = document.getElementById(id)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return { state, update, scrollToSection }
}
