import request from '@/api/request';

export interface SocialAccount {
  id: number;
  provider: string;
  uid: string;
  last_login: string;
  date_joined: string;
  extra_data: Record<string, any>;
}

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  phone: string | null;
  avatar: string | null;
  role: string;
  date_joined: string;
  has_password: boolean;
  socialaccount_set: SocialAccount[];
  headline: string;
  location: string;
  years_experience: number;
  target_roles: string[];
  skills_profile: string[];
  availability: string;
  profile_visibility: 'private' | 'community' | 'public';
  onboarding_step: string;
  onboarding_completed_at: string | null;
  mfa_enabled: boolean;
  mfa_required: boolean;
}

export interface NotificationPreference {
  in_app_enabled: boolean;
  email_enabled: boolean;
  interview_reminders: boolean;
  application_updates: boolean;
  community_updates: boolean;
  direct_messages: boolean;
  digest_frequency: 'none' | 'daily' | 'weekly';
  quiet_hours: Record<string, string>;
  updated_at: string;
}

export interface AuthSession {
  id: string;
  ip_address: string | null;
  user_agent: string;
  device_name: string;
  expires_at: string;
  last_seen_at: string;
  revoked_at: string | null;
  created_at: string;
}

export interface ChangePasswordData { old_password?: string; new_password1: string; new_password2: string; }

export const getUserProfileApi = (): Promise<UserProfile> => request({ url: '/auth/profile/', method: 'get' });
export const updateUserProfileApi = (data: Partial<UserProfile>): Promise<UserProfile> => request({ url: '/auth/profile/', method: 'patch', data });
export const completeOnboardingApi = (): Promise<UserProfile> => request({ url: '/auth/onboarding/complete/', method: 'post' });
export const uploadAvatarApi = (formData: FormData): Promise<{ avatar_url: string }> => request({ url: '/auth/upload-avatar/', method: 'post', data: formData, headers: { 'Content-Type': 'multipart/form-data' } });
export const changePasswordApi = (data: ChangePasswordData) => request({ url: '/auth/password/change/', method: 'post', data });
export const connectGitHubApi = (code: string): Promise<{ message: string }> => request({ url: '/auth/github/connect/', method: 'post', data: { code } });
export const disconnectSocialApi = (accountId: number): Promise<{ message: string }> => request({ url: `/auth/social/disconnect/${accountId}/`, method: 'post' });
export const getNotificationPreferenceApi = (): Promise<NotificationPreference> => request({ url: '/auth/notification-preferences/', method: 'get' });
export const updateNotificationPreferenceApi = (data: Partial<NotificationPreference>): Promise<NotificationPreference> => request({ url: '/auth/notification-preferences/', method: 'patch', data });
export const getAuthSessionsApi = async (): Promise<AuthSession[]> => { const response: any = await request({ url: '/auth/sessions/', method: 'get' }); return Array.isArray(response) ? response : (response.results || []); };
export const revokeAuthSessionApi = (id: string) => request({ url: `/auth/sessions/${id}/revoke/`, method: 'post' });
export const createPrivacyRequestApi = (request_type: 'export' | 'delete', reason = '') => request({ url: '/auth/privacy-requests/', method: 'post', data: { request_type, reason } });
export const logoutAllSessionsApi = () => request({ url: '/auth/logout/', method: 'post', data: { all_sessions: true } });
export const getMFAStatusApi = () => request({ url: '/auth/mfa/status/', method: 'get' });
export const setupMFAApi = () => request({ url: '/auth/mfa/setup/', method: 'post' });
export const verifyMFAApi = (code: string) => request({ url: '/auth/mfa/verify/', method: 'post', data: { code } });
export const disableMFAApi = (password: string, code: string) => request({ url: '/auth/mfa/disable/', method: 'post', data: { password, code } });
