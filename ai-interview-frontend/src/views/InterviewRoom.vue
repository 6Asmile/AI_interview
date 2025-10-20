<template>
  <div class="interview-room-container min-h-screen bg-gray-100 p-4">
    <div class="flex flex-wrap md:flex-nowrap gap-4 max-w-7xl mx-auto">

      <!-- 左侧：摄像头与实时分析 -->
      <div class="w-full md:w-1/3">
        <div class="bg-white rounded-lg shadow-lg p-4 h-full sticky top-4">
          <!-- 视频 -->
          <div class="relative mb-4">
            <video ref="videoRef" autoplay muted playsinline class="w-full h-auto rounded-md bg-gray-200 aspect-video"></video>
            <div v-if="!modelsLoaded" class="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 text-white rounded-md">
              摄像头加载中...
            </div>
          </div>

          <!-- 情绪分析 -->
          <div class="grid grid-cols-2 gap-4 text-center">
            <div>
              <h3 class="text-sm font-semibold text-gray-500">情绪分析</h3>
              <p class="text-lg font-bold text-blue-600">{{ getPrimaryEmotion(emotions) }}</p>
            </div>
             <div>
              <h3 class="text-sm font-semibold text-gray-500">语音状态</h3>
              <p class="text-lg font-bold text-gray-700">{{ isRecording ? '采集中' : '待机' }}</p>
            </div>
          </div>
          <el-divider />
          <div class="space-y-2">
            <el-progress 
              v-for="emotion in sortedEmotions" 
              :key="emotion.name" 
              :percentage="emotion.score" 
              :stroke-width="10"
            >
              <span>{{ emotion.name }}</span>
            </el-progress>
          </div>
        </div>
      </div>

      <!-- 右侧：面试官与问答区域 -->
      <div class="w-full md:w-2/3">
        <div class="bg-white rounded-lg shadow-lg p-6">
          <div class="flex justify-between items-center mb-4">
            <h2 class="text-xl font-bold text-gray-800">AI 面试官</h2>
            <el-button type="danger" @click="() => confirmFinishInterview()" :loading="isFinishing">
              {{ isFinishing ? '正在结束...' : '结束面试' }}
            </el-button>
          </div>

          <!-- 问题区域 -->
          <div class="question-area bg-gray-50 p-4 rounded-lg min-h-[150px] mb-4">
            <div class="flex justify-between items-center text-sm text-gray-500 mb-2">
              <span>问题 {{ currentQuestion?.sequence }} / {{ sessionInfo?.question_count }}</span>
              <el-button @click="speak(streamedQuestionText)" type="primary" link v-if="streamedQuestionText && !isSpeaking">
                <el-icon><Microphone /></el-icon> 播放
              </el-button>
              <span v-if="isSpeaking" class="text-blue-500">正在发言...</span>
            </div>
            <p class="text-gray-800 text-lg leading-relaxed">{{ streamedQuestionText || currentQuestion?.question_text }}</p>
          </div>

          <!-- AI 简评 -->
          <div v-if="lastFeedback" class="feedback-area bg-green-50 p-3 rounded-lg mb-4 text-sm text-green-800">
            <strong>AI 简评 (上一问):</strong> {{ lastFeedback }}
          </div>

          <!-- 回答区域 -->
          <div class="answer-area">
            <RichTextEditor v-model="userAnswer" placeholder="请在这里输入您的回答..." />
            <div class="mt-4 flex justify-end">
              <el-button type="primary" size="large" @click="submitAnswer" :loading="isSubmitting" :disabled="!userAnswer.trim()">
                {{ isSubmitting ? '处理中...' : '确认并进入下一题' }}
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, toRaw } from 'vue';
import { useRoute, useRouter } from 'vue-router';
// [核心修正 3/3] 移除未使用的 FaceExpressions 类型导入
import { useFaceApi, emotionMap } from '@/composables/useFaceApi';
import { useTTS } from '@/composables/useTTS';
import { ElMessage, ElMessageBox, ElButton, ElDivider, ElProgress, ElIcon } from 'element-plus';
import { Microphone } from '@element-plus/icons-vue';
import { getInterviewSessionApi, submitAnswerStreamApi, type InterviewSessionItem, type InterviewQuestionItem, type AnalysisFrame } from '@/api/modules/interview';
import RichTextEditor from '@/components/common/RichTextEditor.vue';

const route = useRoute();
const router = useRouter();

