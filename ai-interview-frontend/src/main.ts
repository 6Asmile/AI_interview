// src/main.ts

import { createApp } from 'vue'

// 1. 引入 Element Plus
import ElementPlus from 'element-plus'
// 2. 引入 Element Plus 的样式文件
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router' // 引入 router
import pinia from './store'   // 引入 pinia
import './assets/styles/main.css' // 引入我们自己的全局样式
import './assets/styles/global.css'; // 引入我们的全局样式文件
// 创建 Vue 应用实例
const app = createApp(App)

// 3. 全局注册所有插件
app.use(ElementPlus) // 注册 Element Plus
app.use(router)      // 注册 Vue Router
app.use(pinia)       // 注册 Pinia

// 将应用挂载到 index.html 中的 #app 元素上
app.mount('#app')