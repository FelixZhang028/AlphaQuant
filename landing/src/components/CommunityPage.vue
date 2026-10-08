<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import NavBar from './NavBar.vue'
import FooterBar from './FooterBar.vue'
import DynamicBackground from './DynamicBackground.vue'
import { getLocalUser } from '../api.js'

// ------------------------------------------------------------------
// 社区论坛（一期：本地体验版）
// 帖子与回复保存在浏览器 localStorage，后续接入后端 API 后无缝升级。
// ------------------------------------------------------------------

const STORAGE_KEY = 'zt_community_posts'

const CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: 'share', label: '策略分享' },
  { key: 'factor', label: '因子研究' },
  { key: 'data', label: '数据处理' },
  { key: 'qa', label: '新手求助' },
  { key: 'notice', label: '平台公告' },
]

const SEED_POSTS = [
  {
    id: 1,
    title: '欢迎使用智投引擎社区',
    category: 'notice',
    author: '官方团队',
    time: '2026-09-01 10:00',
    likes: 128,
    content: '欢迎来到智投引擎社区！这里可以交流量化策略、因子研究心得与数据处理经验。\n\n新手建议先完成工作台内的新手引导（顶栏 ? 图标），再尝试零代码策略模板。',
    replies: [
      { author: '量化小白', time: '2026-09-01 11:20', content: '引导很清晰，跑通了第一个动量模板回测！' },
    ],
  },
  {
    id: 2,
    title: '分享一个低波动 + 动量的组合思路',
    category: 'share',
    author: 'Alpha猎人',
    time: '2026-09-03 21:40',
    likes: 86,
    content: '在因子实验室用「训练/测试集」流程验证了低波动与 20 日动量的等权组合：训练期确定权重后，测试期 Rank IC 比单因子更稳。\n\n大家还可以试试先在相关性矩阵里剔除高相关成分，再合成。',
    replies: [
      { author: '均值回归派', time: '2026-09-04 09:12', content: '试了，IC 确实稳一些，不过换手率要注意。' },
      { author: '数据矿工', time: '2026-09-04 15:33', content: '补充：训练期和测试期之间记得留出 horizon 天的收益窗口，避免未来函数。' },
    ],
  },
  {
    id: 3,
    title: '本地数据下载失败（网络超时）怎么办？',
    category: 'qa',
    author: '量化小白',
    time: '2026-09-05 14:05',
    likes: 12,
    content: '数据管理里点更新，报网络超时。有人遇到过吗？',
    replies: [
      { author: '官方团队', time: '2026-09-05 14:30', content: '数据源支持 AkShare / BaoStock 自动回退，偶发超时重试即可；也可缩小日期区间分批下载。' },
    ],
  },
]

const posts = ref([])
const activeCategory = ref('all')
const detailId = ref(null)
const showCompose = ref(false)
const compose = reactive({ title: '', category: 'share', content: '' })
const replyDraft = reactive({})

const detail = computed(() => posts.value.find((p) => p.id === detailId.value) || null)
const filtered = computed(() =>
  activeCategory.value === 'all' ? posts.value : posts.value.filter((p) => p.category === activeCategory.value)
)

function categoryLabel(key) {
  return CATEGORIES.find((c) => c.key === key)?.label || key
}

function loadPosts() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      posts.value = JSON.parse(raw)
      return
    }
  } catch {
    /* 忽略损坏数据 */
  }
  posts.value = SEED_POSTS.map((p) => ({ ...p, replies: [...p.replies] }))
  savePosts()
}

function savePosts() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(posts.value))
}

function nowStamp() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function submitPost() {
  if (!compose.title.trim() || !compose.content.trim()) return
  const user = getLocalUser()
  posts.value.unshift({
    id: Date.now(),
    title: compose.title.trim(),
    category: compose.category,
    author: user?.name || '游客',
    time: nowStamp(),
    likes: 0,
    content: compose.content.trim(),
    replies: [],
  })
  savePosts()
  compose.title = ''
  compose.content = ''
  compose.category = 'share'
  showCompose.value = false
}

function toggleLike(post) {
  post.likes += 1
  savePosts()
}

function submitReply(post) {
  const text = (replyDraft[post.id] || '').trim()
  if (!text) return
  const user = getLocalUser()
  post.replies.push({ author: user?.name || '游客', time: nowStamp(), content: text })
  replyDraft[post.id] = ''
  savePosts()
}

onMounted(loadPosts)
</script>

