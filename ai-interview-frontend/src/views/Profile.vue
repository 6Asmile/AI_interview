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
          <el-upload
            :show-file-list="false"
            :before-upload="beforeAvatarUpload"
            :http-request="handleAvatarUpload"
          >
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
          <el-alert v-if="!profileForm.has_password" title="您当前可能使用第三方账户登录，尚未设置密码。设置新密码后，您将可以使用邮箱和密码进行登录。" type="info" show-icon :closable="false" />
          <el-form-item v-if="profileForm.has_password" label="当前密码" prop="old_password">
            <el-input v-model="passwordForm.old_password" type="password" show-password placeholder="请输入当前密码" />
          </el-form-item>
          <el-form-item label="新密码" prop="new_password1" :style="{ marginTop: profileForm.has_password ? '0px' : '20px' }">
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

    <!-- 第三方账户绑定 -->
    <el-card>
      <template #header>
        <div class="page-card-header">
          <span>第三方账户绑定</span>
        </div>
      </template>
      <div v-if="!loading" class="social-accounts">
        <div class="account-item">
          <div class="account-info">
            <img src="@/assets/icons/github.svg" alt="GitHub" class="provider-icon" />
            <span>GitHub</span>
          </div>
          <div v-if="githubAccount" class="account-status">
            <span>已绑定: {{ githubAccount.extra_data.login }}</span>
            <el-button type="danger" plain size="small" @click="handleDisconnect('github')">解绑</el-button>
          </div>
          <div v-else class="account-status">
            <span>未绑定</span>
            <el-button type="primary" size="small" @click="handleConnectGitHub">去绑定</el-button>
          </div>
        </div>
      </div>
      <el-skeleton :rows="2" animated v-if="loading" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue';
import { ElMessage, ElMessageBox, ElLoading } from 'element-plus';
import type { FormInstance, FormRules, UploadProps, UploadRequestOptions } from 'element-plus';
import { useAuthStore } from '@/store/modules/auth';
import { 
  getUserProfileApi, 
  updateUserProfileApi, 
  uploadAvatarApi, 
  changePasswordApi, 
  disconnectSocialApi, // 确保导入
  type UserProfile, 
  type ChangePasswordData,
  type SocialAccount 
} from '@/api/modules/user';
import defaultAvatar from '@/assets/images/default_avatar.png';

const authStore = useAuthStore();
const loading = ref(true);
const savingProfile = ref(false);
const savingPassword = ref(false);

const profileForm = reactive<Partial<UserProfile>>({});
const passwordFormRef = ref<FormInstance>();
const passwordForm = reactive<ChangePasswordData>({
  old_password: '',
  new_password1: '',
  new_password2: '',
});

const validatePass2 = (rule: any, value: any, callback: any) => {
  if (value === '') { callback(new Error('请再次输入密码')); } 
  else if (value !== passwordForm.new_password1) { callback(new Error("两次输入的密码不一致!")); } 
  else { callback(); }
};

const passwordRules = reactive<FormRules>({
  old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password1: [{ required: true, message: '请输入新密码', trigger: 'blur' }, { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }],
  new_password2: [{ validator: validatePass2, trigger: 'blur', required: true }],
});

const githubAccount = computed<SocialAccount | undefined>(() => {
  return profileForm.socialaccount_set?.find(acc => acc.provider === 'github');
});

const fetchProfile = async () => {
  loading.value = true;
  try {
    const res = await getUserProfileApi();
    Object.assign(profileForm, res);
  } catch (error) { console.error("获取用户信息失败", error); ElMessage.error("获取用户信息失败"); } 
  finally { loading.value = false; }
};

// 【核心修正】onMounted 现在只负责获取个人信息
onMounted(() => {
  fetchProfile();
});

const beforeAvatarUpload: UploadProps['beforeUpload'] = (rawFile) => {
  const isJpgOrPng = rawFile.type === 'image/jpeg' || rawFile.type === 'image/png';
  if (!isJpgOrPng) { ElMessage.error('头像只能是 JPG/PNG 格式!'); return false; }
  const isLt2M = rawFile.size / 1024 / 1024 < 2;
  if (!isLt2M) { ElMessage.error('头像大小不能超过 2MB!'); return false; }
  return true;
};

const handleAvatarUpload = async (options: UploadRequestOptions) => {
  const formData = new FormData();
  formData.append('avatar', options.file);
  try {
    const res = await uploadAvatarApi(formData);
    profileForm.avatar = res.avatar_url;
    authStore.fetchUser();
    ElMessage.success('头像上传成功！');
  } catch (error) { console.error("上传头像失败", error); ElMessage.error('头像上传失败'); }
};

const handleSaveProfile = async () => {
  savingProfile.value = true;
  try {
    await updateUserProfileApi({ username: profileForm.username, phone: profileForm.phone });
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
        passwordFormRef.value?.resetFields();
        await fetchProfile();
      } catch (error) { console.error("密码更新失败", error); } 
      finally { savingPassword.value = false; }
    }
  });
};

// 【核心修正】发起绑定流程
const handleConnectGitHub = () => {
  const clientID = import.meta.env.VITE_GITHUB_CLIENT_ID;
  if (!clientID) { ElMessage.error('GitHub 登录未配置'); return; }

  const redirectUri = "http://localhost:5173/oauth/callback"; // 指向统一回调页
  
  // 在跳转前，在 localStorage 中设置一个清晰的标记
  localStorage.setItem('oauth_flow', 'connect');

  const githubAuthUrl = `https://github.com/login/oauth/authorize?client_id=${clientID}&redirect_uri=${redirectUri}&scope=user:email`;
  window.location.href = githubAuthUrl;
};

const handleDisconnect = async (provider: string) => {
  if (!githubAccount.value) return;
  ElMessageBox.confirm(`您确定要解绑此 ${provider.toUpperCase()} 账户吗？`, '警告', {
    confirmButtonText: '确定解绑', cancelButtonText: '取消', type: 'warning',
  }).then(async () => {
    const loading = ElLoading.service({ text: '正在解绑...' });
    try {
      await disconnectSocialApi(githubAccount.value!.id);
      ElMessage.success('账户已成功解绑！');
      await fetchProfile();
    } catch (error) {
      console.error("解绑失败", error);
      ElMessage.error("解绑失败，请稍后再试。");
    } finally {
      loading.close();
    }
  });
};
</script>

<style scoped>
.profile-container { display: flex; flex-direction: column; gap: 20px; }
.profile-content { display: flex; align-items: flex-start; gap: 50px; }
.avatar-section { display: flex; flex-direction: column; align-items: center; gap: 20px; }
.info-section { flex-grow: 1; max-width: 500px; }
.social-accounts { display: flex; flex-direction: column; gap: 15px; }
.account-item { display: flex; justify-content: space-between; align-items: center; padding: 10px; border: 1px solid #e4e7ed; border-radius: 4px; }
.account-info { display: flex; align-items: center; gap: 10px; font-weight: 500; }
.provider-icon { width: 24px; height: 24px; }
.account-status { display: flex; align-items: center; gap: 10px; color: #909399; }
</style>