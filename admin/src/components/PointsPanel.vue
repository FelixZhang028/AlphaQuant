<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { adjustUserPoints, adminPoints, createRedeemCodes, setRedeemCodeActive } from '../api.js'
import { number, time } from '../format.js'

// 积分与兑换码：最近 30 天发了多少、用了多少；生成和停用兑换码；给某个用户加或扣积分（要写原因，用户在明细里能看到）。
// 每天的免费次数、每次多少积分、新用户送多少在“系统设置”里改。
const props = defineProps({ users: { type: Array, default: () => [] } })
const emit = defineEmits(['notify', 'changed'])

const data = ref(null)
const error = ref('')
const saving = ref(false)
const codeForm = reactive({ count: 1, points: 100, valid_days: 30, max_uses: '1', expires_days: '', note: '' })
const created = ref([])
const adjust = reactive({ user_id: '', amount: '', days: 30, note: '' })

async function load() {
  error.value = ''
  try {
    data.value = await adminPoints(30)
  } catch (e) {
    error.value = e.message || '加载失败'
  }
}
onMounted(load)

const people = computed(() => props.users.filter((u) => !u.is_admin))
const given = computed(() => Object.entries(data.value?.given || {}).map(([kind, n]) => ({ kind, label: data.value.sources[kind] || kind, n })))
const used = computed(() => Object.entries(data.value?.used || {}).map(([kind, v]) => ({ kind, label: data.value.labels[kind] || kind, ...v })))
const usedTotal = computed(() => used.value.reduce((sum, item) => sum + item.points, 0))

const whole = (text, min = 1) => {
  const value = String(text).trim()
  return value === '' ? null : Number.isInteger(Number(value)) && Number(value) >= min ? Number(value) : NaN
}

async function makeCodes() {
  const payload = {
    count: whole(codeForm.count), points: whole(codeForm.points), valid_days: whole(codeForm.valid_days),
    max_uses: whole(codeForm.max_uses), expires_days: whole(codeForm.expires_days), note: codeForm.note.trim(),
  }
  if ([payload.count, payload.points, payload.valid_days].some((v) => !v) || Number.isNaN(payload.max_uses) || Number.isNaN(payload.expires_days)) {
    emit('notify', '个数、积分、有效天数要填正整数；每码可用账户和兑换期限留空表示不限')
    return
  }
  saving.value = true
  try {
    const result = await createRedeemCodes(payload)
    created.value = result.created
    data.value = result
    emit('notify', `已生成 ${result.created.length} 个兑换码`)
  } catch (e) {
    emit('notify', e.message || '生成失败')
  } finally {
    saving.value = false
  }
}

async function toggle(code) {
  if (code.active && !window.confirm(`停用兑换码 ${code.code}？停用后不能再兑换，已经兑换的积分不受影响。`)) return
  try {
    data.value = { ...data.value, ...(await setRedeemCodeActive(code.code, !code.active)) }
  } catch (e) {
    emit('notify', e.message || '操作失败')
  }
}

async function copy(text, what = text) {
  try {
    await navigator.clipboard.writeText(text)
    emit('notify', `已复制 ${what}`)
  } catch {
    emit('notify', '复制失败，请手动选中复制')
  }
}

async function adjustPoints() {
  const amount = Number(String(adjust.amount).trim())
  const person = people.value.find((u) => u.id === Number(adjust.user_id))
  if (!person) return emit('notify', '请选择用户')
  if (!Number.isInteger(amount) || amount === 0) return emit('notify', '积分要填非 0 的整数：正数加，负数扣')
  if (!adjust.note.trim()) return emit('notify', '请写原因，用户在积分明细里能看到')
  const word = amount > 0 ? `加 ${amount} 积分（${adjust.days} 天有效）` : `扣 ${-amount} 积分`
  if (!window.confirm(`给「${person.name}」（${person.email}）${word}？原因：${adjust.note.trim()}`)) return
  saving.value = true
  try {
    const result = await adjustUserPoints(person.id, { amount, days: Number(adjust.days) || 30, note: adjust.note.trim() })
    emit('notify', `${person.name} 现在有 ${result.points} 积分`)
    Object.assign(adjust, { amount: '', note: '' })
    emit('changed')
    await load()
  } catch (e) {
    emit('notify', e.message || '操作失败')
  } finally {
    saving.value = false
  }
}

function codeState(code) {
  if (!code.active) return { text: '已停用', tone: 'text-rose-300' }
  if (code.expired) return { text: '已过期', tone: 'text-slate-500' }
  if (code.max_uses != null && code.used >= code.max_uses) return { text: '已用完', tone: 'text-amber-300' }
  return { text: '可用', tone: 'text-emerald-300' }
}

