<template>
  <div class="interview-room-container min-h-screen p-4 lg:p-8">
    <div class="main-content-grid max-w-screen-2xl mx-auto">
      
      <aside class="left-panel glass-card p-4 flex flex-col gap-4">
        <div class="video-container relative aspect-[4/3] bg-gray-200 rounded-lg overflow-hidden shadow-inner">
          <video ref="videoRef" autoplay muted playsinline class="w-full h-full object-cover"></video>
          <div v-if="!modelsLoaded" class="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 text-white">摄像头加载中...</div>
        </div>
        <div class="analysis-section">
          <h3 class="uppercase text-xs font-semibold text-gray-400 tracking-wider mb-3">实时分析</h3>
          <div class="grid grid-cols-2 gap-4 text-center p-3 bg-white/50 rounded-lg">
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
              <p class="text-xs text-gray-500 mt-1">问题 {{ currentQuestion?.sequence }} / {{ sessionInfo?.question_count }}</p>
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
           <el-button type="primary" size="large" @click="submitAnswer" :loading="isSubmitting" :disabled="!userAnswer.trim()" class="w-full transition-all duration-300 hover:shadow-lg hover:-translate-y-1">
            {{ isSubmitting ? '处理中...' : '确认并进入下一题' }}
          </el-button>
          <el-button type="danger" @click="() => confirmFinishInterview()" :loading="isFinishing" class="w-full" plain>
            {{ isFinishing ? '正在结束...' : '结束面试' }}
          </el-button>
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
import { VideoPlay, VideoPause, RefreshRight, Microphone, SwitchButton } from '@element-plus/icons-vue';
import { getInterviewSessionApi, submitAnswerStreamApi, type InterviewSessionItem, type InterviewQuestionItem, type AnalysisFrame } from '@/api/modules/interview';
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
const setupCamera = async () => { if (videoRef.value) { try { const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false }); videoRef.value.srcObject = stream; videoRef.value.onloadedmetadata = () => { startAnalysis(); }; } catch (err) { ElMessage.error("无法访问摄像头，请检查权限。"); } } };
const startAnalysis = () => { if (analysisInterval.value) clearInterval(analysisInterval.value); analysisInterval.value = setInterval(async () => { if (videoRef.value) { await detectFace(videoRef.value); if (emotions.value) { const plainEmotions: Record<string, number> = {}; for (const key in emotionMap) { if (Object.prototype.hasOwnProperty.call(emotions.value, key)) { plainEmotions[key] = (emotions.value as any)[key]; } } analysisFrames.value.push({ timestamp: Date.now(), emotions: plainEmotions }); } } }, 1000); };
const fetchSessionData = async () => { try { const sessionId = route.params.id as string; const res = await getInterviewSessionApi(sessionId); sessionInfo.value = res; const unanswered = res.questions.filter(q => !q.answer_text); if (unanswered.length > 0) { currentQuestion.value = unanswered[0]; } else { ElMessage.info("面试已完成，正在跳转到报告页面..."); router.push({ name: 'ReportDetail', params: { id: sessionId } }); } } catch (error) { ElMessage.error("加载面试信息失败"); } };

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
const confirmFinishInterview = (isAutoFinish: boolean | Event = false) => { cancel(); stopSpeech(); const action = () => { isFinishing.value = true; if (sessionInfo.value) { ElMessage.success("面试结束，正在生成报告..."); router.push({ name: 'ReportDetail', params: { id: sessionInfo.value.id } }); } }; if(isAutoFinish === true) return action(); ElMessageBox.confirm('您确定要提前结束本次面试吗？', '确认结束', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }).then(action).catch(() => { ElMessage.info('面试已继续'); }); };
onMounted(async () => { await loadModels(); await setupCamera(); await fetchSessionData(); });
onUnmounted(() => { if (analysisInterval.value) clearInterval(analysisInterval.value); if (videoRef.value && videoRef.value.srcObject) { (videoRef.value.srcObject as MediaStream).getTracks().forEach(track => track.stop()); } cancel(); stopSpeech(); });
</script>

<style scoped>
.glass-card { background: rgba(255, 255, 255, 0.55); backdrop-filter: blur(16px) saturate(180%); -webkit-backdrop-filter: blur(16px) saturate(180%); border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 1rem; box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1); }
.interview-room-container { overflow: hidden; }
.main-content-grid { display: grid; grid-template-columns: 300px 1fr 260px; grid-template-rows: calc(100vh - 6rem); gap: 1.5rem; }
@media (max-width: 1280px) { .main-content-grid { grid-template-columns: 300px 1fr; grid-template-rows: auto; } .right-panel { grid-column: 1 / -1; flex-direction: row; align-items: flex-start; } .right-panel .controls, .right-panel .tips { flex-basis: 50%; } }
@media (max-width: 768px) { .interview-room-container { overflow-y: auto; } .main-content-grid { display: flex; flex-direction: column; height: auto; } .right-panel { flex-direction: column; } }
</style>