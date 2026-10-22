<script setup>
const columns = [
  {
    title: '产品',
    links: [
      { label: '可视化回测', href: '/app.html?view=backtest-review' },
      { label: '数据说明', href: '/app.html?view=data-guide' },
      { label: '零代码策略', href: '/app.html?view=strategy-studio' },
      { label: '因子实验室', href: '/app.html?view=factor-lab' },
      { label: 'AI研究员', href: '/app.html?view=agent-lab' },
    ],
  },
  {
    title: '资源',
    links: [
      { label: '策略示例', href: '/app.html?view=strategy-hub' },
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
              <img src="/brand/prismind-icon-small.svg" width="27" height="27" alt="" aria-hidden="true" class="shrink-0" />
              <span class="ds-logo-wordmark">Prismind</span><span class="ds-logo-sub">镜思</span>
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
          © {{ year }} 镜思 Prismind. 保留所有权利。平台提供的数据、回测与分析结果仅供研究参考，不构成任何投资建议。
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
