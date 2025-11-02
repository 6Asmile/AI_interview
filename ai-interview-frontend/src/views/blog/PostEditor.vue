<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { 
  ElMessage, ElInput, ElForm, ElFormItem, ElButton, ElSelect, ElOption, ElUpload, 
  ElIcon, ElContainer, ElHeader, ElAside, ElMain, ElCard, ElRow, ElCol, ElEmpty, ElCollapseTransition
} from 'element-plus';
import { ArrowLeft, ArrowRight, Plus, MagicStick, Files, Operation, CaretTop, CaretBottom } from '@element-plus/icons-vue';
import type { UploadRequestOptions } from 'element-plus';
import { 
  getPostDetailApi, createPostApi, updatePostApi, 
  getCategoryListApi, getTagListApi 
} from '@/api/modules/blog';
import type { PostFormData, Category, Tag } from '@/api/modules/blog';
import MarkdownEditor from '@/components/common/MarkdownEditor.vue';
import { useEditorStore } from '@/store/modules/editor';
import { useSystemStore } from '@/store/modules/system';

interface CatalogItem {
  text: string;
  level: number;
  id: string; // 注意：md-editor-v3 生成的 id 是标题的文本内容
}

const route = useRoute();
const router = useRouter();
const editorStore = useEditorStore();
const systemStore = useSystemStore();

const postId = computed(() => route.params.id ? Number(route.params.id) : null);
const isNewPost = computed(() => !postId.value);

const postData = reactive<PostFormData>({
  title: '',
  content: '',
  status: 'draft',
  category: null,
  tags: [],
  excerpt: '',
  cover_image: null,
  cover_image_file: null,
});

const categories = ref<Category[]>([]);
const tags = ref<Tag[]>([]);
const isLoading = ref(true);
const isSettingsCollapsed = ref(false);
const catalog = ref<CatalogItem[]>([]);

const wordCount = computed(() => postData.content?.length || 0);

// 【核心修复】修正事件名称并正确接收
const onGetCatalog = (list: CatalogItem[]) => {
  catalog.value = list;
};

// 【核心修复】修正滚动逻辑
const handleAnchorClick = (anchor: CatalogItem) => {
  const preview = document.querySelector('.md-editor-preview-wrapper');
  if (preview) {
    const heading = preview.querySelector(`[id="${anchor.text}"]`) as HTMLElement;
    if (heading) {
      preview.scrollTo({
        top: heading.offsetTop,
        behavior: 'smooth',
      });
    }
  }
};

const fetchData = async () => {
  isLoading.value = true;
  try {
    const [catRes, tagRes] = await Promise.all([ getCategoryListApi(), getTagListApi() ]);
    categories.value = catRes.results;
    tags.value = tagRes.results;

    if (!isNewPost.value && postId.value) {
      const post = await getPostDetailApi(postId.value);
      postData.title = post.title;
      postData.content = post.content;
      postData.status = post.status;
      postData.excerpt = post.excerpt ?? '';
      postData.cover_image = post.cover_image;
      postData.category = post.category?.id ?? null;
      postData.tags = post.tags.map(t => t.id);
    }
  } catch (error) {
    ElMessage.error('加载数据失败');
  } finally {
    isLoading.value = false;
  }
};

onMounted(() => {
  fetchData();
  systemStore.fetchUserSettings();
  editorStore.resetState();
});

onUnmounted(() => {
  editorStore.resetState();
});

const handleCoverSuccess = (uploadFile: any) => {
  postData.cover_image = URL.createObjectURL(uploadFile.raw!);
  postData.cover_image_file = uploadFile.raw!;
};

const customHttpRequest = (options: UploadRequestOptions): Promise<void> => {
  handleCoverSuccess({ raw: options.file });
  return Promise.resolve();
};

const handleSave = async (status: 'draft' | 'published') => {
  postData.status = status;
  let newPostId: number | null = null;
  
  try {
    if (isNewPost.value) {
      const newPost = await createPostApi(postData);
      newPostId = newPost.id;
    } else {
      await updatePostApi(postId.value!, postData);
      newPostId = postId.value;
    }
  } catch (error) {
    ElMessage.error('操作失败，请检查网络或联系管理员');
    return;
  }

  ElMessage.success(status === 'draft' ? '草稿已保存' : '文章已发布');
  if (newPostId) {
    router.push({ name: 'PostDetail', params: { id: newPostId } });
  } else {
    router.push({ name: 'BlogHome' });
  }
};
</script>

