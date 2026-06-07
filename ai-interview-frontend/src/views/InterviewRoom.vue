<template>
  <div class="interview-room-container min-h-screen p-4 lg:p-8">
    <div class="main-content-grid max-w-screen-2xl mx-auto">
      
      <aside class="left-panel glass-card p-4 flex flex-col gap-4">
        <div class="panel-section-heading">
          <p class="panel-eyebrow">Live Presence</p>
          <h3>实时分析</h3>
        </div>
        <div class="video-container relative aspect-[4/3] bg-gray-200 rounded-lg overflow-hidden shadow-inner">
          <video ref="videoRef" autoplay muted playsinline class="w-full h-full object-cover"></video>
          <div v-if="!modelsLoaded" class="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 text-white">摄像头加载中...</div>
          <div v-if="isVideoRecording" class="absolute top-2 left-2 flex items-center gap-2 bg-red-500 text-white px-3 py-1 rounded-full text-xs">
            <span class="w-2 h-2 bg-white rounded-full animate-pulse"></span>
            录制中
          </div>
        </div>
        <div class="analysis-section">
          <div class="analysis-summary grid grid-cols-2 gap-4 text-center p-3 bg-white/50 rounded-lg">
            <div><p class="text-xs text-gray-500">主要情绪</p><p class="text-lg font-bold text-blue-600">{{ getPrimaryEmotion(emotions) }}</p></div>
            <div><p class="text-xs text-gray-500">语音状态</p><p class="text-lg font-bold text-gray-700">{{ isRecording ? '采集中' : '待机' }}</p></div>
          </div>
        </div>
        <div class="emotion-bars-container space-y-2">
           <el-progress v-for="emotion in sortedEmotions" :key="emotion.name" :percentage="emotion.score" :stroke-width="8" striped striped-flow>
              <span class="text-xs text-gray-600">{{ emotion.name }}</span>
            </el-progress>
        </div>
      </aside>

      <main class="center-panel glass-card p-6 flex flex-col">
        <div class="question-display-area flex-grow flex flex-col gap-4">
          <div class="ai-presenter flex items-start gap-4">
            <el-avatar :src="aiAvatar" :size="48" class="flex-shrink-0 shadow-lg" />
            <div class="flex-grow">
              <div class="question-header flex items-center gap-4">
                <h2 class="font-bold text-xl text-gray-800">AI 面试官</h2>
                <el-tooltip :content="speechTooltip" placement="top" :disabled="!currentQuestion">
                  <el-button v-if="currentQuestion" @click="toggleSpeech" :icon="speechIcon" type="primary" circle />
                </el-tooltip>
              </div>
              <p class="question-progress text-xs text-gray-500 mt-1">问题 {{ currentQuestion?.sequence }} / {{ sessionInfo?.question_count }}</p>
            </div>
          </div>
          
          <div class="question-text-box bg-white/60 p-5 rounded-lg min-h-[150px] text-gray-900 text-lg leading-relaxed overflow-y-auto flex items-center">
            <p>{{ streamedQuestionText || currentQuestion?.question_text }}</p>
          </div>

          <div v-if="lastFeedback" class="feedback-box bg-green-100/80 p-3 rounded-lg text-sm text-green-800 border border-green-200">
            <strong>AI 简评 (上一问):</strong> {{ decodeURIComponent(lastFeedback) }}
          </div>
        </div>
        
        <div class="answer-input-area mt-6">
          <RichTextEditor v-model="userAnswer" placeholder="请在这里输入您的回答，或使用下方的语音输入功能..." />
          <div class="speech-control-bar flex items-center justify-center gap-4 p-3 mt-2 bg-white/50 rounded-lg">
            <el-tooltip content="开始语音输入" placement="top" :disabled="isListening">
              <el-button @click="startSpeech" :disabled="isListening" type="primary" circle :icon="Microphone" />
            </el-tooltip>
            <el-tooltip content="停止语音输入" placement="top" :disabled="!isListening">
              <el-button @click="stopSpeech" :disabled="!isListening" type="danger" circle :icon="SwitchButton" />
            </el-tooltip>
            <span v-if="isListening" class="text-sm text-red-500 animate-pulse">正在聆听...</span>
            <span v-else class="text-sm text-gray-500">点击麦克风开始语音回答</span>
          </div>
        </div>
      </main>

      <aside class="right-panel flex flex-col gap-6">
        <div class="controls glass-card p-4 flex flex-col items-center gap-4">
          <div class="panel-section-heading panel-section-heading--compact">
            <p class="panel-eyebrow">Interview Actions</p>
            <h3>操作面板</h3>
          </div>
          <div v-if="isUploading" class="w-full">
            <p class="text-xs text-gray-500 mb-2 text-center">正在上传录像...</p>
            <el-progress :percentage="uploadProgress" :stroke-width="6" />
          </div>
           <el-button type="primary" size="large" @click="submitAnswer" :loading="isSubmitting" :disabled="!userAnswer.trim()" class="w-full transition-all duration-300 hover:shadow-lg hover:-translate-y-1">
            {{ isSubmitting ? '处理中...' : '确认并进入下一题' }}
          </el-button>
          <el-button type="danger" @click="() => confirmFinishInterview()" :loading="isFinishing" class="w-full" plain>
            {{ isFinishing ? '正在结束...' : '结束面试' }}
          </el-button>
        </div>
        <div v-if="sessionInfo?.recording_enabled" class="recording-status glass-card p-4">
          <h3 class="uppercase text-xs font-semibold text-gray-400 tracking-wider mb-3">录像状态</h3>
          <div class="flex items-center gap-2">
            <el-icon :class="isVideoRecording ? 'text-red-500 animate-pulse' : 'text-gray-400'" :size="20">
              <VideoCamera />
            </el-icon>
            <span class="text-sm" :class="isVideoRecording ? 'text-red-500' : 'text-gray-500'">
              {{ isVideoRecording ? '正在录制面试视频' : '录像未启动' }}
            </span>
          </div>
        </div>
        <div class="tips glass-card p-4">
          <h3 class="uppercase text-xs font-semibold text-gray-400 tracking-wider mb-3">面试注意事项</h3>
          <ul class="text-xs text-gray-600 list-disc pl-4 space-y-2">
            <li>请确保网络通畅，选择光线充足、背景整洁的环境。</li>
            <li>请正视摄像头，保持声音清晰、语速适中。</li>
            <li>回答问题时，建议结合 STAR 法则，突出个人贡献和量化成果。</li>
          </ul>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, shallowRef } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useFaceApi, emotionMap } from '@/composables/useFaceApi';
