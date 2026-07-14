# system/views.py
import time
import uuid

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import Q
from rest_framework import generics, permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (
    AISetting,
    Industry,
    AIModel,
    ModelAlias,
    ModelDeployment,
    ModelRequestLedger,
    ProviderCredential,
    RoutePolicy,
    RoutePolicyTarget,
    UsageBudget,
)
from .serializers import (
    AISettingSerializer,
    IndustryWithJobsSerializer,
    AIModelSerializer,
    ModelAliasSerializer,
    ModelDeploymentSerializer,
    ModelRequestLedgerSerializer,
    ProviderCredentialSerializer,
    RoutePolicySerializer,
    RoutePolicyTargetSerializer,
    UsageBudgetSerializer,
)
from .model_gateway import ModelGateway


class SystemReadinessView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        checks = {}

        def run(name, callback, *, critical=False):
            started = time.monotonic()
            try:
                detail = callback()
                checks[name] = {
                    'ok': True,
                    'critical': critical,
                    'latency_ms': int((time.monotonic() - started) * 1000),
                    **(detail or {}),
                }
            except Exception as exc:
                checks[name] = {
                    'ok': False,
                    'critical': critical,
                    'latency_ms': int((time.monotonic() - started) * 1000),
                    'reason': type(exc).__name__,
                }

        def check_database():
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            return {}

        def check_cache():
            key = f'readiness:{uuid.uuid4()}'
            cache.set(key, 'ok', timeout=10)
            if cache.get(key) != 'ok':
                raise RuntimeError('cache_roundtrip_failed')
            cache.delete(key)
            return {}

        def check_broker():
            from ai_interview_backend.celery_app import app
            with app.connection_for_write().ensure_connection(max_retries=0):
                return {}

        def check_worker():
            from ai_interview_backend.celery_app import app
            replies = app.control.inspect(timeout=1).ping() or {}
            if not replies:
                raise RuntimeError('no_worker_heartbeat')
            return {'workers': len(replies)}

        def check_http(url, headers=None):
            response = requests.get(url, headers=headers or {}, timeout=2)
            response.raise_for_status()
            return {'status_code': response.status_code}

        run('database', check_database, critical=True)
        run('redis', check_cache, critical=True)
        run('rabbitmq', check_broker, critical=True)
        run('celery_worker', check_worker, critical=True)

        qdrant_url = str(getattr(settings, 'QDRANT_URL', '') or '').rstrip('/')
        if qdrant_url:
            run('qdrant', lambda: check_http(f'{qdrant_url}/collections'))
        else:
            checks['qdrant'] = {'ok': False, 'critical': False, 'reason': 'not_configured'}

        meili_url = str(getattr(settings, 'MEILISEARCH_URL', '') or '').rstrip('/')
        meili_headers = {}
        if getattr(settings, 'MEILISEARCH_API_KEY', ''):
            meili_headers['Authorization'] = f"Bearer {settings.MEILISEARCH_API_KEY}"
        if meili_url:
            run('meilisearch', lambda: check_http(f'{meili_url}/health', meili_headers))
        else:
            checks['meilisearch'] = {'ok': False, 'critical': False, 'reason': 'not_configured'}

        litellm_url = str(getattr(settings, 'LITELLM_PROXY_URL', '') or '').rstrip('/')
        litellm_health_url = litellm_url.removesuffix('/v1') + '/health/liveliness'
        run('litellm', lambda: check_http(litellm_health_url))

        critical_ok = all(item['ok'] for item in checks.values() if item.get('critical'))
        return Response({
            'ok': critical_ok,
            'async_jobs_available': bool(checks.get('celery_worker', {}).get('ok')),
            'components': checks,
        }, status=200 if critical_ok else 503)

class AIModelListView(generics.ListAPIView):
    """
    获取所有已启用的 AI 模型列表。
    """
    queryset = AIModel.objects.filter(is_active=True)
    serializer_class = AIModelSerializer
    permission_classes = [permissions.AllowAny] # 公开给所有用户看
class AISettingRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """
    获取和更新当前用户的 AI 设置。
    - GET: 返回当前用户的设置。
    - PUT/PATCH: 更新当前用户的设置。
    """
    queryset = AISetting.objects.all()
    serializer_class = AISettingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """
        重写此方法，以获取或创建当前用户的 AI 设置实例。
        """
        # get_or_create 返回一个 (object, created) 的元组
        obj, created = AISetting.objects.get_or_create(user=self.request.user)
        return obj


class AIModelGatewayHealthView(APIView):
    """
    对当前用户配置的模型网关做轻量健康检查。
    默认只检查是否配置；传入 model_type=chat|embedding|rerank 时会调用真实供应商。
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        model_type = request.data.get('model_type') or AIModel.ModelType.CHAT
        allowed_types = {choice[0] for choice in AIModel.ModelType.choices}
        if model_type not in allowed_types:
            return Response({'ok': False, 'error': 'unsupported_model_type'}, status=400)
        result = ModelGateway(request.user).health_check(model_type)
        return Response(result)

class IndustryWithJobsListView(generics.ListAPIView):
    """
    获取所有已启用的行业及其下的岗位列表。
    """
    # 我们查询的是 Industry，而不是 JobPosition
    queryset = Industry.objects.filter(is_active=True).prefetch_related(
        'job_positions' # 优化查询，一次性获取所有关联的岗位
    )
    serializer_class = IndustryWithJobsSerializer
    permission_classes = [permissions.AllowAny]


def _can_manage_gateway(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, 'role', '') == 'admin'))


class GatewayAdminPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return _can_manage_gateway(request.user)


class ProviderCredentialViewSet(viewsets.ModelViewSet):
    serializer_class = ProviderCredentialSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = ProviderCredential.objects.select_related('legacy_model')
        if _can_manage_gateway(user):
            return queryset.filter(Q(user=user) | Q(scope=ProviderCredential.Scope.PLATFORM))
        return queryset.filter(user=user, scope=ProviderCredential.Scope.BYOK)

    def perform_destroy(self, instance):
        if instance.scope == ProviderCredential.Scope.PLATFORM and not _can_manage_gateway(self.request.user):
            raise PermissionDenied('只有管理员可以删除平台凭据。')
        instance.delete()


class ModelDeploymentViewSet(viewsets.ModelViewSet):
    queryset = ModelDeployment.objects.select_related('credential').all()
    serializer_class = ModelDeploymentSerializer
    permission_classes = [GatewayAdminPermission]
    filterset_fields = ('provider', 'model_type', 'is_active', 'last_health_status')


class ModelAliasViewSet(viewsets.ModelViewSet):
    queryset = ModelAlias.objects.select_related('route_policy').prefetch_related('route_policy__targets__deployment')
    serializer_class = ModelAliasSerializer
    permission_classes = [GatewayAdminPermission]
    filterset_fields = ('model_type', 'is_active')


class RoutePolicyViewSet(viewsets.ModelViewSet):
    queryset = RoutePolicy.objects.select_related('alias').prefetch_related('targets__deployment')
    serializer_class = RoutePolicySerializer
    permission_classes = [GatewayAdminPermission]


class RoutePolicyTargetViewSet(viewsets.ModelViewSet):
    queryset = RoutePolicyTarget.objects.select_related('policy', 'deployment')
    serializer_class = RoutePolicyTargetSerializer
    permission_classes = [GatewayAdminPermission]


class UsageBudgetViewSet(viewsets.ModelViewSet):
    queryset = UsageBudget.objects.select_related('user')
    serializer_class = UsageBudgetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset if _can_manage_gateway(self.request.user) else self.queryset.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        if not _can_manage_gateway(request.user):
            raise PermissionDenied('只有管理员可以配置额度。')
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not _can_manage_gateway(request.user):
            raise PermissionDenied('只有管理员可以配置额度。')
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not _can_manage_gateway(request.user):
            raise PermissionDenied('只有管理员可以配置额度。')
        return super().destroy(request, *args, **kwargs)


class ModelRequestLedgerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ModelRequestLedger.objects.select_related('user', 'alias', 'deployment')
    serializer_class = ModelRequestLedgerSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ('status', 'task_name')

    def get_queryset(self):
        queryset = self.queryset
        if not _can_manage_gateway(self.request.user):
            queryset = queryset.filter(user=self.request.user)
        return queryset
