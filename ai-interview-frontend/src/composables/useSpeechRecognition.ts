import { ref, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';

export function useSpeechRecognition(onResult: (transcript: string) => void) {
  const isSupported = 'SpeechRecognition' in window || 'webkitSpeechRecognition' in window;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  
  const isListening = ref(false);
  const error = ref<string | null>(null);
  
  let recognition: any | null = null;

  if (isSupported) {
    recognition = new SpeechRecognition();
    recognition.continuous = true; // 持续识别
    recognition.interimResults = true; // 返回临时结果
    recognition.lang = 'zh-CN'; // 设置语言

    recognition.onstart = () => {
      isListening.value = true;
      error.value = null;
    };

    recognition.onresult = (event: any) => {
      let finalTranscript = '';
      let interimTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interimTranscript += event.results[i][0].transcript;
        }
      }
      
      // 将最终识别结果通过回调函数传递出去
      if (finalTranscript) {
        onResult(finalTranscript);
      }
    };

    recognition.onerror = (event: any) => {
      error.value = `语音识别错误: ${event.error}`;
      ElMessage.error(error.value);
      isListening.value = false;
    };

    recognition.onend = () => {
      isListening.value = false;
    };
  }

  const start = () => {
    if (!isSupported) {
      ElMessage.warning('您的浏览器不支持语音识别功能。');
      return;
    }
    if (!isListening.value) {
      recognition.start();
    }
  };

  const stop = () => {
    if (isListening.value) {
      recognition.stop();
    }
  };

  onUnmounted(() => {
    stop();
  });

  return {
    isListening,
    isSupported,
    error,
    start,
    stop,
  };
}