const sessionInfo = ref<InterviewSessionItem | null>(null);
const currentQuestion = ref<InterviewQuestionItem | null>(null);
const userAnswer = ref('');
const streamedQuestionText = ref('');
const lastFeedback = ref('');
const isSubmitting = ref(false);
const isFinishing = ref(false);
const isRecording = ref(false);

const { modelsLoaded, emotions, loadModels, detectFace, getPrimaryEmotion } = useFaceApi();
const { isSpeaking, speak, cancel } = useTTS();

const videoRef = ref<HTMLVideoElement | null>(null);
const analysisInterval = ref<NodeJS.Timeout | null>(null);
let analysisFrames = ref<AnalysisFrame[]>([]);

const sortedEmotions = computed(() => {
  if (!emotions.value) return [];
  return emotions.value.asSortedArray().map(emotion => ({
      name: emotionMap[emotion.expression] || emotion.expression,
      score: Math.round(emotion.probability * 100),
  }));
});

const setupCamera = async () => {
  if (videoRef.value) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      videoRef.value.srcObject = stream;
      videoRef.value.onloadedmetadata = () => {
        startAnalysis();
      };
    } catch (err) {
      console.error("摄像头访问失败:", err);
      ElMessage.error("无法访问摄像头，请检查权限。");
    }
  }
};

const startAnalysis = () => {
  if (analysisInterval.value) clearInterval(analysisInterval.value);
  analysisInterval.value = setInterval(async () => {
    if (videoRef.value) {
      await detectFace(videoRef.value);
      if (emotions.value) {
        // [核心修正 1/3 & 2/3] 创建一个纯净的、类型安全的对象，解决所有类型冲突
        const plainEmotions: Record<string, number> = {};
        for (const key in emotionMap) {
          if (Object.prototype.hasOwnProperty.call(emotions.value, key)) {
            plainEmotions[key] = (emotions.value as any)[key];
          }
        }
        
        analysisFrames.value.push({
          timestamp: Date.now(),
          emotions: plainEmotions,
        });
      }
    }
  }, 1000);
};

const fetchSessionData = async () => {
  try {
    const sessionId = route.params.id as string;
    const res = await getInterviewSessionApi(sessionId);
    sessionInfo.value = res;
    const unanswered = res.questions.filter(q => !q.answer_text);
    if (unanswered.length > 0) {
      currentQuestion.value = unanswered[0];
    } else {
      ElMessage.info("面试已完成，正在跳转到报告页面...");
      router.push({ name: 'ReportDetail', params: { id: sessionId } });
    }
  } catch (error) {
    ElMessage.error("加载面试信息失败");
  }
};

const submitAnswer = async () => {
  if (!sessionInfo.value || !currentQuestion.value || !userAnswer.value.trim()) return;

  isSubmitting.value = true;
  streamedQuestionText.value = '';

  try {
    const result = await submitAnswerStreamApi(
      sessionInfo.value.id,
      {
        question_id: currentQuestion.value.id,
        answer_text: userAnswer.value,
        analysis_data: analysisFrames.value,
      },
      (chunk) => {
        streamedQuestionText.value += chunk;
      }
    );
    
    lastFeedback.value = result.feedback;
    
    if (result.isFinished) {
      confirmFinishInterview(true);
    } else {
      await fetchSessionData();
      userAnswer.value = '';
      analysisFrames.value = [];
    }

  } catch (error) {
    console.error("提交回答失败:", error);
    ElMessage.error("提交失败，请重试。");
  } finally {
    isSubmitting.value = false;
  }
};

const confirmFinishInterview = (isAutoFinish = false) => {
  const action = () => {
    isFinishing.value = true;
    if (sessionInfo.value) {
      ElMessage.success("面试结束，正在生成报告...");
      router.push({ name: 'ReportDetail', params: { id: sessionInfo.value.id } });
    }
  };

  if(isAutoFinish) {
    return action();
  }

  ElMessageBox.confirm('您确定要提前结束本次面试吗？', '确认结束', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(action).catch(() => {
    ElMessage.info('面试已继续');
  });
};

onMounted(async () => {
  await loadModels();
  await setupCamera();
  await fetchSessionData();
});

onUnmounted(() => {
  if (analysisInterval.value) clearInterval(analysisInterval.value);
  if (videoRef.value && videoRef.value.srcObject) {
    (videoRef.value.srcObject as MediaStream).getTracks().forEach(track => track.stop());
  }
  cancel();
});
</script>

<style scoped>
.interview-room-container {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
}
</style>