from django.urls import path, include
from .views_auth import (
    UserRegisterView,
    SendCodeView,
    AvatarUploadView,
    UserProfileView,
    PasswordChangeView,
    SocialAccountDisconnectView,
    NotificationPreferenceView,
    AuthSessionListView,
    AuthSessionRevokeView,
    LogoutView,
    PrivacyRequestView,
    MFAStatusView,
    MFASetupView,
    OnboardingCompleteView,
    MFAVerifyView,
    MFADisableView,
)
from .views_oauth import (
    GitHubConnect,
    GitHubLinkConfirmView,
    GitHubLogin,
    GitHubOAuthCallbackView,
    GitHubOAuthStartView,
)
from .token_views import BrowserSessionView, CsrfTokenView

urlpatterns = [
    path('csrf/', CsrfTokenView.as_view(), name='auth-csrf'),
    path('session/', BrowserSessionView.as_view(), name='browser-session'),
    # --- 常规认证与用户管理 ---
    path('register/', UserRegisterView.as_view(), name='user-register'),
    path('send-code/', SendCodeView.as_view(), name='send-code'),
    path('upload-avatar/', AvatarUploadView.as_view(), name='upload-avatar'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('onboarding/complete/', OnboardingCompleteView.as_view(), name='onboarding-complete'),
    path('password/change/', PasswordChangeView.as_view(), name='password-change'),
    path('notification-preferences/', NotificationPreferenceView.as_view(), name='notification-preferences'),
    path('sessions/', AuthSessionListView.as_view(), name='auth-sessions'),
    path('sessions/<uuid:session_id>/revoke/', AuthSessionRevokeView.as_view(), name='auth-session-revoke'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('logout-all/', LogoutView.as_view(), {'all_sessions': True}, name='logout-all'),
    path('privacy-requests/', PrivacyRequestView.as_view(), name='privacy-requests'),
    path('mfa/status/', MFAStatusView.as_view(), name='mfa-status'),
    path('mfa/setup/', MFASetupView.as_view(), name='mfa-setup'),
    path('mfa/verify/', MFAVerifyView.as_view(), name='mfa-verify'),
    path('mfa/disable/', MFADisableView.as_view(), name='mfa-disable'),

    # --- 第三方 OAuth ---
    path('oauth/github/start/', GitHubOAuthStartView.as_view(), name='github-oauth-start'),
    path('oauth/github/callback/', GitHubOAuthCallbackView.as_view(), name='github-oauth-callback'),
    path('oauth/github/link/confirm/', GitHubLinkConfirmView.as_view(), name='github-link-confirm'),
    path('github/', GitHubLogin.as_view(), name='github_login'),
    path('github/connect/', GitHubConnect.as_view(), name='github_connect'),
    # 【核心修正】使用我们自己的解绑 API
    # URL 格式: /api/v1/auth/social/disconnect/{account_id}/
    path('social/disconnect/<int:account_id>/', SocialAccountDisconnectView.as_view(), name='social-disconnect'),

    # --- dj-rest-auth 内部依赖 ---
    path('registration/', include('dj_rest_auth.registration.urls'))
]
