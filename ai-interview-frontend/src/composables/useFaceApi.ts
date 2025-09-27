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

// 【核心修正】使用 faceapi 提供的精确类型
export type FaceExpressions = faceapi.FaceExpressions;

export function useFaceApi() {
  const modelsLoaded = ref(false);
  // 【核心修正】应用更精确的类型
  const emotions = ref<FaceExpressions | null>(null);
  const headPose = ref<{ pitch: number, yaw: number, roll: number } | null>(null);
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
      const detections = await faceapi
        .detectSingleFace(videoElement, new faceapi.TinyFaceDetectorOptions())
        .withFaceLandmarks()
        .withFaceExpressions();

      if (detections) {
        emotions.value = detections.expressions;
        
        const landmarks = detections.landmarks;
        const nose = landmarks.getNose();
        const jawline = landmarks.getJawOutline();
        
        if (nose.length > 0 && jawline.length > 0) {
          const yaw = jawline[16].x - jawline[0].x;
          const pitch = (jawline[8].y - nose[0].y) / (jawline[8].y - jawline[0].y);
          headPose.value = { 
            yaw: (jawline[8].x - (jawline[0].x + jawline[16].x) / 2) / yaw,
            pitch: pitch,
            roll: 0,
          };
        } else {
          headPose.value = null;
        }
      } else {
        emotions.value = null;
        headPose.value = null;
      }
    } catch (e) {
        console.error("面部检测时出错:", e);
        emotions.value = null;
        headPose.value = null;
    }
  };
  
  // 【核心修正】为参数添加精确类型
  const getPrimaryEmotion = (expressions: FaceExpressions | null): string => {
    if (!expressions) return '未检测到';
    // face-api.js 提供了更方便的方法
    const sorted = expressions.asSortedArray();
    if (sorted.length > 0) {
      return emotionMap[sorted[0].expression] || '未知';
    }
    return '未检测到';
  };

  const getActionState = (pose: { pitch: number, yaw: number, roll: number } | null): string => {
    if (!pose) return '未检测到';
    if (pose.pitch > 0.6) return '平时镜头';
    if (pose.pitch < 0.4) return '抬头';
    if (pose.yaw > 0.15) return '向右看';
    if (pose.yaw < -0.15) return '向左看';
    return '专注';
  };

  return {
    modelsLoaded,
    emotions,
    headPose,
    error,
    loadModels,
    detectFace,
    getPrimaryEmotion,
    getActionState,
  };
}