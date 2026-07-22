import { createApp } from 'vue';
import 'element-plus/dist/index.css';
import App from './App.vue';
import router from './router';
import './style.css';

createApp(App).use(router).mount('#app');
