from rest_framework import views, status, generics, permissions
from rest_framework.response import Response
from rest_framework import serializers
from .services import send_verification_code
from .models import User
from .serializers import UserRegisterSerializer
from rest_framework.parsers import MultiPartParser, FormParser # 1. 导入解析器
from .serializers import UserProfileSerializer
class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class SendCodeView(views.APIView):
    """
    发送邮箱验证码的视图。
    """
    # 【核心修正】
    # 明确为此视图设置权限，覆盖全局的 IsAuthenticated 设置。
    # AllowAny 意味着任何人都可以访问此接口。
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        if send_verification_code(email):
            return Response({"message": "验证码已成功发送，请注意查收。"}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "邮件发送失败，请稍后再试或联系管理员。"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserRegisterView(generics.CreateAPIView):
    """
    用户注册视图。
    """
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    # 【核心修正】
    # 注册接口同样需要对所有用户开放。
    permission_classes = [permissions.AllowAny]


class AvatarUploadView(views.APIView):
    """
    处理当前登录用户头像上传的视图。
    """
    permission_classes = [permissions.IsAuthenticated]  # 2. 必须登录才能上传
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('avatar')
        if not file_obj:
            return Response({'error': '没有提供头像文件'}, status=status.HTTP_400_BAD_REQUEST)

        # 验证文件大小和类型 (可选但推荐)
        if file_obj.size > 2 * 1024 * 1024:  # 2MB
            return Response({'error': '头像文件不能超过 2MB'}, status=status.HTTP_400_BAD_REQUEST)

        # 直接更新当前用户的头像字段
        user = request.user
        user.avatar = file_obj
        user.save()

        # 3. 返回更新后的头像 URL
        return Response({'avatar_url': user.avatar.url}, status=status.HTTP_200_OK)

class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    获取和更新当前登录用户的个人信息。
    """
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # 始终返回当前请求的用户实例
        return self.request.user