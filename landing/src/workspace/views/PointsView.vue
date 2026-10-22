<script setup>
// 积分：余额、每日打卡、每一批的到期时间、兑换码、每种 AI 功能的免费次数和价格、明细。
// 充值以后再开；现在积分来自注册赠送、兑换码和管理员发放。
import { computed, onActivated, ref } from 'vue'
import { checkIn, getPoints, redeemPoints } from '../../api.js'
import { checkinText, chinaTime, cleanCode, codeProblem, expiresSoon, expiryText, ledgerText, priceText, signed } from '../points.js'
import SectionCard from '../ui/SectionCard.vue'

const props = defineProps({ user: { type: Object, default: null }, notify: { type: Function, default: () => {} } })

const data = ref(null)
const loadError = ref('')
const code = ref('')
const redeeming = ref(false)
const redeemError = ref('')

// 告诉顶栏：余额和今天打没打卡。
function announce(summary) {
  window.dispatchEvent(new CustomEvent('fq-points-changed', { detail: { balance: summary.balance, checkin: summary.checkin } }))
}

async function load() {
  loadError.value = ''
  try {
    data.value = await getPoints()
    announce(data.value)
  } catch (e) {
    loadError.value = e.message || '积分加载失败'
  }
}
onActivated(load)

async function redeem() {
  redeemError.value = codeProblem(code.value)
  if (redeemError.value) return
  redeeming.value = true
  try {
    const result = await redeemPoints(cleanCode(code.value))
    data.value = result.summary
    announce(result.summary)
    code.value = ''
    props.notify(`兑换成功：${result.points} 积分，${result.valid_days} 天内有效`)
  } catch (e) {
    redeemError.value = e.message || '兑换失败'
  } finally {
    redeeming.value = false
  }
}

const checking = ref(false)
async function doCheckin() {
  checking.value = true
  try {
    const result = await checkIn()
    data.value = result.summary
    announce(result.summary)
    props.notify(`打卡成功：+${result.points} 积分，${result.days} 天内有效`)
  } catch (e) {
    props.notify(e.message || '打卡失败')
    load()
  } finally {
    checking.value = false
  }
}

const soonest = computed(() => data.value?.lots?.[0] || null)
const inputClass = 'w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-indigo-400/50'
</script>

