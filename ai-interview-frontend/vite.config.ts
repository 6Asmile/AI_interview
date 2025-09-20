// vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 1. 引入 Node.js 'url' 模块中的两个辅助函数
import { fileURLToPath, URL } from 'node:url'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      // 2. 使用 import.meta.url 这个 ESM 标准来获取当前文件的绝对路径，
      //    并从中解析出 'src' 目录的完整路径。
      //    这是在 ESM 中替代 __dirname 的标准做法。
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  }
})