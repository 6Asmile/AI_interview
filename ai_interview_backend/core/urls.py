from django.urls import path

from .views import WebSocketTicketView
from .task_views import AsyncOperationCancelView, AsyncOperationDetailView, AsyncOperationListView, AsyncOperationRetryView


urlpatterns = [
    path('ws-tickets/', WebSocketTicketView.as_view(), name='websocket-ticket'),
    path('tasks/', AsyncOperationListView.as_view(), name='async-operation-list'),
    path('tasks/<uuid:pk>/', AsyncOperationDetailView.as_view(), name='async-operation-detail'),
    path('tasks/<uuid:pk>/retry/', AsyncOperationRetryView.as_view(), name='async-operation-retry'),
    path('tasks/<uuid:pk>/cancel/', AsyncOperationCancelView.as_view(), name='async-operation-cancel'),
]
