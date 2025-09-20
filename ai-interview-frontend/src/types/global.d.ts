// src/types/global.d.ts

// 这段代码的作用是告诉 TypeScript，
// 全局的 Window 接口除了它已知的属性外，
// 还可能包含这两个可选的属性。
interface Window {
  SpeechRecognition?: any;
  webkitSpeechRecognition?: any;
}