import { useTTS } from '@/composables/useTTS';
import { useSpeechRecognition } from '@/composables/useSpeechRecognition';
import { ElMessage, ElMessageBox, ElButton, ElProgress, ElIcon, ElAvatar, ElTooltip } from 'element-plus';
import { VideoPlay, VideoPause, RefreshRight, Microphone, SwitchButton, VideoCamera } from '@element-plus/icons-vue';
import { getInterviewSessionApi, submitAnswerStreamApi, finishInterviewApi, type InterviewSessionItem, type InterviewQuestionItem, type AnalysisFrame } from '@/api/modules/interview';
import { VideoUploader } from '@/api/modules/videoUpload';
import RichTextEditor from '@/components/common/RichTextEditor.vue';
import aiAvatar from '@/assets/images/image.png';

const route = useRoute();
const router = useRouter();
const sessionInfo = ref<InterviewSessionItem | null>(null);
const currentQuestion = ref<InterviewQuestionItem | null>(null);
const userAnswer = ref('');
const streamedQuestionText = ref('');
const lastFeedback = ref('');
const isSubmitting = ref(false);
const isFinishing = ref(false);
const { modelsLoaded, emotions, loadModels, detectFace, getPrimaryEmotion } = useFaceApi();
const { isSpeaking, isPaused, speak, pause, resume, cancel } = useTTS();
const videoRef = ref<HTMLVideoElement | null>(null);
const analysisInterval = ref<NodeJS.Timeout | null>(null);
let analysisFrames = ref<AnalysisFrame[]>([]);

const mediaRecorder = ref<MediaRecorder | null>(null);
const recordedChunks = ref<Blob[]>([]);
const isVideoRecording = ref(false);
const uploadProgress = ref(0);
const isUploading = ref(false);
const mediaStream = ref<MediaStream | null>(null);
const handleSpeechResult = (transcript: string) => {
  if (userAnswer.value.endsWith('</p>')) { userAnswer.value = userAnswer.value.slice(0, -4) + transcript + '</p>'; } 
  else { userAnswer.value += transcript; }
};
const { isListening, start: startSpeech, stop: stopSpeech } = useSpeechRecognition(handleSpeechResult);
const isRecording = computed(() => isListening.value);
const speechIcon = shallowRef(VideoPlay);
const speechTooltip = ref('播放问题');

