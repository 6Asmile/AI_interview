<template>
  <div class="interview-room-container">
    <el-row :gutter="20" class="main-content">
      <!-- 左侧：用户实时视频区域 -->
      <el-col :span="14">
        <div class="video-wrapper">
          <video ref="videoPlayer" class="video-player" autoplay playsinline muted></video>
          <div v-if="!cameraReady" class="video-placeholder">
            <el-icon :size="50" class="is-loading"><Loading /></el-icon>
            <p>摄像头加载中...</p>
          </div>
          <div class="status-dashboard" v-if="modelsLoaded && cameraReady">
            <div class="dashboard-section">
              <p class="section-title">情绪分析</p>
              <div v-if="emotionBars.length > 0" class="progress-group">
                <div v-for="emotion in emotionBars" :key="emotion.name" class="progress-item">
                  <span>{{ emotion.name }}</span>
                  <el-progress :percentage="emotion.percentage" :color="emotion.color" />
                </div>
              </div>
              <div v-else class="no-detection">未检测到面部</div>
            </div>
            <div class="dashboard-section">
              <p class="section-title">动作分析</p>
              <div class="action-item">
                <span>头部姿态: <strong>{{ actionState }}</strong></span>
              </div>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 右侧：面试官与交互区域 -->
      <el-col :span="10">
        <div class="interaction-wrapper">
          <div class="interviewer-panel">
            <img src="@/assets/images/image.png" alt="虚拟面试官" class="interviewer-avatar" />
            <div class="interviewer-info">
              <div class="interviewer-header">
                <p class="interviewer-name">AI 面试官</p>
                <el-tag v-if="isSpeaking" type="success" effect="dark" round>
                  <el-icon class="is-loading"><Loading /></el-icon>
                  正在发言...
                </el-tag>
              </div>
              <div class="question-feedback-area">
                <div class="question-header">
                  <span class="question-sequence">问题 {{ currentQuestion?.sequence }} / {{ sessionInfo.question_count }}</span>
                  <p class="question-text">{{ currentQuestion?.question_text }}</p>
                </div>
                <el-divider v-if="lastFeedback" />
                <div v-if="lastFeedback" class="feedback-header">
                  <p class="feedback-title">AI 简评 (上一问):</p>
                  <p class="feedback-text">{{ lastFeedback }}</p>
                </div>
              </div>
            </div>
          </div>
          <div class="answer-panel">
            <div class="answer-area">
              <VoiceRecorder
                v-if="!userAnswerText"
                @recognition-finished="handleRecognitionFinished"
                @recording-started="handleRecordingStarted"
                @recording-ended="handleRecordingEnded"
              />
              <div v-if="userAnswerText" class="transcript-area">
                <p class="transcript-title">您的回答 (语音识别结果):</p>
                <el-input v-model="userAnswerText" type="textarea" :rows="6" placeholder="您可以在这里对识别结果进行微调"/>
              </div>
            </div>
            <div class="controls-area">
              <el-button v-if="userAnswerText" type="success" size="large" @click="handleNextQuestion" :loading="submitting">确认并进入下一题</el-button>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
    <el-button class="end-interview-btn" type="danger" circle @click="handleEndInterview" title="结束面试">
      <el-icon :size="20"><SwitchButton /></el-icon>
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, Ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElLoading, ElMessage, ElMessageBox } from 'element-plus';
import { SwitchButton, Loading } from '@element-plus/icons-vue';
import VoiceRecorder from '@/components/common/VoiceRecorder.vue';
import { 
  getInterviewSessionApi, 
  submitAnswerApi, 
  type InterviewSessionItem, 
  type InterviewQuestionItem, 
  type SubmitAnswerData,
  type AnalysisFrame
} from '@/api/modules/interview';
import { getInterviewReportApi } from '@/api/modules/report';
import { useTTS } from '@/composables/useTTS';
import { useFaceApi, emotionMap } from '@/composables/useFaceApi';
import { FaceExpressions } from 'face-api.js';

const route = useRoute();
const router = useRouter();
const { isSpeaking, speak, cancel } = useTTS();
const { modelsLoaded, emotions, headPose, loadModels, detectFace, getActionState } = useFaceApi();

const loading = ref(true);
const submitting = ref(false);
const sessionInfo: Ref<Partial<InterviewSessionItem>> = ref({ job_position: '加载中...', question_count: 5 });
const allQuestions = ref<InterviewQuestionItem[]>([]);
const currentQuestion = ref<InterviewQuestionItem | null>(null);
const userAnswerText = ref('');
const lastFeedback = ref('');
const videoPlayer = ref<HTMLVideoElement | null>(null);
const cameraReady = ref(false);
let mediaStream: MediaStream | null = null;
const statusMap: Record<string, string> = {
  pending: '待开始', running: '进行中', finished: '已完成', canceled: '已取消',
};
let detectionInterval: number | null = null;
const isCollectingData = ref(false);
const analysisDataCollector = ref<AnalysisFrame[]>([]);
let answerStartTime = 0;

