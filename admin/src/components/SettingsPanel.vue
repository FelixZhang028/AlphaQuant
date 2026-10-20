<script setup>
// 系统设置：AI 模型、AI 次数、数据更新、邮件服务，保存后立刻生效，不用重启后端。
// 密钥加密保存，页面上只显示前后几位；保存要再输一次管理员密码。没在这里设置的项用 .env 里的值。
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { adminSettings, saveAdminSettings, saveWeknoraSettings, testAdminSettings, weknoraSettings } from '../api.js'
import { PROVIDERS, initialForm, pendingChanges, providerOf, secretPlaceholder, sourceText } from '../settings.js'

const emit = defineEmits(['notify'])
const groups = ref([])
const form = reactive({})
const clear = ref([])
const error = ref('')
const loading = ref(true)
const provider = ref('openrouter')
const tests = reactive({})            // target -> { busy, ok, message }
const asking = ref(false)             // 输入管理员密码的对话框
const password = ref('')
const saving = ref(false)
const saveError = ref('')
const passwordEl = ref(null)
const weknora = reactive({ base_url: '', api_key: '', api_key_configured: false, saving: false })

const changes = computed(() => pendingChanges(groups.value, form, clear.value))
const providerNote = computed(() => PROVIDERS.find((p) => p.key === provider.value)?.note || '')

function reset(body) {
  groups.value = body.groups
  for (const key of Object.keys(form)) delete form[key]
  Object.assign(form, initialForm(body.groups))
  clear.value = []
  provider.value = providerOf(form.FELLOWQUANT_AI_BASE_URL)
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    reset(await adminSettings())
    const kb = await weknoraSettings().catch(() => null)
    if (kb) Object.assign(weknora, { base_url: kb.base_url || '', api_key: '', api_key_configured: Boolean(kb.api_key_configured) })
  } catch (e) { error.value = e.message || '设置加载失败' }
  finally { loading.value = false }
}
onMounted(load)

function chooseProvider(key) {
  provider.value = key
  const preset = PROVIDERS.find((p) => p.key === key)
  if (!preset || preset.base === null) return
  form.FELLOWQUANT_AI_BASE_URL = preset.base
  form.FELLOWQUANT_AI_MODEL = preset.model
  // OpenRouter 用默认地址：已经在后台设置过地址的，改回用 .env（默认就是 OpenRouter）。
  const base = groups.value.flatMap((g) => g.items).find((i) => i.name === 'FELLOWQUANT_AI_BASE_URL')
  if (key === 'openrouter' && base?.source === 'admin') toggleClear(base, true)
}
function toggleClear(item, on = !clear.value.includes(item.name)) {
  clear.value = on ? [...new Set([...clear.value, item.name])] : clear.value.filter((name) => name !== item.name)
  if (on && item.kind !== 'secret') form[item.name] = ''
  if (!on) form[item.name] = item.kind === 'secret' ? '' : String(item.value ?? '')
}

async function runTest(target) {
  tests[target] = { busy: true }
  try {
    const result = await testAdminSettings(target, changes.value.values)
    tests[target] = result.ok
      ? { ok: true, message: target === 'email' ? `已发到 ${result.to}，请查收（用时 ${result.seconds} 秒）` : `连接成功 · 用时 ${result.seconds} 秒 · 模型 ${result.model}` }
      : { ok: false, message: `${result.message}（用时 ${result.seconds} 秒）` }
  } catch (e) { tests[target] = { ok: false, message: e.message || '测试失败' } }
}

async function askPassword() {
  if (!changes.value.count) return
  saveError.value = ''
  password.value = ''
  asking.value = true
  await nextTick()
  passwordEl.value?.focus()
}
async function save() {
  if (!password.value || saving.value) return
  saving.value = true
  saveError.value = ''
  try {
    const body = await saveAdminSettings({ password: password.value, values: changes.value.values, clear: changes.value.clear })
    reset(body)
    asking.value = false
    emit('notify', `已保存 ${body.changed.length} 项设置，立刻生效`)
  } catch (e) { saveError.value = e.message || '保存失败' }
  finally { saving.value = false; password.value = '' }
}

async function saveWeknora() {
  weknora.saving = true
  try {
    const body = await saveWeknoraSettings({ base_url: weknora.base_url, api_key: weknora.api_key })
    weknora.api_key_configured = weknora.api_key_configured || Boolean(weknora.api_key)
    weknora.api_key = ''
    emit('notify', body.message || '知识库配置已保存')
  } catch (e) { emit('notify', e.message || '保存失败') }
  finally { weknora.saving = false }
}

