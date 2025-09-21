from django.urls import path, include
from .views_auth import UserRegisterView, SendCodeView, AvatarUploadView, UserProfileView
from .views_oauth import GitHubLogin, PasswordChangeView

urlpatterns = [
    path('register/', UserRegisterView.as_view(), name='user-register'),
    path('send-code/', SendCodeView.as_view(), name='send-code'),
    path('upload-avatar/', AvatarUploadView.as_view(), name='upload-avatar'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('password/change/', PasswordChangeView.as_view(), name='password-change'),
    # dj-rest-auth social login
    path('github/', GitHubLogin.as_view(), name='github_login'),

    # 【核心修正】包含 dj-rest-auth 的注册 URL
    path('', include('dj_rest_auth.urls')),
    # 这会提供一些 allauth 可能依赖的内部 URL
    path('registration/', include('dj_rest_auth.registration.urls'))
]