<script setup>
import { computed, reactive, ref } from 'vue'
import DynamicBackground from './DynamicBackground.vue'
import ThemeToggle from './ThemeToggle.vue'
import { login, register, setSession, forgotRequest, forgotReset } from '../api.js'

const mode = ref('login') // 'login' | 'register' | 'forgot'

const form = reactive({
  name: '',
  email: '',
  password: '',
  confirm: '',
  remember: true,
  agree: false,
})

// 忘记密码流程状态（两步：1 验证身份 → 2 重置密码）
const forgot = reactive({
  step: 1,
  name: '',
  email: '',
  code: '',
  generatedCode: '',
  password: '',
  confirm: '',
})

const errors = reactive({})
const showPwd = ref(false)
const showCfm = ref(false)
const showNewPwd = ref(false)
const submitting = ref(false)
const done = ref(false)

// 切换时锁定并平滑过渡容器高度，避免 out-in 间隙导致的布局跳动
const stage = ref(null)
function lockHeight() {
  const el = stage.value
  if (!el) return
  el.style.height = el.scrollHeight + 'px'
}
function animateToHeight(el) {
  const stageEl = stage.value
  if (!stageEl) return
  const target = el.scrollHeight
  // 下一帧再设置目标高度，触发 height 过渡
  requestAnimationFrame(() => {
    stageEl.style.height = target + 'px'
  })
}
function releaseHeight() {
  const el = stage.value
  if (!el) return
  el.style.height = 'auto'
}

const isLogin = computed(() => mode.value === 'login')
const isForgot = computed(() => mode.value === 'forgot')

const heading = computed(
  () =>
    ({
      login: { title: '欢迎回来', sub: '登录以进入你的量化工作台' },
      register: { title: '创建账户', sub: '几分钟内开启你的量化之旅' },
      forgot: { title: '忘记密码', sub: '验证账号身份后即可重置密码' },
    })[mode.value]
)

function switchMode(m) {
  mode.value = m
  Object.keys(errors).forEach((k) => delete errors[k])
  done.value = false
}

function enterForgot() {
  mode.value = 'forgot'
  Object.keys(errors).forEach((k) => delete errors[k])
  done.value = false
  forgot.step = 1
  forgot.code = ''
  forgot.generatedCode = ''
  forgot.password = ''
  forgot.confirm = ''
}

function validate() {
  Object.keys(errors).forEach((k) => delete errors[k])
  if (!isLogin.value && !form.name.trim()) errors.name = '请输入用户名'
  if (!form.email.trim()) {
    errors.email = '请输入邮箱'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
    errors.email = '邮箱格式不正确'
  }
  if (!form.password) {
    errors.password = '请输入密码'
  } else if (form.password.length < 8) {
    errors.password = '密码至少 8 位'
  }
  if (!isLogin.value) {
    if (form.confirm !== form.password) errors.confirm = '两次密码不一致'
    if (!form.agree) errors.agree = '请阅读并同意服务条款'
  }
  return Object.keys(errors).length === 0
}

async function onSubmit() {
  if (submitting.value) return
  if (!validate()) return
  submitting.value = true
  try {
    if (isLogin.value) {
      const data = await login({ email: form.email, password: form.password })
      setSession(data.token, data.user)
      done.value = true
      // 登录成功，跳转功能台
      setTimeout(() => (window.location.href = '/app.html'), 500)
    } else {
      await register({ name: form.name, email: form.email, password: form.password })
      // 注册成功，自动登录并跳转功能台
      const data = await login({ email: form.email, password: form.password })
      setSession(data.token, data.user)
      done.value = true
      setTimeout(() => (window.location.href = '/app.html'), 600)
    }
  } catch (e) {
    // 后端字段级错误（如 409 邮箱已注册 / 401 凭据错误）映射到表单
    const msg = e && e.message ? e.message : '请求失败，请稍后重试'
    if (/邮箱/.test(msg)) errors.email = msg
    else if (/密码|凭据/.test(msg)) errors.password = msg
    else errors.form = msg
  } finally {
    submitting.value = false
  }
}

