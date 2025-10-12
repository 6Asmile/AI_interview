<template>
  <div class="interview-room" v-loading="isLoading" element-loading-text="正在加载面试间...">
    <div class="main-content">
      <div class="video-panel">
        <video ref="videoEl" autoplay muted playsinline class="video-feed"></video>
        <div v-if="!modelsLoaded" class="video-overlay">摄像头加载中...</div>

        <div v-if="modelsLoaded" class="analysis-overlay">
          <div class="analysis-box">
            <h4>情绪分析</h4>
            <p class="primary-emotion">{{ getPrimaryEmotion(emotions) }}</p>
            <div class="emotion-bars">
               <div v-for="emotion in formattedEmotions" :key="emotion.name" class="emotion-bar-item">
                 <span class="emotion-name">{{ emotion.name }}</span>
                 <div class="emotion-bar-wrapper">
                   <div class="emotion-bar" :style="{ width: emotion.score + '%' }"></div>
                 </div>
                 <span class="emotion-score">{{ emotion.score }}%</span>
               </div>
            </div>
          </div>
          <div class="analysis-box">
            <h4>动作分析</h4>
            <p>头部姿态: {{ getActionState(headPose) }}</p>
          </div>
        </div>
      </div>

      <div class="interaction-panel">
        <div class="ai-panel">
          <div class="ai-header">
            <div>
              <img src="@/assets/images/image.png" alt="AI Avatar" class="ai-avatar">
              <div>
                <h3>AI 面试官</h3>
                <p class="ai-status" v-if="isSpeaking">正在发言...</p>
              </div>
            </div>
            <el-button type="danger" @click="confirmFinishInterview" :disabled="isFinishing">
              {{ isFinishing ? '正在结束...' : '结束面试' }}
            </el-button>
          </div>

          <div class="question-display">
            <h4>问题 {{ currentQuestion?.sequence }} / {{ sessionInfo?.question_count }}</h4>
            <p>{{ streamedQuestionText || currentQuestion?.question_text }}</p>
          </div>

          <div class="feedback-display" v-if="lastFeedback">
            <h4>AI 简评 (上一问):</h4>
            <p>{{ lastFeedback }}</p>
          </div>
        </div>

        <div class="user-panel">
          <el-input
            type="textarea"
            :rows="4"
            placeholder="请在此处回答，或使用下方的语音输入按钮"
            v-model="userAnswer"
            :readonly="isRecording"
          ></el-input>
          <div class="user-actions">
            <VoiceRecorder
              @recording-started="isRecording = true"
              @recording-ended="isRecording = false"
              @recognition-finished="handleRecognitionFinished"
            />
            <el-button
              type="primary"
              @click="submitAnswer"
              :disabled="isSubmitting || isRecording || !userAnswer.trim()"
              :loading="isSubmitting"
            >
              {{ isSubmitting ? '处理中...' : '确认并进入下一题' }}
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getInterviewSessionApi, getInterviewReportApi, type InterviewSessionItem, type InterviewQuestionItem, type AnalysisFrame, type SubmitAnswerData } from '@/api/modules/interview';
import { useTTS } from '@/composables/useTTS';
import { useFaceApi, emotionMap } from '@/composables/useFaceApi';
import VoiceRecorder from '@/components/common/VoiceRecorder.vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const route = useRoute();
const router = useRouter();
const { isSpeaking, speak, cancel } = useTTS();
const { modelsLoaded, emotions, headPose, loadModels, detectFace, getPrimaryEmotion, getActionState } = useFaceApi();

const isLoading = ref(true);
const isSubmitting = ref(false);
const isRecording = ref(false);
const isFinishing = ref(false);
const sessionInfo = ref<InterviewSessionItem | null>(null);
const currentQuestion = ref<InterviewQuestionItem | null>(null);
const lastFeedback = ref('');
const userAnswer = ref('');
const streamedQuestionText = ref('');
const videoEl = ref<HTMLVideoElement | null>(null);
let detectionInterval: any = null;

const analysisFrames = ref<AnalysisFrame[]>([]);


