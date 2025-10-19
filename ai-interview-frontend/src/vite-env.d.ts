// src/vite-env.d.ts

/// <reference types="vite/client" />

// --- 【核心修复】手动声明 @wangeditor/editor-for-vue 模块 ---
declare module '@wangeditor/editor-for-vue' {
  import { ComponentOptions } from 'vue';
  const Editor: ComponentOptions;
  const Toolbar: ComponentOptions;
  export { Editor, Toolbar };
}