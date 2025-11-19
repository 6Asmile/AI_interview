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
      // 【核心新增】代理媒体文件请求
      '/media': {
        target: 'http://127.0.0.1:8000', // 转发给后端
        changeOrigin: true,
      },
    }
  }
})