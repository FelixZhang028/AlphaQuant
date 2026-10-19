import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 打包后放在网站的 /admin/ 下（后端用 FELLOWQUANT_ADMIN_DIR 提供）；开发时仍在根路径。
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/admin/' : '/',
  plugins: [vue()],
  server: {
    port: 5175,
    strictPort: true,
  },
}))