watch([isSpeaking, isPaused], ([speaking, paused]) => {
  if (speaking && !paused) { speechIcon.value = VideoPause; speechTooltip.value = '暂停'; } 
  else if (speaking && paused) { speechIcon.value = VideoPlay; speechTooltip.value = '继续播放'; } 
  else { speechIcon.value = RefreshRight; speechTooltip.value = '重播问题'; }
}, { immediate: true });

const toggleSpeech = () => {
  const textToSpeak = streamedQuestionText.value || currentQuestion.value?.question_text;
  if (!textToSpeak) return;
  if (isSpeaking.value) {
    if (isPaused.value) { resume(); } else { pause(); }
  } else { speak(textToSpeak); }
};

// [核心修正 1/2] 新增 HTML 清洗函数
const sanitizeHtml = (dirtyHtml: string): string => {
  const tempDiv = document.createElement('div');
  tempDiv.innerHTML = dirtyHtml;
  
  // 遍历所有子元素
  const allElements = tempDiv.querySelectorAll('*');
  allElements.forEach(el => {
    // 移除 style 属性
    el.removeAttribute('style');
    // 你可以在这里移除更多不想要的属性，例如 class, id 等
    // el.removeAttribute('class');
  });

  return tempDiv.innerHTML;
};

const sortedEmotions = computed(() => { if (!emotions.value) return []; return emotions.value.asSortedArray().map(emotion => ({ name: emotionMap[emotion.expression] || emotion.expression, score: Math.round(emotion.probability * 100) })); });

const setupCamera = async () => {
  if (videoRef.value) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { width: 1280, height: 720 }, 
        audio: true 
      });
      mediaStream.value = stream;
      videoRef.value.srcObject = stream;
      videoRef.value.onloadedmetadata = () => {
        startAnalysis();
        console.log('[录像] sessionInfo.recording_enabled:', sessionInfo.value?.recording_enabled);
        if (sessionInfo.value?.recording_enabled) {
          console.log('[录像] 开始自动录制...');
          startVideoRecording();
        }
      };
    } catch (err) {
      ElMessage.error("无法访问摄像头或麦克风，请检查权限。");
    }
  }
};

const startVideoRecording = () => {
  if (!mediaStream.value) return;
  
  recordedChunks.value = [];
  const options = { mimeType: 'video/webm;codecs=vp9,opus' };
  
  try {
    mediaRecorder.value = new MediaRecorder(mediaStream.value, options);
  } catch (e) {
    try {
      mediaRecorder.value = new MediaRecorder(mediaStream.value, { mimeType: 'video/webm' });
    } catch (e2) {
      ElMessage.error("浏览器不支持视频录制");
      return;
    }
  }
  
  mediaRecorder.value.ondataavailable = (event) => {
    if (event.data.size > 0) {
      recordedChunks.value.push(event.data);
    }
  };
  
  mediaRecorder.value.start(1000);
  isVideoRecording.value = true;
  console.log('[录像] 录制已启动');
};

const stopVideoRecording = (): Promise<Blob | null> => {
  return new Promise((resolve) => {
    if (!mediaRecorder.value || !isVideoRecording.value) {
      resolve(null);
      return;
    }
    
    mediaRecorder.value.onstop = () => {
      const blob = new Blob(recordedChunks.value, { type: 'video/webm' });
      isVideoRecording.value = false;
      resolve(blob);
    };
    
    mediaRecorder.value.stop();
  });
};

