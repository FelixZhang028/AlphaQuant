/* FellowQuant 主页 WebGL 背景 —— 细K线波场（Thin Candle Waves）
 *
 * 意象：一簇平面「K线图」走势场——
 *  - 每条线为阶梯状 close 价折线（行情 step 图），细线
 *  - 每个槽位带上下影线（wick），K 线图语言
 *  - 形态由 fBm 噪声驱动，随时间缓慢演变（morph）
 *  - 动态闪烁：沿线条流动的微光 + 随机高亮脉冲（像行情跳动）
 *
 * 实现：每条线 = 1 条折线带 + 1 组影线段，动画全在顶点着色器，
 *  CPU 零逐帧开销；无后处理直出渲染，性能稳、无闪烁。
 * 主题：dark / light 双调色板，setTheme() 运行时切换。
 */
import * as THREE from 'three'

/* ---------- 主题调色板 ---------- */
const PALETTES = {
  dark: {
    // 纯黑背景 + 霓虹鲜艳 K 线配色
    bgTop: '#000000',
    bgMid: '#000000',
    bgBottom: '#000000',
    colorA: '#2f9dff', // 电光蓝
    colorB: '#00ffc8', // 霓虹青绿
    colorC: '#8fd8ff', // 点缀冰蓝
    alphaBase: 0.52,
    wickAlpha: 0.34,
    dust: '#a8d0e0',
  },
  light: {
    bgTop: '#f7fafb',
    bgMid: '#eef4f6',
    bgBottom: '#e2edf0',
    colorA: '#2e7bab',
    colorB: '#2aa793',
    colorC: '#5ba8c9',
    alphaBase: 0.4,
    wickAlpha: 0.26,
    dust: '#93a9b4',
  },
}

/* ---------- 线场参数 ---------- */
const LINE_COUNT = 16
const LINE_W = 150
const SEGMENTS = 600 // 每槽 8 顶点 → 阶梯竖边清晰
const SLOT_W = 2.0
const SLOTS = Math.floor(LINE_W / SLOT_W)
const EDGE_FADE = 0.14

