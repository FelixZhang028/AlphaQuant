<script setup>
// 功能台右下角的 AI 问答：在任何页面都能问，回答只根据平台的本地数据，用到的数据可以展开看。
// 知道当前页面正在看的股票或回测（chatFocus.js），问“这只”“这次回测”时自动带上，也可以不带。
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { aiStatus, askAiChat, deleteAiChat, getAiChat, listAiChats } from '../../api.js'
import { openResearch } from '../researchNavigation.js'
import { overlays, pageFocus } from '../chatFocus.js'
import { blockLinks, chatContext, codeColumn, dataSummary, focusText, loadChatState, saveChatState, suggestionsFor, usageText } from '../aiChat.js'

const props = defineProps({
  view: { type: String, default: '' },
  label: { type: String, default: '' },
  hidden: { type: Boolean, default: false },
})

const saved = loadChatState()
// 手机上窗口铺满屏幕：刷新页面后不自动打开，免得挡住页面。
const isPhone = () => window.matchMedia('(max-width: 639px)').matches
const open = ref(Boolean(saved.open) && !isPhone())
// 上次正在看的对话：第一次打开窗口时接着显示，之后不再自动切换。
let restoreId = saved.chat || ''
const showHistory = ref(false)
const status = ref(null)
const statusError = ref('')
const chat = ref(null)
const chats = ref([])
const message = ref('')
const asking = ref(false)
const pending = ref('')
const error = ref('')
const usage = ref(null)
const includeFocus = ref(true)
const listEl = ref(null)
const inputEl = ref(null)

const available = computed(() => status.value?.ai?.available === true)
const focus = computed(() => pageFocus[props.view] || null)
const focusLabel = computed(() => focusText(focus.value))
const suggestions = computed(() => suggestionsFor(props.view, includeFocus.value ? focus.value : null))
const turns = computed(() => chat.value?.turns || [])
const usageLine = computed(() => usageText(usage.value))

// 换了页面或者换了正在看的股票，就重新默认带上。
watch(() => [props.view, focusLabel.value], () => { includeFocus.value = true })
watch([open, () => chat.value?.id], () => saveChatState({ open: open.value, chat: chat.value?.id || '' }))

async function loadStatus() {
  statusError.value = ''
  try {
    status.value = await aiStatus()
    usage.value = status.value.usage?.chat || null
  } catch (e) { statusError.value = e.message || '读取 AI 状态失败' }
}
async function loadChats() {
  try { chats.value = (await listAiChats()).items || [] } catch { chats.value = [] }
}
async function openChat(id, quiet = false) {
  error.value = ''
  try {
    chat.value = await getAiChat(id)
    showHistory.value = false
    scrollToEnd()
  } catch (e) { if (!quiet) error.value = e.message || '打开对话失败' }   // 上次的对话已经删掉时不提示
}
function newChat() {
  chat.value = null
  showHistory.value = false
  error.value = ''
  nextTick(() => inputEl.value?.focus())
}
async function removeChat(item) {
  if (!window.confirm(`删除对话“${item.title}”？删除后不能恢复。`)) return
  try {
    await deleteAiChat(item.id)
    if (chat.value?.id === item.id) chat.value = null
    await loadChats()
  } catch (e) { error.value = e.message || '删除失败' }
}

function scrollToEnd() {
  nextTick(() => { if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight })
}
async function send(text = message.value) {
  const question = text.trim()
  if (!question || asking.value || !available.value) return
  asking.value = true
  pending.value = question
  message.value = ''
  error.value = ''
  scrollToEnd()
  try {
    const response = await askAiChat({ message: question, chatId: chat.value?.id || '', context: chatContext(props.label, focus.value, includeFocus.value) })
    chat.value = response.chat
    usage.value = response.usage
    loadChats()
  } catch (e) {
    error.value = e.message || '回答没有完成，请稍后再试'
    message.value = question
  } finally {
    asking.value = false
    pending.value = ''
    scrollToEnd()
  }
}
function onKey(event) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    send()
  }
}
function go(link) {
  openResearch(link.view, link.context)
  if (isPhone()) open.value = false   // 手机上窗口铺满屏幕，跳转后先收起
}