const uploadVideo = async (videoBlob: Blob): Promise<string | null> => {
  isUploading.value = true;
  uploadProgress.value = 0;
  
  try {
    const uploader = new VideoUploader({
      onProgress: (progress) => {
        uploadProgress.value = progress;
      }
    });
    
    const taskId = await uploader.upload(videoBlob, `interview_${sessionInfo.value?.id}_${Date.now()}.webm`);
    return taskId;
  } catch (error) {
    ElMessage.error("视频上传失败");
    return null;
  } finally {
    isUploading.value = false;
  }
};
const startAnalysis = () => { if (analysisInterval.value) clearInterval(analysisInterval.value); analysisInterval.value = setInterval(async () => { if (videoRef.value) { await detectFace(videoRef.value); if (emotions.value) { const plainEmotions: Record<string, number> = {}; for (const key in emotionMap) { if (Object.prototype.hasOwnProperty.call(emotions.value, key)) { plainEmotions[key] = (emotions.value as any)[key]; } } analysisFrames.value.push({ timestamp: Date.now(), emotions: plainEmotions }); } } }, 1000); };
const fetchSessionData = async () => {
  try {
    const sessionId = route.params.id as string;
    const res = await getInterviewSessionApi(sessionId);
    sessionInfo.value = res;

    if (res.status === 'finished') {
      ElMessage.info("面试已完成，正在跳转到报告页面...");
      router.push({ name: 'ReportDetail', params: { id: sessionId } });
      return;
    }

    if (res.status === 'canceled') {
      ElMessage.warning("该面试已取消");
      router.push({ name: 'Dashboard' });
      return;
    }

    const unanswered = res.questions.filter(q => !q.answer_text);
    if (unanswered.length > 0) {
      currentQuestion.value = unanswered[0];
      streamedQuestionText.value = '';
      return;
    }

    currentQuestion.value = res.questions[res.questions.length - 1] || null;
  } catch (error) {
    ElMessage.error("加载面试信息失败");
  }
};

const submitAnswer = async () => {
  cancel();
  stopSpeech();
  if (!sessionInfo.value || !currentQuestion.value || !userAnswer.value.trim()) return;
  isSubmitting.value = true;
  streamedQuestionText.value = '';

  // [核心修正 2/2] 在提交前清洗 HTML
  const cleanAnswer = sanitizeHtml(userAnswer.value);

  try {
    const result = await submitAnswerStreamApi(sessionInfo.value.id, {
        question_id: currentQuestion.value.id,
        answer_text: cleanAnswer, // 使用清洗后的数据
        analysis_data: analysisFrames.value,
      }, (chunk) => { streamedQuestionText.value += chunk; });
    lastFeedback.value = result.feedback;
    if (result.isFinished) {
      confirmFinishInterview(true);
    } else {
      await fetchSessionData();
      userAnswer.value = '';
      analysisFrames.value = [];
    }
  } catch (error) { ElMessage.error("提交失败，请重试。");
  } finally { isSubmitting.value = false; }
};
const confirmFinishInterview = async (isAutoFinish: boolean | Event = false) => {
  cancel();
  stopSpeech();
  
  const action = async () => {
    isFinishing.value = true;
    if (!sessionInfo.value) return;
    
    console.log('[录像] 结束面试 - recording_enabled:', sessionInfo.value.recording_enabled, 'isVideoRecording:', isVideoRecording.value);
    
    let videoUploadId: string | null = null;
    
    if (isVideoRecording.value) {
      console.log('[录像] 正在停止录制...');
      const videoBlob = await stopVideoRecording();
      console.log('[录像] 录制停止，blob大小:', videoBlob?.size);
      if (videoBlob && videoBlob.size > 0) {
        ElMessage.info("正在上传面试录像，请稍候...");
        videoUploadId = await uploadVideo(videoBlob);
        if (videoUploadId) {
          ElMessage.success("录像上传成功");
          console.log('[录像] 上传成功，taskId:', videoUploadId);
        }
      } else {
        console.log('[录像] 录制数据为空或不存在');
      }
    } else {
      console.log('[录像] 当前没有在录制');
    }
    
    try {
      const report = await finishInterviewApi(sessionInfo.value.id, {
        video_upload_id: videoUploadId || undefined
      });
      ElMessage.success("面试结束，正在生成报告...");
      if (report?.error) {
        throw new Error(report.error);
      }
      router.push({ name: 'ReportDetail', params: { id: sessionInfo.value.id } });
    } catch (error) {
      const message = error instanceof Error ? error.message : "结束面试失败";
      ElMessage.error(message);
    } finally {
      isFinishing.value = false;
    }
  };
  
  if (isAutoFinish === true) return action();
  
  ElMessageBox.confirm('您确定要提前结束本次面试吗？', '确认结束', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(action).catch(() => {
    ElMessage.info('面试已继续');
  });
};
onMounted(async () => { await loadModels(); await fetchSessionData(); await setupCamera(); });
onUnmounted(() => {
  if (analysisInterval.value) clearInterval(analysisInterval.value);
  if (mediaRecorder.value && isVideoRecording.value) {
    mediaRecorder.value.stop();
  }
  if (mediaStream.value) {
    mediaStream.value.getTracks().forEach(track => track.stop());
  }
  if (videoRef.value && videoRef.value.srcObject) {
    (videoRef.value.srcObject as MediaStream).getTracks().forEach(track => track.stop());
  }
  cancel();
  stopSpeech();
});
</script>

<style scoped>
.glass-card {
  background: rgba(255, 255, 255, 0.58);
  backdrop-filter: blur(18px) saturate(180%);
  -webkit-backdrop-filter: blur(18px) saturate(180%);
  border: 1px solid rgba(220, 232, 250, 0.82);
  border-radius: 28px;
  box-shadow: 0 24px 55px rgba(35, 63, 110, 0.12);
}

.interview-room-container {
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(96, 155, 255, 0.12), transparent 25%),
    radial-gradient(circle at top right, rgba(67, 207, 164, 0.08), transparent 20%),
    linear-gradient(180deg, #f6f9ff 0%, #eff4fb 100%);
}

.main-content-grid {
  display: grid;
  grid-template-columns: 320px 1fr 290px;
  grid-template-rows: calc(100vh - 6rem);
  gap: 1.5rem;
}

.panel-section-heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.panel-section-heading--compact {
  width: 100%;
}

.panel-eyebrow {
  margin: 0;
  color: #6d86b2;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.panel-section-heading h3 {
  margin: 0;
  color: #1c2e4d;
  font-size: 22px;
}

.left-panel,
.center-panel,
.right-panel .glass-card {
  position: relative;
}

.video-container {
  border-radius: 24px;
  border: 1px solid rgba(222, 232, 246, 0.9);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.analysis-summary {
  border: 1px solid rgba(223, 232, 245, 0.9);
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92) 0%, rgba(245, 248, 255, 0.82) 100%) !important;
}

