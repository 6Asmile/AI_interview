<!-- src/components/common/VoiceRecorder.vue -->
<template>
  <div class="recorder-container">
    <div class="status-indicator" :class="status">{{ statusText }}</div>
    <button class="record-button" :class="status" @click="toggleRecording">
      <el-icon :size="40"><component :is="iconComponent" /></el-icon>
    </button>
    <div class="tip-text">{{ tipText }}</div>
  </div>
</template>

// src/components/common/VoiceRecorder.vue -> <script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';
import { Microphone, VideoPause } from '@element-plus/icons-vue';

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const isSupported = !!SpeechRecognition;

type RecorderStatus = 'idle' | 'recording';

const status = ref<RecorderStatus>('idle');
const recognition = ref<any>(null);
const finalTranscript = ref('');

// 【核心改造】定义新的 emit 事件
const emit = defineEmits(['recognition-finished', 'recording-started', 'recording-ended']);

const statusText = computed(() => (status.value === 'recording' ? '正在聆听...' : '准备就绪'));
const iconComponent = computed(() => (status.value === 'recording' ? VideoPause : Microphone));
const tipText = computed(() => (status.value === 'recording' ? '点击按钮结束' : '点击按钮开始回答'));

const startRecognition = () => {
  if (!isSupported) {
    ElMessage.error('抱歉，您的浏览器不支持实时语音识别功能。');
    return;
  }
  
  recognition.value = new SpeechRecognition();
  recognition.value.lang = 'zh-CN';
  recognition.value.continuous = true;
  recognition.value.interimResults = true;

  recognition.value.onstart = () => {
    status.value = 'recording';
    finalTranscript.value = '';
    emit('recording-started'); // 【核心改造】发出开始事件
  };

  recognition.value.onresult = (event: any) => {
    let interimTranscript = '';
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript.value += event.results[i][0].transcript;
      } else {
        interimTranscript += event.results[i][0].transcript;
      }
    }
  };

  recognition.value.onerror = (event: any) => {
    console.error('语音识别错误:', event.error);
    ElMessage.error(`语音识别出错: ${event.error}`);
    status.value = 'idle';
    emit('recording-ended'); // 【核心改造】出错时也要发出结束事件
  };

  recognition.value.onend = () => {
    status.value = 'idle';
    emit('recording-ended'); // 【核心改造】正常结束时发出结束事件
    if (finalTranscript.value) {
      emit('recognition-finished', finalTranscript.value);
    }
  };

  recognition.value.start();
};

const stopRecognition = () => {
  if (recognition.value && status.value === 'recording') {
    recognition.value.stop();
  }
};

const toggleRecording = () => {
  if (status.value === 'idle') {
    startRecognition();
  } else {
    stopRecognition();
  }
};

onUnmounted(() => {
  stopRecognition();
});
</script>

<style scoped>
/* 样式可以保持不变，但 processing 状态不再需要 */
.recorder-container { display: flex; flex-direction: column; align-items: center; gap: 15px; }
.record-button { width: 100px; height: 100px; border-radius: 50%; border: none; display: flex; justify-content: center; align-items: center; cursor: pointer; transition: all 0.3s ease; color: white; }
.record-button.idle { background-color: #409EFF; }
.record-button.recording { background-color: #F56C6C; animation: pulse 1.5s infinite; }
.status-indicator { font-size: 1.2rem; font-weight: 500; }
.status-indicator.recording { color: #F56C6C; }
.status-indicator.idle { color: #606266; }
.tip-text { color: #c0c4cc; }

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(245, 108, 108, 0.7); }
  70% { box-shadow: 0 0 0 20px rgba(245, 108, 108, 0); }
  100% { box-shadow: 0 0 0 0 rgba(245, 108, 108, 0); }
}
</style>