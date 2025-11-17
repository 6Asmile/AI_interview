"""
URL configuration for ai_interview_backend project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static # 确保导入 static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
# 【核心新增】导入 spectacular 的视图
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from interviews.views import GenerateResumeView
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
        path('', include('blog.urls')),
        path('', include('interactions.urls')),
        path('', include('notifications.urls')),
        # 【新增】添加通用的文件上传路由
        path('upload/', FileUploadView.as_view(), name='file-upload'),
        path('', include('reports.urls')),
        path('generate-resume/', GenerateResumeView.as_view(), name='generate-resume'),
    ])),
    # 【核心新增】API Schema & 文档路由
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Swagger UI:
    path('api/v1/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    # Redoc UI:
    path('api/v1/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# 【核心修正】确保这行代码在主 urlpatterns 列表之外
# 这会为 /media/ 开头的 URL 添加路由，使其能正确找到上传的文件
if settings.DEBUG:
    # 静态文件路由（Admin 样式、JS 依赖）
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)