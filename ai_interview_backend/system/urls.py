# system/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import (
    AISettingRetrieveUpdateView,
    IndustryWithJobsListView,
    AIModelListView,
    AIModelGatewayHealthView,
    ModelAliasViewSet,
    ModelDeploymentViewSet,
    ModelRequestLedgerViewSet,
    ProviderCredentialViewSet,
    RoutePolicyTargetViewSet,
    RoutePolicyViewSet,
    UsageBudgetViewSet,
)


router = DefaultRouter()
router.register('gateway/credentials', ProviderCredentialViewSet, basename='gateway-credential')
router.register('gateway/deployments', ModelDeploymentViewSet, basename='gateway-deployment')
router.register('gateway/aliases', ModelAliasViewSet, basename='gateway-alias')
router.register('gateway/route-policies', RoutePolicyViewSet, basename='gateway-route-policy')
router.register('gateway/route-targets', RoutePolicyTargetViewSet, basename='gateway-route-target')
router.register('gateway/budgets', UsageBudgetViewSet, basename='gateway-budget')
router.register('gateway/requests', ModelRequestLedgerViewSet, basename='gateway-request')

urlpatterns = [
    path('', include(router.urls)),
    path('settings/ai/', AISettingRetrieveUpdateView.as_view(), name='ai-settings'),
    path('settings/ai/health/', AIModelGatewayHealthView.as_view(), name='ai-settings-health'),
    path('jobs-by-industry/', IndustryWithJobsListView.as_view(), name='jobs-by-industry-list'),
    path('ai-models/', AIModelListView.as_view(), name='ai-model-list'), # 新增
]