/* 确定性随机（保证每次加载构图一致） */
function mulberry32(seed) {
  return function () {
    let t = (seed += 0x6d2b79f5)
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/* ---------- 噪声（顶点：走势；片元：闪烁） ---------- */
const NOISE_GLSL = /* glsl */ `
  float hash21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
  float vnoise(vec2 p) {
    vec2 i = floor(p); vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x),
               mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), f.x), f.y);
  }
  float fbm(vec2 p) {
    float v = 0.0; float a = 0.55;
    for (int i = 0; i < 4; i++) { v += a * vnoise(p); p *= 2.15; a *= 0.5; }
    return v;
  }
  // 走势：低频趋势 + fBm 波动（像价格曲线：有趋势有噪音）
  float trend(vec2 p) {
    return fbm(p) + (fbm(p * 0.22) - 0.5) * 1.6;
  }
`

const EDGE_GLSL = /* glsl */ `
  float edgeFade(float x) {
    return smoothstep(0.0, ${EDGE_FADE.toFixed(2)}, x) * smoothstep(1.0, ${(1 - EDGE_FADE).toFixed(2)}, x);
  }
`

/* 闪烁（片元）：流动微光 + 随机高亮脉冲（行情跳动感） */
const FLICKER_GLSL = /* glsl */ `
  // 返回 vec2(微光, 脉冲)
  vec2 flicker(float x, float seed, float t) {
    float tw = vnoise(vec2(x * 60.0 + seed, t * 1.6));
    float flash = smoothstep(0.88, 0.985, vnoise(vec2(x * 24.0 - t * 1.3, seed * 3.0 + 17.0)));
    return vec2(tw, flash);
  }
`

/* ---------- 渐变背景纹理 ---------- */
function makeBackgroundTexture(P) {
  const canvas = document.createElement('canvas')
  canvas.width = 2
  canvas.height = 512
  const ctx = canvas.getContext('2d')
  const gradient = ctx.createLinearGradient(0, 0, 0, 512)
  gradient.addColorStop(0, P.bgTop)
  gradient.addColorStop(0.55, P.bgMid)
  gradient.addColorStop(1, P.bgBottom)
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 2, 512)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

/**
 * 创建细K线波场场景。
 * @param {HTMLCanvasElement} canvas 目标画布
 * @param {{ progress: number, mouse: { sx: number, sy: number } }} scrollState 滚动状态
 * @param {'dark'|'light'} initialTheme 初始主题
 * @returns {{ dispose: () => void, setTheme: (t: 'dark'|'light') => void }}
 */
export function createQuantScene(canvas, scrollState, initialTheme = 'dark') {
  let currentTheme = null
  let disposed = false

  /* ----- renderer（无 powerPreference，避免双显卡切换黑帧） ----- */
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
  renderer.setSize(window.innerWidth, window.innerHeight)

  const scene = new THREE.Scene()
  let bgTexture = null

  const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 200)
  const rig = new THREE.Group()
  rig.add(camera)
  scene.add(rig)

  const rand = mulberry32(20261003)
  const disposables = []
  function track(object) {
    disposables.push(object)
    return object
  }

  /* ----- 细K线场：每条线 = 阶梯折线 + 影线段 ----- */
  const lines = []
  for (let i = 0; i < LINE_COUNT; i++) {
    const tNorm = i / (LINE_COUNT - 1)
    const bell = 1 - Math.pow(Math.abs(tNorm - 0.5) * 2, 1.6)
    const offset = (tNorm - 0.5) * 20 + (rand() - 0.5) * 1.2
    const centerWeight = 0.35 + 0.65 * bell
    const isAccent = rand() < 0.2
    const seed = rand() * 100
    const morph = 0.045 + rand() * 0.035
    const slotFreq = 0.12 + rand() * 0.1 // 每槽走势频率
    const amp = 2.4 + rand() * 2.6
    const breathPhase = rand() * Math.PI * 2
    const breathSpeed = 0.05 + rand() * 0.06

    // 共享 uniforms（折线与影线一致）
    const shared = {
      uTime: { value: 0 },
      uSeed: { value: seed },
      uMorph: { value: morph },
      uSlotFreq: { value: slotFreq },
      uAmp: { value: amp },
      uOffset: { value: offset },
      uColorA: { value: new THREE.Color('#2779a7') },
      uColorB: { value: new THREE.Color('#49c5b6') },
      uAlpha: { value: 0.4 },
    }

    /* --- 阶梯 close 折线 --- */
    const stripGeo = track(new THREE.BufferGeometry())
    {
      const pos = new Float32Array(SEGMENTS * 3)
      for (let s = 0; s < SEGMENTS; s++) {
        pos[s * 3] = -LINE_W / 2 + (s / (SEGMENTS - 1)) * LINE_W
      }
      stripGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    }
    const stripMat = track(
      new THREE.ShaderMaterial({
        uniforms: shared,
        transparent: true,
        depthWrite: false,
        vertexShader: /* glsl */ `
          uniform float uTime; uniform float uSeed; uniform float uMorph;
          uniform float uSlotFreq; uniform float uAmp; uniform float uOffset;
          varying float vX;
          ${NOISE_GLSL}
          void main() {
            vX = position.x / ${LINE_W.toFixed(1)} + 0.5;
            // 阶梯：按槽位采样 → 同槽同值，槽间竖边（step 图）
            float slot = floor((position.x + ${LINE_W.toFixed(1)} * 0.5) / ${SLOT_W.toFixed(2)});
            float h = trend(vec2(slot * uSlotFreq + uSeed, uTime * uMorph + uSeed));
            vec3 p = position;
            p.y = uOffset + (h - 0.55) * uAmp;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform vec3 uColorA; uniform vec3 uColorB; uniform float uAlpha;
          uniform float uTime; uniform float uSeed;
          varying float vX;
          ${NOISE_GLSL}
          ${EDGE_GLSL}
          ${FLICKER_GLSL}
          void main() {
            vec2 f = flicker(vX, uSeed, uTime);
            vec3 col = mix(uColorA, uColorB, vX);
            col = mix(col, vec3(1.0), f.y * 0.55); // 脉冲提亮
            float a = uAlpha * edgeFade(vX) * (0.7 + 0.3 * f.x) * (1.0 + 1.8 * f.y);
            gl_FragColor = vec4(col, min(a, 1.0));
          }
        `,
      }),
    )
    const strip = new THREE.Line(stripGeo, stripMat)
    strip.frustumCulled = false

    /* --- 影线段（每槽上下影线，静态长度随 close 缓慢演变） --- */
    const wickGeo = track(new THREE.BufferGeometry())
    {
      const pos = new Float32Array(SLOTS * 2 * 3)
      const end = new Float32Array(SLOTS * 2) // 0=下端 1=上端
      for (let n = 0; n < SLOTS; n++) {
        const x = -LINE_W / 2 + (n + 0.5) * SLOT_W
        pos[n * 6 + 0] = x
        pos[n * 6 + 3] = x
        end[n * 2] = 0
        end[n * 2 + 1] = 1
      }
      wickGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      wickGeo.setAttribute('aEnd', new THREE.BufferAttribute(end, 1))
    }
    const wickMat = track(
      new THREE.ShaderMaterial({
        uniforms: { ...shared, uWickAlpha: { value: 0.3 } },
        transparent: true,
        depthWrite: false,
        vertexShader: /* glsl */ `
          uniform float uTime; uniform float uSeed; uniform float uMorph;
          uniform float uSlotFreq; uniform float uAmp; uniform float uOffset;
          attribute float aEnd;
          varying float vX; varying float vSlot;
          ${NOISE_GLSL}
          void main() {
            vX = position.x / ${LINE_W.toFixed(1)} + 0.5;
            float slot = floor((position.x + ${LINE_W.toFixed(1)} * 0.5) / ${SLOT_W.toFixed(2)});
            vSlot = slot;
            float h = trend(vec2(slot * uSlotFreq + uSeed, uTime * uMorph + uSeed));
            float close = uOffset + (h - 0.55) * uAmp;
            // 影线长度：静态哈希（不随时间跳变），上下分割随机
            float len = 0.35 + 0.85 * hash21(vec2(slot * 7.31, uSeed));
            float topLen = len * hash21(vec2(slot * 3.7, uSeed + 11.0));
            float botLen = len - topLen;
            vec3 p = position;
            p.y = close + (aEnd > 0.5 ? topLen : -botLen);
            gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
          }
        `,
        fragmentShader: /* glsl */ `
          uniform vec3 uColorA; uniform vec3 uColorB; uniform float uWickAlpha;
          uniform float uTime; uniform float uSeed;
          varying float vX; varying float vSlot;
          ${NOISE_GLSL}
          ${EDGE_GLSL}
          ${FLICKER_GLSL}
          void main() {
            vec2 f = flicker(vX, uSeed, uTime);
            // 槽位级闪烁：随机槽位周期性亮起（行情跳动）
            float tw = 0.5 + 0.5 * sin(uTime * 2.2 + vSlot * 2.6 + uSeed * 10.0);
            vec3 col = mix(uColorA, uColorB, vX);
            col = mix(col, vec3(1.0), f.y * 0.5);
            float a = uWickAlpha * edgeFade(vX) * (0.45 + 0.55 * tw) * (1.0 + 1.6 * f.y);
            gl_FragColor = vec4(col, min(a, 1.0));
          }
        `,
      }),
    )
    const wicks = new THREE.LineSegments(wickGeo, wickMat)
    wicks.frustumCulled = false

    // 平面构图：窄深度带，轻微层次
    strip.position.set(0, 0, -28 + (rand() - 0.5) * 10)
    wicks.position.copy(strip.position)
    scene.add(strip)
    scene.add(wicks)
    lines.push({ shared, wickMat, centerWeight, isAccent })
  }

  /* ----- 微尘（缓漂 + 闪烁，平面感） ----- */
  const DUST_COUNT = 160
  const dustGeo = track(new THREE.BufferGeometry())
  {
    const pos = new Float32Array(DUST_COUNT * 3)
    const seed = new Float32Array(DUST_COUNT)
    for (let i = 0; i < DUST_COUNT; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 120
      pos[i * 3 + 1] = (Math.random() - 0.5) * 24
      pos[i * 3 + 2] = -34 + Math.random() * 14
      seed[i] = Math.random() * Math.PI * 2
    }
    dustGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    dustGeo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1))
  }
  const dustMat = track(
    new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uColor: { value: new THREE.Color('#7fa8b8') },
        uAlpha: { value: 0.3 },
      },
      transparent: true,
      depthWrite: false,
      vertexShader: /* glsl */ `
        uniform float uTime;
        attribute float aSeed;
        varying float vTw;
        void main() {
          vec3 p = position;
          p.y += sin(uTime * 0.06 + aSeed * 2.0) * 0.8;
          p.x += cos(uTime * 0.05 + aSeed * 3.0) * 0.8;
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = (1.0 + fract(aSeed) * 1.4) * (26.0 / max(1.0, -mv.z));
          vTw = 0.5 + 0.5 * sin(uTime * 0.22 + aSeed * 4.0);
        }
      `,
      fragmentShader: /* glsl */ `
        uniform vec3 uColor; uniform float uAlpha;
        varying float vTw;
        void main() {
          float d = length(gl_PointCoord - 0.5);
          float a = smoothstep(0.5, 0.12, d) * uAlpha * (0.75 + 0.25 * vTw);
          gl_FragColor = vec4(uColor, a);
        }
      `,
    }),
  )
  scene.add(new THREE.Points(dustGeo, dustMat))

  /* ----- 主题切换 ----- */
  function applyPalette(name) {
    const P = PALETTES[name]
    if (!P) return
    currentTheme = name

    if (bgTexture) bgTexture.dispose()
    bgTexture = makeBackgroundTexture(P)
    scene.background = bgTexture

    for (let i = 0; i < lines.length; i++) {
      const s = lines[i]
      if (s.isAccent) {
        s.shared.uColorA.value.set(P.colorC)
        s.shared.uColorB.value.set(P.colorB)
      } else if (i % 2 === 0) {
        s.shared.uColorA.value.set(P.colorA)
        s.shared.uColorB.value.set(P.colorB)
      } else {
        s.shared.uColorA.value.set(P.colorB)
        s.shared.uColorB.value.set(P.colorA)
      }
      s.wickMat.uniforms.uWickAlpha.value = P.wickAlpha
    }
    dustMat.uniforms.uColor.value.set(P.dust)
    dustMat.uniforms.uAlpha.value = name === 'dark' ? 0.3 : 0.24
  }

  applyPalette(initialTheme)

  /* ----- 渲染循环（无后处理，直出；动画全在着色器） ----- */
  let rafId = 0
  let lastTime = performance.now()
  let elapsed = 0
  let camProgress = 0

  function tick() {
    if (disposed) return
    rafId = requestAnimationFrame(tick)
    const now = performance.now()
    const dt = Math.min(0.05, (now - lastTime) / 1000)
    lastTime = now
    elapsed += dt

    for (const s of lines) {
      s.shared.uTime.value = elapsed
    }
    dustMat.uniforms.uTime.value = elapsed

    // 呼吸透明度（CPU 仅更新每线一个 uniform）
    const base = PALETTES[currentTheme].alphaBase
    for (const s of lines) {
      const breath = base * s.centerWeight
      s.shared.uAlpha.value = breath
    }

    // 相机：滚动轻微升降 + 鼠标视差 + 空闲呼吸（保持平面感）
    camProgress += (scrollState.progress - camProgress) * Math.min(1, dt * 3)
    const p = camProgress
    rig.position.y = -p * 3.5 + Math.sin(elapsed * 0.06) * 0.25
    camera.position.x = scrollState.mouse.sx * 1.2
    camera.position.y = -scrollState.mouse.sy * 0.6
    camera.lookAt(0, rig.position.y, -28)

    renderer.render(scene, camera)
  }
  tick()

  /* ----- resize ----- */
  function onResize() {
    const w = window.innerWidth
    const h = window.innerHeight
    renderer.setSize(w, h)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  window.addEventListener('resize', onResize)

  /* ----- WebGL 上下文丢失防御 ----- */
  function onContextLost(e) {
    e.preventDefault()
    cancelAnimationFrame(rafId)
    canvas.style.display = 'none'
    console.warn('[FellowQuant] WebGL 上下文丢失，已切换为渐变背景')
  }
  function onContextRestored() {
    if (disposed) return
    canvas.style.display = ''
    lastTime = performance.now()
    tick()
  }
  canvas.addEventListener('webglcontextlost', onContextLost, false)
  canvas.addEventListener('webglcontextrestored', onContextRestored, false)

  return {
    setTheme(name) {
      if (name !== currentTheme) applyPalette(name)
    },
    dispose() {
      disposed = true
      cancelAnimationFrame(rafId)
      window.removeEventListener('resize', onResize)
      canvas.removeEventListener('webglcontextlost', onContextLost)
      canvas.removeEventListener('webglcontextrestored', onContextRestored)
      for (const d of disposables) d.dispose()
      if (bgTexture) bgTexture.dispose()
      renderer.dispose()
    },
  }
}
