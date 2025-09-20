# users/views.py
from rest_framework import generics, permissions
from .models import User
from .serializers import UserRegisterSerializer

class UserRegisterView(generics.CreateAPIView):
    """
    用户注册视图
    """
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    # 允许任何人访问此视图
    permission_classes = [permissions.AllowAny]
    # 为这个特定的视图禁用所有认证检查，以绕过CSRF
    authentication_classes = []