const emotionBars = computed(() => {
  if (!emotions.value) return [];
  return Object.entries(emotions.value).map(([key, value]) => {
    const numericValue = value as number;
    return { name: emotionMap[key] || key, percentage: Math.round(numericValue * 100), color: numericValue > 0.6 ? '#67C23A' : (numericValue > 0.3 ? '#E6A23C' : '#909399'),};
  }).filter(item => item.percentage > 1).sort((a, b) => b.percentage - a.percentage);
});
const actionState = computed(() => getActionState(headPose.value));

watch(currentQuestion, (newQuestion, oldQuestion) => {
  if (newQuestion && newQuestion.id !== oldQuestion?.id) {
    setTimeout(() => { speak(newQuestion.question_text); }, 500);
  }
});

onMounted(async () => {
  await Promise.all([loadModels(), startCamera()]);
  const sessionId = route.params.id as string;
  if (sessionId) { await fetchSessionDetails(sessionId); } 
  else { ElMessage.error('无效的面试会话，即将返回首页'); router.push('/dashboard'); }
});

onUnmounted(() => {
  stopCamera();
  cancel();
  if (detectionInterval) { clearInterval(detectionInterval); }
});

const startCamera = async () => {
  try {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      if (videoPlayer.value) {
        videoPlayer.value.srcObject = mediaStream;
        videoPlayer.value.onloadedmetadata = () => { cameraReady.value = true; startFaceDetection(); };
      }
    }
  } catch (error) { console.error("无法访问摄像头:", error); ElMessage.error("无法访问摄像头，请检查您的设备和浏览器权限。"); }
};

const stopCamera = () => {
  if (mediaStream) { mediaStream.getTracks().forEach(track => track.stop()); mediaStream = null; }
};

// 【核心修正】
const startFaceDetection = () => {
  if (detectionInterval) clearInterval(detectionInterval);
  detectionInterval = window.setInterval(async () => {
    if (videoPlayer.value && !videoPlayer.value.paused) {
      await detectFace(videoPlayer.value);
      if (isCollectingData.value && emotions.value) {
        // 创建一个纯净的情绪数据对象，不包含 asSortedArray 方法
        const pureEmotions: Record<string, number> = {
          neutral: emotions.value.neutral,
          happy: emotions.value.happy,
          sad: emotions.value.sad,
          angry: emotions.value.angry,
          fearful: emotions.value.fearful,
          disgusted: emotions.value.disgusted,
          surprised: emotions.value.surprised,
        };
        
        analysisDataCollector.value.push({
          timestamp: Date.now() - answerStartTime,
          emotions: pureEmotions, // 存储纯净的对象
          action: getActionState(headPose.value),
        });
      }
    }
  }, 500);
};

const fetchSessionDetails = async (sessionId: string) => {
  loading.value = true;
  try {
    const data = await getInterviewSessionApi(sessionId);
    sessionInfo.value = data;
    allQuestions.value = data.questions.sort((a, b) => a.sequence - b.sequence);
    if (allQuestions.value.length > 0) {
      currentQuestion.value = allQuestions.value[allQuestions.value.length - 1];
    } else {
      currentQuestion.value = null;
    }
  } catch (error) { console.error('获取面试详情失败', error); ElMessage.error('无法加载面试信息，即将返回首页'); router.push('/dashboard'); } 
  finally { loading.value = false; }
};

const handleRecordingStarted = () => {
  console.log("录音开始，启动数据收集...");
  analysisDataCollector.value = [];
  answerStartTime = Date.now();
  isCollectingData.value = true;
};

const handleRecordingEnded = () => {
  console.log("录音结束，停止数据收集。");
  isCollectingData.value = false;
  console.log("本轮收集到的分析数据:", analysisDataCollector.value);
};

const handleRecognitionFinished = (transcript: string) => {
  if (!transcript) { ElMessage.warning('未能识别到有效的语音内容'); return; }
  userAnswerText.value = transcript;
  ElMessage.success('语音识别完成！您可以在文本框中进行修改。');
};