const formattedEmotions = computed(() => {
  if (!emotions.value) return [];
  return Object.entries(emotions.value)
    .map(([key, value]) => ({
      name: emotionMap[key] || key,
      score: Math.round(Number(value) * 100),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);
});

const fetchSessionData = async () => {
  isLoading.value = true;
  try {
    const sessionId = route.params.id as string;
    if (!sessionId) {
      ElMessage.error('无效的面试ID');
      router.push({ name: 'Dashboard' });
      return;
    }
    const data = await getInterviewSessionApi(sessionId);
    sessionInfo.value = data;
    const unansweredQuestion = data.questions.find(q => !q.answer_text);
    if (unansweredQuestion) {
      currentQuestion.value = unansweredQuestion;
      if (unansweredQuestion.question_text) {
        speak(unansweredQuestion.question_text);
      }
    } else if (data.status === 'finished') {
      ElMessage.success('面试已完成！正在跳转到报告页面...');
      router.push({ name: 'ReportDetail', params: { id: sessionId } });
    } else {
      ElMessage.warning('找不到当前问题，请联系管理员。');
    }
  } catch (error) {
    ElMessage.error('加载面试信息失败');
    router.push({ name: 'Dashboard' });
  } finally {
    isLoading.value = false;
  }
};

const handleRecognitionFinished = (transcript: string) => {
  userAnswer.value = userAnswer.value ? `${userAnswer.value} ${transcript}` : transcript;
};

const submitAnswer = async () => {
  if (!currentQuestion.value || !sessionInfo.value) return;

  isSubmitting.value = true;
  cancel();
  lastFeedback.value = 'AI 正在分析您的回答...';
  streamedQuestionText.value = '';

  try {
    const sessionId = sessionInfo.value.id;
    
    // 【核心修正】确保 data 对象被正确、完整地定义
    const data: SubmitAnswerData = {
      question_id: currentQuestion.value.id,
      answer_text: userAnswer.value,
      analysis_data: analysisFrames.value,
    };
    analysisFrames.value = [];

    const baseUrl = import.meta.env.VITE_API_BASE_URL.replace(/\/api\/v1\/?$/, '');
    const finalUrl = `${baseUrl}/api/v1/interviews/${sessionId}/submit-answer-stream/`;
    
    const response = await fetch(finalUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      // 【核心修正】确保使用正确的 data 对象
      body: JSON.stringify(data),
    });

    if (!response.ok) throw new Error('服务器响应错误');

    const encodedFeedback = response.headers.get('X-Feedback');
    if (encodedFeedback) {
      lastFeedback.value = decodeURIComponent(encodedFeedback);
    } else {
      lastFeedback.value = '简评生成失败，请继续。';
    }

    if (response.headers.get('Content-Type')?.includes('application/json')) {
      const result = await response.json();
      if (result.interview_finished) {
        lastFeedback.value = result.feedback;
        ElMessage.success('恭喜您完成所有问题！报告生成中...');
        streamedQuestionText.value = '面试已结束，正在为您生成报告...';
        setTimeout(() => {
          router.push({ name: 'ReportDetail', params: { id: sessionId } });
        }, 3000);
        return;
      }
    }

    if (response.body) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        streamedQuestionText.value += chunk;
      }
      speak(streamedQuestionText.value);
    }
    
    userAnswer.value = '';
    setTimeout(async () => {
        const updatedSession = await getInterviewSessionApi(sessionId);
        sessionInfo.value = updatedSession;
        currentQuestion.value = updatedSession.questions.find(q => !q.answer_text) || updatedSession.questions[updatedSession.questions.length - 1];
    }, 500);

  } catch (error) {
    console.error("提交答案时发生错误:", error);
    ElMessage.error('提交答案时发生错误');
    lastFeedback.value = '';
    streamedQuestionText.value = '出现错误，请刷新页面重试。';
  } finally {
    isSubmitting.value = false;
  }
};

const finishInterview = async () => {
  if (!sessionInfo.value) return;
  isFinishing.value = true;
  try {
    await getInterviewReportApi(sessionInfo.value.id);
    ElMessage.success('面试已结束，正在为您生成最终报告...');
    router.push({ name: 'ReportDetail', params: { id: sessionInfo.value.id } });
  } catch (error) {
    ElMessage.error('结束面试失败，请稍后再试。');
  } finally {
    isFinishing.value = false;
  }
};

