<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const canvas = ref(null)
let ctx = null
let rafId = 0
let width = 0
let height = 0
let dpr = 1
let particles = []
let pointer = { x: -9999, y: -9999 }
let running = true

// 量化主题色：深蓝 / 靛 / 紫 / 青
const PALETTE = [
  'rgba(99, 102, 241, 0.9)',   // indigo-500
  'rgba(56, 189, 248, 0.9)',   // sky-400
  'rgba(139, 92, 246, 0.9)',   // violet-500
  'rgba(45, 212, 191, 0.9)',   // teal-300
]

function initParticles() {
  // 密度随屏幕面积自适应，上限以保证性能
  const count = Math.min(90, Math.floor((width * height) / 22000))
  particles = Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.28,
    vy: (Math.random() - 0.5) * 0.28,
    r: Math.random() * 1.8 + 0.6,
    c: PALETTE[(Math.random() * PALETTE.length) | 0],
  }))
}

function resize() {
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  width = canvas.value.clientWidth
  height = canvas.value.clientHeight
  canvas.value.width = width * dpr
  canvas.value.height = height * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  initParticles()
}

function draw() {
  ctx.clearRect(0, 0, width, height)

  for (let i = 0; i < particles.length; i++) {
    const p = particles[i]
    p.x += p.vx
    p.y += p.vy

    // 边界环绕
    if (p.x < -20) p.x = width + 20
    else if (p.x > width + 20) p.x = -20
    if (p.y < -20) p.y = height + 20
    else if (p.y > height + 20) p.y = -20

    // 鼠标轻微吸引（营造“指令环”感）
    const dx = p.x - pointer.x
    const dy = p.y - pointer.y
    const dist2 = dx * dx + dy * dy
    if (dist2 < 16000) {
      const f = (1 - dist2 / 16000) * 0.35
      p.x += (dx / Math.sqrt(dist2 || 1)) * f
      p.y += (dy / Math.sqrt(dist2 || 1)) * f
    }

    ctx.beginPath()
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
    ctx.fillStyle = p.c
    ctx.fill()
  }

  // 连线：量化数据流网络（批量绘制减少 stroke 调用）
  ctx.lineWidth = 1
  ctx.strokeStyle = 'rgba(129, 140, 248, 0.18)'
  ctx.beginPath()
  for (let i = 0; i < particles.length; i++) {
    const a = particles[i]
    for (let j = i + 1; j < particles.length; j++) {
      const b = particles[j]
      const dx = a.x - b.x
      const dy = a.y - b.y
      const d2 = dx * dx + dy * dy
      if (d2 < 16000) {
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
      }
    }
  }
  ctx.stroke()

  if (running) rafId = requestAnimationFrame(draw)
}

function onPointerMove(e) {
  pointer.x = e.clientX
  pointer.y = e.clientY
}
function onPointerLeave() {
  pointer.x = -9999
  pointer.y = -9999
}

const reduceMotion =
  typeof window !== 'undefined' &&
  window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

onMounted(() => {
  if (reduceMotion) return
  ctx = canvas.value.getContext('2d')
  resize()
  window.addEventListener('resize', resize)
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  window.addEventListener('pointerleave', onPointerLeave)
  draw()
})

onBeforeUnmount(() => {
  running = false
  if (rafId) cancelAnimationFrame(rafId)
  window.removeEventListener('resize', resize)
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerleave', onPointerLeave)
})
</script>

<template>
  <div aria-hidden="true" class="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-ink">
    <!-- 动态网格（缓慢漂移 + 呼吸） -->
    <div class="bg-grid-anim absolute inset-0 opacity-60" />

    <!-- 漂浮的渐变光晕 -->
    <div class="orb orb-1" />
    <div class="orb orb-2" />
    <div class="orb orb-3" />

    <!-- 顶部柔和的扫描光带 -->
    <div class="scanline" />

    <!-- Canvas 粒子网络（量化数据流） -->
    <canvas v-if="!reduceMotion" ref="canvas" class="absolute inset-0 h-full w-full" />
  </div>
</template>

<style scoped>
.bg-grid-anim {
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.06) 1px, transparent 1px);
  background-size: 56px 56px;
  animation: gridDrift 28s linear infinite, gridPulse 8s ease-in-out infinite;
}
@keyframes gridDrift {
  from { background-position: 0 0, 0 0; }
  to { background-position: 56px 56px, 56px 56px; }
}
@keyframes gridPulse {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 0.85; }
}

.orb {
  position: absolute;
  border-radius: 9999px;
  filter: blur(120px);
  will-change: transform;
}
.orb-1 {
  width: 820px; height: 820px;
  background: radial-gradient(circle at 30% 30%, rgba(99,102,241,0.55), transparent 60%);
  top: -200px; left: 50%;
  transform: translateX(-50%);
  animation: floatA 22s ease-in-out infinite;
}
.orb-2 {
  width: 460px; height: 460px;
  background: radial-gradient(circle at 60% 40%, rgba(56,189,248,0.40), transparent 60%);
  top: 35%; left: -120px;
  animation: floatB 26s ease-in-out infinite;
}
.orb-3 {
  width: 520px; height: 520px;
  background: radial-gradient(circle at 50% 50%, rgba(139,92,246,0.42), transparent 60%);
  bottom: -160px; right: -120px;
  animation: floatC 30s ease-in-out infinite;
}
@keyframes floatA {
  0%, 100% { transform: translate(-50%, 0) scale(1); }
  50% { transform: translate(-50%, 40px) scale(1.08); }
}
@keyframes floatB {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(60px, -40px) scale(1.12); }
}
@keyframes floatC {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(-50px, -30px) scale(1.1); }
}

.scanline {
  position: absolute;
  inset: 0 0 auto 0;
  height: 220px;
  background: linear-gradient(to bottom, rgba(129, 140, 248, 0.08), transparent);
  animation: scan 9s ease-in-out infinite;
  opacity: 0.6;
}
@keyframes scan {
  0%, 100% { transform: translateY(0); opacity: 0.5; }
  50% { transform: translateY(60px); opacity: 0.8; }
}

@media (prefers-reduced-motion: reduce) {
  .bg-grid-anim, .orb, .scanline { animation: none; }
}
</style>
