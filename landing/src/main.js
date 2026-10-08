import { createApp } from 'vue'
import App from './App.vue'
import { revealDirective } from './composables/useReveal'
import './style.css'

const app = createApp(App)
app.directive('reveal', revealDirective)
app.mount('#app')