const inputClass = 'w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-indigo-400/40'
const tableClass = '[&_td]:whitespace-nowrap [&_th]:whitespace-nowrap [&_td]:px-3 [&_th]:px-3 [&_td:first-child]:pl-0 [&_th:first-child]:pl-0 [&_td:last-child]:pr-0 [&_th:last-child]:pr-0 w-full text-left text-sm'
</script>

<template>
  <div class="space-y-6">
    <p v-if="error" role="alert" class="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{{ error }}</p>

    <section v-if="data" class="grid gap-5 sm:grid-cols-3" aria-label="积分概况">
      <div class="glass glass-sheen rounded-2xl p-5">
        <p class="text-xs text-slate-400">用户手里还有效的积分</p>
        <p class="mt-2 text-3xl font-bold text-white">{{ number(data.outstanding) }}</p>
        <p class="mt-2 text-xs text-slate-500">所有用户加起来，不含已过期的</p>
      </div>
      <div class="glass rounded-2xl p-5">
        <p class="text-xs text-slate-400">最近 30 天发出的积分</p>
        <ul v-if="given.length" class="mt-3 space-y-1.5 text-sm">
          <li v-for="g in given" :key="g.kind" class="flex justify-between text-slate-300"><span>{{ g.label }}</span><span class="text-white">{{ number(g.n) }}</span></li>
        </ul>
        <p v-else class="mt-3 text-sm text-slate-500">还没有发过积分。</p>
      </div>
      <div class="glass rounded-2xl p-5">
        <p class="text-xs text-slate-400">最近 30 天用掉的积分 <span class="text-white">{{ number(usedTotal) }}</span></p>
        <ul v-if="used.length" class="mt-3 space-y-1.5 text-sm">
          <li v-for="u in used" :key="u.kind" class="flex justify-between text-slate-300"><span>{{ u.label }} <span class="text-xs text-slate-500">{{ u.times }} 次</span></span><span class="text-white">{{ number(u.points) }}</span></li>
        </ul>
        <p v-else class="mt-3 text-sm text-slate-500">还没有人用积分。</p>
      </div>
    </section>

    <section class="glass rounded-2xl p-5" aria-label="生成兑换码">
      <h2 class="text-sm font-semibold text-white">生成兑换码</h2>
      <form class="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-[6rem_7rem_8rem_9rem_9rem_1fr_auto] lg:items-end" @submit.prevent="makeCodes">
        <label class="text-xs text-slate-400">个数<input v-model="codeForm.count" inputmode="numeric" :class="inputClass" class="mt-1" /></label>
        <label class="text-xs text-slate-400">每个多少积分<input v-model="codeForm.points" inputmode="numeric" :class="inputClass" class="mt-1" /></label>
        <label class="text-xs text-slate-400">兑换后有效天数<input v-model="codeForm.valid_days" inputmode="numeric" :class="inputClass" class="mt-1" /></label>
        <label class="text-xs text-slate-400">每码几个账户能用<input v-model="codeForm.max_uses" inputmode="numeric" placeholder="留空不限" :class="inputClass" class="mt-1" /></label>
        <label class="text-xs text-slate-400">多少天内可以兑换<input v-model="codeForm.expires_days" inputmode="numeric" placeholder="留空不限" :class="inputClass" class="mt-1" /></label>
        <label class="text-xs text-slate-400">备注<input v-model="codeForm.note" maxlength="60" placeholder="例如 发给第一批试用的朋友" :class="inputClass" class="mt-1" /></label>
        <button type="submit" :disabled="saving" class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white disabled:opacity-50">生成</button>
      </form>
      <div v-if="created.length" class="mt-4 rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-4">
        <div class="flex flex-wrap items-center gap-3">
          <p class="text-sm text-emerald-300">新生成的 {{ created.length }} 个兑换码</p>
          <button type="button" class="rounded-full border border-emerald-400/30 px-3 py-0.5 text-xs text-emerald-300 hover:bg-emerald-400/10" @click="copy(created.join('\n'), `${created.length} 个兑换码`)">全部复制</button>
        </div>
        <p class="mt-2 break-all font-mono text-xs leading-6 text-slate-200">{{ created.join('　') }}</p>
      </div>
      <p class="mt-2 text-xs text-slate-500">兑换码不区分大小写。一个账户同一个码只能兑换一次；“每码几个账户能用”填 1 就是一人一码。</p>
    </section>

    <section class="glass rounded-2xl p-5" aria-label="给用户加或扣积分">
      <h2 class="text-sm font-semibold text-white">给用户加或扣积分</h2>
      <form class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1.4fr_7rem_7rem_1fr_auto] lg:items-end" @submit.prevent="adjustPoints">
        <label class="text-xs text-slate-400">用户
          <select v-model="adjust.user_id" :class="inputClass" class="mt-1">
            <option value="" class="bg-ink">选择用户</option>
            <option v-for="u in people" :key="u.id" :value="u.id" class="bg-ink">{{ u.name }}（{{ u.email }}）· {{ u.points ?? 0 }} 积分</option>
          </select>
        </label>
        <label class="text-xs text-slate-400">积分（负数是扣）<input v-model="adjust.amount" inputmode="numeric" placeholder="例如 50" :class="inputClass" class="mt-1" /></label>
        <label class="text-xs text-slate-400">有效天数<input v-model="adjust.days" inputmode="numeric" :class="inputClass" class="mt-1" /></label>
        <label class="text-xs text-slate-400">原因（用户能看到）<input v-model="adjust.note" maxlength="60" placeholder="例如 反馈问题的感谢" :class="inputClass" class="mt-1" /></label>
        <button type="submit" :disabled="saving" class="rounded-full border border-indigo-400/40 bg-indigo-500/10 px-5 py-2 text-sm text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50">确定</button>
      </form>
      <p class="mt-2 text-xs text-slate-500">扣积分时从快到期的开始扣，最多扣到 0。每一次都记在“操作记录”里。有积分以前注册的账户，下次打开功能台时才补上注册赠送，在那之前显示 0。</p>
    </section>

    <section v-if="data" class="glass rounded-2xl p-5" aria-label="兑换码列表">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-white">全部兑换码</h2>
        <span class="text-xs text-slate-500">共 {{ data.codes.length }} 个</span>
      </div>
      <div class="mt-4 overflow-x-auto">
        <table :class="tableClass" class="min-w-[820px]">
          <thead>
            <tr class="text-xs text-slate-500">
              <th class="pb-3 font-medium">兑换码</th>
              <th class="pb-3 text-right font-medium">积分</th>
              <th class="pb-3 text-right font-medium">有效天数</th>
              <th class="pb-3 text-right font-medium">已用 / 可用</th>
              <th class="pb-3 font-medium">兑换期限</th>
              <th class="pb-3 font-medium">备注</th>
              <th class="pb-3 font-medium">状态</th>
              <th class="pb-3 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/5">
            <tr v-for="c in data.codes" :key="c.code" class="text-slate-300" :class="{ 'opacity-50': !c.active || c.expired }">
              <td class="py-3 font-mono text-xs text-indigo-300">{{ c.code }}</td>
              <td class="py-3 text-right text-white">{{ number(c.points) }}</td>
              <td class="py-3 text-right text-slate-400">{{ c.valid_days }} 天</td>
              <td class="py-3 text-right">{{ c.used }} / {{ c.max_uses ?? '不限' }}</td>
              <td class="py-3 text-slate-400">{{ c.expires_at ? time(c.expires_at) : '不限' }}</td>
              <td class="py-3 text-slate-400">{{ c.note || '—' }}</td>
              <td class="py-3" :class="codeState(c).tone">{{ codeState(c).text }}</td>
              <td class="py-3 text-right">
                <div class="flex justify-end gap-2">
                  <button type="button" class="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300 hover:text-white" @click="copy(c.code)">复制</button>
                  <button type="button" class="rounded-full border px-3 py-1 text-xs"
                    :class="c.active ? 'border-rose-400/30 text-rose-300 hover:bg-rose-400/10' : 'border-emerald-400/30 text-emerald-300 hover:bg-emerald-400/10'"
                    @click="toggle(c)">{{ c.active ? '停用' : '恢复' }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!data.codes.length" class="py-6 text-center text-sm text-slate-500">还没有兑换码。</p>
      </div>
    </section>

    <section v-if="data" class="glass rounded-2xl p-5" aria-label="最近的积分记录">
      <h2 class="text-sm font-semibold text-white">最近的积分记录</h2>
      <div class="mt-4 overflow-x-auto">
        <table :class="tableClass" class="min-w-[640px]">
          <thead>
            <tr class="text-xs text-slate-500">
              <th class="pb-3 font-medium">时间</th>
              <th class="pb-3 font-medium">用户</th>
              <th class="pb-3 font-medium">类型</th>
              <th class="pb-3 font-medium">说明</th>
              <th class="pb-3 text-right font-medium">积分</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/5">
            <tr v-for="r in data.recent" :key="r.id" class="text-slate-300">
              <td class="py-2.5 text-slate-400">{{ time(r.created_at) }}</td>
              <td class="py-2.5">{{ r.email }}</td>
              <td class="py-2.5">{{ r.label }}</td>
              <td class="py-2.5 text-slate-400">{{ r.kind === 'spend' ? data.labels[r.feature] || r.feature : r.note || '—' }}</td>
              <td class="py-2.5 text-right font-medium" :class="r.delta > 0 ? 'text-indigo-200' : 'text-slate-300'">{{ r.delta > 0 ? `+${r.delta}` : r.delta }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!data.recent.length" class="py-6 text-center text-sm text-slate-500">还没有记录。</p>
      </div>
    </section>
  </div>
</template>
