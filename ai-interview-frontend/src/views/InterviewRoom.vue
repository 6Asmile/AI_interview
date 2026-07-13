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

      <main class="center-panel glass-card p-6 flex flex-col">
        <div class="question-display-area flex-grow flex flex-col gap-4">
          <div class="ai-presenter flex items-start gap-4">
            <el-avatar :src="aiAvatar" :size="48" class="flex-shrink-0 shadow-lg" />
            <div class="flex-grow">
              <div class="question-header flex items-center gap-4">
                <h2 class="font-bold text-xl text-gray-800">AI 面试官</h2>
                <span class="stage-chip">{{ stageLabel(sessionInfo?.current_stage) }}</span>
                <el-tooltip :content="speechTooltip" placement="top" :disabled="!currentQuestion">
                  <el-button v-if="currentQuestion" @click="toggleSpeech" :icon="speechIcon" type="primary" circle />
                </el-tooltip>
              </div>
              <p class="question-progress text-xs text-gray-500 mt-1">
                <template v-if="isAdaptiveInterview">第 {{ currentQuestion?.sequence }} 轮 · 预计剩余 {{ remainingMinutes }} 分钟</template>
                <template v-else>问题 {{ currentQuestion?.sequence }} / {{ sessionInfo?.question_count }}</template>
              </p>
            </div>
          </div>
          
          <div class="question-text-box bg-white/60 p-5 rounded-lg min-h-[150px] text-gray-900 text-lg leading-relaxed overflow-y-auto flex items-center">
            <p>{{ displayedQuestionText }}</p>
          </div>

          <div v-if="submissionState !== 'idle' || submitErrorText" class="question-status-banner" :class="`question-status-banner--${submissionState}`">
            <strong>{{ submissionStatusTitle }}</strong>
            <p>{{ submissionStatusDescription }}</p>
            <div v-if="activeGenerationJob" class="generation-job-panel">
              <div class="generation-job-meta">
                <span>生成任务 #{{ activeGenerationJob.id }}</span>
                <strong>{{ generationJobStatusLabel(activeGenerationJob.status) }}</strong>
              </div>
              <p v-if="generationJobRecoveryHint" class="generation-job-hint">{{ generationJobRecoveryHint }}</p>
              <p v-if="activeGenerationJob.partial_text" class="generation-job-preview">{{ activeGenerationJob.partial_text }}</p>
              <p v-else-if="activeGenerationJob.error_message" class="generation-job-preview">{{ activeGenerationJob.error_message }}</p>
            </div>
            <div v-if="canRegenerateNextQuestion" class="status-action-row">
              <el-button size="small" plain :loading="isRefreshingGenerationJob" @click="refreshGenerationJobs(recoveryQuestionId || undefined)">
                刷新生成状态
              </el-button>
              <el-button size="small" type="primary" plain :loading="isRegeneratingNextQuestion" @click="regenerateNextQuestion">
                保留回答，重新生成下一题
              </el-button>
            </div>
          </div>

          <div class="answer-guidance-card">
            <div class="answer-guidance-header">
              <strong>答题检查项</strong>
              <span>{{ stageLabel(sessionInfo?.current_stage) }}</span>
            </div>
            <div class="answer-guidance-tags">
              <span v-for="item in answerChecklist" :key="item">{{ item }}</span>
            </div>
            <p class="answer-guidance-copy">{{ answerGuidanceText }}</p>
          </div>

          <div v-if="!isRealisticMode && lastFeedbackText" class="feedback-summary-bar">
            <div class="feedback-summary-main">
              <span class="feedback-dot"></span>
              <div>
                <strong>上一问已点评</strong>
                <p>{{ lastAnswerFeedback?.follow_up_target || '点击查看完整点评和下一步追问方向' }}</p>
              </div>
            </div>
            <span v-if="lastAnswerFeedback?.quality_score !== undefined" class="quality-pill">
              {{ lastAnswerFeedback.quality_score }} 分 · {{ answerLevelLabel(lastAnswerFeedback.answer_level) }}
            </span>
            <el-button size="small" type="success" plain @click="showFeedbackDialog = true">查看详情</el-button>
          </div>
        </div>
        
        <div class="answer-input-area mt-6">
          <div class="answer-mode-row">
            <el-radio-group v-model="answerInputMode" size="small">
              <el-radio-button label="text">文本回答</el-radio-button>
              <el-radio-button label="voice">语音回答</el-radio-button>
            </el-radio-group>
            <span class="answer-mode-hint">
              {{ answerInputMode === 'voice' ? '停止录音后会进行后端 ASR，转写文本可编辑确认' : '可直接输入，也可切换语音回答' }}
            </span>
          </div>
          <RichTextEditor v-model="userAnswer" placeholder="请在这里输入您的回答，或使用下方的语音输入功能..." />
          <div class="answer-support-row">
            <span v-if="draftRestored" class="draft-indicator">已恢复本题草稿</span>
            <span v-else-if="hasDraft" class="draft-indicator draft-indicator--soft">草稿已自动保存</span>
            <span class="answer-length-indicator">正文约 {{ answerPlainText.length }} 字</span>
            <span v-if="audioArtifactId" class="draft-indicator draft-indicator--soft">已关联语音记录</span>
          </div>
          <div v-if="interimTranscript" class="interim-transcript-card">
            <span>浏览器实时转写</span>
            <p>{{ interimTranscript }}</p>
          </div>
          <div v-if="backendAsrStatus !== 'idle' || backendAsrError" class="interim-transcript-card">
            <span>后端 ASR：{{ backendAsrStatus }}</span>
            <p v-if="backendAsrError">{{ backendAsrError }}</p>
            <p v-else>{{ backendAsrStatus === 'transcribing' ? '正在使用已配置 ASR 模型生成最终转写...' : '语音采集中，停止后生成最终转写。' }}</p>
          </div>
          <div class="speech-control-bar flex items-center justify-center gap-4 p-3 mt-2 bg-white/50 rounded-lg">
            <el-tooltip content="开始语音输入" placement="top" :disabled="isListening">
              <el-button @click="answerInputMode === 'voice' ? startVoiceAnswer() : startSpeech()" :disabled="isListening || backendAsrStatus === 'listening' || backendAsrStatus === 'transcribing'" type="primary" circle :icon="Microphone" />
            </el-tooltip>
            <el-tooltip content="停止语音输入" placement="top" :disabled="!isListening">
              <el-button @click="answerInputMode === 'voice' ? stopVoiceAnswer() : stopSpeech()" :disabled="!isListening && backendAsrStatus !== 'listening'" type="danger" circle :icon="SwitchButton" />
            </el-tooltip>
            <span v-if="isListening || backendAsrStatus === 'listening'" class="text-sm text-red-500 animate-pulse">正在采集语音，停止后请确认转写文本</span>
            <span v-else-if="backendAsrStatus === 'transcribing'" class="text-sm text-blue-500">后端 ASR 正在转写...</span>
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
           <el-button type="primary" size="large" @click="submitAnswer" :loading="isSubmitting" :disabled="!canSubmitAnswer" class="w-full transition-all duration-300 hover:shadow-lg hover:-translate-y-1">
            {{ submitButtonText }}
          </el-button>
          <el-button type="danger" @click="() => confirmFinishInterview()" :loading="isFinishing" :disabled="isSubmitting" class="w-full" plain>
            {{ isFinishing ? '正在结束...' : '结束面试' }}
          </el-button>
        </div>
        <div class="progress-card glass-card p-4">
          <h3 class="uppercase text-xs font-semibold text-gray-400 tracking-wider mb-3">面试进度</h3>
          <div class="progress-ring-row">
            <div class="progress-ring">{{ roomProgress }}%</div>
            <div>
              <strong v-if="isAdaptiveInterview">{{ answeredCount }} 轮</strong>
              <strong v-else>{{ answeredCount }} / {{ questionTotal || '-' }}</strong>
              <p>{{ isAdaptiveInterview ? '已完成回答' : '已完成问题' }}</p>
            </div>
          </div>
          <el-progress :percentage="roomProgress" :stroke-width="8" :show-text="false" />
        </div>
        <div v-if="!isRealisticMode" class="agent-status glass-card p-4">
          <h3 class="uppercase text-xs font-semibold text-gray-400 tracking-wider mb-3">Agent 状态</h3>
          <div class="agent-state-grid">
            <div>
              <span>阶段</span>
              <strong>{{ stageLabel(sessionInfo?.current_stage) }}</strong>
            </div>
            <div>
              <span>动态难度</span>
              <strong>{{ difficultyLabel(agentMemory?.adaptive_difficulty) }}</strong>
            </div>
          </div>
          <div class="agent-quality" v-if="agentMemory?.last_quality_score !== undefined">
            <span>上一题质量</span>
            <el-progress :percentage="agentMemory.last_quality_score" :stroke-width="7" />
          </div>
          <p v-if="agentMemory?.follow_up_target" class="agent-target">{{ agentMemory.follow_up_target }}</p>
          <div v-if="agentPendingTopics.length" class="agent-tags">
            <span v-for="topic in agentPendingTopics" :key="topic">{{ topic }}</span>
          </div>
        </div>
        <div v-if="!isRealisticMode" class="focus-card glass-card p-4">
          <h3 class="uppercase text-xs font-semibold text-gray-400 tracking-wider mb-3">当前答题重点</h3>
          <p>{{ agentMemory?.question_strategy || agentMemory?.follow_up_target || '先给结论，再补充案例、指标和个人贡献。' }}</p>
        </div>
      </aside>
    </div>
    <el-dialog v-model="showFeedbackDialog" title="上一问 AI 点评" width="560px" class="feedback-dialog">
      <div class="feedback-dialog-body">
        <div class="dialog-score-row" v-if="lastAnswerFeedback?.quality_score !== undefined">
          <span class="quality-pill quality-pill--large">
            {{ lastAnswerFeedback.quality_score }} 分 · {{ answerLevelLabel(lastAnswerFeedback.answer_level) }}
          </span>
        </div>
        <section>
          <h4>简评</h4>
          <p>{{ lastFeedbackText }}</p>
        </section>
        <section v-if="lastAnswerFeedback?.follow_up_target">
          <h4>追问方向</h4>
          <p>{{ lastAnswerFeedback.follow_up_target }}</p>
        </section>
        <section v-if="lastAnswerFeedback?.follow_up_reason">
          <h4>为什么这样追问</h4>
          <p>{{ lastAnswerFeedback.follow_up_reason }}</p>
        </section>
      </div>
    </el-dialog>

    <el-dialog v-model="finishFlowVisible" title="结束面试处理中" width="520px" :close-on-click-modal="false" :show-close="!isFinishing">
      <div class="finish-flow-dialog">
        <div v-for="step in finishSteps" :key="step.key" class="finish-step" :class="`finish-step--${step.status}`">
          <span class="finish-step-index">{{ step.index }}</span>
          <div>
            <strong>{{ step.title }}</strong>
            <p>{{ step.description }}</p>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button v-if="!isFinishing" @click="finishFlowVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, shallowRef, defineAsyncComponent } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/store/modules/auth';
