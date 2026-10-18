<script setup>
import { onMounted, ref } from 'vue'
import DynamicBackground from './components/DynamicBackground.vue'
import AdminLogin from './components/AdminLogin.vue'
import AdminPage from './components/AdminPage.vue'
import { clearSession, getToken, me } from './api.js'

const checking = ref(true)
const authed = ref(false)

onMounted(async () => {
  if (!getToken()) {
    checking.value = false
    return
  }
  try {
    const u = await me()
    if (u.is_admin) authed.value = true
    else clearSession()
  } catch {
    clearSession()
  }
  checking.value = false
})

function onLogin() {
  authed.value = true
}
function onLogout() {
  clearSession()
  authed.value = false
}
</script>

<template>
  <div class="relative min-h-screen text-slate-200">
    <DynamicBackground />
    <div v-if="checking" class="flex min-h-screen items-center justify-center">
      <div class="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-indigo-400" />
    </div>
    <AdminLogin v-else-if="!authed" @logged-in="onLogin" />
    <AdminPage v-else @logout="onLogout" />
  </div>
</template>