<template>
  <div class="space-y-6">
    <p v-if="loadError" role="alert" class="rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{{ loadError }}</p>

    <section class="glass glass-sheen relative overflow-hidden rounded-2xl p-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
      <p class="text-xs text-slate-400">我的积分</p>
      <template v-if="data">
        <p v-if="data.unlimited" class="mt-2 text-2xl font-semibold text-white">管理员不扣积分</p>
        <template v-else>
          <p class="mt-1 text-4xl font-bold tabular-nums text-white">{{ data.balance }}</p>
          <p v-if="soonest" class="mt-2 text-sm" :class="expiresSoon(soonest.expires_at) ? 'text-amber-300' : 'text-slate-400'">
            最早一批 {{ soonest.remaining }} 积分 · {{ expiryText(soonest.expires_at) }}
          </p>
          <p v-else class="mt-2 text-sm text-slate-400">现在没有积分；每天的免费次数照常可用。</p>
        </template>
      </template>
      <p v-else-if="!loadError" class="mt-2 text-sm text-slate-500">加载中…</p>
      </div>
      <div v-if="data && !data.unlimited && data.checkin?.enabled" class="flex flex-col items-start gap-1.5 sm:items-end">
        <button type="button" :disabled="checking || data.checkin.done_today"
          class="rounded-full px-5 py-2 text-sm font-semibold transition disabled:cursor-default"
          :class="data.checkin.done_today ? 'border border-white/10 bg-white/5 text-slate-400' : 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white hover:brightness-110'"
          @click="doCheckin">{{ data.checkin.done_today ? '今天已打卡' : checking ? '打卡中…' : `每日打卡 +${data.checkin.points}` }}</button>
        <p class="text-xs text-slate-500">{{ checkinText(data.checkin) }}</p>
      </div>
      </div>
      <p class="mt-4 text-xs text-slate-500">每种 AI 功能每天先用免费次数，用完以后才扣积分。回测、因子研究、事件研究、行情查询和导出数据都不用积分。</p>
    </section>

    <SectionCard title="兑换积分" hint="充值即将开放；现在可以用兑换码兑换积分">
      <form class="flex flex-col gap-3 sm:flex-row" @submit.prevent="redeem">
        <label class="sr-only" for="redeem-code">兑换码</label>
        <input id="redeem-code" v-model="code" :class="inputClass" class="sm:flex-1" placeholder="例如 PM-ABCD-EFGH-JKLM" autocomplete="off" spellcheck="false" maxlength="60" />
        <button type="submit" :disabled="redeeming" class="shrink-0 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {{ redeeming ? '兑换中…' : '兑换' }}
        </button>
      </form>
      <p v-if="redeemError" role="alert" class="mt-2 text-sm text-rose-300">{{ redeemError }}</p>
    </SectionCard>

    <SectionCard v-if="data && !data.unlimited" title="积分明细" hint="每一批积分有自己的有效期，先扣快到期的">
      <ul v-if="data.lots.length" class="grid gap-3 sm:grid-cols-2">
        <li v-for="lot in data.lots" :key="lot.id" class="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm">
          <div class="flex items-center justify-between gap-3">
            <span class="text-slate-300">{{ lot.label }}</span>
            <span class="tabular-nums text-white">{{ lot.remaining }} <span class="text-slate-500">/ {{ lot.amount }}</span></span>
          </div>
          <p class="mt-1 text-xs" :class="expiresSoon(lot.expires_at) ? 'text-amber-300' : 'text-slate-500'">{{ expiryText(lot.expires_at) }}</p>
        </li>
      </ul>
      <p v-else class="text-sm text-slate-500">还没有有效的积分。</p>
    </SectionCard>

    <SectionCard v-if="data" title="每种 AI 功能的价格" hint="每天北京时间 0 点重置免费次数">
      <ul class="grid gap-3 sm:grid-cols-2">
        <li v-for="price in data.prices" :key="price.kind" class="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm">
          <p class="text-slate-200">{{ price.label }}</p>
          <p class="mt-1 text-xs text-slate-400">{{ priceText(price, data.unlimited) }}</p>
        </li>
      </ul>
      <p v-if="!data.unlimited && data.daily_cap" class="mt-3 text-xs text-slate-500">
        为了防止滥用，每人每天最多使用 {{ data.daily_cap }} 次 AI（免费的加用积分的）。模型没有回答时不扣积分，也不占次数。
      </p>
    </SectionCard>

    <SectionCard v-if="data && !data.unlimited" title="最近的记录">
      <ul v-if="data.ledger.length" class="divide-y divide-white/5 text-sm">
        <li v-for="row in data.ledger" :key="row.id" class="flex items-center justify-between gap-3 py-2.5">
          <span class="min-w-0">
            <span class="block truncate text-slate-200">{{ ledgerText(row) }}</span>
            <span class="text-xs text-slate-500">{{ chinaTime(row.created_at) }}</span>
          </span>
          <span class="shrink-0 tabular-nums font-medium" :class="row.delta > 0 ? 'text-indigo-200' : 'text-slate-300'">{{ signed(row.delta) }}</span>
        </li>
      </ul>
      <p v-else class="text-sm text-slate-500">还没有记录。</p>
      <p class="mt-3 text-xs text-slate-500">积分只能在本平台使用，不能提现，也不能转给别人。详细规则见 <a href="/legal.html#terms" target="_blank" class="text-indigo-300 hover:text-indigo-200">服务条款</a>。</p>
    </SectionCard>
  </div>
</template>