import { useFaceApi, emotionMap } from '@/composables/useFaceApi';
import { useTTS } from '@/composables/useTTS';
import { useSpeechRecognition } from '@/composables/useSpeechRecognition';
import { ElMessage, ElMessageBox, ElButton, ElProgress, ElIcon, ElAvatar, ElTooltip } from 'element-plus';
import { VideoPlay, VideoPause, RefreshRight, Microphone, SwitchButton, VideoCamera } from '@element-plus/icons-vue';
import { getInterviewSessionApi, submitAnswerStreamApi, finishInterviewApi, regenerateNextQuestionApi, generateQuestionTTSApi, getInterviewQuestionGenerationJobsApi, SubmitAnswerStreamError, type InterviewSessionItem, type InterviewQuestionItem, type AnalysisFrame, type AnswerFeedback, type InterviewQuestionGenerationJobItem } from '@/api/modules/interview';
import { VideoUploader } from '@/api/modules/videoUpload';
import aiAvatar from '@/assets/images/image.png';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const RichTextEditor = defineAsyncComponent(() => import('@/components/common/RichTextEditor.vue'));
type SubmissionState = 'idle' | 'evaluating' | 'streaming_next' | 'finishing' | 'error';
type AnswerInputMode = 'text' | 'voice';

const sessionInfo = ref<InterviewSessionItem | null>(null);
const currentQuestion = ref<InterviewQuestionItem | null>(null);
const userAnswer = ref('');
const answerInputMode = ref<AnswerInputMode>('text');
const streamedQuestionText = ref('');
const lastFeedback = ref('');
const lastAnswerFeedback = ref<AnswerFeedback | null>(null);
const isSubmitting = ref(false);
const isFinishing = ref(false);
const submissionState = ref<SubmissionState>('idle');
const submitErrorText = ref('');
const recoveryQuestionId = ref<number | null>(null);
const isRegeneratingNextQuestion = ref(false);
const isRefreshingGenerationJob = ref(false);
const generationJobs = ref<InterviewQuestionGenerationJobItem[]>([]);
const generationPollTimer = ref<ReturnType<typeof window.setInterval> | null>(null);
const draftRestored = ref(false);
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
const speechSocket = ref<WebSocket | null>(null);
const answerAudioRecorder = ref<MediaRecorder | null>(null);
const answerAudioStream = ref<MediaStream | null>(null);
const backendAsrStatus = ref<'idle' | 'connecting' | 'listening' | 'transcribing' | 'completed' | 'failed'>('idle');
const backendAsrError = ref('');
const audioArtifactId = ref('');
const asrTranscriptMeta = ref<Record<string, any>>({});
const backendQuestionAudio = ref<HTMLAudioElement | null>(null);
const isBackendTtsPlaying = ref(false);
const SHORT_ANSWER_THRESHOLD = 24;
const draftStorageKey = computed(() => {
  if (!sessionInfo.value?.id || !currentQuestion.value?.id) return '';
  return `interview-answer-draft:${sessionInfo.value.id}:${currentQuestion.value.id}`;
});
const handleSpeechResult = (transcript: string) => {
  if (userAnswer.value.endsWith('</p>')) { userAnswer.value = userAnswer.value.slice(0, -4) + transcript + '</p>'; } 
  else { userAnswer.value += transcript; }
};
const { isListening, interimTranscript, start: startSpeech, stop: stopSpeech, clearInterimTranscript } = useSpeechRecognition(handleSpeechResult);
const isRecording = computed(() => isListening.value || backendAsrStatus.value === 'listening' || backendAsrStatus.value === 'transcribing');
const speechIcon = shallowRef(VideoPlay);
const speechTooltip = ref('播放问题');
const showFeedbackDialog = ref(false);
type FinishStepStatus = 'pending' | 'active' | 'done' | 'error' | 'skipped';
const finishFlowVisible = ref(false);
const clockTick = ref(Date.now());
let clockTimer: ReturnType<typeof window.setInterval> | null = null;
const finishSteps = ref([
  { key: 'stop_recording', index: 1, title: '停止录制', description: '等待浏览器写入最后一段录像数据', status: 'pending' as FinishStepStatus },
  { key: 'upload_recording', index: 2, title: '上传录像', description: '上传原始录像，压缩会在后台继续处理', status: 'pending' as FinishStepStatus },
  { key: 'generate_report', index: 3, title: '生成报告', description: '整理问答、评分和验证链路', status: 'pending' as FinishStepStatus },
  { key: 'navigate', index: 4, title: '跳转报告', description: '打开本次面试评估报告', status: 'pending' as FinishStepStatus },
]);
const agentMemory = computed(() => sessionInfo.value?.memory_summary || {});
const agentPendingTopics = computed(() => {
  const topics = sessionInfo.value?.pending_topics || agentMemory.value?.pending_topics || [];
  return topics.slice(0, 3);
});
const answeredCount = computed(() => sessionInfo.value?.questions.filter(q => q.answer_text).length || 0);
const questionTotal = computed(() => sessionInfo.value?.question_count || sessionInfo.value?.questions.length || 0);
const isAdaptiveInterview = computed(() => sessionInfo.value?.progress_mode === 'time_and_coverage');
const isRealisticMode = computed(() => sessionInfo.value?.experience_mode !== 'coaching');
const liveElapsedSeconds = computed(() => {
  clockTick.value;
  if (!sessionInfo.value?.started_at) return sessionInfo.value?.elapsed_seconds || 0;
  const startedAt = new Date(sessionInfo.value.started_at).getTime();
  return Math.max(sessionInfo.value?.elapsed_seconds || 0, Math.floor((Date.now() - startedAt) / 1000));
});
const remainingMinutes = computed(() => {
  const targetSeconds = (sessionInfo.value?.target_duration_minutes || 30) * 60;
  return Math.max(0, Math.ceil((targetSeconds - liveElapsedSeconds.value) / 60));
});
const roomProgress = computed(() => {
  if (isAdaptiveInterview.value) {
    const targetSeconds = (sessionInfo.value?.target_duration_minutes || 30) * 60;
    return Math.min(95, Math.round((liveElapsedSeconds.value / Math.max(1, targetSeconds)) * 100));
  }
  if (!questionTotal.value) return 0;
  const progressBase = Math.max(answeredCount.value, (currentQuestion.value?.sequence || 1) - 1);
  return Math.min(100, Math.round((progressBase / questionTotal.value) * 100));
});
const displayedQuestionText = computed(() => {
  return streamedQuestionText.value || currentQuestion.value?.question_text || '正在准备问题...';
});
const lastFeedbackText = computed(() => {
  return lastAnswerFeedback.value?.feedback || (lastFeedback.value ? decodeURIComponent(lastFeedback.value) : '');
});
const answerPlainText = computed(() => {
  const tempDiv = document.createElement('div');
  tempDiv.innerHTML = userAnswer.value;
  return (tempDiv.textContent || tempDiv.innerText || '').replace(/\s+/g, ' ').trim();
});
const hasDraft = computed(() => Boolean(answerPlainText.value));
const canSubmitAnswer = computed(() => {
  return Boolean(answerPlainText.value) && !isSubmitting.value && submissionState.value !== 'finishing';
});
const canRegenerateNextQuestion = computed(() => {
  return submissionState.value === 'error'
    && Boolean(sessionInfo.value?.id && recoveryQuestionId.value)
    && (!activeGenerationJob.value || activeGenerationJob.value.status !== 'running' || Boolean(activeGenerationJob.value.can_retry));
});
const activeGenerationJob = computed(() => {
  if (!generationJobs.value.length) return null;
  if (recoveryQuestionId.value) {
    const related = generationJobs.value.find(job => job.answered_question === recoveryQuestionId.value);
    if (related) return related;
  }
  return generationJobs.value.find(job => job.status === 'running') || null;
});
const generationJobRecoveryHint = computed(() => {
  const job = activeGenerationJob.value;
  if (!job) return '';
  if (job.status === 'running' && job.can_retry) {
    return '生成任务已超过安全等待时间，可以保留已保存回答重新生成下一题。';
  }
  if (job.status === 'running' && typeof job.retry_after_seconds === 'number' && job.retry_after_seconds > 0) {
    return `后端仍在生成，约 ${job.retry_after_seconds} 秒后仍无结果可自动恢复。`;
  }
  if (job.status === 'failed' && job.can_retry) {
    return '本次生成失败，可以直接保留回答重新生成下一题。';
  }
  return '';
});
const submitButtonText = computed(() => {
  const labelMap: Record<SubmissionState, string> = {
    idle: '确认并进入下一题',
    evaluating: 'AI 正在评估回答...',
    streaming_next: '正在生成下一题...',
    finishing: '正在结束面试...',
    error: '重试提交',
  };
  return labelMap[submissionState.value];
});
const submissionStatusTitle = computed(() => {
  const titleMap: Record<SubmissionState, string> = {
    idle: '',
    evaluating: '回答已提交，AI 正在评估',
    streaming_next: 'AI 正在生成下一题',
    finishing: '正在结束本次面试',
    error: '提交失败',
  };
  return titleMap[submissionState.value] || '';
});
const submissionStatusDescription = computed(() => {
  if (submitErrorText.value) return submitErrorText.value;
  if (activeGenerationJob.value?.status === 'running') {
    if (activeGenerationJob.value.can_retry) {
      return '回答已保存，下一题生成任务已超时。可以保留回答后重新生成，避免重复提交。';
    }
    return '回答已保存，下一题仍在后端生成。系统会自动刷新状态，完成后恢复到下一题。';
  }
  if (activeGenerationJob.value?.status === 'failed') {
    return activeGenerationJob.value.error_message || '下一题生成失败，可以保留回答后重新生成。';
  }
  const descriptionMap: Record<SubmissionState, string> = {
    idle: '',
    evaluating: '系统会先分析你的回答质量，再决定下一题的追问方向。',
    streaming_next: '保持当前页面，下一题生成后会自动展示。',
    finishing: '正在整理本轮记录并准备报告。',
    error: recoveryQuestionId.value ? '回答可能已经保存。如果只是下一题流式生成中断，可以直接重新生成下一题，避免重复提交。' : '请检查网络后重新提交，当前回答草稿仍会保留。',
  };
  return descriptionMap[submissionState.value] || '';
});
const answerGuidanceText = computed(() => {
  if (isRealisticMode.value) return '请结合真实经历回答，说明你当时的判断、行动和结果。';
  return agentMemory.value?.question_strategy || agentMemory.value?.follow_up_target || '先回答结论，再补充场景、动作、结果和复盘。';
});
const answerChecklist = computed(() => {
  const stage = sessionInfo.value?.current_stage;
  if (stage === 'opening') {
    return ['先给岗位匹配结论', '挑1个代表项目', '突出个人优势', '控制在1到3分钟'];
  }
  if (stage === 'resume_deep_dive') {
    return ['先说背景目标', '交代你的角色', '说明具体动作', '补充结果指标'];
  }
  if (stage === 'scenario_challenge') {
    return ['先给判断结论', '说明取舍逻辑', '覆盖风险边界', '最后补复盘优化'];
  }
  return ['先给结论', '讲清具体场景', '突出个人动作', '补量化结果或复盘'];
});

