import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';
import Components from 'unplugin-vue-components/vite';
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers';

export default defineConfig({
  plugins: [vue(), Components({ resolvers: [ElementPlusResolver()], dts: false })],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '0.0.0.0',
    port: 5174,
    proxy: {
      '/api/admin/v1': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});
