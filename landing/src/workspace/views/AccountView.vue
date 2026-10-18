<script setup>
import { reactive, ref } from 'vue'
import { changePassword, deleteAccount, logout } from '../../api.js'

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

function doLogout() {
  logout()
  window.location.href = '/'
}

// 修改密码：要输入原密码；改完以后其他设备上的登录会失效，这台设备不用重新登录。
const password = reactive({ old: '', next: '', confirm: '' })
const changing = ref(false)
const passwordError = ref('')
async function savePassword() {
  passwordError.value = ''
  if (!password.old) return (passwordError.value = '请输入原密码')
  if (password.next.length < 8 || password.next.length > 128) return (passwordError.value = '新密码需要 8 到 128 位')
  if (password.next !== password.confirm) return (passwordError.value = '两次输入的新密码不一致')
  changing.value = true
  try {
    await changePassword({ old_password: password.old, new_password: password.next })
    Object.assign(password, { old: '', next: '', confirm: '' })
    props.notify('密码已修改，其他设备需要重新登录')
  } catch (e) {
    passwordError.value = e.message || '修改失败'
  } finally {
    changing.value = false
  }
}

// 注销账户：删除账户和全部数据（策略、回测、研究记录、AI 分析），不能恢复。
const confirmingDelete = ref(false)
const deletePassword = ref('')
const deleting = ref(false)
const deleteError = ref('')
async function removeAccount() {
  deleteError.value = ''
  if (!deletePassword.value) return (deleteError.value = '请输入密码确认')
  deleting.value = true
  try {
    await deleteAccount({ password: deletePassword.value })
    window.location.href = '/'
  } catch (e) {
    deleteError.value = e.message || '注销失败'
  } finally {
    deleting.value = false
  }
}

const inputClass = 'w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/50'
</script>

<template>
  <div class="space-y-6">
    <section class="glass glass-sheen relative overflow-hidden rounded-2xl p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-indigo-500/20 blur-3xl" />
      <div class="flex items-center gap-4">
        <span class="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-2xl font-bold text-white shadow-lg shadow-indigo-500/40">{{ (user?.name || 'U').slice(0, 1) }}</span>
        <div>
          <p class="text-xl font-bold text-white">{{ user?.name }}</p>
          <p class="text-sm text-slate-400">{{ user?.email }}</p>
        </div>
      </div>
      <p class="mt-4 text-xs text-slate-500">注册时间：{{ user?.created_at || '—' }}</p>
    </section>

    <section class="glass rounded-2xl p-5">
      <h2 class="text-sm font-semibold text-white">账户信息</h2>
      <div class="mt-4 grid gap-4 sm:grid-cols-2">
        <div class="rounded-xl border border-white/10 bg-white/5 p-4">
          <p class="text-xs text-slate-400">用户编号</p>
          <p class="mt-1 font-mono text-sm text-indigo-300">U-{{ user?.id || '—' }}</p>
        </div>
        <div class="rounded-xl border border-white/10 bg-white/5 p-4">
          <p class="text-xs text-slate-400">账户类型</p>
          <p class="mt-1 text-sm text-white">{{ user?.is_admin ? '管理员' : '标准用户' }}</p>
        </div>
      </div>
    </section>

    <section class="glass rounded-2xl p-5" aria-label="修改密码">
      <h2 class="text-sm font-semibold text-white">修改密码</h2>
      <p class="mt-2 text-sm text-slate-400">改完以后，其他设备上的登录会失效，需要用新密码重新登录。</p>
      <form class="mt-4 grid max-w-md gap-3" @submit.prevent="savePassword">
        <label class="text-xs text-slate-400">原密码<input v-model="password.old" type="password" autocomplete="current-password" :class="inputClass" class="mt-1" /></label>
        <label class="text-xs text-slate-400">新密码（8 到 128 位）<input v-model="password.next" type="password" autocomplete="new-password" :class="inputClass" class="mt-1" /></label>
        <label class="text-xs text-slate-400">再输入一次新密码<input v-model="password.confirm" type="password" autocomplete="new-password" :class="inputClass" class="mt-1" /></label>
        <p v-if="passwordError" role="alert" class="text-sm text-rose-300">{{ passwordError }}</p>
        <button type="submit" :disabled="changing" class="justify-self-start rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white disabled:opacity-50">{{ changing ? '保存中…' : '修改密码' }}</button>
      </form>
    </section>

    <section class="glass rounded-2xl p-5">
      <h2 class="text-sm font-semibold text-white">会话</h2>
      <p class="mt-2 text-sm text-slate-400">退出登录后，这个账户在所有设备上的登录都会失效，需要重新验证身份才能访问功能台。</p>
      <button @click="doLogout" class="mt-4 rounded-full border border-rose-400/20 px-5 py-2 text-sm text-rose-300 transition hover:bg-rose-400/10">退出登录</button>
    </section>

    <section v-if="!user?.is_admin" class="glass rounded-2xl border border-rose-400/15 p-5" aria-label="注销账户">
      <h2 class="text-sm font-semibold text-white">注销账户</h2>
      <p class="mt-2 text-sm text-slate-400">删除这个账户和它的全部数据：策略、回测、研究记录、AI 分析和研究经验。删除后不能恢复。</p>
      <button v-if="!confirmingDelete" type="button" class="mt-4 rounded-full border border-rose-400/30 px-5 py-2 text-sm text-rose-300 hover:bg-rose-400/10" @click="confirmingDelete = true">注销账户</button>
      <form v-else class="mt-4 grid max-w-md gap-3" @submit.prevent="removeAccount">
        <label class="text-xs text-slate-400">输入密码确认注销<input v-model="deletePassword" type="password" autocomplete="current-password" :class="inputClass" class="mt-1" /></label>
        <p v-if="deleteError" role="alert" class="text-sm text-rose-300">{{ deleteError }}</p>
        <div class="flex flex-wrap gap-3">
          <button type="submit" :disabled="deleting" class="rounded-full bg-rose-500/80 px-5 py-2 text-sm font-semibold text-white disabled:opacity-50">{{ deleting ? '删除中…' : '确认删除账户和全部数据' }}</button>
          <button type="button" class="rounded-full border border-white/10 px-5 py-2 text-sm text-slate-300" @click="confirmingDelete = false; deletePassword = ''">取消</button>
        </div>
      </form>
    </section>
  </div>
</template>