const generationJobStatusLabel = (status?: string) => {
  const labels: Record<string, string> = {
    pending: '待生成',
    running: '生成中',
    completed: '已完成',
    failed: '失败',
  };
  return status ? labels[status] || status : '未知';
};

const upsertGenerationJob = (job: Partial<InterviewQuestionGenerationJobItem>) => {
  if (!job.id) return;
  const existingIndex = generationJobs.value.findIndex(item => item.id === job.id);
  const normalizedJob: InterviewQuestionGenerationJobItem = {
    id: job.id,
    session: job.session || sessionInfo.value?.id || '',
    answered_question: job.answered_question ?? recoveryQuestionId.value,
    generated_question: job.generated_question ?? null,
    sequence: job.sequence || ((currentQuestion.value?.sequence || 0) + 1),
    status: job.status || 'running',
    request_hash: job.request_hash || '',
    engine_name: job.engine_name || '',
    partial_text: job.partial_text || '',
    final_text: job.final_text || '',
    error_message: job.error_message || '',
    started_at: job.started_at || null,
    completed_at: job.completed_at || null,
    is_stale: Boolean(job.is_stale),
    retry_after_seconds: job.retry_after_seconds,
    can_retry: Boolean(job.can_retry),
    created_at: job.created_at || new Date().toISOString(),
    updated_at: job.updated_at || new Date().toISOString(),
  };
  if (existingIndex >= 0) {
    generationJobs.value.splice(existingIndex, 1, {
      ...generationJobs.value[existingIndex],
      ...normalizedJob,
    });
  } else {
    generationJobs.value.unshift(normalizedJob);
  }
};

