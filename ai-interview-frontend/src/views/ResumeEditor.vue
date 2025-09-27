<template>
  <div class="resume-editor-container" v-loading="store.isLoading">
    <!-- 顶部操作栏 -->
    <div class="editor-header">
      <h1>在线简历编辑器</h1>
      <div class="actions">
        <el-button @click="router.back()">返回</el-button>
        <el-button type="primary" @click="handleSave" :loading="store.isSaving">
          {{ store.isSaving ? '保存中...' : '保存简历' }}
        </el-button>
      </div>
    </div>

    <!-- 编辑器主区域 -->
    <div class="editor-main">
      <!-- 左侧设置面板 -->
      <div class="settings-panel">
        <el-scrollbar>
          <SettingsPanel />
        </el-scrollbar>
      </div>
      <!-- 右侧预览区域 -->
      <div class="preview-panel">
         <el-scrollbar>
           <!-- 【核心修正】将 store 中的 resumeData 通过 prop 传递给 ResumePreview 组件 -->
           <ResumePreview :resume-data="store.resumeData" />
         </el-scrollbar>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useResumeEditorStore } from '@/store/modules/resumeEditor';
import SettingsPanel from '@/components/resume/SettingsPanel.vue';
import ResumePreview from '@/components/resume/ResumePreview.vue';
import { ElMessage } from 'element-plus';

// 定义 props 来接收路由参数
const props = defineProps<{
  id: string;
}>();

const router = useRouter();
const store = useResumeEditorStore();
const resumeId = Number(props.id);

onMounted(() => {
  if (isNaN(resumeId) || resumeId <= 0) {
    ElMessage.error('无效的简历ID');
    router.push({ name: 'ResumeManagement' });
    return;
  }
  // 组件挂载时，从服务器加载简历数据
  store.fetchResume(resumeId);
});

// 组件卸载时，清空 store 中的数据
onUnmounted(() => {
  store.resetState();
});

const handleSave = () => {
  store.saveResume();
};
</script>

<style scoped>
.resume-editor-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px); /* 减去顶部导航栏高度 */
  overflow: hidden;
  background-color: #f0f2f5;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  background-color: #fff;
  border-bottom: 1px solid #dcdfe6;
  flex-shrink: 0;
  height: 64px;
}

.editor-header h1 {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
}

.editor-main {
  display: flex;
  flex-grow: 1;
  overflow: hidden;
}

.settings-panel {
  width: 380px;
  background-color: #fff;
  border-right: 1px solid #dcdfe6;
  flex-shrink: 0;
  height: 100%;
}

.preview-panel {
  flex-grow: 1;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 20px;
  height: 100%;
}

.el-scrollbar {
  height: 100%;
}
</style>