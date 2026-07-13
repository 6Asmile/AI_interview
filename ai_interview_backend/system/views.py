# system/views.py
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
