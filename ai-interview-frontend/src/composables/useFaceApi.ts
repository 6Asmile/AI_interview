import { ref } from 'vue';
import * as faceapi from 'face-api.js';
import { ElMessage } from 'element-plus';

export const emotionMap: Record<string, string> = {
  neutral: '平静',
  happy: '开心',
  sad: '悲伤',
  angry: '生气',
  fearful: '害怕',
  disgusted: '厌恶',
  surprised: '惊讶',
};

export type FaceExpressions = faceapi.FaceExpressions;

export function useFaceApi() {
  const modelsLoaded = ref(false);
  const emotions = ref<FaceExpressions | null>(null);
  // --- [核心移除] ---
  // const headPose = ref<{ pitch: number, yaw: number, roll: number } | null>(null);
  const error = ref<string | null>(null);

  const loadModels = async () => {
    const MODEL_URL = '/models';
    try {
      console.log('开始加载面部识别模型...');
      await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
        faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
        faceapi.nets.faceExpressionNet.loadFromUri(MODEL_URL),
      ]);
      modelsLoaded.value = true;
      console.log('面部识别模型加载成功！');
    } catch (e) {
      error.value = '加载面部识别模型失败。';
      console.error(error.value, e);
      ElMessage.error(error.value);
    }
  };

  const detectFace = async (videoElement: HTMLVideoElement) => {
    if (!modelsLoaded.value || !videoElement) {
      return;
    }

    try {
      // --- [核心修改] 移除 withFaceLandmarks，因为它只为动作分析服务，可以节省性能 ---
      const detections = await faceapi
        .detectSingleFace(videoElement, new faceapi.TinyFaceDetectorOptions())
        .withFaceExpressions();

      if (detections) {
        emotions.value = detections.expressions;
      } else {
        emotions.value = null;
      }
    } catch (e) {
        console.error("面部检测时出错:", e);
        emotions.value = null;
    }
  };
  
  const getPrimaryEmotion = (expressions: FaceExpressions | null): string => {
    if (!expressions) return '未检测到';
    const sorted = expressions.asSortedArray();
    if (sorted.length > 0) {
      return emotionMap[sorted[0].expression] || '未知';
    }
    return '未检测到';
  };
  
  // --- [核心移除] ---
  // const getActionState = (...) => { ... };

  return {
    modelsLoaded,
    emotions,
    // headPose, // 移除
    error,
    loadModels,
    detectFace,
    getPrimaryEmotion,
    // getActionState, // 移除
  };
}