const confirmFinishInterview = () => {
  ElMessageBox.confirm('您确定要提前结束本次面试吗？结束后将直接生成报告。', '确认结束', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(finishInterview);
};

const startDetection = () => {
  if (detectionInterval) clearInterval(detectionInterval);
  detectionInterval = setInterval(async () => {
    if (videoEl.value) {
      await detectFace(videoEl.value);
      if (emotions.value && headPose.value) {
        const pureEmotions: Record<string, number> = {
          neutral: emotions.value.neutral, happy: emotions.value.happy,
          sad: emotions.value.sad, angry: emotions.value.angry,
          fearful: emotions.value.fearful, disgusted: emotions.value.disgusted,
          surprised: emotions.value.surprised,
        };
        analysisFrames.value.push({
          timestamp: Date.now(),
          emotions: pureEmotions,
          action: getActionState(headPose.value),
        });
      }
    }
  }, 500);
};

const setupCamera = async () => {
  if (videoEl.value) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      videoEl.value.srcObject = stream;
      videoEl.value.onloadedmetadata = () => {
        nextTick(async () => {
          if (!modelsLoaded.value) await loadModels();
          if (modelsLoaded.value) {
            startDetection();
          }
        });
      };
    } catch (err) {
      ElMessage.error('无法访问摄像头');
      console.error(err);
    }
  }
};

onMounted(() => {
  fetchSessionData();
  setupCamera();
});

onUnmounted(() => {
  if (detectionInterval) clearInterval(detectionInterval);
  if (videoEl.value && videoEl.value.srcObject) {
    (videoEl.value.srcObject as MediaStream).getTracks().forEach(track => track.stop());
  }
  cancel();
});
</script>




<style scoped>
.interview-room {
  display: flex;
  justify-content: center;
  align-items: center;
  height: calc(100vh - 60px);
  background-color: #f5f7fa;
  padding: 20px;
}

.main-content {
  display: flex;
  gap: 20px;
  width: 100%;
  max-width: 1400px;
  height: 100%;
}

.video-panel {
  flex-basis: 50%;
  position: relative;
  background-color: #000;
  border-radius: 8px;
  overflow: hidden;
}

.video-feed {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: rotateY(180deg);
}

.video-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  color: white;
  background-color: rgba(0,0,0,0.5);
}

.analysis-overlay {
    position: absolute;
    top: 20px;
    left: 20px;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.analysis-box {
    background-color: rgba(0,0,0,0.6);
    color: white;
    padding: 10px 15px;
    border-radius: 6px;
}

.analysis-box h4 {
    margin: 0 0 5px 0;
    font-size: 14px;
}

.interaction-panel {
  flex-basis: 50%;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.ai-panel, .user-panel {
  background-color: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 12px 0 rgba(0,0,0,0.1);
}

.ai-panel {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
}

.user-panel {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

.question-display {
    flex-grow: 1;
}

.feedback-display {
    border-top: 1px solid #ebeef5;
    padding-top: 15px;
    margin-top: 15px;
}

h3, h4 {
    margin-top: 0;
}

.user-actions {
    margin-top: 15px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
}
.ai-header {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 20px;
}
.ai-avatar {
  width: 50px;
  height: 50px;
  border-radius: 50%;
}
.ai-status {
  color: #409EFF;
  font-size: 14px;
}

/* 【新增】情绪分析条形图样式 */
.emotion-bars {
  font-size: 12px;
}
.emotion-bar-item {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 2px;
}
.emotion-name {
  width: 30px;
}
.emotion-bar-wrapper {
  flex-grow: 1;
  height: 10px;
  background-color: rgba(255, 255, 255, 0.2);
  border-radius: 5px;
}
.emotion-bar {
  height: 100%;
  background-color: #67c23a;
  border-radius: 5px;
  transition: width 0.3s ease;
}
.emotion-score {
  width: 30px;
  text-align: right;
}
.primary-emotion {
  font-weight: bold;
  font-size: 16px;
  margin-bottom: 10px;
}
.emotion-bar-item {
  display: flex;
  align-items: center;
  gap: 8px; /* 增加间距 */
  margin-bottom: 4px;
}
.emotion-name {
  width: 40px; /* 统一名称宽度 */
  flex-shrink: 0;
}
.emotion-score {
  width: 35px; /* 统一分数宽度 */
  text-align: right;
  flex-shrink: 0;
}
.primary-emotion {
  font-weight: bold;
  font-size: 16px;
  margin-bottom: 10px;
}
</style>