.emotion-bars-container {
  padding: 16px 18px;
  border: 1px solid rgba(223, 232, 245, 0.95);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
}

.center-panel {
  padding: 28px !important;
}

.question-display-area {
  gap: 20px !important;
}

.ai-presenter {
  padding: 18px 20px;
  border: 1px solid rgba(222, 231, 245, 0.92);
  border-radius: 24px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(239, 245, 255, 0.72) 100%);
}

.question-header h2 {
  color: #172944 !important;
  font-size: 22px;
}

.question-progress {
  color: #70819b !important;
  font-size: 13px !important;
}

.question-text-box {
  min-height: 220px !important;
  padding: 28px !important;
  border: 1px solid rgba(225, 233, 245, 0.95);
  border-radius: 28px !important;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.93) 0%, rgba(247, 250, 255, 0.88) 100%) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
}

.question-text-box p {
  margin: 0;
  color: #1f2f4c;
  font-size: 28px;
  line-height: 1.7;
}

.feedback-box {
  border-radius: 20px !important;
  box-shadow: 0 14px 28px rgba(76, 148, 91, 0.08);
}

.answer-input-area {
  margin-top: 22px !important;
  padding-top: 22px;
  border-top: 1px solid rgba(223, 231, 244, 0.9);
}

.speech-control-bar {
  border: 1px solid rgba(222, 231, 245, 0.9);
  border-radius: 20px !important;
  background: rgba(255, 255, 255, 0.78) !important;
}

.controls {
  gap: 16px !important;
}

.controls :deep(.el-button--primary) {
  min-height: 52px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, #2a65d8 0%, #5f9fff 100%);
  box-shadow: 0 18px 28px rgba(42, 101, 216, 0.18);
}

.controls :deep(.el-button--danger.is-plain) {
  min-height: 48px;
  border-radius: 16px;
}

.recording-status,
.tips {
  border-radius: 24px;
}

.tips ul {
  line-height: 1.8;
}

:deep(.el-progress-bar__outer) {
  background: #e9eff8;
}

:deep(.el-progress-bar__inner) {
  border-radius: 999px;
}

@media (max-width: 1280px) {
  .main-content-grid {
    grid-template-columns: 300px 1fr;
    grid-template-rows: auto;
  }

  .right-panel {
    grid-column: 1 / -1;
    flex-direction: row;
    align-items: flex-start;
  }

  .right-panel .controls,
  .right-panel .tips,
  .right-panel .recording-status {
    flex: 1;
  }
}

@media (max-width: 768px) {
  .interview-room-container {
    overflow-y: auto;
    padding: 16px;
  }

  .main-content-grid {
    display: flex;
    flex-direction: column;
    height: auto;
  }

  .right-panel {
    flex-direction: column;
  }

  .question-text-box p {
    font-size: 22px;
  }
}
</style>
