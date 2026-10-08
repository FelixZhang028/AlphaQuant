<script setup>
import { useTheme } from '../theme.js'

const { theme, toggle } = useTheme()
</script>

<template>
  <button
    type="button"
    class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/5 text-slate-400 transition hover:bg-white/10 hover:text-slate-200"
    :title="theme === 'dark' ? '切换为浅色模式' : '切换为深色模式'"
    :aria-label="theme === 'dark' ? '切换为浅色模式' : '切换为深色模式'"
    @click="toggle"
  >
    <!-- 浅色模式显示月亮（点击进入深色），深色模式显示太阳（点击回到浅色） -->
    <svg v-if="theme === 'dark'" class="h-4.5 w-4.5" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
    <svg v-else class="h-4.5 w-4.5" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
    </svg>
  </button>
</template>
