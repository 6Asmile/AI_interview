"""
URL configuration for ai_interview_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.contrib import admin
from django.urls import path, include  # 确保 include 已导入

from django.conf import settings
from django.conf.urls.static import static

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# 【核心修正】设置 Admin 站点的标题
admin.site.site_header = "IFaceOff 管理后台"
admin.site.site_title = "IFaceOff Admin Portal"
admin.site.index_title = "欢迎来到 IFaceOff 管理后台"


urlpatterns = [
    path('admin/', admin.site.urls),

    # 认证相关 API
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/', include('resumes.urls')),
    path('api/v1/', include('interviews.urls')),
    path('api/v1/', include('system.urls')),
]

# 2. 在开发模式下，添加用于服务 media 文件的 URL 路由
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)