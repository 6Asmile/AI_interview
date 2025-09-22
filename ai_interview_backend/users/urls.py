from django.urls import path, include
from .views_auth import (
    UserRegisterView,
    SendCodeView,
    AvatarUploadView,
    UserProfileView,
    PasswordChangeView,
    SocialAccountDisconnectView
)
from .views_oauth import GitHubLogin, GitHubConnect

urlpatterns = [
    # --- 常规认证与用户管理 ---
    path('register/', UserRegisterView.as_view(), name='user-register'),
    path('send-code/', SendCodeView.as_view(), name='send-code'),
    path('upload-avatar/', AvatarUploadView.as_view(), name='upload-avatar'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('password/change/', PasswordChangeView.as_view(), name='password-change'),

    # --- 第三方 OAuth ---
    path('github/', GitHubLogin.as_view(), name='github_login'),
    path('github/connect/', GitHubConnect.as_view(), name='github_connect'),
    # 【核心修正】使用我们自己的解绑 API
    # URL 格式: /api/v1/auth/social/disconnect/{account_id}/
    path('social/disconnect/<int:account_id>/', SocialAccountDisconnectView.as_view(), name='social-disconnect'),

    # --- dj-rest-auth 内部依赖 ---
    path('registration/', include('dj_rest_auth.registration.urls'))
]