const handleNextQuestion = async () => {
  if (!currentQuestion.value || !userAnswerText.value) { ElMessage.warning('回答内容不能为空'); return; }
  submitting.value = true;
  ElMessage.info('正在提交回答...');
  try {
    const sessionId = route.params.id as string;
    const data: SubmitAnswerData = {
      question_id: currentQuestion.value.id,
      answer_text: userAnswerText.value,
      analysis_data: analysisDataCollector.value,
    };
    const res = await submitAnswerApi(sessionId, data);
    
    lastFeedback.value = res.feedback;
    
    if (res.interview_finished) {
      currentQuestion.value = null;
      ElMessageBox.alert('您已完成所有问题！现在可以点击右下角的“结束面试”按钮来生成您的专属面试报告。', '答题结束', {
        confirmButtonText: '好的',
        type: 'success',
      });
      userAnswerText.value = '（所有问题已完成）';
    } else if (res.next_question) {
      allQuestions.value.push(res.next_question);
      currentQuestion.value = res.next_question;
      userAnswerText.value = '';
      ElMessage.success('收到简评，请看下一个问题');
    }
  } catch (error) { console.error('提交回答失败', error); ElMessage.error('提交回答失败，请稍后再试'); } 
  finally { submitting.value = false; }
};

const handleEndInterview = () => {
  ElMessageBox.confirm('您确定要结束面试并生成最终报告吗？', '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
    .then(async () => {
      const loading = ElLoading.service({ text: '正在汇总分析并生成报告...' });
      try {
        const sessionId = route.params.id as string;
        await getInterviewReportApi(sessionId);
        loading.close();
        ElMessage.success('面试报告已生成！');
        router.push({ name: 'ReportDetail', params: { id: sessionId } });
      } catch (error) {
        loading.close();
        console.error('生成报告失败', error);
        ElMessage.error('生成报告失败，请稍后在历史记录中重试。');
      }
    });
};
</script>

<style scoped>
/* 所有样式保持不变 */
.interview-room-container { width: 100%; height: 100vh; padding: 20px; box-sizing: border-box; position: relative; overflow: hidden; }
.main-content { height: 100%; }
.el-col { height: 100%; }
.video-wrapper { width: 100%; height: 100%; background-color: #000; border-radius: 12px; overflow: hidden; position: relative; display: flex; justify-content: center; align-items: center; }
.video-player { width: 100%; height: 100%; object-fit: cover; transform: rotateY(180deg); }
.video-placeholder { position: absolute; color: #fff; text-align: center; }
.status-dashboard { position: absolute; top: 15px; right: 15px; width: 220px; background-color: rgba(0, 0, 0, 0.6); color: white; padding: 15px; border-radius: 8px; backdrop-filter: blur(8px); border: 1px solid rgba(255, 255, 255, 0.1); display: flex; flex-direction: column; gap: 15px; }
.section-title { font-weight: bold; margin-bottom: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.2); padding-bottom: 5px; margin-top: 0; }
.progress-group { display: flex; flex-direction: column; gap: 8px; }
.progress-item { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.progress-item span { width: 50px; text-align: right; }
.progress-item .el-progress { flex: 1; }
.no-detection { font-size: 14px; color: #909399; text-align: center; padding: 10px 0; }
.action-item { font-size: 14px; }
.action-item span { color: #c0c4cc; margin-right: 5px; }
.action-item strong { text-transform: capitalize; }
.interaction-wrapper { height: 100%; display: flex; flex-direction: column; gap: 20px; }
.interviewer-panel { flex-grow: 1; min-height: 200px; background: #ffffff; border-radius: 12px; padding: 20px; display: flex; gap: 20px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); }
.interviewer-avatar { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; }
.interviewer-info { flex: 1; display: flex; flex-direction: column; }
.interviewer-header { display: flex; justify-content: space-between; align-items: center; }
.interviewer-name { font-weight: bold; font-size: 1.2rem; margin: 0; }
.question-feedback-area { margin-top: 15px; flex-grow: 1; overflow-y: auto; }
.question-header { margin-top: 0; }
.question-sequence { font-size: 1rem; color: #909399; }
.question-text { font-size: 1.25rem; font-weight: 500; color: #303133; margin-top: 8px; line-height: 1.6; }
.feedback-header { margin-top: 10px; }
.feedback-title { font-weight: bold; color: #409EFF; }
.feedback-text { font-size: 0.9rem; color: #606266; margin-top: 5px; line-height: 1.5; }
.answer-panel { flex-grow: 1; background: #ffffff; border-radius: 12px; padding: 20px; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); }
.answer-area { display: flex; justify-content: center; align-items: center; flex-grow: 1; }
.transcript-area { width: 100%; }
.transcript-title { font-weight: 500; margin-bottom: 10px; color: #606266; }
.controls-area { margin-top: 20px; text-align: center; }
.end-interview-btn { position: absolute; bottom: 30px; right: 30px; width: 60px; height: 60px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); }
</style>