const stopGenerationJobPolling = () => {
  if (generationPollTimer.value) {
    window.clearInterval(generationPollTimer.value);
    generationPollTimer.value = null;
  }
};

const refreshGenerationJobs = async (answeredQuestionId?: number) => {
  if (!sessionInfo.value?.id) return null;
  isRefreshingGenerationJob.value = true;
  try {
    const jobs = await getInterviewQuestionGenerationJobsApi(sessionInfo.value.id);
    generationJobs.value = jobs;
    const targetJob = answeredQuestionId
      ? jobs.find(job => job.answered_question === answeredQuestionId)
      : jobs.find(job => job.status === 'running') || jobs[0];

    if (targetJob?.status === 'completed') {
      stopGenerationJobPolling();
      recoveryQuestionId.value = null;
      submitErrorText.value = '';
      await fetchSessionData();
      ElMessage.success('已恢复生成完成的下一题');
    }

    if (targetJob?.status === 'failed') {
      stopGenerationJobPolling();
      submissionState.value = 'error';
      submitErrorText.value = targetJob.error_message || '下一题生成失败，可以重新生成。';
    }

    if (targetJob?.status === 'running' && targetJob.can_retry) {
      stopGenerationJobPolling();
      submissionState.value = 'error';
      submitErrorText.value = '下一题生成任务已超时，可以保留回答后重新生成。';
    }

    return targetJob || null;
  } finally {
    isRefreshingGenerationJob.value = false;
  }
};

const startGenerationJobPolling = (answeredQuestionId: number) => {
  stopGenerationJobPolling();
  generationPollTimer.value = window.setInterval(() => {
    refreshGenerationJobs(answeredQuestionId).catch(() => {
      submitErrorText.value = '刷新下一题生成状态失败，请稍后手动刷新。';
    });
  }, 3000);
};

const clearCurrentDraft = () => {
  if (!draftStorageKey.value) return;
  localStorage.removeItem(draftStorageKey.value);
};

const restoreDraftForCurrentQuestion = () => {
  draftRestored.value = false;
  if (!draftStorageKey.value) return;
  const savedDraft = localStorage.getItem(draftStorageKey.value);
  if (!savedDraft || answerPlainText.value) return;
  userAnswer.value = savedDraft;
  draftRestored.value = true;
};

watch(userAnswer, (value) => {
  if (draftRestored.value && value.trim()) {
    draftRestored.value = false;
  }
  if (!draftStorageKey.value) return;
  if (value.trim()) {
    localStorage.setItem(draftStorageKey.value, value);
  } else {
    localStorage.removeItem(draftStorageKey.value);
  }
});

watch(() => currentQuestion.value?.id, () => {
  restoreDraftForCurrentQuestion();
});

const stageLabel = (stage?: string) => {
  const labels: Record<string, string> = {
    opening: '开场定位',
    self_intro: '自我介绍',
    project_anchor: '项目定位',
    project_deep_dive: '项目深挖',
    fundamentals_probe: '基础知识验证',
    role_specific: '岗位专项',
    system_design: '系统设计',
    behavioral: '行为面试',
    candidate_questions: '候选人反问',
    closing: '自然收尾',
    resume_deep_dive: '简历深挖',
    technical_deep_dive: '技术深挖',
    scenario_challenge: '场景挑战',
    wrap_up: '收尾复盘'
  };
  return stage ? labels[stage] || stage : '准备中';
};

const difficultyLabel = (difficulty?: string) => {
  const labels: Record<string, string> = { easy: '基础澄清', medium: '标准追问', hard: '高压深挖' };
  return difficulty ? labels[difficulty] || difficulty : '标准追问';
};

const answerLevelLabel = (level?: string) => {
  const labels: Record<string, string> = { weak: '偏弱', average: '一般', solid: '扎实', strong: '优秀' };
  return level ? labels[level] || level : '待评估';
};

const resetFinishSteps = () => {
  finishSteps.value = finishSteps.value.map(step => ({ ...step, status: 'pending' }));
};

const setFinishStep = (key: string, status: FinishStepStatus, description?: string) => {
  finishSteps.value = finishSteps.value.map(step => (
    step.key === key ? { ...step, status, description: description || step.description } : step
  ));
};

watch([isSpeaking, isPaused], ([speaking, paused]) => {
  if (speaking && !paused) { speechIcon.value = VideoPause; speechTooltip.value = '暂停'; } 
  else if (speaking && paused) { speechIcon.value = VideoPlay; speechTooltip.value = '继续播放'; } 
  else { speechIcon.value = RefreshRight; speechTooltip.value = '重播问题'; }
}, { immediate: true });

const stopBackendQuestionAudio = () => {
  if (backendQuestionAudio.value) {
    backendQuestionAudio.value.pause();
    backendQuestionAudio.value.currentTime = 0;
  }
  isBackendTtsPlaying.value = false;
};

const playWithBrowserTts = (textToSpeak: string) => {
  if (isSpeaking.value) {
    if (isPaused.value) { resume(); } else { pause(); }
  } else {
    speak(textToSpeak);
  }
};

const toggleSpeech = async () => {
  const textToSpeak = streamedQuestionText.value || currentQuestion.value?.question_text;
  if (!textToSpeak) return;
  if (isBackendTtsPlaying.value && backendQuestionAudio.value) {
    backendQuestionAudio.value.pause();
    isBackendTtsPlaying.value = false;
    speechIcon.value = VideoPlay;
    speechTooltip.value = '继续播放';
    return;
  }
  if (backendQuestionAudio.value && backendQuestionAudio.value.paused && backendQuestionAudio.value.src) {
    await backendQuestionAudio.value.play();
    isBackendTtsPlaying.value = true;
    speechIcon.value = VideoPause;
    speechTooltip.value = '暂停';
    return;
  }
  if (!sessionInfo.value?.id || !currentQuestion.value?.id) {
    playWithBrowserTts(textToSpeak);
    return;
  }
  try {
    const result = await generateQuestionTTSApi(sessionInfo.value.id, currentQuestion.value.id);
    if (!result.audio_url) throw new Error(result.error || 'tts_unavailable');
    cancel();
    backendQuestionAudio.value = new Audio(result.audio_url);
    backendQuestionAudio.value.onended = () => {
      isBackendTtsPlaying.value = false;
      speechIcon.value = RefreshRight;
      speechTooltip.value = '重播问题';
    };
    backendQuestionAudio.value.onerror = () => {
      isBackendTtsPlaying.value = false;
      playWithBrowserTts(textToSpeak);
    };
    await backendQuestionAudio.value.play();
    isBackendTtsPlaying.value = true;
    speechIcon.value = VideoPause;
    speechTooltip.value = '暂停';
  } catch {
    playWithBrowserTts(textToSpeak);
  }
};

