<template>
  <div class="post-editor-container p-4 lg:p-8" v-loading="isLoading">
    <div class="flex justify-between items-center mb-6 pb-4 border-b">
      <h1 class="text-2xl font-bold text-gray-800">{{ isNewPost ? '撰写新文章' : '编辑文章' }}</h1>
      <div class="flex gap-4">
        <el-button @click="saveDraft" :loading="isSaving">保存草稿</el-button>
        <el-button type="primary" @click="publishPost" :loading="isSaving">发布文章</el-button>
      </div>
    </div>
    <div class="editor-layout grid grid-cols-12 gap-6">
      <div class="col-span-12 lg:col-span-9">
        <el-input v-model="post.title" placeholder="请输入文章标题" size="large" class="mb-4 title-input" />
        <MarkdownEditor v-model="post.content" height="calc(100vh - 250px)" />
      </div>
      <div class="col-span-12 lg:col-span-3">
        <el-card shadow="never" class="settings-card">
          <template #header><div class="font-semibold">发布设置</div></template>
          <el-form label-position="top">
            <el-form-item label="文章状态"><el-select v-model="post.status" class="w-full"><el-option label="草稿" value="draft"></el-option><el-option label="已发布" value="published"></el-option><el-option label="仅自己可见" value="private"></el-option></el-select></el-form-item>
            <el-form-item label="分类"><el-select v-model="post.category" class="w-full" clearable><el-option v-for="cat in categories" :key="cat.id" :label="cat.name" :value="cat.id" /></el-select></el-form-item>
            
            <!-- [核心修正] 移除 allow-create 属性 -->
            <el-form-item label="标签"><el-select v-model="post.tags" class="w-full" multiple filterable><el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id" /></el-select></el-form-item>
            
            <el-form-item label="封面图">
              <el-upload class="cover-uploader" action="#" :show-file-list="false" :auto-upload="false" :on-change="handleCoverChange">
                <img v-if="coverPreviewUrl" :src="coverPreviewUrl" class="cover" />
                <el-icon v-else class="cover-uploader-icon"><Plus /></el-icon>
              </el-upload>
            </el-form-item>
          </el-form>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getPostDetailApi, createPostApi, updatePostApi, getCategoryListApi, getTagListApi, type PostFormData, type Category, type Tag, type PostDetail } from '@/api/modules/blog';
import MarkdownEditor from '@/components/common/MarkdownEditor.vue';
import { ElMessage, ElCard, ElInput, ElButton, ElForm, ElFormItem, ElSelect, ElOption, ElUpload, ElIcon } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import type { UploadFile } from 'element-plus';

const route = useRoute();
const router = useRouter();
const isLoading = ref(false);
const isSaving = ref(false);
const isNewPost = computed(() => !route.params.id);

const post = reactive<PostFormData>({
  title: '',
  content: '',
  status: 'draft',
  category: null,
  tags: [],
  cover_image: null,
  cover_image_file: null,
});

const coverPreviewUrl = ref('');
const categories = ref<Category[]>([]);
const tags = ref<Tag[]>([]);

const handleCoverChange = (uploadFile: UploadFile) => {
  if (uploadFile.raw) {
    post.cover_image_file = uploadFile.raw as File;
    coverPreviewUrl.value = URL.createObjectURL(uploadFile.raw);
  }
};

const loadInitialData = async () => {
  isLoading.value = true;
  try {
    const [catRes, tagRes] = await Promise.all([ getCategoryListApi(), getTagListApi() ]);
    categories.value = catRes;
    tags.value = tagRes;
    if (!isNewPost.value) {
      const postId = Number(route.params.id);
      const postData = await getPostDetailApi(postId);
      Object.assign(post, {
        ...postData,
        category: postData.category?.id,
        tags: postData.tags?.map(t => t.id),
      });
      if (postData.cover_image) {
        coverPreviewUrl.value = postData.cover_image;
      }
    }
  } catch (error) { ElMessage.error('加载数据失败'); } 
  finally { isLoading.value = false; }
};

const handleSave = async (status: 'draft' | 'published' | 'private') => {
  if (!post.title?.trim()) return ElMessage.warning('请输入文章标题');
  isSaving.value = true;
  try {
    const payload: PostFormData = { ...post, status };
    let savedPost: PostDetail;
    if (isNewPost.value) {
      savedPost = await createPostApi(payload);
      ElMessage.success('文章创建成功！');
      router.replace({ name: 'PostEditor', params: { id: savedPost.id } });
    } else {
      const postId = Number(route.params.id);
      savedPost = await updatePostApi(postId, payload);
      ElMessage.success('文章已保存！');
    }
    Object.assign(post, {
      ...savedPost,
      category: savedPost.category?.id,
      tags: savedPost.tags?.map(t => t.id),
      cover_image_file: null,
    });
    if (savedPost.cover_image) {
      coverPreviewUrl.value = savedPost.cover_image;
    }
  } catch (error) { ElMessage.error('保存失败'); } 
  finally { isSaving.value = false; }
};

const saveDraft = () => handleSave('draft');
const publishPost = () => handleSave('published');

onMounted(loadInitialData);
</script>

<style scoped>
.title-input :deep(.el-input__inner) {
  font-size: 1.5rem;
  font-weight: bold;
  border: none;
  box-shadow: none;
  padding-left: 0;
}
.cover-uploader .cover {
  width: 100%;
  height: 150px;
  object-fit: cover;
  display: block;
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
  height: 100%;
  text-align: center;
}
</style>