<template>
  <div class="min-h-screen text-slate-200">
    <DynamicBackground />
    <NavBar />

    <main class="mx-auto max-w-5xl px-5 pb-20 pt-28 lg:px-8">
      <!-- 标题区 -->
      <div class="glass glass-sheen relative overflow-hidden rounded-2xl p-8">
        <div class="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-indigo-500/20 blur-3xl" />
        <h1 class="text-2xl font-bold text-white sm:text-3xl">社区论坛</h1>
        <p class="mt-2 max-w-xl text-sm leading-relaxed text-slate-400">
          与量化同行交流策略思路、因子研究与数据处理经验。
          <span class="text-slate-500">（一期为本地体验版：帖子保存在本浏览器，账号体系与精华帖功能陆续开放）</span>
        </p>
        <button
          class="mt-5 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5"
          @click="showCompose = !showCompose"
        >{{ showCompose ? '收起' : '发布新帖' }}</button>
      </div>

      <!-- 发帖框 -->
      <div v-if="showCompose" class="glass mt-6 rounded-2xl p-6">
        <h2 class="text-sm font-semibold text-white">发布新帖</h2>
        <div class="mt-4 grid gap-4 sm:grid-cols-[1fr_10rem]">
          <input
            v-model="compose.title"
            placeholder="帖子标题"
            class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
          />
          <select
            v-model="compose.category"
            class="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
          >
            <option v-for="c in CATEGORIES.slice(1)" :key="c.key" :value="c.key">{{ c.label }}</option>
          </select>
        </div>
        <textarea
          v-model="compose.content"
          rows="5"
          placeholder="分享你的策略思路、研究心得或遇到的问题…"
          class="mt-4 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
        />
        <div class="mt-4 flex justify-end">
          <button
            class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-50"
            :disabled="!compose.title.trim() || !compose.content.trim()"
            @click="submitPost"
          >发布</button>
        </div>
      </div>

      <!-- 帖子详情 -->
      <template v-if="detail">
        <div class="glass mt-6 rounded-2xl p-6">
          <button class="mb-4 text-xs text-slate-400 transition hover:text-white" @click="detailId = null">← 返回列表</button>
          <div class="flex flex-wrap items-center gap-3">
            <span class="rounded-full border border-indigo-400/30 bg-indigo-500/10 px-2.5 py-0.5 text-xs text-indigo-200">{{ categoryLabel(detail.category) }}</span>
            <h2 class="text-lg font-bold text-white">{{ detail.title }}</h2>
          </div>
          <p class="mt-2 text-xs text-slate-500">{{ detail.author }} · {{ detail.time }} · {{ detail.likes }} 赞</p>
          <p class="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{{ detail.content }}</p>
          <button
            class="mt-4 rounded-full border border-white/10 px-4 py-1.5 text-xs text-slate-300 transition hover:border-indigo-400/40 hover:text-white"
            @click="toggleLike(detail)"
          >👍 有用 ({{ detail.likes }})</button>
        </div>

        <!-- 回复 -->
        <div class="glass mt-4 rounded-2xl p-6">
          <h3 class="text-sm font-semibold text-white">回复（{{ detail.replies.length }}）</h3>
          <ul class="mt-4 space-y-4">
            <li v-for="(r, i) in detail.replies" :key="i" class="rounded-xl border border-white/5 bg-white/5 p-4">
              <p class="text-xs text-slate-500">{{ r.author }} · {{ r.time }}</p>
              <p class="mt-1.5 whitespace-pre-wrap text-sm text-slate-300">{{ r.content }}</p>
            </li>
          </ul>
          <div class="mt-5 flex gap-3">
            <input
              v-model="replyDraft[detail.id]"
              placeholder="写下你的回复…"
              class="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40"
              @keyup.enter="submitReply(detail)"
            />
            <button
              class="rounded-full border border-white/10 px-5 py-2 text-sm text-slate-300 transition hover:bg-white/5"
              @click="submitReply(detail)"
            >回复</button>
          </div>
        </div>
      </template>

      <!-- 帖子列表 -->
      <template v-else>
        <div class="mt-8 flex flex-wrap gap-2">
          <button
            v-for="c in CATEGORIES"
            :key="c.key"
            class="rounded-full px-4 py-1.5 text-xs transition"
            :class="activeCategory === c.key ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white' : 'border border-white/10 text-slate-400 hover:text-slate-200'"
            @click="activeCategory = c.key"
          >{{ c.label }}</button>
        </div>

        <div class="mt-5 space-y-4">
          <button
            v-for="p in filtered"
            :key="p.id"
            class="glass block w-full rounded-2xl p-5 text-left transition hover:border-indigo-400/30"
            @click="detailId = p.id"
          >
            <div class="flex flex-wrap items-center gap-3">
              <span class="rounded-full border border-indigo-400/30 bg-indigo-500/10 px-2.5 py-0.5 text-xs text-indigo-200">{{ categoryLabel(p.category) }}</span>
              <h3 class="text-sm font-semibold text-white">{{ p.title }}</h3>
            </div>
            <p class="mt-2 line-clamp-2 text-sm text-slate-400">{{ p.content }}</p>
            <p class="mt-3 flex items-center gap-4 text-xs text-slate-500">
              <span>{{ p.author }}</span>
              <span>{{ p.time }}</span>
              <span>💬 {{ p.replies.length }}</span>
              <span>👍 {{ p.likes }}</span>
            </p>
          </button>
          <p v-if="!filtered.length" class="glass rounded-2xl p-10 text-center text-sm text-slate-500">该分类下暂无帖子，来发第一帖吧。</p>
        </div>
      </template>
    </main>

    <FooterBar />
  </div>
</template>