const getSpeechWsUrl = () => {
  const configuredWsBase = (import.meta.env.VITE_WS_URL || '').replace(/\/$/, '');
  const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/api\/v1\/?$/, '').replace(/\/$/, '');
  const wsBase = configuredWsBase || (
    apiBase && /^https?:\/\//.test(apiBase)
      ? apiBase.replace(/^http/, 'ws')
      : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
  );
  return `${wsBase}/ws/interviews/${sessionInfo.value?.id}/speech/?token=${authStore.token}`;
};

const appendTranscriptToAnswer = (transcript: string) => {
  if (!transcript.trim()) return;
  if (userAnswer.value.endsWith('</p>')) {
    userAnswer.value = userAnswer.value.slice(0, -4) + transcript + '</p>';
  } else if (userAnswer.value.trim()) {
    userAnswer.value += `<p>${transcript}</p>`;
  } else {
    userAnswer.value = `<p>${transcript}</p>`;
  }
};

const startVoiceAnswer = async () => {
  if (!sessionInfo.value?.id || !currentQuestion.value?.id) return;
  stopBackendQuestionAudio();
  cancel();
  backendAsrError.value = '';
  audioArtifactId.value = '';
  asrTranscriptMeta.value = {};
  backendAsrStatus.value = 'connecting';
  startSpeech();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    answerAudioStream.value = stream;
    const socket = new WebSocket(getSpeechWsUrl());
    speechSocket.value = socket;
    socket.onopen = () => {
      backendAsrStatus.value = 'listening';
      socket.send(JSON.stringify({
        event: 'asr.start',
        question_id: currentQuestion.value?.id,
        mime_type: 'audio/webm',
      }));
      const recorder = MediaRecorder.isTypeSupported('audio/webm')
        ? new MediaRecorder(stream, { mimeType: 'audio/webm' })
        : new MediaRecorder(stream);
      answerAudioRecorder.value = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0 && socket.readyState === WebSocket.OPEN) {
          socket.send(event.data);
        }
      };
      recorder.start(2000);
    };
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.event === 'asr.status' && payload.status === 'transcribing') {
        backendAsrStatus.value = 'transcribing';
      }
      if (payload.event === 'asr.final') {
        backendAsrStatus.value = 'completed';
        audioArtifactId.value = payload.artifact_id || '';
        asrTranscriptMeta.value = {
          confidence: payload.confidence,
          source: 'backend_asr',
        };
        appendTranscriptToAnswer(payload.transcript || '');
        ElMessage.success('语音转写完成，请确认文本后提交');
      }
      if (payload.event === 'asr.error') {
        backendAsrStatus.value = 'failed';
        backendAsrError.value = payload.error || '后端语音识别失败';
        ElMessage.warning('后端语音识别失败，可继续手动编辑回答');
      }
    };
    socket.onerror = () => {
      backendAsrStatus.value = 'failed';
      backendAsrError.value = 'speech_websocket_error';
    };
    socket.onclose = () => {
      if (backendAsrStatus.value === 'listening') backendAsrStatus.value = 'idle';
    };
  } catch (error) {
    backendAsrStatus.value = 'failed';
    backendAsrError.value = error instanceof Error ? error.message : '无法访问麦克风';
    stopSpeech();
    ElMessage.error('无法开始语音回答');
  }
};

const stopVoiceAnswer = () => {
  stopSpeech();
  if (answerAudioRecorder.value && answerAudioRecorder.value.state !== 'inactive') {
    answerAudioRecorder.value.stop();
  }
  answerAudioRecorder.value = null;
  answerAudioStream.value?.getTracks().forEach(track => track.stop());
  answerAudioStream.value = null;
  if (speechSocket.value?.readyState === WebSocket.OPEN) {
    backendAsrStatus.value = 'transcribing';
    speechSocket.value.send(JSON.stringify({ event: 'asr.stop' }));
  }
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
    const answered = res.questions.filter(q => q.answer_text);
    const latestAnswered = answered[answered.length - 1];
    if (latestAnswered?.ai_feedback) {
      lastAnswerFeedback.value = latestAnswered.ai_feedback;
      lastFeedback.value = latestAnswered.ai_feedback.feedback || '';
    }

    if (unanswered.length > 0) {
      currentQuestion.value = unanswered[0];
      streamedQuestionText.value = '';
      submitErrorText.value = '';
      stopGenerationJobPolling();
      if (submissionState.value !== 'finishing') {
        submissionState.value = 'idle';
      }
      return;
    }

    currentQuestion.value = res.questions[res.questions.length - 1] || null;
    if (latestAnswered?.id && res.status === 'running') {
      recoveryQuestionId.value = latestAnswered.id;
      const job = await refreshGenerationJobs(latestAnswered.id);
      if (job?.status === 'running') {
        submissionState.value = 'streaming_next';
        startGenerationJobPolling(latestAnswered.id);
      }
    }
  } catch (error) {
    ElMessage.error("加载面试信息失败");
  }
};

const submitAnswer = async () => {
  cancel();
  stopSpeech();
  clearInterimTranscript();
  if (!sessionInfo.value || !currentQuestion.value || !answerPlainText.value.trim()) return;
  if (answerPlainText.value.length < SHORT_ANSWER_THRESHOLD) {
    try {
      await ElMessageBox.confirm('当前回答较短，可能会影响追问质量。是否仍然提交？', '回答较短', {
        confirmButtonText: '仍然提交',
        cancelButtonText: '继续补充',
        type: 'warning'
      });
    } catch {
      return;
    }
  }
  isSubmitting.value = true;
  streamedQuestionText.value = '';
  submitErrorText.value = '';
  recoveryQuestionId.value = null;
  submissionState.value = 'evaluating';

  // [核心修正 2/2] 在提交前清洗 HTML
  const cleanAnswer = sanitizeHtml(userAnswer.value);
  const submittedQuestionId = currentQuestion.value.id;

  try {
    const result = await submitAnswerStreamApi(sessionInfo.value.id, {
        question_id: currentQuestion.value.id,
        answer_text: cleanAnswer, // 使用清洗后的数据
        analysis_data: analysisFrames.value,
        audio_artifact_id: audioArtifactId.value || undefined,
        asr_transcript_meta: Object.keys(asrTranscriptMeta.value).length ? asrTranscriptMeta.value : undefined,
      }, (chunk) => {
        if (submissionState.value !== 'streaming_next') {
          submissionState.value = 'streaming_next';
        }
        streamedQuestionText.value += chunk;
      }, (job) => {
        recoveryQuestionId.value = submittedQuestionId;
        upsertGenerationJob(job);
        startGenerationJobPolling(submittedQuestionId);
      });
    lastFeedback.value = result.feedback;
    lastAnswerFeedback.value = result.feedbackDetail || currentQuestion.value.ai_feedback || null;
    if (result.nextQuestion?.question_text) {
      streamedQuestionText.value = result.nextQuestion.question_text;
    }
    recoveryQuestionId.value = null;
    clearCurrentDraft();
    if (result.isFinished) {
      submissionState.value = 'finishing';
      await confirmFinishInterview(true);
    } else {
      userAnswer.value = '';
      audioArtifactId.value = '';
      asrTranscriptMeta.value = {};
      backendAsrStatus.value = 'idle';
      backendAsrError.value = '';
      analysisFrames.value = [];
      if (draftStorageKey.value) {
        localStorage.removeItem(`interview-answer-draft:${sessionInfo.value.id}:${submittedQuestionId}`);
      }
      await fetchSessionData();
    }
  } catch (error) {
    submissionState.value = 'error';
    recoveryQuestionId.value = submittedQuestionId;
    submitErrorText.value = error instanceof Error ? error.message : '提交失败，请重试。';
    if (error instanceof SubmitAnswerStreamError && error.generationJob) {
      upsertGenerationJob(error.generationJob);
      if (error.generationJob.status === 'running') {
        submitErrorText.value = '';
        submissionState.value = 'streaming_next';
        startGenerationJobPolling(submittedQuestionId);
        ElMessage.info('回答已保存，正在恢复下一题生成状态');
        return;
      }
    }
    try {
      const job = await refreshGenerationJobs(submittedQuestionId);
      if (job?.status === 'running') {
        submitErrorText.value = '';
        submissionState.value = 'streaming_next';
        startGenerationJobPolling(submittedQuestionId);
        ElMessage.info('回答已保存，正在恢复下一题生成状态');
      } else {
        ElMessage.error(submitErrorText.value);
      }
    } catch {
      ElMessage.error(submitErrorText.value);
    }
  } finally {
    isSubmitting.value = false;
    if (submissionState.value !== 'finishing' && submissionState.value !== 'error' && submissionState.value !== 'streaming_next') {
      submissionState.value = 'idle';
    }
  }
};