<template>
  <div class="post-editor-layout" :class="{ 'left-collapsed': editorStore.isLeftSidebarCollapsed, 'right-collapsed': editorStore.isRightSidebarCollapsed }">
    <el-container>
      <el-header class="editor-header">
        <div class="header-left">
          <el-input v-model="postData.title" placeholder="请输入文章标题..." class="header-title-input"/>
        </div>
        <div class="header-right">
          <span class="word-count">字数: {{ wordCount }}</span>
          <el-button @click="handleSave('draft')">保存草稿</el-button>
          <el-button type="primary" @click="handleSave('published')">发布文章</el-button>
        </div>
      </el-header>

      <el-container class="main-container">
        <el-aside width="240px" class="left-aside">
          <div class="sidebar-content">
            <h4>大纲</h4>
            <div v-if="catalog.length > 0" class="outline-list">
              <div
                v-for="anchor in catalog"
                :key="anchor.text"
                :style="{ paddingLeft: `${(anchor.level - 1) * 15}px` }"
                class="outline-item"
                @click="handleAnchorClick(anchor)"
              >
                <a>{{ anchor.text }}</a>
              </div>
            </div>
            <el-empty v-else description="暂无大纲" :image-size="80" />
          </div>
        </el-aside>
        
        <div class="sidebar-toggle-btn left" @click="editorStore.toggleLeftSidebar()">
          <el-icon><ArrowRight v-if="editorStore.isLeftSidebarCollapsed" /><ArrowLeft v-else /></el-icon>
        </div>

        <el-main class="main-content">
          <div class="editor-area">
            <MarkdownEditor v-model="postData.content" @onGetCatalog="onGetCatalog" />
          </div>
          
          <el-card class="publish-settings-card">
            <template #header>
              <div class="card-header">
                <span>发布设置</span>
                <el-button text class="collapse-btn" @click="isSettingsCollapsed = !isSettingsCollapsed">
                  {{ isSettingsCollapsed ? '展开' : '收起' }}
                  <el-icon><CaretTop v-if="!isSettingsCollapsed" /><CaretBottom v-else /></el-icon>
                </el-button>
              </div>
            </template>
            <el-collapse-transition>
              <div v-show="!isSettingsCollapsed">
                <el-form :model="postData" label-position="top">
                  <el-row :gutter="40">
                    <el-col :span="8">
                      <el-form-item label="分类">
                        <el-select v-model="postData.category" placeholder="选择文章分类" clearable>
                          <el-option v-for="cat in categories" :key="cat.id" :label="cat.name" :value="cat.id" />
                        </el-select>
                      </el-form-item>
                    </el-col>
                    <el-col :span="16">
                      <el-form-item label="标签">
                        <el-select v-model="postData.tags" multiple filterable placeholder="添加文章标签">
                           <el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id" />
                        </el-select>
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="封面图">
                        <el-upload class="cover-uploader" action="#" :show-file-list="false" :http-request="customHttpRequest">
                          <img v-if="postData.cover_image" :src="postData.cover_image" class="cover-image" />
                          <el-icon v-else class="cover-uploader-icon"><Plus /></el-icon>
                        </el-upload>
                      </el-form-item>
                    </el-col>
                     <el-col :span="16">
                      <el-form-item label="文章摘要">
                        <el-input v-model="postData.excerpt" type="textarea" :rows="5" placeholder="输入文章摘要..." maxlength="256" show-word-limit />
                      </el-form-item>
                    </el-col>
                  </el-row>
                </el-form>
              </div>
            </el-collapse-transition>
          </el-card>
        </el-main>

        <div class="sidebar-toggle-btn right" @click="editorStore.toggleRightSidebar()">
          <el-icon><ArrowLeft v-if="editorStore.isRightSidebarCollapsed" /><ArrowRight v-else /></el-icon>
        </div>

        <el-aside width="300px" class="right-aside">
          <div class="sidebar-content">
            <div class="ai-assistant-module">
              <h4><el-icon><MagicStick /></el-icon> AI 助手</h4>
              <p class="ai-model-info">当前模型: {{ systemStore.activeModelName }}</p>
              <el-button type="primary" plain>生成大纲</el-button>
              <el-button type="primary" plain>润色全文</el-button>
            </div>
          </div>
        </el-aside>
      </el-container>
    </el-container>
  </div>
