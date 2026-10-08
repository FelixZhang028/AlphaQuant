/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        serif: ['Georgia', 'Times New Roman', 'Songti SC', 'SimSun', 'serif'],
      },
      colors: {
        // ink/panel 挂到 CSS 变量（RGB 三元组），随 data-theme 切换，且支持 /透明度 修饰符
        ink: 'rgb(var(--fq-ink-rgb) / <alpha-value>)',
        panel: 'rgb(var(--fq-panel-rgb) / <alpha-value>)',
      },
      transitionTimingFunction: {
        'out-expo': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
}
