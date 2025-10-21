import { ref, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';

const synth = window.speechSynthesis;

export function useTTS() {
  const isSupported = 'speechSynthesis' in window;
  const isSpeaking = ref(false);
  const isPaused = ref(false);

  let currentUtterance: SpeechSynthesisUtterance | null = null;

  const speak = (text: string) => {
    if (!isSupported || !synth) {
      console.warn('浏览器不支持语音合成功能。');
      return;
    }
    
    if (synth.speaking) {
      synth.cancel();
    }

    currentUtterance = new SpeechSynthesisUtterance(text);
    const voices = synth.getVoices();
    const chineseVoice = voices.find(voice => voice.lang.startsWith('zh-CN'));
    if (chineseVoice) {
      currentUtterance.voice = chineseVoice;
    }

    currentUtterance.onstart = () => {
      isSpeaking.value = true;
      isPaused.value = false;
    };

    currentUtterance.onend = () => {
      isSpeaking.value = false;
      isPaused.value = false;
      currentUtterance = null;
    };
    
    currentUtterance.onerror = (event) => {
      if (event.error !== 'interrupted') {
        console.error('语音合成错误:', event.error);
        ElMessage.error('播放问题时出错。');
      }
      isSpeaking.value = false;
      isPaused.value = false;
    };
    
    setTimeout(() => {
        synth.speak(currentUtterance!);
    }, 0);
  };

  // [核心新增] 暂停功能
  const pause = () => {
    if (synth.speaking && !synth.paused) {
      synth.pause();
      isPaused.value = true;
    }
  };

  // [核心新增] 恢复功能
  const resume = () => {
    if (synth.paused) {
      synth.resume();
      isPaused.value = false;
    }
  };

  const cancel = () => {
    if (isSupported && synth) {
      synth.cancel();
      isSpeaking.value = false;
      isPaused.value = false;
    }
  };

  onUnmounted(() => {
    cancel();
  });

  return {
    isSpeaking,
    isPaused, // 暴露暂停状态
    speak,
    pause,    // 暴露暂停方法
    resume,   // 暴露恢复方法
    cancel,
  };
}