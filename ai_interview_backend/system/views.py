# system/views.py
from rest_framework import generics, permissions
from .models import AISetting,  Industry  # 导入
from .serializers import AISettingSerializer,  IndustryWithJobsSerializer  # 导入

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