function validateForgot() {
  Object.keys(errors).forEach((k) => delete errors[k])
  if (forgot.step === 1) {
    if (!forgot.name.trim()) errors.name = '请输入账号名'
    if (!forgot.email.trim()) {
      errors.email = '请输入邮箱'
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(forgot.email)) {
      errors.email = '邮箱格式不正确'
    }
  } else {
    if (!/^\d{4,8}$/.test(forgot.code.trim())) errors.code = '请输入收到的验证码'
    if (!forgot.password || forgot.password.length < 8) errors.password = '密码至少 8 位'
    if (forgot.confirm !== forgot.password) errors.confirm = '两次密码不一致'
  }
  return Object.keys(errors).length === 0
}

async function onForgotSubmit() {
  if (submitting.value) return
  if (!validateForgot()) return
  submitting.value = true
  try {
    if (forgot.step === 1) {
      const data = await forgotRequest({ name: forgot.name.trim(), email: forgot.email })
      forgot.generatedCode = data.message
      forgot.step = 2
    } else {
      await forgotReset({
        name: forgot.name.trim(),
        email: forgot.email,
        code: forgot.code.trim(),
        new_password: forgot.password,
      })
      done.value = true
      setTimeout(() => switchMode('login'), 1200)
    }
  } catch (e) {
    const msg = e && e.message ? e.message : '请求失败，请稍后重试'
    if (/账号名/.test(msg)) errors.name = msg
    else if (/邮箱/.test(msg)) errors.email = msg
    else if (/验证码/.test(msg)) errors.code = msg
    else if (/密码/.test(msg)) errors.password = msg
    else errors.form = msg
  } finally {
    submitting.value = false
  }
}

const features = [
  { t: '极速撮合引擎', d: '微秒级延迟，Rust 高性能通道' },
  { t: '智能策略热加载', d: 'Python 策略秒级验证迭代' },
  { t: '全天候风控', d: '动态回撤与暴露监控' },
]
</script>

