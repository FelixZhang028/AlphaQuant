<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  scrollState: { type: Object, required: true },
  theme: { type: String, default: 'dark' },
})

const canvasRef = ref(null)
let sceneApi = null

onMounted(async () => {
  try {
    // 动态加载 three.js 场景，避免将 WebGL 依赖打进首屏主包
    const { createQuantScene } = await import('../home/quantScene')
    sceneApi = createQuantScene(canvasRef.value, props.scrollState, props.theme)
  } catch (err) {
    // WebGL 不可用时隐藏画布，页面以 CSS 渐变兜底背景运行
    canvasRef.value.style.display = 'none'
    console.warn('[FellowQuant] WebGL 初始化失败，页面将以降级背景运行：', err)
  }
})

watch(
  () => props.theme,
  (t) => sceneApi?.setTheme?.(t),
)

onBeforeUnmount(() => {
  sceneApi?.dispose?.()
  sceneApi = null
})
</script>

<template>
  <canvas ref="canvasRef" class="fq-webgl" aria-hidden="true"></canvas>
</template>

<style scoped>
.fq-webgl {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  display: block;
}
</style>
