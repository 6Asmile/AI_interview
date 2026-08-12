from django.urls import path

from .views_v2 import (
    OperationCancelView,
    OperationDetailView,
    OperationEventsView,
    OperationRetryView,
)


urlpatterns = [
    path('operations/<uuid:pk>/', OperationDetailView.as_view(), name='operation-v2-detail'),
    path('operations/<uuid:pk>/events/', OperationEventsView.as_view(), name='operation-v2-events'),
    path('operations/<uuid:pk>/retry/', OperationRetryView.as_view(), name='operation-v2-retry'),
    path('operations/<uuid:pk>/cancel/', OperationCancelView.as_view(), name='operation-v2-cancel'),
]