const regenerateNextQuestion = async () => {
  if (!sessionInfo.value?.id || !recoveryQuestionId.value) return;
  isRegeneratingNextQuestion.value = true;
  streamedQuestionText.value = '';
  submitErrorText.value = '';
  submissionState.value = 'streaming_next';

  try {
    const result = await regenerateNextQuestionApi(sessionInfo.value.id, recoveryQuestionId.value);
    if (result.feedback_detail) {
      lastAnswerFeedback.value = result.feedback_detail;
      lastFeedback.value = result.feedback_detail.feedback || '';
    }
    if (result.interview_finished) {
      submissionState.value = 'finishing';
      await confirmFinishInterview(true);
      return;
    }
    if (result.next_question) {
      userAnswer.value = '';
      analysisFrames.value = [];
      clearCurrentDraft();
      recoveryQuestionId.value = null;
      await fetchSessionData();
      ElMessage.success(result.already_exists ? '已恢复下一题' : '下一题已重新生成');
      submissionState.value = 'idle';
      return;
    }
    throw new Error('未获取到下一题，请稍后重试。');
  } catch (error) {
    submissionState.value = 'error';
    submitErrorText.value = error instanceof Error ? error.message : '重新生成下一题失败';
    try {
      const job = await refreshGenerationJobs(recoveryQuestionId.value || undefined);
      if (job?.status === 'running' && recoveryQuestionId.value) {
        submitErrorText.value = '';
        submissionState.value = 'streaming_next';
        startGenerationJobPolling(recoveryQuestionId.value);
        ElMessage.info('下一题仍在生成，已切换为自动恢复');
      } else {
        ElMessage.error(submitErrorText.value);
      }
    } catch {
      ElMessage.error(submitErrorText.value);
    }
  } finally {
    isRegeneratingNextQuestion.value = false;
  }
};

const confirmFinishInterview = async (isAutoFinish: boolean | Event = false) => {
  cancel();
  stopSpeech();
  clearInterimTranscript();
  
  const action = async () => {
    isFinishing.value = true;
    finishFlowVisible.value = true;
    resetFinishSteps();
    submissionState.value = 'finishing';
    if (!sessionInfo.value) return;
    
    console.log('[录像] 结束面试 - recording_enabled:', sessionInfo.value.recording_enabled, 'isVideoRecording:', isVideoRecording.value);
    
    let videoUploadId: string | null = null;
    
    if (isVideoRecording.value) {
      setFinishStep('stop_recording', 'active');
      console.log('[录像] 正在停止录制...');
      const videoBlob = await stopVideoRecording();
      console.log('[录像] 录制停止，blob大小:', videoBlob?.size);
      setFinishStep('stop_recording', 'done', '录像已停止，原始数据已写入浏览器缓存');
      if (videoBlob && videoBlob.size > 0) {
        setFinishStep('upload_recording', 'active');
        ElMessage.info("正在上传面试录像，请稍候...");
        videoUploadId = await uploadVideo(videoBlob);
        if (videoUploadId) {
          setFinishStep('upload_recording', 'done', '原始录像已上传，后台压缩转码会继续进行');
          ElMessage.success("录像上传成功");
          console.log('[录像] 上传成功，taskId:', videoUploadId);
        } else {
          setFinishStep('upload_recording', 'error', '录像上传失败，本次报告仍会继续生成');
        }
      } else {
        setFinishStep('upload_recording', 'skipped', '未获取到有效录像数据，跳过上传');
        console.log('[录像] 录制数据为空或不存在');
      }
    } else {
      setFinishStep('stop_recording', 'skipped', '本次未开启或未启动录像');
      setFinishStep('upload_recording', 'skipped', '无录像需要上传');
      console.log('[录像] 当前没有在录制');
    }
    
    try {
      setFinishStep('generate_report', 'active');
      const report = await finishInterviewApi(sessionInfo.value.id, {
        video_upload_id: videoUploadId || undefined
      });
      if (report?.error) {
        throw new Error(report.error);
      }
      setFinishStep('generate_report', 'done', '报告已生成，正在打开报告页');
      setFinishStep('navigate', 'active');
      ElMessage.success("面试结束，报告已生成");
      setFinishStep('navigate', 'done');
      router.push({ name: 'ReportDetail', params: { id: sessionInfo.value.id } });
    } catch (error) {
      const message = error instanceof Error ? error.message : "结束面试失败";
      setFinishStep('generate_report', 'error', message);
      submissionState.value = 'error';
      submitErrorText.value = message;
      ElMessage.error(message);
    } finally {
      isFinishing.value = false;
      if (submissionState.value === 'finishing') {
        submissionState.value = 'idle';
      }
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
onMounted(async () => {
  clockTimer = window.setInterval(() => { clockTick.value = Date.now(); }, 1000);
  await loadModels();
  await fetchSessionData();
  await setupCamera();
});
onUnmounted(() => {
  if (clockTimer) window.clearInterval(clockTimer);
  stopGenerationJobPolling();
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
  stopBackendQuestionAudio();
  stopVoiceAnswer();
  speechSocket.value?.close();
  stopSpeech();
  clearInterimTranscript();
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
  --room-header-offset: 74px;
  height: calc(100dvh - var(--room-header-offset));
  min-height: 0 !important;
  padding: clamp(12px, 1vw, 20px) clamp(14px, 1.2vw, 24px) !important;
  background:
    radial-gradient(circle at top left, rgba(96, 155, 255, 0.12), transparent 25%),
    radial-gradient(circle at top right, rgba(67, 207, 164, 0.08), transparent 20%),
    linear-gradient(180deg, #f6f9ff 0%, #eff4fb 100%);
}

.main-content-grid {
  display: grid;
  grid-template-columns: clamp(300px, 20vw, 390px) minmax(640px, 1fr) clamp(280px, 17vw, 340px);
  gap: clamp(14px, 1.05vw, 22px);
  width: min(1880px, calc(100vw - 32px));
  max-width: none !important;
  height: 100%;
  min-height: 0;
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

.left-panel,
.center-panel,
.right-panel {
  min-height: 0;
}

.left-panel,
.center-panel {
  overflow: hidden;
}

.left-panel {
  gap: clamp(10px, 1.1vh, 14px) !important;
  padding: clamp(14px, 1vw, 18px) !important;
  overflow-y: auto;
}

.video-container {
  flex-shrink: 0;
  min-height: 168px;
  max-height: clamp(205px, 25vh, 300px);
  border-radius: 24px;
  border: 1px solid rgba(222, 232, 246, 0.9);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.analysis-section {
  flex-shrink: 0;
}

.analysis-summary {
  gap: 10px !important;
  padding: 9px !important;
  border: 1px solid rgba(223, 232, 245, 0.9);
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92) 0%, rgba(245, 248, 255, 0.82) 100%) !important;
}

.emotion-bars-container {
  flex: 0 1 auto;
  min-height: 112px;
  max-height: clamp(130px, 16vh, 168px);
  padding: 12px 14px;
  overflow-y: auto;
  border: 1px solid rgba(223, 232, 245, 0.95);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
}

.center-panel {
  padding: clamp(18px, 1.25vw, 24px) !important;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.72) 0%, rgba(244, 248, 255, 0.7) 100%);
}

.question-display-area {
  min-height: 0;
  gap: clamp(12px, 1.5vh, 16px) !important;
}

.ai-presenter {
  flex-shrink: 0;
  min-height: clamp(92px, 13vh, 122px);
  padding: clamp(14px, 1vw, 18px);
  align-items: center !important;
  border: 1px solid rgba(222, 231, 245, 0.92);
  border-radius: 24px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(239, 245, 255, 0.72) 100%);
}

.question-header h2 {
  color: #172944 !important;
  font-size: 22px;
}

.stage-chip {
  padding: 5px 10px;
  border-radius: 999px;
  color: #2c5d8f;
  font-size: 12px;
  font-weight: 700;
  background: rgba(225, 239, 255, 0.92);
  border: 1px solid rgba(166, 202, 245, 0.7);
}

.question-progress {
  color: #70819b !important;
  font-size: 13px !important;
}

.question-text-box {
  flex: 1 1 clamp(190px, 32vh, 360px);
  min-height: clamp(170px, 24vh, 230px) !important;
  max-height: clamp(230px, 39vh, 380px);
  padding: clamp(20px, 1.45vw, 28px) !important;
  border: 1px solid rgba(225, 233, 245, 0.95);
  border-radius: 28px !important;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.93) 0%, rgba(247, 250, 255, 0.88) 100%) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
}