</template>

<style scoped>
.post-editor-layout { 
  height: 100vh; 
  background-color: #f4f5f5; 
  overflow: hidden; 
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #fff;
  padding: 0 10px 0 20px;
  z-index: 10;
}
.header-left { 
  flex: 1; 
  margin-right: 20px; 
}
.header-title-input { 
  max-width: 600px; 
}
.header-title-input :deep(.el-input__inner) { 
  border: none; 
  font-size: 1.2rem; 
  font-weight: 500; 
  box-shadow: none !important; 
}
.header-right { 
  display: flex; 
  align-items: center; 
  gap: 16px; 
}

.main-container { 
  position: relative; 
  height: calc(100vh - 60px); 
}

.left-aside, .right-aside {
  transition: all 0.3s ease;
  background-color: #fff;
  height: 100%;
}
.left-aside { 
  border-right: 1px solid #e5e6eb; 
}
.right-aside { 
  border-left: 1px solid #e5e6eb; 
}

.sidebar-content { 
  padding: 20px; 
  overflow-y: auto; 
  height: 100%; 
}

.sidebar-toggle-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 48px;
  background: #fff;
  border: 1px solid #e5e6eb;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 20;
}
.sidebar-toggle-btn.left { 
  left: 240px; 
  border-top-right-radius: 4px;
  border-bottom-right-radius: 4px;
  border-left: none;
  transition: left 0.3s ease;
}
.sidebar-toggle-btn.right { 
  right: 300px; 
  border-top-left-radius: 4px;
  border-bottom-left-radius: 4px;
  border-right: none;
  transition: right 0.3s ease;
}

.main-content {
  padding: 10px;
  margin: 0 10px;
  height: 100%;
  overflow-y: auto; 
  background-color: #fff;
  display: flex;
  flex-direction: column;
}
.editor-area {
  flex-grow: 1;
  min-height: 80vh;
  display: flex;
}
.editor-area > :deep(.v-md-editor) {
  flex-grow: 1 !important;
  box-shadow: none !important;
}

.publish-settings-card {
  margin-top: 20px;
  flex-shrink: 0; 
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.collapse-btn {
  font-size: 0.9rem;
}
.publish-settings-card .el-select { 
  width: 100%; 
}

.outline-list {
  padding: 0;
  margin: 0;
  list-style: none;
}
.outline-item {
  padding: 6px 0;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.outline-item a {
  font-size: 0.9rem;
  color: #606266;
  text-decoration: none;
  transition: color 0.2s;
}
.outline-item:hover a {
  color: var(--el-color-primary);
}

.left-collapsed .left-aside { 
  margin-left: -240px; 
}
.left-collapsed .sidebar-toggle-btn.left { 
  left: 0; 
}
.right-collapsed .right-aside { 
  margin-right: -300px; 
}
.right-collapsed .sidebar-toggle-btn.right { 
  right: 0; 
}

.cover-uploader :deep(.el-upload) { 
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: var(--el-transition-duration-fast);
  width: 100%;
  height: 150px;
}
.cover-uploader :deep(.el-upload:hover) { 
  border-color: var(--el-color-primary); 
}
.cover-uploader-icon {
  font-size: 28px;
  color: #8c939d;
  width: 100%;
  height: 150px;
  display: flex;
  justify-content: center;
  align-items: center;
}
.cover-image {
  width: 100%;
  height: 150px;
  object-fit: cover;
}

.ai-assistant-module {
  margin-top: 24px;
  padding: 16px;
  background-color: #f7f8fa;
  border-radius: 4px;
}
.ai-assistant-module h4 { 
  margin: 0 0 8px; 
  display: flex;
  align-items: center;
  gap: 8px;
}
.ai-model-info { 
  font-size: 0.8rem; 
  color: #909399; 
  margin: 0 0 16px; 
}
</style>