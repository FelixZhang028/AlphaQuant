<script setup>
const columns = [
  {
    title: '产品',
    links: [
      { label: '可视化回测', href: '/app.html?view=backtest-review' },
      { label: '本地数据中心', href: '/app.html?view=data-management' },
      { label: '零代码策略', href: '/app.html?view=strategy-studio' },
      { label: '因子实验室', href: '/app.html?view=factor-lab' },
      { label: 'AI研究员', href: '/app.html?view=agent-lab' },
    ],
  },
  {
    title: '资源',
    links: [
      { label: '策略示例', href: '/app.html?view=strategy-hub' },
      { label: '社区论坛', href: '/community.html' },
      { label: '新手引导', href: '/app.html?view=overview' },
    ],
  },
  {
    title: '公司',
    links: [
      { label: '关于我们', href: '/index.html#about' },
      { label: '服务条款', href: '/legal.html#terms' },
      { label: '隐私政策', href: '/legal.html#privacy' },
    ],
  },
]
const year = new Date().getFullYear()
</script>

<template>
  <footer id="footer" class="w-full overflow-hidden pb-12 pt-ds-9">
    <div class="ds-container flex flex-col gap-ds-9">
      <div class="flex w-full flex-col gap-ds-9 md:flex-row md:items-start md:gap-ds-10">
        <!-- 左列：品牌 -->
        <div class="flex shrink-0 flex-col gap-ds-5 md:max-w-[240px]">
          <div class="flex flex-col gap-ds-6">
            <a class="flex items-center gap-2 no-underline" href="/index.html">
              <svg width="27" height="27" viewBox="0 0 27 27" fill="none" aria-hidden="true">
                <rect width="27" height="27" rx="8" fill="url(#fq-logo-grad)" />
                <path d="M7.4 17.6V11.4" stroke="#fff" stroke-width="1.7" stroke-linecap="round" />
                <rect x="5.9" y="12.4" width="3" height="3.7" rx="0.9" fill="#fff" />
                <path d="M13.5 15.2V7.9" stroke="#fff" stroke-width="1.7" stroke-linecap="round" />
                <rect x="12" y="9" width="3" height="4.5" rx="0.9" fill="#fff" />
                <path d="M19.6 12.7V5.6" stroke="#fff" stroke-width="1.7" stroke-linecap="round" />
                <rect x="18.1" y="6.8" width="3" height="4.9" rx="0.9" fill="#fff" />
              </svg>
              <span class="ds-logo-wordmark">FellowQuant</span>
            </a>
            <p class="ds-text-caption m-0 text-ds-description">让数据说话，把判断留给你</p>
          </div>
        </div>

        <!-- 右列：链接 -->
        <div class="flex flex-1 flex-wrap justify-between gap-x-ds-5 gap-y-ds-8">
          <div v-for="col in columns" :key="col.title" class="flex min-w-[120px] flex-col gap-ds-6">
            <p class="ds-text-caption m-0 font-medium text-ds-primary">{{ col.title }}</p>
            <div class="flex flex-col gap-ds-5">
              <a
                v-for="link in col.links"
                :key="link.label"
                :href="link.href"
                class="ds-text-caption text-ds-description no-underline hover:text-ds-primary"
              >
                {{ link.label }}
              </a>
            </div>
          </div>
        </div>
      </div>

      <!-- 底栏 -->
      <div
        class="flex w-full flex-col items-start justify-between gap-4 border-t border-ds-border-subtle pt-ds-6 md:flex-row md:items-center"
      >
        <p class="ds-text-caption m-0 text-ds-description">
          © {{ year }} FellowQuant. 保留所有权利。平台提供的数据、回测与分析结果仅供研究参考，不构成任何投资建议。
        </p>
        <div class="ds-text-caption flex gap-6 text-ds-description">
          <a href="/legal.html#privacy" class="no-underline hover:text-ds-primary">隐私政策</a>
          <a href="/legal.html#terms" class="no-underline hover:text-ds-primary">服务条款</a>
          <a href="/legal.html#risk" class="no-underline hover:text-ds-primary">风险提示</a>
        </div>
      </div>
    </div>
  </footer>
</template>
