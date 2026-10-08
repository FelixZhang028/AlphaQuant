/**
 * 滚动渐显（scroll-reveal）指令。
 * 用法：<div v-reveal>…</div>
 *      <div v-reveal="{ delay: 150 }">…</div>  （delay 单位 ms）
 *
 * 原理：挂载时给元素加 .reveal 类（初始透明 + 下移），
 * IntersectionObserver 观测到元素进入视口后加 .is-visible 触发 CSS 过渡，
 * 且只触发一次（unobserve），避免反复闪烁。
 */
const observerOptions = {
  threshold: 0.12,
  rootMargin: '0px 0px -8% 0px',
}

let observer = null

function getObserver() {
  if (!observer) {
    observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        }
      }
    }, observerOptions)
  }
  return observer
}

export const revealDirective = {
  mounted(el, binding) {
    const delay = binding.value?.delay
    if (delay) el.style.setProperty('--reveal-delay', `${delay}ms`)
    el.classList.add('reveal')
    getObserver().observe(el)
  },
  unmounted(el) {
    observer?.unobserve(el)
  },
}
