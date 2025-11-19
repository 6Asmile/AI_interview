// vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    // 确保监听所有 IP，这有时能解决一些网络绑定问题
    host: '0.0.0.0', 
    proxy: {
      '/api/v1': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // 【核心修改】
      '/ws': {
        // 注意：这里故意使用 http:// 而不是 ws://
        // vite 的代理中间件会自动处理 WebSocket 的 Upgrade 头
        target: 'http://127.0.0.1:8000', 
        ws: true,
        changeOrigin: true,
        // 添加这个以防万一
        secure: false,
      }
    }
  }
})