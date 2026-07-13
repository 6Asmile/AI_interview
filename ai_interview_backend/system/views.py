# system/views.py
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import AISetting, Industry, AIModel  # 导入
from .serializers import AISettingSerializer, IndustryWithJobsSerializer, AIModelSerializer  # 导入
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