const input = 'w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-indigo-400/40 disabled:opacity-50'
const primary = 'rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50'
const secondary = 'rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-slate-300 hover:text-white disabled:opacity-50'
const sourceTone = (item) => (item.unreadable ? 'border-rose-400/40 text-rose-200' : item.source === 'admin' ? 'border-indigo-400/40 text-indigo-200' : 'border-white/10 text-slate-400')
</script>

<template>
  <div class="space-y-6 pb-20">
    <section class="glass rounded-2xl p-5 text-sm text-slate-300">
      <h2 class="text-sm font-semibold text-white">系统设置</h2>
      <p class="mt-2 leading-relaxed">在这里改的设置<b class="text-white">保存后立刻生效，不用重启后端</b>。密钥和邮箱密码加密后保存，页面上只显示前后几位，保存时要再输一次管理员密码。没在这里设置的项，照常用后端 <code class="text-indigo-300">.env</code> 里的值；点“改回用 .env”就不再用后台的设置。</p>
      <p class="mt-1 text-xs text-slate-500">APP_SECRET、首个管理员账户、数据目录这类启动前就要确定的设置仍然只能在 .env 里改。换了 APP_SECRET 以后，这里保存的密钥会解不开，需要重新填写。</p>
    </section>

    <p v-if="error" role="alert" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{{ error }} <button type="button" class="underline" @click="load">重试</button></p>
    <p v-else-if="loading" class="text-sm text-slate-400" role="status">正在读取设置…</p>

    <section v-for="group in groups" :key="group.key" class="glass rounded-2xl p-5" :aria-label="group.label">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">{{ group.label }}</h2>
        <div v-if="group.key === 'ai'" class="ml-auto flex flex-wrap gap-2">
          <button type="button" :class="secondary" :disabled="tests.text?.busy" @click="runTest('text')">{{ tests.text?.busy ? '测试中…' : '测试文本模型' }}</button>
          <button type="button" :class="secondary" :disabled="tests.decision?.busy" @click="runTest('decision')">{{ tests.decision?.busy ? '测试中…' : '测试 Jev' }}</button>
        </div>
        <button v-if="group.key === 'mail'" type="button" class="ml-auto" :class="secondary" :disabled="tests.email?.busy" @click="runTest('email')">{{ tests.email?.busy ? '发送中…' : '发一封测试邮件给我' }}</button>
      </div>
      <div v-if="group.key === 'ai'" class="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-3">
        <p class="text-xs text-slate-400">文本模型的服务商</p>
        <div class="mt-2 flex flex-wrap gap-2" role="group" aria-label="文本模型的服务商">
          <button v-for="p in PROVIDERS" :key="p.key" type="button" :aria-pressed="provider === p.key"
            class="rounded-full border px-3 py-1 text-xs transition"
            :class="provider === p.key ? 'border-indigo-400/50 bg-indigo-500/15 text-white' : 'border-white/10 text-slate-400 hover:text-slate-200'"
            @click="chooseProvider(p.key)">{{ p.label }}</button>
        </div>
        <p class="mt-2 text-xs text-slate-500">{{ providerNote }} 选好以后还要点下面的“保存修改”。可以先点“测试文本模型”，测试用的是页面上现在的值，不会保存。</p>
      </div>
      <p v-for="target in group.key === 'ai' ? ['text', 'decision'] : group.key === 'mail' ? ['email'] : []" v-show="tests[target]?.message" :key="target"
        class="mt-3 text-xs" :class="tests[target]?.ok ? 'text-emerald-300' : 'text-rose-300'" role="status">{{ tests[target]?.message }}</p>

      <div class="mt-4 grid gap-x-6 gap-y-4 md:grid-cols-2">
        <div v-for="item in group.items" :key="item.name" class="space-y-1.5">
          <div class="flex flex-wrap items-center gap-2">
            <label :for="`setting-${item.name}`" class="text-xs text-slate-300">{{ item.label }}</label>
            <span class="rounded-full border px-2 py-0.5 text-[10px]" :class="sourceTone(item)">{{ clear.includes(item.name) ? '保存后改回用 .env' : sourceText(item) }}</span>
            <button v-if="item.source === 'admin'" type="button" class="ml-auto text-[11px] text-indigo-300 hover:text-indigo-200" @click="toggleClear(item)">
              {{ clear.includes(item.name) ? '不改回了' : item.env_set ? '改回用 .env' : '清除后台设置' }}</button>
          </div>
          <select v-if="item.kind === 'switch'" :id="`setting-${item.name}`" v-model="form[item.name]" :class="input" :disabled="clear.includes(item.name)">
            <option value="" disabled>{{ item.default === 'on' ? '默认：开' : '默认：关' }}</option>
            <option value="on">开</option>
            <option value="off">关</option>
          </select>
          <input v-else :id="`setting-${item.name}`" v-model="form[item.name]" :class="input" :disabled="clear.includes(item.name)"
            :type="item.kind === 'secret' ? 'password' : item.kind === 'time' ? 'time' : ['int', 'number'].includes(item.kind) ? 'number' : item.kind === 'email' ? 'email' : 'text'"
            :step="item.kind === 'number' ? '0.05' : undefined" :min="item.minimum ?? undefined" :max="item.maximum ?? undefined"
            :autocomplete="item.kind === 'secret' ? 'new-password' : 'off'" spellcheck="false"
            :placeholder="item.kind === 'secret' ? secretPlaceholder(item) : item.default ? `默认：${item.default}` : '没有设置'" />
          <p v-if="item.unreadable" class="text-[11px] text-rose-300">这一项是用另一个 APP_SECRET 加密的，现在解不开，程序用的是 .env 里的值。请重新填写并保存。</p>
          <p v-if="item.help" class="text-[11px] leading-relaxed text-slate-500">{{ item.help }}</p>
        </div>
      </div>
    </section>

    <!-- 知识库：沿用原来的配置接口 -->
    <section class="glass rounded-2xl p-5" aria-label="知识库 WeKnora">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-sm font-semibold text-white">知识库 WeKnora（可选）</h2>
        <button type="button" class="ml-auto" :class="primary" :disabled="weknora.saving || !weknora.base_url" @click="saveWeknora">{{ weknora.saving ? '保存中…' : '保存知识库配置' }}</button>
      </div>
      <div class="mt-4 grid gap-4 md:grid-cols-2">
        <div class="space-y-1.5"><label for="kb-url" class="text-xs text-slate-300">服务地址</label><input id="kb-url" v-model="weknora.base_url" :class="input" placeholder="https://…" spellcheck="false" /></div>
        <div class="space-y-1.5"><label for="kb-key" class="text-xs text-slate-300">密钥</label>
          <input id="kb-key" v-model="weknora.api_key" type="password" autocomplete="new-password" :class="input" :placeholder="weknora.api_key_configured ? '已设置，留空表示不修改' : '还没有设置'" /></div>
      </div>
      <p class="mt-2 text-[11px] text-slate-500">功能台的“投研知识库”用这个服务。单独保存，立刻生效。</p>
    </section>

    <!-- 保存栏 -->
    <div v-if="changes.count" class="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-ink/95 px-5 py-3 backdrop-blur">
      <div class="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
        <p class="text-sm text-slate-300">有 {{ changes.count }} 项修改还没有保存。</p>
        <button type="button" class="ml-auto" :class="secondary" @click="load">放弃修改</button>
        <button type="button" :class="primary" @click="askPassword">保存修改</button>
      </div>
    </div>

    <!-- 再输一次管理员密码 -->
    <div v-if="asking" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" @click.self="asking = false">
      <form class="glass w-full max-w-sm rounded-2xl p-5" role="dialog" aria-label="确认管理员密码" @submit.prevent="save">
        <h2 class="text-sm font-semibold text-white">确认管理员密码</h2>
        <p class="mt-2 text-xs text-slate-400">保存 {{ changes.count }} 项设置。为了防止别人趁你离开时改掉密钥，请再输一次管理员密码。</p>
        <input ref="passwordEl" v-model="password" type="password" autocomplete="current-password" class="mt-4" :class="input" placeholder="管理员密码" />
        <p v-if="saveError" class="mt-2 text-xs text-rose-300" role="alert">{{ saveError }}</p>
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" :class="secondary" @click="asking = false">取消</button>
          <button type="submit" :class="primary" :disabled="!password || saving">{{ saving ? '保存中…' : '确认保存' }}</button>
        </div>
      </form>
    </div>
  </div>
</template>
