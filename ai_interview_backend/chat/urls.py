from django.urls import path
from rest_framework_nested import routers

from .views import AttachmentUploadView, ConversationViewSet, MessageViewSet, StartConversationView, UserBlockViewSet


router = routers.DefaultRouter()
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'chat/blocks', UserBlockViewSet, basename='chat-block')

conversations_router = routers.NestedDefaultRouter(router, r'conversations', lookup='conversation')
conversations_router.register(r'messages', MessageViewSet, basename='conversation-messages')

urlpatterns = router.urls + conversations_router.urls + [
    path('conversations/start_with/<int:user_id>/', StartConversationView.as_view(), name='start-conversation'),
    path('chat/attachments/', AttachmentUploadView.as_view(), name='chat-attachment-upload'),
]
