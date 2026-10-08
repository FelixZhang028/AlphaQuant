/* 主页双语文案（中/英） */
export const CONTENT = {
  zh: {
    nav: { home: '首页', belief: '信念', features: '功能', about: '关于', login: '登录' },
    hero: {
      eyebrow: 'Personal Quant Workbench',
      sub: '洞见市场先机',
      tagLine1: '数据更新 → 策略信号 → 组合构建 → 模拟成交 → 绩效与风险分析',
      tagLine2: '打通从思想到收益的最后一公里',
      ctaPrimary: '开始使用',
      ctaSecondary: '自然语言建策略',
      scrollHint: '滚动探索',
    },
    belief: {
      title: 'Belief · 我们的信念',
      headline: '真正的量化，<br />不是简单的回测与下单。',
      p1: '而是将市场的混沌转化为可复利的数学逻辑。我们相信，每一行代码、每一个因子、每一次执行，都承载着对不确定性的深刻洞察。',
      p2Prefix: 'FellowQuant 致力于为您打通',
      p2Gold: '从思想到收益的最后一公里',
      p2Suffix: '。',
    },
    services: {
      title: 'Services · 服务体系',
      desc: '三重维度，构筑非凡体系。',
      items: [
        { num: '01', title: '微秒级交易通道', sub: '极速执行 · 高性能撮合引擎 · 每一笔指令以最低延迟抵达市场' },
        { num: '02', title: '思想快速验证', sub: '智能策略 · 技术指标与机器学习模型 · Python 策略热加载' },
        { num: '03', title: '全天候安全网', sub: '风控护航 · 多层级动态风险控制 · 实时监控持仓、回撤与暴露' },
      ],
    },
    features: {
      title: 'Features · 核心功能',
      desc: '三种方式，开启量化之旅。',
      items: [
        { num: '01', title: '可视化回测', sub: '向量化毫秒级回测 · 20+ 绩效指标 · 资金曲线与持仓可视化', href: '/app.html?view=backtest-review' },
        { num: '02', title: 'XTick 数据服务', sub: '官方接口动态生成表单 · 行情因子一键查询 · 导出 CSV', href: '/app.html?view=xtick-data' },
        { num: '03', title: '零代码策略', sub: '一句话生成结构化策略 · 六种模板 · 积木编辑器', href: '/app.html?view=strategy-studio' },
      ],
    },
    about: {
      title: 'About · 关于',
      headline: '数据驱动决策，<br />算法解锁 Alpha。',
      p1: 'FellowQuant 是一站式 A 股量化研究与回测平台。从数据更新、策略信号、组合构建，到模拟成交、绩效与成本分析，形成完整研究闭环，让您专注于策略本身。',
      p2: '每一次回测都经过可信度审计：数据完整性、未来函数防护、成本真实性与容量约束，五维评级让每份结果有据可查。',
      links: [
        { label: '开始使用', href: '/auth.html' },
        { label: '进入工作台', href: '/app.html?view=overview' },
      ],
    },
    footer: {
      links: [
        { label: '可视化回测', href: '/app.html?view=backtest-review' },
        { label: 'XTick 数据服务', href: '/app.html?view=xtick-data' },
        { label: '零代码策略', href: '/app.html?view=strategy-studio' },
        { label: '因子实验室', href: '/app.html?view=factor-lab' },
        { label: 'AI 研究员', href: '/app.html?view=agent-lab' },
        { label: '社区论坛', href: '/community.html' },
      ],
      disclaimer: '本平台仅用于策略研究与模拟，不构成投资建议。',
      copyright: (y) => `© ${y} FellowQuant 智投引擎 · 保留所有权利`,
    },
    a11y: { toLight: '切换为浅色模式', toDark: '切换为深色模式', toEn: 'Switch to English', toZh: '切换为中文' },
  },
  en: {
    nav: { home: 'Home', belief: 'Belief', features: 'Features', about: 'About', login: 'Sign in' },
    hero: {
      eyebrow: 'Personal Quant Workbench',
      sub: 'Insight before the market moves',
      tagLine1: 'Data refresh → strategy signals → portfolio construction → simulated execution → performance & risk',
      tagLine2: 'Bridging the last mile from idea to return',
      ctaPrimary: 'Get Started',
      ctaSecondary: 'Strategy in One Sentence',
      scrollHint: 'Scroll to explore',
    },
    belief: {
      title: 'Belief · Our Conviction',
      headline: 'Real quant is more than<br />backtests and order routing.',
      p1: 'It turns market chaos into compounding mathematical logic. Every line of code, every factor and every execution carries a deep insight into uncertainty.',
      p2Prefix: 'FellowQuant bridges ',
      p2Gold: 'the last mile from idea to return',
      p2Suffix: ' for you.',
    },
    services: {
      title: 'Services · What We Deliver',
      desc: 'Three dimensions, one exceptional system.',
      items: [
        { num: '01', title: 'Microsecond Channel', sub: 'Fast execution · high-performance matching engine · every order reaches the market with minimal latency' },
        { num: '02', title: 'Rapid Validation', sub: 'Smart strategies · technical indicators & ML models · hot-reloadable Python strategies' },
        { num: '03', title: 'Round-the-clock Safety Net', sub: 'Risk control · multi-layer dynamic limits · real-time monitoring of positions, drawdown and exposure' },
      ],
    },
    features: {
      title: 'Features · Core Capabilities',
      desc: 'Three ways to begin your quant journey.',
      items: [
        { num: '01', title: 'Visual Backtesting', sub: 'Vectorized millisecond backtests · 20+ performance metrics · equity curve & position visualization', href: '/app.html?view=backtest-review' },
        { num: '02', title: 'XTick Data Service', sub: 'Dynamic forms from official APIs · one-click factor queries · CSV export', href: '/app.html?view=xtick-data' },
        { num: '03', title: 'No-code Strategies', sub: 'Structured strategies from one sentence · six templates · block editor', href: '/app.html?view=strategy-studio' },
      ],
    },
    about: {
      title: 'About · FellowQuant',
      headline: 'Data-driven decisions,<br />algorithms that unlock alpha.',
      p1: 'FellowQuant is an all-in-one A-share quant research and backtesting platform. From data refresh and strategy signals to portfolio construction, simulated execution, and performance & cost analysis — a complete research loop, so you can focus on the strategy itself.',
      p2: 'Every backtest goes through a credibility audit: data integrity, look-ahead protection, cost realism and capacity constraints — a five-dimension rating makes every result verifiable.',
      links: [
        { label: 'Get Started', href: '/auth.html' },
        { label: 'Open Workbench', href: '/app.html?view=overview' },
      ],
    },
    footer: {
      links: [
        { label: 'Visual Backtesting', href: '/app.html?view=backtest-review' },
        { label: 'XTick Data Service', href: '/app.html?view=xtick-data' },
        { label: 'No-code Strategies', href: '/app.html?view=strategy-studio' },
        { label: 'Factor Lab', href: '/app.html?view=factor-lab' },
        { label: 'AI Researcher', href: '/app.html?view=agent-lab' },
        { label: 'Community', href: '/community.html' },
      ],
      disclaimer: 'For strategy research and simulation only. Not investment advice.',
      copyright: (y) => `© ${y} FellowQuant · All rights reserved`,
    },
    a11y: { toLight: 'Switch to light mode', toDark: 'Switch to dark mode', toEn: 'Switch to English', toZh: '切换为中文' },
  },
}
