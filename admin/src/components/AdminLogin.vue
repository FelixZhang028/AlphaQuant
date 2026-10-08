<script setup>
import { reactive, ref } from 'vue'
import { login } from '../api.js'

const emit = defineEmits(['logged-in'])
const form = reactive({ email: '', password: '' })
const error = ref('')
const loading = ref(false)

async function onSubmit() {
  if (loading.value) return
  error.value = ''
  if (!form.email || !form.password) {
    error.value = '请输入邮箱和密码'
    return
  }
  loading.value = true
  try {
    await login(form.email, form.password)
    emit('logged-in')
  } catch (e) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center px-4 py-10">
    <div class="glass-strong w-full max-w-md rounded-3xl p-8">
      <div class="flex items-center gap-3">
        <span class="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-lg font-bold text-white shadow-lg shadow-indigo-500/40">智</span>
        <div>
          <p class="text-lg font-semibold text-white">智投引擎</p>
          <p class="text-xs text-slate-500">管理后台 · 管理员登录</p>
        </div>
      </div>

      <p class="mt-7 text-2xl font-bold text-white">欢迎回来</p>
      <p class="mt-1 text-sm text-slate-400">请使用管理员账户登录</p>

      <div v-if="error" class="mt-5 flex items-center gap-2 rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">
        <svg class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v4m0 4h.01M10.3 3.9l-7.3 12.6A2 2 0 004.7 19h14.6a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" /></svg>
        {{ error }}
      </div>

      <form class="mt-6 space-y-4" @submit.prevent="onSubmit">
        <div>
          <label class="mb-1.5 block text-xs text-slate-400">邮箱</label>
          <input v-model="form.email" type="email" autocomplete="username" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40 focus:ring-2 focus:ring-indigo-500/20" />
        </div>
        <div>
          <label class="mb-1.5 block text-xs text-slate-400">密码</label>
          <input v-model="form.password" type="password" autocomplete="current-password" placeholder="••••••••" class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40 focus:ring-2 focus:ring-indigo-500/20" />
        </div>
        <button type="submit" :disabled="loading" class="flex w-full items-center justify-center gap-2 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70">
          <svg v-if="loading" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" /></svg>
          {{ loading ? '登录中…' : '登录' }}
        </button>
      </form>

      <div class="mt-6 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-slate-500">
        管理员账户由部署者通过后端环境变量创建，请使用已配置的管理员邮箱和密码登录。
      </div>
    </div>
  </div>
</template>