async function toggle(value = !open.value) {
  open.value = value
  if (value) {
    await Promise.all([loadStatus(), loadChats()])
    if (!chat.value && restoreId) {
      const id = restoreId
      restoreId = ''
      await openChat(id, true)
    }
    nextTick(() => inputEl.value?.focus())
    scrollToEnd()
  }
}
function onEscape(event) {
  if (event.key === 'Escape' && open.value) toggle(false)
}
function onOpenEvent() { toggle(true) }
onMounted(() => {
  window.addEventListener('keydown', onEscape)
  window.addEventListener('fq-open-chat', onOpenEvent)
  if (open.value) toggle(true)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onEscape)
  window.removeEventListener('fq-open-chat', onOpenEvent)
})
</script>

<template>
  <div v-if="!hidden">
    <!-- 悬浮按钮 -->
    <button v-if="!open && !overlays.drawer" type="button" aria-label="打开 AI 问答" title="AI 问答"
      class="fixed bottom-5 right-5 z-[55] flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-xl shadow-indigo-900/40 transition hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-300"
      @click="toggle(true)">
      <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zM21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" /></svg>
    </button>

    <!-- 对话窗口：电脑上在右下角，手机上铺满屏幕 -->
    <section v-if="open" role="dialog" aria-label="AI 问答"
      class="fixed inset-0 z-[56] flex flex-col border-white/10 bg-ink/95 shadow-2xl shadow-black/50 backdrop-blur-xl sm:inset-auto sm:bottom-5 sm:right-5 sm:h-[min(640px,calc(100vh-6rem))] sm:w-[400px] sm:rounded-2xl sm:border">
      <header class="flex items-center gap-2 border-b border-white/10 px-4 py-3">
        <h2 class="whitespace-nowrap text-sm font-semibold text-white">AI 问答</h2>
        <div class="ml-auto flex items-center gap-1">
          <button type="button" class="whitespace-nowrap rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/5 hover:text-white" @click="newChat">新对话</button>
          <button type="button" class="whitespace-nowrap rounded-lg px-2 py-1 text-xs hover:bg-white/5" :class="showHistory ? 'text-indigo-200' : 'text-slate-400 hover:text-white'"
            :aria-pressed="showHistory" @click="showHistory = !showHistory">以前的对话</button>
          <button type="button" aria-label="收起 AI 问答" class="flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-white/5 hover:text-white" @click="toggle(false)">
            <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" /></svg>
          </button>
        </div>
      </header>

      <!-- 以前的对话 -->
      <div v-if="showHistory" class="flex-1 overflow-y-auto p-3">
        <p v-if="!chats.length" class="px-1 py-6 text-center text-sm text-slate-500">还没有对话。</p>
        <ul v-else class="space-y-1">
          <li v-for="item in chats" :key="item.id" class="group flex items-center gap-2 rounded-xl px-3 py-2 hover:bg-white/5"
            :class="chat?.id === item.id ? 'bg-indigo-500/10' : ''">
            <button type="button" class="min-w-0 flex-1 text-left" @click="openChat(item.id)">
              <span class="block truncate text-sm text-slate-200">{{ item.title }}</span>
              <span class="text-xs text-slate-500">{{ item.updated_at.slice(0, 10) }} · {{ item.turns }} 轮</span>
            </button>
            <button type="button" class="shrink-0 text-xs text-slate-500 hover:text-rose-300" :aria-label="`删除对话 ${item.title}`" @click="removeChat(item)">删除</button>
          </li>
        </ul>
      </div>

      <!-- 对话 -->
      <div v-else ref="listEl" class="flex-1 space-y-4 overflow-y-auto px-4 py-4" aria-live="polite">
        <div v-if="!turns.length && !pending" class="space-y-3">
          <p class="text-sm leading-relaxed text-slate-300">可以问平台数据里的股票、财报、估值、排序，你自己的回测，以及投资概念。回答只根据平台的本地数据，不提供买卖建议。</p>
          <p class="text-xs text-slate-500">试试这些问题：</p>
          <div class="flex flex-col items-start gap-2">
            <button v-for="text in suggestions" :key="text" type="button" :disabled="!available || asking"
              class="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-left text-xs text-slate-300 transition hover:border-indigo-400/40 hover:text-white disabled:opacity-50"
              @click="send(text)">{{ text }}</button>
          </div>
        </div>
        <template v-for="(turn, i) in turns" :key="turn.at + i">
          <div class="flex justify-end"><p class="max-w-[85%] whitespace-pre-line rounded-2xl rounded-br-sm bg-indigo-500/20 px-3 py-2 text-sm text-white">{{ turn.question }}</p></div>
          <div class="space-y-2">
            <p class="whitespace-pre-line text-sm leading-relaxed text-slate-200">{{ turn.answer }}</p>
            <details v-if="turn.data?.length" class="rounded-xl border border-white/10 bg-white/[0.03]">
              <summary class="cursor-pointer px-3 py-2 text-xs text-slate-400">{{ dataSummary(turn) }}</summary>
              <div class="space-y-3 border-t border-white/10 px-3 py-3">
                <section v-for="(block, j) in turn.data" :key="j" class="space-y-1.5">
                  <p class="text-xs font-semibold text-slate-300">{{ block.title }}<span v-if="block.as_of" class="ml-1 font-normal text-slate-500">· 截至 {{ block.as_of }}</span></p>
                  <p v-if="block.error" class="text-xs text-amber-300">没有查到：{{ block.error }}</p>
                  <div v-else-if="block.columns?.length" class="overflow-x-auto">
                    <table class="w-full text-left text-[11px]">
                      <thead class="text-slate-500"><tr><th v-for="col in block.columns" :key="col" class="whitespace-nowrap py-1 pr-3 font-medium">{{ col }}</th></tr></thead>
                      <tbody class="divide-y divide-white/5 text-slate-300">
                        <tr v-for="(row, r) in block.rows" :key="r">
                          <td v-for="(cell, c) in row" :key="c" class="whitespace-nowrap py-1 pr-3">
                            <button v-if="c === codeColumn(block)" type="button" class="text-indigo-300 hover:underline" @click="go({ view: 'market-lookup', context: { symbol: cell } })">{{ cell }}</button>
                            <template v-else>{{ cell }}</template>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <p v-for="note in block.notes || []" :key="note" class="text-[11px] text-slate-500">{{ note }}</p>
                  <div v-if="blockLinks(block).length" class="flex flex-wrap gap-3">
                    <button v-for="link in blockLinks(block)" :key="link.label" type="button" class="text-xs text-indigo-300 hover:text-indigo-200" @click="go(link)">{{ link.label }} →</button>
                  </div>
                </section>
              </div>
            </details>
          </div>
        </template>
        <template v-if="pending">
          <div class="flex justify-end"><p class="max-w-[85%] whitespace-pre-line rounded-2xl rounded-br-sm bg-indigo-500/20 px-3 py-2 text-sm text-white">{{ pending }}</p></div>
          <p class="text-sm text-slate-400" role="status">正在查本地数据并整理回答…</p>
        </template>
      </div>

      <!-- 输入 -->
      <footer v-if="!showHistory" class="space-y-2 border-t border-white/10 px-4 py-3">
        <p v-if="error" class="text-xs text-rose-300" role="alert">{{ error }}</p>
        <p v-if="statusError" class="text-xs text-rose-300" role="alert">{{ statusError }} <button type="button" class="underline" @click="loadStatus">重试</button></p>
        <p v-else-if="status && !available" class="text-xs text-amber-200">平台还没有配置文本模型，暂时不能使用 AI 问答。管理员在后端的 .env 里填好 AI 密钥后就能用。</p>
        <div v-if="focusLabel && available" class="flex items-center gap-2 text-xs">
          <span :class="includeFocus ? 'text-slate-300' : 'text-slate-500 line-through'">正在看：{{ focusLabel }}</span>
          <button type="button" class="text-indigo-300 hover:text-indigo-200" @click="includeFocus = !includeFocus">{{ includeFocus ? '不带上' : '带上' }}</button>
        </div>
        <form class="flex items-end gap-2" @submit.prevent="send()">
          <label for="ai-chat-input" class="sr-only">输入问题</label>
          <textarea id="ai-chat-input" ref="inputEl" v-model="message" rows="2" maxlength="500" :disabled="!available || asking"
            placeholder="输入问题，Enter 发送，Shift+Enter 换行" @keydown="onKey"
            class="min-h-[2.75rem] flex-1 resize-none rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/40 disabled:opacity-50" />
          <button type="submit" :disabled="!available || asking || !message.trim()"
            class="rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 px-3 py-2 text-sm font-semibold text-white transition disabled:opacity-40">{{ asking ? '回答中' : '发送' }}</button>
        </form>
        <p class="text-[11px] text-slate-500">{{ usageLine ? `${usageLine} · ` : '' }}回答只根据本地数据，仅供研究参考，不构成投资建议。</p>
      </footer>
    </section>
  </div>
</template>
