# ai-interview-backend/chat/urls.py (新建文件)

from rest_framework_nested import routers
from .views import ConversationViewSet, MessageViewSet,StartConversationView
from django.urls import path # <-- 导入 path

# 1. 创建主路由
router = routers.DefaultRouter()
router.register(r'conversations', ConversationViewSet, basename='conversation')

# 2. 创建嵌套路由
# 这会生成类似 /conversations/{conversation_pk}/messages/ 的 URL
conversations_router = routers.NestedDefaultRouter(router, r'conversations', lookup='conversation')
conversations_router.register(r'messages', MessageViewSet, basename='conversation-messages')


# 将所有 URL 合并
urlpatterns = router.urls + conversations_router.urls + [
    # 【核心新增】为新视图添加路径
    path('conversations/start_with/<int:user_id>/', StartConversationView.as_view(), name='start-conversation'),
]