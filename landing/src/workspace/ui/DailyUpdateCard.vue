<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'
import { dailyUpdateStatus, runDailyUpdate } from '../../api.js'
import { coverageText, lastText, progressText } from '../dailyUpdate.js'

const props = defineProps({
  admin: { type: Boolean, default: false },
  notify: { type: Function, default: () => {} },
})
const emit = defineEmits(['finished'])

const status = ref(null)
const error = ref('')
const starting = ref(false)
const running = computed(() => status.value?.state === 'running')
const tone = computed(() => ({ failed: 'text-amber-200', disabled: 'text-slate-400' }[status.value?.state] || 'text-slate-300'))

let timer = null
async function load() {
  try {
    const wasRunning = running.value
    status.value = await dailyUpdateStatus()
    error.value = ''
    if (wasRunning && !running.value) emit('finished')
  } catch (e) {
    error.value = e.message || '读取更新状态失败'
  }
  // 更新进行中时每 10 秒刷新一次进度。
  if (running.value && !timer) timer = setInterval(load, 10000)
  if (!running.value && timer) { clearInterval(timer); timer = null }
}
function stop() {
  if (timer) clearInterval(timer)
  timer = null
}

async function runNow() {
  starting.value = true
  try {
    await runDailyUpdate()
    props.notify('已开始更新今天的数据，在后台运行')
    await load()
  } catch (e) {
    props.notify(e.message || '启动失败')
  } finally {
    starting.value = false
  }
}

onMounted(load)
onActivated(load)
onDeactivated(stop)
onBeforeUnmount(stop)
</script>

<template>
  <section class="glass rounded-2xl p-5" aria-label="每天自动更新">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 flex-1">
        <h2 class="text-base font-semibold text-white">每天自动更新</h2>
        <p class="mt-1 text-sm text-slate-400">每个交易日 {{ status?.time || '18:30' }} 以后，平台自动更新全市场的行情、估值、分红送转、指数和行业数据，不需要手动操作。</p>
      </div>
      <button v-if="admin && status && !running" type="button" :disabled="starting"
        class="rounded-full border border-indigo-400/40 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 transition hover:bg-indigo-500/20 disabled:opacity-50"
        @click="runNow">{{ starting ? '启动中…' : '现在更新' }}</button>
    </div>
    <p v-if="error" class="mt-3 text-sm text-rose-300" role="alert">{{ error }} <button type="button" class="underline" @click="load">重试</button></p>
    <div v-else-if="status" class="mt-3 space-y-1.5 text-sm">
      <p class="text-white">{{ coverageText(status.data) }}</p>
      <p :class="tone">{{ running ? `正在更新：${progressText(status.progress)}` : status.text }}</p>
      <p class="text-slate-400">{{ lastText(status.last) }}</p>
      <ul v-if="admin && status.last?.errors?.length" class="mt-1 space-y-0.5 text-xs text-amber-300">
        <li v-for="item in status.last.errors" :key="item" class="break-words">{{ item }}</li>
      </ul>
    </div>
    <p v-else class="mt-3 text-sm text-slate-400">正在读取更新状态…</p>
  </section>
</template>