.question-text-box p {
  margin: 0;
  color: #1f2f4c;
  font-size: clamp(22px, 1.35vw, 29px);
  line-height: 1.62;
}

.question-status-banner,
.answer-guidance-card,
.interim-transcript-card {
  flex-shrink: 0;
  padding: 14px 16px;
  border-radius: 20px;
  border: 1px solid rgba(222, 231, 245, 0.95);
  background: rgba(255, 255, 255, 0.82);
}

.question-status-banner strong,
.answer-guidance-header strong,
.interim-transcript-card span {
  display: block;
  color: #1d3150;
  font-size: 14px;
}

.question-status-banner p,
.answer-guidance-copy,
.interim-transcript-card p {
  margin: 6px 0 0;
  color: #53647f;
  font-size: 13px;
  line-height: 1.68;
}

.status-action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.generation-job-panel {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid rgba(174, 199, 230, 0.78);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.62);
}

.generation-job-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #53647f;
  font-size: 12px;
}

.generation-job-meta strong {
  flex-shrink: 0;
  padding: 3px 8px;
  border-radius: 999px;
  color: #265f9f;
  font-size: 11px;
  background: rgba(224, 239, 255, 0.95);
}

.generation-job-hint {
  margin-top: 8px !important;
  color: #6a5872 !important;
  font-size: 12px;
  line-height: 1.5;
}

.generation-job-preview {
  display: -webkit-box;
  margin-top: 8px !important;
  overflow: hidden;
  color: #40536f !important;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.question-status-banner--evaluating,
.question-status-banner--streaming_next {
  background: linear-gradient(135deg, rgba(240, 247, 255, 0.96), rgba(251, 254, 255, 0.92));
  border-color: rgba(168, 203, 246, 0.82);
}

.question-status-banner--error {
  background: linear-gradient(135deg, rgba(255, 244, 244, 0.95), rgba(255, 251, 251, 0.92));
  border-color: rgba(238, 174, 174, 0.9);
}

.question-status-banner--finishing {
  background: linear-gradient(135deg, rgba(245, 246, 255, 0.96), rgba(252, 253, 255, 0.92));
  border-color: rgba(194, 203, 239, 0.88);
}

.answer-guidance-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(245, 249, 255, 0.86));
}

.answer-guidance-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.answer-guidance-header span {
  flex-shrink: 0;
  padding: 4px 9px;
  border-radius: 999px;
  color: #53739b;
  font-size: 11px;
  font-weight: 700;
  background: rgba(231, 240, 255, 0.9);
}

.answer-guidance-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.answer-guidance-tags span {
  padding: 6px 10px;
  border-radius: 999px;
  color: #2e5177;
  font-size: 12px;
  background: rgba(235, 242, 252, 0.95);
}

.feedback-summary-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  padding: 12px 14px;
  border: 1px solid rgba(143, 211, 177, 0.58);
  border-radius: 20px;
  background: linear-gradient(135deg, rgba(239, 253, 246, 0.9), rgba(248, 252, 255, 0.94));
  box-shadow: 0 14px 30px rgba(68, 146, 104, 0.08);
}

.feedback-summary-main {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 10px;
}

.feedback-summary-main strong {
  display: block;
  color: #17634d;
  font-size: 14px;
}

.feedback-summary-main p {
  max-width: 560px;
  margin: 2px 0 0;
  overflow: hidden;
  color: #527165;
  font-size: 12px;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feedback-dot {
  width: 9px;
  height: 9px;
  flex-shrink: 0;
  border-radius: 999px;
  background: #32b477;
  box-shadow: 0 0 0 5px rgba(50, 180, 119, 0.13);
}

.quality-pill {
  flex-shrink: 0;
  padding: 4px 9px;
  border-radius: 999px;
  color: #17634d;
  font-size: 12px;
  font-weight: 700;
  background: rgba(214, 247, 233, 0.95);
  border: 1px solid rgba(131, 210, 174, 0.65);
}

.quality-pill--large {
  padding: 6px 12px;
  font-size: 13px;
}

.answer-input-area {
  flex-shrink: 0;
  margin-top: clamp(12px, 1.5vh, 18px) !important;
  padding-top: clamp(12px, 1.5vh, 18px);
  border-top: 1px solid rgba(223, 231, 244, 0.9);
}

.answer-mode-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.answer-mode-hint {
  color: #667892;
  font-size: 13px;
}

.answer-input-area :deep(.rich-text-editor-wrapper) {
  overflow: hidden;
  border-color: rgba(209, 222, 241, 0.95);
  border-radius: 18px;
}

.answer-input-area :deep(.w-e-text-container) {
  height: clamp(120px, 17vh, 178px) !important;
}

.answer-support-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}

