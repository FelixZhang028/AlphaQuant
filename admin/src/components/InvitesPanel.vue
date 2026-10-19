<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { createInvite, registrationSettings, setInviteActive, setRegistrationMode } from '../api.js'

// 注册方式和邀请码：改完立即生效，不用重启后端。.env 里写的邀请码只能在服务器上改。
const emit = defineEmits(['notify', 'changed'])
const settings = ref(null)
const error = ref('')
const saving = ref(false)
const form = reactive({ code: '', max_uses: '', note: '' })
const lastCode = ref('')

const modes = [
  { value: 'invite', label: '凭邀请码注册', hint: '只有拿到邀请码的人能注册（试用阶段推荐）' },
  { value: 'open', label: '开放注册', hint: '任何人都能注册' },
  { value: 'closed', label: '暂停注册', hint: '谁也不能注册，已有账户照常登录' },
]

async function load() {
  error.value = ''
  try {
    settings.value = await registrationSettings()
  } catch (e) {
    error.value = e.message || '加载失败'
  }
}
onMounted(load)

const available = computed(() => (settings.value?.invites || []).filter((i) => i.active && (i.limit == null || i.used < i.limit)).length)

async function chooseMode(mode) {
  if (!settings.value || mode === settings.value.mode) return
  saving.value = true
  try {
    settings.value = await setRegistrationMode(mode)
    emit('notify', `注册方式已改为：${modes.find((m) => m.value === mode)?.label}`)
    emit('changed')
  } catch (e) {
    emit('notify', e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function make() {
  const uses = String(form.max_uses).trim()
  if (uses && !(Number.isInteger(Number(uses)) && Number(uses) >= 1)) {
    emit('notify', '可用次数要填正整数，留空表示不限')
    return
  }
  saving.value = true
  try {
    const data = await createInvite({ code: form.code.trim(), max_uses: uses ? Number(uses) : null, note: form.note.trim() })
    settings.value = data
    lastCode.value = data.code
    Object.assign(form, { code: '', max_uses: '', note: '' })
    emit('notify', `已生成邀请码 ${data.code}`)
    emit('changed')
  } catch (e) {
    emit('notify', e.message || '生成失败')
  } finally {
    saving.value = false
  }
}

async function toggle(invite) {
  if (invite.active && !window.confirm(`停用邀请码 ${invite.code}？停用后不能再用它注册，已经注册的账户不受影响。`)) return
  try {
    settings.value = await setInviteActive(invite.code, !invite.active)
    emit('changed')
  } catch (e) {
    emit('notify', e.message || '操作失败')
  }
}

async function copy(code) {
  try {
    await navigator.clipboard.writeText(code)
    emit('notify', `已复制 ${code}`)
  } catch {
    emit('notify', '复制失败，请手动选中复制')
  }
}

const time = (value) => (value ? new Date(value).toLocaleString() : '—')
const inputClass = 'w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-indigo-400/40'
</script>

<template>
  <div class="space-y-6">
    <p v-if="error" role="alert" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{{ error }}</p>

    <section v-if="settings" class="glass rounded-2xl p-5" aria-label="注册方式">
      <h2 class="text-sm font-semibold text-white">注册方式</h2>
      <p v-if="settings.locked" class="mt-2 text-sm text-amber-200">服务器的 .env 里写了 FELLOWQUANT_REGISTRATION=closed，现在固定为暂停注册；要在页面上修改，先在服务器上去掉这一行并重启后端。</p>
      <div class="mt-4 grid gap-3 sm:grid-cols-3">
        <button v-for="m in modes" :key="m.value" type="button" :disabled="saving || settings.locked"
          class="rounded-xl border p-4 text-left transition disabled:cursor-not-allowed"
          :class="settings.mode === m.value ? 'border-indigo-400/50 bg-indigo-500/15' : 'border-white/10 bg-white/5 hover:border-white/25'"
          :aria-pressed="settings.mode === m.value" @click="chooseMode(m.value)">
          <p class="text-sm font-semibold text-white">{{ m.label }}<span v-if="settings.mode === m.value" class="ml-2 text-xs font-normal text-indigo-300">当前</span></p>
          <p class="mt-1 text-xs text-slate-400">{{ m.hint }}</p>
        </button>
      </div>
      <p v-if="settings.mode === 'invite' && !available" class="mt-3 text-sm text-amber-200">现在没有还能用的邀请码，谁也注册不了。在下面生成一个吧。</p>
    </section>

    <section class="glass rounded-2xl p-5" aria-label="生成邀请码">
      <h2 class="text-sm font-semibold text-white">生成邀请码</h2>
      <form class="mt-4 grid gap-3 sm:grid-cols-[1fr_9rem_1fr_auto] sm:items-end" @submit.prevent="make">
        <label class="text-xs text-slate-400">邀请码（留空自动生成）<input v-model="form.code" maxlength="32" placeholder="例如 FRIENDS2026" :class="inputClass" class="mt-1 uppercase" /></label>
        <label class="text-xs text-slate-400">可用次数（留空不限）<input v-model="form.max_uses" inputmode="numeric" placeholder="例如 20" :class="inputClass" class="mt-1" /></label>
        <label class="text-xs text-slate-400">备注<input v-model="form.note" maxlength="60" placeholder="例如 发给第一批试用的朋友" :class="inputClass" class="mt-1" /></label>
        <button type="submit" :disabled="saving" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white disabled:opacity-50">生成</button>
      </form>
      <p v-if="lastCode" class="mt-3 text-sm text-emerald-300">新的邀请码：<span class="font-mono">{{ lastCode }}</span>
        <button type="button" class="ml-2 rounded-full border border-emerald-400/30 px-3 py-0.5 text-xs hover:bg-emerald-400/10" @click="copy(lastCode)">复制</button></p>
      <p class="mt-2 text-xs text-slate-500">邀请码不区分大小写，只能用字母、数字、- 和 _，4 到 32 位。</p>
    </section>

    <section v-if="settings" class="glass rounded-2xl p-5" aria-label="邀请码列表">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-white">全部邀请码</h2>
        <span class="text-xs text-slate-500">还能用的 {{ available }} 个</span>
      </div>
      <div class="mt-4 overflow-x-auto">
        <table class="[&_td]:whitespace-nowrap [&_th]:whitespace-nowrap [&_td]:px-3 [&_th]:px-3 [&_td:first-child]:pl-0 [&_th:first-child]:pl-0 [&_td:last-child]:pr-0 [&_th:last-child]:pr-0 w-full min-w-[720px] text-left text-sm">
          <thead>
            <tr class="text-xs text-slate-500">
              <th class="pb-3 font-medium">邀请码</th>
              <th class="pb-3 text-right font-medium">已用 / 可用</th>
              <th class="pb-3 font-medium">备注</th>
              <th class="pb-3 font-medium">来源</th>
              <th class="pb-3 font-medium">生成时间</th>
              <th class="pb-3 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/5">
            <tr v-for="i in settings.invites" :key="i.code" class="text-slate-300" :class="{ 'opacity-50': !i.active }">
              <td class="py-3 font-mono text-xs text-indigo-300">{{ i.code }}<span v-if="!i.active" class="ml-2 font-sans text-rose-300">已停用</span></td>
              <td class="py-3 text-right" :class="i.limit != null && i.used >= i.limit ? 'text-amber-300' : 'text-white'">{{ i.used }} / {{ i.limit ?? '不限' }}</td>
              <td class="py-3 text-slate-400">{{ i.note || '—' }}</td>
              <td class="py-3 text-slate-400">{{ i.source === 'env' ? '.env 文件' : '管理后台' }}</td>
              <td class="py-3 text-slate-400">{{ time(i.created_at) }}</td>
              <td class="py-3 text-right">
                <div class="flex justify-end gap-2">
                  <button type="button" class="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300 hover:text-white" @click="copy(i.code)">复制</button>
                  <button v-if="i.source === 'page'" type="button"
                    class="rounded-full border px-3 py-1 text-xs"
                    :class="i.active ? 'border-rose-400/30 text-rose-300 hover:bg-rose-400/10' : 'border-emerald-400/30 text-emerald-300 hover:bg-emerald-400/10'"
                    @click="toggle(i)">{{ i.active ? '停用' : '恢复' }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!settings.invites.length" class="py-6 text-center text-sm text-slate-500">还没有邀请码。</p>
      </div>
    </section>
  </div>
</template>