<template>
  <div class="relative flex min-h-screen items-center justify-center px-4 py-10 text-slate-200">
    <DynamicBackground />

    <!-- 顶部返回首页 -->
    <a
      href="/"
      class="absolute left-5 top-5 z-20 flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 backdrop-blur-md transition hover:border-white/25 hover:text-white"
    >
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
      </svg>
      返回首页
    </a>

    <!-- 右上角主题切换 -->
    <div class="absolute right-5 top-5 z-20">
      <ThemeToggle />
    </div>

    <div
      class="glass-strong relative z-10 grid w-full max-w-4xl overflow-hidden rounded-3xl lg:grid-cols-2"
    >
      <!-- 左侧品牌展示 -->
      <aside
        class="relative hidden flex-col justify-between overflow-hidden p-10 lg:flex"
      >
        <div
          class="absolute inset-0 bg-gradient-to-br from-indigo-600/40 via-violet-600/25 to-transparent"
        />
        <div class="bg-grid absolute inset-0 opacity-50" />
        <div
          class="pointer-events-none absolute -left-16 top-10 h-56 w-56 rounded-full bg-indigo-500/30 blur-3xl"
        />
        <div
          class="pointer-events-none absolute -right-10 bottom-0 h-56 w-56 rounded-full bg-violet-500/30 blur-3xl"
        />

        <div class="relative">
          <a href="/" class="flex items-center gap-2.5">
            <span
              class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-base font-bold text-white shadow-lg shadow-indigo-500/40"
            >智</span>
            <span class="text-xl font-semibold tracking-wide text-white">智投引擎</span>
          </a>
          <p class="mt-8 text-2xl font-bold leading-snug text-white">
            数据驱动决策，<br />算法解锁 <span class="font-serif italic text-indigo-300">Alpha</span>
          </p>
          <p class="mt-4 max-w-xs text-sm leading-relaxed text-slate-300/80">
            为量化而生 · 极速、稳定、智能的一站式量化平台。
          </p>
        </div>

        <ul class="relative space-y-4">
          <li v-for="f in features" :key="f.t" class="flex items-start gap-3">
            <span
              class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/15 bg-white/10 text-indigo-200"
            >
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </span>
            <div>
              <p class="text-sm font-semibold text-white">{{ f.t }}</p>
              <p class="text-xs text-slate-400">{{ f.d }}</p>
            </div>
          </li>
        </ul>
      </aside>

      <!-- 右侧表单 -->
      <div class="relative p-7 sm:p-10">
        <!-- 模式切换：滑动指示器（忘记密码模式下隐藏） -->
        <div
          v-if="!isForgot"
          class="relative mx-auto mb-7 flex w-full max-w-sm rounded-full border border-white/10 bg-white/5 p-1 text-sm"
        >
          <span
            class="pointer-events-none absolute bottom-1 left-1 top-1 w-[calc(50%-0.25rem)] rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 shadow-lg shadow-indigo-500/30 transition-transform duration-500 ease-out-expo"
            :style="{ transform: mode === 'login' ? 'translateX(0)' : 'translateX(100%)' }"
          />
          <button
            v-for="m in [{ k: 'login', l: '登录' }, { k: 'register', l: '注册' }]"
            :key="m.k"
            type="button"
            class="relative z-10 flex-1 rounded-full px-4 py-2 font-medium transition-colors duration-300"
            :class="mode === m.k ? 'text-white' : 'text-slate-400 hover:text-slate-200'"
            @click="switchMode(m.k)"
          >
            {{ m.l }}
          </button>
        </div>

        <div class="mx-auto w-full max-w-sm">
          <div ref="stage" class="stage-auth relative overflow-hidden">
          <Transition
            name="auth-switch"
            mode="out-in"
            @before-leave="lockHeight"
            @enter="animateToHeight"
            @after-enter="releaseHeight"
          >
            <div :key="mode">
              <h1 class="text-2xl font-bold text-white">{{ heading.title }}</h1>
              <p class="mt-1.5 text-sm text-slate-400">{{ heading.sub }}</p>

              <!-- 表单级错误提示 -->
              <div
                v-if="errors.form"
                class="mt-5 flex items-center gap-2 rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-200"
              >
                <svg class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v4m0 4h.01M10.3 3.9l-7.3 12.6A2 2 0 004.7 19h14.6a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
                </svg>
                {{ errors.form }}
              </div>

              <!-- 成功提示 -->
              <div
                v-if="done"
                class="mt-6 flex items-center gap-2 rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-200"
              >
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                {{ isForgot ? '密码重置成功，即将返回登录…' : isLogin ? '登录成功，正在跳转…' : '注册成功，请登录。' }}
              </div>

              <!-- 登录 / 注册表单 -->
              <form v-if="!isForgot" class="mt-6 space-y-4" novalidate @submit.prevent="onSubmit">
            <div v-if="!isLogin">
              <label class="mb-1.5 block text-xs font-medium text-slate-400">用户名</label>
              <div class="relative">
                <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
                <input
                  v-model="form.name"
                  type="text"
                  autocomplete="name"
                  placeholder="你的称呼"
                  class="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-400/50 focus:bg-white/10 focus:ring-2 focus:ring-indigo-500/30"
                  :class="{ 'border-rose-400/50 focus:ring-rose-500/20': errors.name }"
                />
              </div>
              <p v-if="errors.name" class="mt-1 text-xs text-rose-300">{{ errors.name }}</p>
            </div>

            <div>
              <label class="mb-1.5 block text-xs font-medium text-slate-400">邮箱</label>
              <div class="relative">
                <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M3 8l9 6 9-6M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <input
                  v-model="form.email"
                  type="email"
                  autocomplete="email"
                  placeholder="you@quant.io"
                  class="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-400/50 focus:bg-white/10 focus:ring-2 focus:ring-indigo-500/30"
                  :class="{ 'border-rose-400/50 focus:ring-rose-500/20': errors.email }"
                />
              </div>
              <p v-if="errors.email" class="mt-1 text-xs text-rose-300">{{ errors.email }}</p>
            </div>

            <div>
              <label class="mb-1.5 block text-xs font-medium text-slate-400">密码</label>
              <div class="relative">
                <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 11c1.1 0 2-.9 2-2V7a2 2 0 00-4 0v2c0 1.1.9 2 2 2zM6 11h12v7a2 2 0 01-2 2H8a2 2 0 01-2-2v-7z" />
                </svg>
                <input
                  v-model="form.password"
                  :type="showPwd ? 'text' : 'password'"
                  :autocomplete="isLogin ? 'current-password' : 'new-password'"
                  placeholder="至少 8 位"
                  class="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-10 pr-10 text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-400/50 focus:bg-white/10 focus:ring-2 focus:ring-indigo-500/30"
                  :class="{ 'border-rose-400/50 focus:ring-rose-500/20': errors.password }"
                />
                <button
                  type="button"
                  class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  @click="showPwd = !showPwd"
                  :aria-label="showPwd ? '隐藏密码' : '显示密码'"
                >
                  <svg v-if="showPwd" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18M10.6 10.6a2 2 0 102.8 2.8M9.9 4.2A9.5 9.5 0 0112 4c5 0 9 4.5 10 8a12.9 12.9 0 01-2.2 3.2M6.1 6.1C3.8 7.4 2.3 9.5 2 12c1 3.5 5 8 10 8a9.8 9.8 0 004.9-1.4" />
                  </svg>
                  <svg v-else class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M2 12c1-3.5 5-8 10-8s9 4.5 10 8c-1 3.5-5 8-10 8s-9-4.5-10-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                </button>
              </div>
              <p v-if="errors.password" class="mt-1 text-xs text-rose-300">{{ errors.password }}</p>
            </div>

            <div v-if="!isLogin">
              <label class="mb-1.5 block text-xs font-medium text-slate-400">确认密码</label>
              <div class="relative">
                <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <input
                  v-model="form.confirm"
                  :type="showCfm ? 'text' : 'password'"
                  autocomplete="new-password"
                  placeholder="再次输入密码"
                  class="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-10 pr-10 text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-400/50 focus:bg-white/10 focus:ring-2 focus:ring-indigo-500/30"
                  :class="{ 'border-rose-400/50 focus:ring-rose-500/20': errors.confirm }"
                />
                <button
                  type="button"
                  class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  @click="showCfm = !showCfm"
                  aria-label="切换显示密码"
                >
                  <svg v-if="showCfm" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18M10.6 10.6a2 2 0 102.8 2.8M9.9 4.2A9.5 9.5 0 0112 4c5 0 9 4.5 10 8a12.9 12.9 0 01-2.2 3.2M6.1 6.1C3.8 7.4 2.3 9.5 2 12c1 3.5 5 8 10 8a9.8 9.8 0 004.9-1.4" />
                  </svg>
                  <svg v-else class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M2 12c1-3.5 5-8 10-8s9 4.5 10 8c-1 3.5-5 8-10 8s-9-4.5-10-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                </button>
              </div>
              <p v-if="errors.confirm" class="mt-1 text-xs text-rose-300">{{ errors.confirm }}</p>
            </div>

            <!-- 记住我 / 忘记密码 -->
            <div v-if="isLogin" class="flex items-center justify-between text-xs">
              <label class="flex cursor-pointer items-center gap-2 text-slate-400">
                <input
                  v-model="form.remember"
                  type="checkbox"
                  class="h-3.5 w-3.5 rounded border-white/20 bg-white/5 text-indigo-500 focus:ring-indigo-500/40"
                />
                记住我
              </label>
              <button
                type="button"
                class="text-indigo-300 transition hover:text-indigo-200"
                @click="enterForgot"
              >忘记密码？</button>
            </div>

            <!-- 协议 -->
            <label
              v-else
              class="flex cursor-pointer items-start gap-2 text-xs text-slate-400"
            >
              <input
                v-model="form.agree"
                type="checkbox"
                class="mt-0.5 h-3.5 w-3.5 rounded border-white/20 bg-white/5 text-indigo-500 focus:ring-indigo-500/40"
              />
              <span>
                我已阅读并同意
                <a href="#" class="text-indigo-300 hover:text-indigo-200">《服务条款》</a>
                与
                <a href="#" class="text-indigo-300 hover:text-indigo-200">《隐私政策》</a>
              </span>
            </label>
            <p v-if="errors.agree" class="-mt-2 text-xs text-rose-300">{{ errors.agree }}</p>

            <button
              type="submit"
              :disabled="submitting"
              class="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-indigo-500/50 disabled:opacity-70 disabled:hover:translate-y-0"
            >
              <svg
                v-if="submitting"
                class="h-4 w-4 animate-spin"
                fill="none" viewBox="0 0 24 24"
              >
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              {{ submitting ? '请稍候…' : isLogin ? '登录' : '注册' }}
            </button>
          </form>

            <!-- 忘记密码表单（两步：验证身份 → 重置密码） -->
            <form v-else class="mt-6 space-y-4" novalidate @submit.prevent="onForgotSubmit">
              <!-- 第一步：账号名 + 邮箱 -->
              <template v-if="forgot.step === 1">
                <div>
                  <label class="mb-1.5 block text-xs font-medium text-slate-400">账号名</label>
                  <div class="relative">
                    <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    <input
                      v-model="forgot.name"
                      type="text"
                      autocomplete="username"
                      placeholder="注册时的账号名"
                      class="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-400/50 focus:bg-white/10 focus:ring-2 focus:ring-indigo-500/30"
                      :class="{ 'border-rose-400/50 focus:ring-rose-500/20': errors.name }"
                    />
                  </div>
                  <p v-if="errors.name" class="mt-1 text-xs text-rose-300">{{ errors.name }}</p>
                </div>

                <div>
                  <label class="mb-1.5 block text-xs font-medium text-slate-400">注册邮箱</label>
                  <div class="relative">
                    <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M3 8l9 6 9-6M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                    <input
                      v-model="forgot.email"
                      type="email"
                      autocomplete="email"
                      placeholder="you@quant.io"
                      class="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-400/50 focus:bg-white/10 focus:ring-2 focus:ring-indigo-500/30"
                      :class="{ 'border-rose-400/50 focus:ring-rose-500/20': errors.email }"
                    />
                  </div>
                  <p v-if="errors.email" class="mt-1 text-xs text-rose-300">{{ errors.email }}</p>
                </div>

                <button
                  type="submit"
                  :disabled="submitting"
                  class="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-indigo-500/50 disabled:opacity-70 disabled:hover:translate-y-0"
                >
                  {{ submitting ? '请稍候…' : '获取验证码' }}
                </button>
              </template>

              <!-- 第二步：验证码 + 新密码 -->
              <template v-else>
                <!-- 生成的验证码提示 -->
                <div class="flex items-center gap-2 rounded-xl border border-indigo-400/30 bg-indigo-400/10 px-4 py-3 text-sm text-indigo-200">
                  <svg class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  <span>
                    {{ forgot.generatedCode }}
                    <span class="text-indigo-300/70">（10 分钟内有效）</span>
                  </span>
                </div>

                <div>
                  <label class="mb-1.5 block text-xs font-medium text-slate-400">验证码</label>
                  <div class="relative">
                    <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <input
                      v-model="forgot.code"
                      type="text"
                      inputmode="numeric"
                      maxlength="8"
                      placeholder="输入邮件中的 6 位验证码"
                      class="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-10 pr-3 text-sm tracking-widest text-white placeholder-slate-500 outline-none transition focus:border-indigo-400/50 focus:bg-white/10 focus:ring-2 focus:ring-indigo-500/30"
                      :class="{ 'border-rose-400/50 focus:ring-rose-500/20': errors.code }"
                    />
                  </div>
                  <p v-if="errors.code" class="mt-1 text-xs text-rose-300">{{ errors.code }}</p>
                </div>

                <div>
                  <label class="mb-1.5 block text-xs font-medium text-slate-400">新密码</label>
                  <div class="relative">
                    <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M12 11c1.1 0 2-.9 2-2V7a2 2 0 00-4 0v2c0 1.1.9 2 2 2zM6 11h12v7a2 2 0 01-2 2H8a2 2 0 01-2-2v-7z" />
                    </svg>
                    <input
                      v-model="forgot.password"
                      :type="showNewPwd ? 'text' : 'password'"
                      autocomplete="new-password"
                      placeholder="至少 8 位"
                      class="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-10 pr-10 text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-400/50 focus:bg-white/10 focus:ring-2 focus:ring-indigo-500/30"
                      :class="{ 'border-rose-400/50 focus:ring-rose-500/20': errors.password }"
                    />
                    <button
                      type="button"
                      class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                      @click="showNewPwd = !showNewPwd"
                      :aria-label="showNewPwd ? '隐藏密码' : '显示密码'"
                    >
                      <svg v-if="showNewPwd" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18M10.6 10.6a2 2 0 102.8 2.8M9.9 4.2A9.5 9.5 0 0112 4c5 0 9 4.5 10 8a12.9 12.9 0 01-2.2 3.2M6.1 6.1C3.8 7.4 2.3 9.5 2 12c1 3.5 5 8 10 8a9.8 9.8 0 004.9-1.4" />
                      </svg>
                      <svg v-else class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M2 12c1-3.5 5-8 10-8s9 4.5 10 8c-1 3.5-5 8-10 8s-9-4.5-10-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    </button>
                  </div>
                  <p v-if="errors.password" class="mt-1 text-xs text-rose-300">{{ errors.password }}</p>
                </div>

                <div>
                  <label class="mb-1.5 block text-xs font-medium text-slate-400">确认新密码</label>
                  <div class="relative">
                    <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <input
                      v-model="forgot.confirm"
                      type="password"
                      autocomplete="new-password"
                      placeholder="再次输入新密码"
                      class="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 pl-10 pr-3 text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-400/50 focus:bg-white/10 focus:ring-2 focus:ring-indigo-500/30"
                      :class="{ 'border-rose-400/50 focus:ring-rose-500/20': errors.confirm }"
                    />
                  </div>
                  <p v-if="errors.confirm" class="mt-1 text-xs text-rose-300">{{ errors.confirm }}</p>
                </div>

                <button
                  type="submit"
                  :disabled="submitting"
                  class="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-indigo-500/50 disabled:opacity-70 disabled:hover:translate-y-0"
                >
                  {{ submitting ? '请稍候…' : '重置密码' }}
                </button>

                <button
                  type="button"
                  class="w-full text-center text-xs text-slate-400 transition hover:text-slate-200"
                  @click="forgot.step = 1"
                >
                  收不到验证码？重新获取
                </button>
              </template>

              <p class="pt-1 text-center text-xs text-slate-400">
                想起密码了？
                <button
                  type="button"
                  class="font-medium text-indigo-300 transition hover:text-indigo-200"
                  @click="switchMode('login')"
                >返回登录</button>
              </p>
            </form>
            </div>
          </Transition>
          </div>

          <!-- 第三方登录（忘记密码模式下隐藏） -->
          <div v-if="!isForgot" class="my-6 flex items-center gap-3 text-xs text-slate-500">
            <span class="h-px flex-1 bg-white/10" />
            或使用以下方式
            <span class="h-px flex-1 bg-white/10" />
          </div>
          <div v-if="!isForgot" class="grid grid-cols-3 gap-3">
            <button
              v-for="s in ['GitHub', 'Google', '微信']"
              :key="s"
              type="button"
              class="flex items-center justify-center rounded-xl border border-white/10 bg-white/5 py-2.5 text-xs font-medium text-slate-300 transition hover:border-white/25 hover:bg-white/10 hover:text-white"
            >
              {{ s }}
            </button>
          </div>

          <p v-if="!isForgot" class="mt-7 text-center text-xs text-slate-400">
            {{ isLogin ? '还没有账户？' : '已有账户？' }}
            <button
              type="button"
              class="font-medium text-indigo-300 transition hover:text-indigo-200"
              @click="switchMode(isLogin ? 'register' : 'login')"
            >
              {{ isLogin ? '立即注册' : '立即登录' }}
            </button>
          </p>

          <p class="mt-6 text-center text-[11px] leading-relaxed text-slate-600">
            登录即代表您接受我们的服务条款与隐私政策。<br />
            本平台仅供专业交易者使用，投资有风险，入市需谨慎。
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 切换容器：平滑过渡高度（手风琴），消除 out-in 间隙的布局跳动 */
.stage-auth {
  transition: height 0.34s cubic-bezier(0.16, 1, 0.3, 1);
}

/* 登录/注册切换：out-in 的横向滑入滑出 + 淡入淡出 */
.auth-switch-enter-active,
.auth-switch-leave-active {
  transition:
    opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1),
    transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.auth-switch-enter-from {
  opacity: 0;
  transform: translateX(16px);
}
.auth-switch-leave-to {
  opacity: 0;
  transform: translateX(-16px);
}
@media (prefers-reduced-motion: reduce) {
  .stage-auth { transition: none; }
  .auth-switch-enter-active,
  .auth-switch-leave-active {
    transition: opacity 0.2s ease;
  }
  .auth-switch-enter-from,
  .auth-switch-leave-to {
    transform: none;
  }
}
</style>
