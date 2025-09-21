import { ref, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';

// 将 synth 实例放在函数外部，使其成为一个单例，防止重复初始化
const synth = window.speechSynthesis;

export function useTTS() {
  const isSupported = 'speechSynthesis' in window;
  const isSpeaking = ref(false);

  // 定义一个队列来处理语音请求，虽然在这个场景下，我们总是优先播放最新的
  let utteranceQueue: SpeechSynthesisUtterance[] = [];

  const speak = (text: string) => {
    if (!isSupported || !synth) {
      console.warn('浏览器不支持语音合成功能。');
      return;
    }
    
    // 【核心修正】在播放新语音前，先确保完全停止当前的语音
    // 这能有效防止 'interrupted' 错误
    if (synth.speaking) {
      synth.cancel();
    }

    const utterance = new SpeechSynthesisUtterance(text);
    const voices = synth.getVoices();
    const chineseVoice = voices.find(voice => voice.lang.startsWith('zh-CN'));
    if (chineseVoice) {
      utterance.voice = chineseVoice;
    }

    utterance.onstart = () => {
      isSpeaking.value = true;
    };

    utterance.onend = () => {
      isSpeaking.value = false;
    };

    // utterance.onerror 事件在某些浏览器上并不可靠，
    // interrupted 错误通常不是一个需要向用户报告的严重问题。
    utterance.onerror = (event) => {
      if (event.error !== 'interrupted') {
        console.error('语音合成错误:', event.error);
        ElMessage.error('播放问题时出错。');
      }
      isSpeaking.value = false;
    };
    
    // 在一个微任务后执行 speak，确保 cancel 操作已完成
    setTimeout(() => {
        synth.speak(utterance);
    }, 0);
  };

  const cancel = () => {
    if (isSupported && synth) {
      synth.cancel();
      isSpeaking.value = false;
    }
  };

  onUnmounted(() => {
    cancel();
  });

  return {
    isSpeaking,
    speak,
    cancel,
  };
}