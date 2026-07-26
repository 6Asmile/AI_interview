from django.urls import path

from .views_v2 import OperationDetailView, OperationEventsView


urlpatterns = [
    path('operations/<uuid:pk>/', OperationDetailView.as_view(), name='operation-v2-detail'),
    path('operations/<uuid:pk>/events/', OperationEventsView.as_view(), name='operation-v2-events'),
]
