// src/composables/useTTS.ts
import { ref, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';

// 导出一个函数，这样任何组件都可以使用语音合成功能
export function useTTS() {
  const isSupported = 'speechSynthesis' in window;
  const isSpeaking = ref(false);
  const synth = isSupported ? window.speechSynthesis : null;

  const speak = (text: string) => {
    if (!isSupported || !synth) {
      ElMessage.warning('您的浏览器不支持语音合成功能。');
      return;
    }
    
    // 如果正在说话，先取消
    if (synth.speaking) {
      synth.cancel();
    }

    const utterance = new SpeechSynthesisUtterance(text);
    
    // 可选：配置语音。可以查找可用的中文语音
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

    utterance.onerror = (event) => {
      console.error('语音合成错误:', event.error);
      ElMessage.error('播放问题时出错。');
      isSpeaking.value = false;
    };

    synth.speak(utterance);
  };

  const cancel = () => {
    if (isSupported && synth) {
      synth.cancel();
      isSpeaking.value = false;
    }
  };

  // 确保组件卸载时停止任何语音
  onUnmounted(() => {
    cancel();
  });

  return {
    isSpeaking,
    speak,
    cancel,
  };
}