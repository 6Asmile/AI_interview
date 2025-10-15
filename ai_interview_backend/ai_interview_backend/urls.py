"""
URL configuration for ai_interview_backend project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static # 确保导入 static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from resumes.views_upload import FileUploadView

admin.site.site_header = "IFaceOff 管理后台"
admin.site.site_title = "IFaceOff Admin Portal"
admin.site.index_title = "欢迎来到 IFaceOff 管理后台"

urlpatterns = [
    path('admin/', admin.site.urls),

    # 【核心修正】将所有业务 API 都放在 'api/v1/' 命名空间下
    path('api/v1/', include([
        path('auth/', include('users.urls')),
        path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
        path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
        path('', include('resumes.urls')),
        path('', include('interviews.urls')),
        path('', include('system.urls')),
        # 【新增】添加通用的文件上传路由
        path('upload/', FileUploadView.as_view(), name='file-upload'),
    ])),
]

# 【核心修正】确保这行代码在主 urlpatterns 列表之外
# 这会为 /media/ 开头的 URL 添加路由，使其能正确找到上传的文件
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)