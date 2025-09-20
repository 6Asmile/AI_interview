# system/views.py
from rest_framework import generics, permissions
from .models import AISetting
from .serializers import AISettingSerializer

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