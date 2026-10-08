import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发模式下把 /api 与 /ws 代理到 FastAPI 后端，避免跨域/协议问题
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