.draft-indicator,
.answer-length-indicator {
  color: #6f819d;
  font-size: 12px;
}

.draft-indicator {
  font-weight: 700;
  color: #1d6a4f;
}

.draft-indicator--soft {
  color: #567491;
}

.interim-transcript-card {
  margin-top: 10px;
  background: linear-gradient(180deg, rgba(255, 250, 242, 0.95), rgba(255, 255, 255, 0.9));
  border-color: rgba(236, 207, 165, 0.92);
}

.speech-control-bar {
  min-height: clamp(48px, 6vh, 56px);
  border: 1px solid rgba(222, 231, 245, 0.9);
  border-radius: 20px !important;
  background: rgba(255, 255, 255, 0.78) !important;
}

.right-panel {
  gap: clamp(12px, 1.5vh, 16px) !important;
  overflow-y: auto;
  padding-right: 3px;
}

.controls {
  gap: 14px !important;
  padding: 16px !important;
  flex-shrink: 0;
}

.controls :deep(.el-button--primary) {
  min-height: 50px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, #2a65d8 0%, #5f9fff 100%);
  box-shadow: 0 18px 28px rgba(42, 101, 216, 0.18);
}

.controls :deep(.el-button--danger.is-plain) {
  min-height: 46px;
  border-radius: 16px;
}

.recording-status,
.tips,
.agent-status,
.progress-card,
.focus-card {
  border-radius: 24px;
}

.progress-card,
.focus-card {
  background: rgba(255, 255, 255, 0.48);
  box-shadow: 0 16px 34px rgba(35, 63, 110, 0.08);
}

.recording-status,
.tips {
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.46);
  box-shadow: none;
}

.tips {
  flex: 1 1 auto;
  min-height: 128px;
  overflow-y: auto;
}

.progress-ring-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.progress-ring {
  display: grid;
  width: 58px;
  height: 58px;
  place-items: center;
  flex-shrink: 0;
  border-radius: 20px;
  color: #2362d0;
  font-size: 16px;
  font-weight: 800;
  background: linear-gradient(135deg, rgba(230, 240, 255, 0.95), rgba(255, 255, 255, 0.78));
  border: 1px solid rgba(183, 209, 245, 0.85);
}

.progress-ring-row strong {
  color: #1d2f4e;
  font-size: 19px;
}

.progress-ring-row p {
  margin: 2px 0 0;
  color: #7c8da8;
  font-size: 12px;
}

.agent-status {
  flex-shrink: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.64), rgba(239, 246, 255, 0.58));
}

.agent-state-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
}

.agent-state-grid div {
  padding: 10px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(222, 231, 245, 0.95);
}

.agent-state-grid span,
.agent-quality span {
  display: block;
  margin-bottom: 5px;
  color: #8290a8;
  font-size: 11px;
}

.agent-state-grid strong {
  color: #1e314f;
  font-size: 14px;
}

.agent-quality {
  margin-top: 12px;
}

.agent-target {
  margin: 10px 0 0;
  padding: 10px 11px;
  border-radius: 16px;
  color: #41516c;
  font-size: 12px;
  line-height: 1.6;
  background: rgba(245, 248, 254, 0.86);
  border: 1px solid rgba(222, 231, 245, 0.95);
}

.agent-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.agent-tags span {
  padding: 5px 9px;
  border-radius: 999px;
  color: #355274;
  font-size: 11px;
  background: rgba(232, 240, 253, 0.9);
}

.focus-card {
  flex: 1 1 auto;
  min-height: 126px;
  overflow-y: auto;
}

.focus-card p {
  margin: 0;
  color: #42536f;
  font-size: 13px;
  line-height: 1.75;
}

.tips ul {
  line-height: 1.72;
}

.feedback-dialog :deep(.el-dialog) {
  border-radius: 24px;
}

.feedback-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dialog-score-row {
  display: flex;
}

.feedback-dialog-body section {
  padding: 14px 16px;
  border-radius: 18px;
  background: #f7fafc;
  border: 1px solid #e3edf8;
}

.feedback-dialog-body h4 {
  margin: 0 0 8px;
  color: #1d3150;
  font-size: 14px;
}

.feedback-dialog-body p {
  margin: 0;
  color: #4a5d78;
  font-size: 14px;
  line-height: 1.75;
}

.finish-flow-dialog {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.finish-step {
  display: flex;
  gap: 12px;
  padding: 14px;
  border: 1px solid #e4ebf6;
  border-radius: 18px;
  background: #f8fbff;
}

.finish-step-index {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  flex-shrink: 0;
  border-radius: 999px;
  color: #6c7f9e;
  font-weight: 800;
  background: #eaf1fb;
}

.finish-step strong {
  color: #1f3150;
}

.finish-step p {
  margin: 4px 0 0;
  color: #65748c;
  font-size: 13px;
  line-height: 1.6;
}

.finish-step--active {
  border-color: rgba(90, 145, 232, 0.6);
  background: linear-gradient(135deg, #eff6ff, #ffffff);
}

.finish-step--active .finish-step-index {
  color: #fff;
  background: #2f6fd7;
}

.finish-step--done {
  border-color: rgba(120, 205, 166, 0.7);
  background: #f1fff7;
}

.finish-step--done .finish-step-index {
  color: #fff;
  background: #27a86a;
}

.finish-step--error {
  border-color: rgba(236, 154, 154, 0.8);
  background: #fff5f5;
}

.finish-step--error .finish-step-index {
  color: #fff;
  background: #d94b4b;
}

.finish-step--skipped {
  opacity: 0.72;
}

:deep(.el-progress-bar__outer) {
  background: #e9eff8;
}

:deep(.el-progress-bar__inner) {
  border-radius: 999px;
}

@media (max-width: 1500px) {
  .main-content-grid {
    grid-template-columns: clamp(270px, 22vw, 330px) minmax(560px, 1fr) clamp(260px, 20vw, 300px);
    gap: 1rem;
  }

  .question-text-box {
    min-height: clamp(160px, 23vh, 210px) !important;
    padding: 22px !important;
  }

  .question-header h2 {
    font-size: 20px;
  }
}

@media (max-width: 1320px) {
  .interview-room-container {
    overflow-y: auto;
    height: auto;
    min-height: calc(100dvh - var(--room-header-offset)) !important;
  }

  .main-content-grid {
    grid-template-columns: minmax(280px, 0.34fr) minmax(0, 0.66fr);
    width: 100%;
    height: auto;
    min-height: 0;
  }

  .left-panel,
  .center-panel {
    overflow: visible;
  }

  .right-panel {
    grid-column: 1 / -1;
    display: grid !important;
    grid-template-columns: repeat(2, minmax(280px, 1fr));
    overflow: visible;
    padding-right: 0;
  }

  .right-panel .controls,
  .right-panel .agent-status,
  .right-panel .progress-card,
  .right-panel .focus-card {
    min-width: 0;
  }

  .question-text-box {
    max-height: none;
  }
}

@media (max-width: 980px) {
  .interview-room-container {
    overflow-y: auto;
    height: auto;
    min-height: 100vh !important;
  }

  .main-content-grid {
    grid-template-columns: 1fr;
    width: 100%;
    height: auto;
    min-height: 0;
  }

  .right-panel {
    display: flex !important;
    flex-direction: column;
  }

  .left-panel {
    overflow: visible;
  }

  .left-panel .tips,
  .left-panel .recording-status {
    flex-shrink: 0;
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

  .feedback-summary-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .feedback-summary-main p {
    max-width: 100%;
    white-space: normal;
  }
}
</style>
