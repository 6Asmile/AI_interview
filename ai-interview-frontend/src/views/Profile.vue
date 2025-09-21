<template>
  <div class="page-container profile-container">
    <!-- 个人信息卡片 -->
    <el-card>
      <template #header>
        <div class="page-card-header">
          <span>个人信息</span>
        </div>
      </template>
      <div v-if="!loading" class="profile-content">
        <div class="avatar-section">
          <el-avatar :size="120" :src="profileForm.avatar || defaultAvatar" />
          <el-upload :show-file-list="false" :before-upload="beforeAvatarUpload" :http-request="handleAvatarUpload">
            <el-button type="primary" class="upload-btn">更换头像</el-button>
          </el-upload>
        </div>
        <div class="info-section">
          <el-form :model="profileForm" label-width="80px">
            <el-form-item label="用户名">
              <el-input v-model="profileForm.username" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="profileForm.email" disabled />
            </el-form-item>
            <el-form-item label="手机号">
              <el-input v-model="profileForm.phone" placeholder="暂未绑定" />
            </el-form-item>
            <el-form-item>
              <el-button type="success" @click="handleSaveProfile" :loading="savingProfile">保存信息</el-button>
            </el-form-item>
          </el-form>
        </div>
      </div>
      <el-skeleton :rows="5" animated v-if="loading" />
    </el-card>

    <!-- 安全设置卡片 -->
    <el-card>
      <template #header>
        <div class="page-card-header">
          <span>安全设置</span>
        </div>
      </template>
      <div v-if="!loading" class="info-section">
        <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-width="120px">
          <!-- 如果用户已有密码，则显示“当前密码”输入框 -->
          <el-form-item v-if="profileForm.has_password" label="当前密码" prop="old_password">
            <el-input v-model="passwordForm.old_password" type="password" show-password placeholder="请输入当前密码" />
          </el-form-item>
           <el-alert v-else title="您当前使用第三方账户登录，尚未设置密码。设置新密码后，您将可以使用邮箱和密码进行登录。" type="info" show-icon :closable="false" />
          
          <el-form-item label="新密码" prop="new_password1" style="margin-top: 20px;">
            <el-input v-model="passwordForm.new_password1" type="password" show-password placeholder="请输入新密码" />
          </el-form-item>
          <el-form-item label="确认新密码" prop="new_password2">
            <el-input v-model="passwordForm.new_password2" type="password" show-password placeholder="请再次输入新密码" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handlePasswordChange" :loading="savingPassword">
              {{ profileForm.has_password ? '修改密码' : '设置密码' }}
            </el-button>
          </el-form-item>
        </el-form>
      </div>
       <el-skeleton :rows="4" animated v-if="loading" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules, UploadProps, UploadRequestOptions } from 'element-plus';
import { useAuthStore } from '@/store/modules/auth';
import { getUserProfileApi, updateUserProfileApi, uploadAvatarApi, changePasswordApi, type UserProfile, type ChangePasswordData } from '@/api/modules/user';
import defaultAvatar from '@/assets/images/default_avatar.png';

const authStore = useAuthStore();
const loading = ref(true);
const savingProfile = ref(false);
const savingPassword = ref(false);

// --- 个人信息表单 ---
const profileForm = reactive<Partial<UserProfile>>({});

// --- 密码表单 ---
const passwordFormRef = ref<FormInstance>();
const passwordForm = reactive<ChangePasswordData>({
  old_password: '',
  new_password1: '',
  new_password2: '',
});

const validatePass2 = (_rule: any, value: any, callback: any) => {
  if (value === '') {
    callback(new Error('请再次输入密码'));
  } else if (value !== passwordForm.new_password1) {
    callback(new Error("两次输入的密码不一致!"));
  } else {
    callback();
  }
};

const passwordRules = reactive<FormRules>({
  old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password1: [{ required: true, message: '请输入新密码', trigger: 'blur' }, { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }],
  new_password2: [{ validator: validatePass2, trigger: 'blur', required: true }],
});

// --- 逻辑函数 ---

const fetchProfile = async () => {
  loading.value = true;
  try {
    const res = await getUserProfileApi();
    Object.assign(profileForm, res);
  } catch (error) { console.error("获取用户信息失败", error); } 
  finally { loading.value = false; }
};

onMounted(fetchProfile);

const handleAvatarUpload = async (options: UploadRequestOptions) => {
  const formData = new FormData();
  formData.append('avatar', options.file);
  try {
    const res = await uploadAvatarApi(formData);
    profileForm.avatar = res.avatar_url;
    // 更新 Pinia store 中的头像
    authStore.fetchUser();
    ElMessage.success('头像上传成功！');
  } catch (error) { ElMessage.error('头像上传失败'); }
};

const handleSaveProfile = async () => {
  savingProfile.value = true;
  try {
    await updateUserProfileApi({ username: profileForm.username, phone: profileForm.phone });
    // 更新 Pinia store 中的用户名
    authStore.fetchUser();
    ElMessage.success('个人信息更新成功！');
  } catch (error) { console.error('更新信息失败', error); } 
  finally { savingProfile.value = false; }
};

const handlePasswordChange = async () => {
  if (!passwordFormRef.value) return;
  await passwordFormRef.value.validate(async (valid) => {
    if (valid) {
      savingPassword.value = true;
      try {
        await changePasswordApi(passwordForm);
        ElMessage.success('密码更新成功！');
        // 清空表单
        passwordFormRef.value?.resetFields();
        // 更新用户信息，让 has_password 状态变为 true
        fetchProfile();
      } catch (error) { console.error("密码更新失败", error); } 
      finally { savingPassword.value = false; }
    }
  });
};

const beforeAvatarUpload: UploadProps['beforeUpload'] = (_rawFile) => { /* ... (保持不变) ... */ return true; };
</script>

<style scoped>
.profile-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.profile-content {
  display: flex;
  align-items: flex-start;
  gap: 50px;
}
.avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}
.info-section {
  flex-grow: 1;
  max-width: 500px;
}
</style>