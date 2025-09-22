from allauth.socialaccount.models import SocialAccount
from rest_framework import views, status, generics, permissions
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser, FormParser
from .services import send_verification_code
from .models import User
from .serializers import UserRegisterSerializer, UserProfileSerializer, PasswordChangeSerializer

# --- 验证码发送 ---
class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class SendCodeView(views.APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        if send_verification_code(email):
            return Response({"message": "验证码已成功发送，请注意查收。"}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "邮件发送失败，请稍后再试或联系管理员。"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- 用户注册 ---
class UserRegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]

# --- 个人信息管理 ---
class UserProfileView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        return self.request.user

# --- 头像上传 ---
class AvatarUploadView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('avatar')
        if not file_obj:
            return Response({'error': '没有提供头像文件'}, status=status.HTTP_400_BAD_REQUEST)
        if file_obj.size > 2 * 1024 * 1024:
            return Response({'error': '头像文件不能超过 2MB'}, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        user.avatar = file_obj
        user.save()
        return Response({'avatar_url': user.avatar.url}, status=status.HTTP_200_OK)

# --- 【核心修正】确保密码修改视图在这里定义 ---
class PasswordChangeView(generics.GenericAPIView):
    """
    处理用户设置/修改密码。
    POST /api/v1/auth/password/change/
    """
    serializer_class = PasswordChangeSerializer
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "密码已成功更新。"}, status=status.HTTP_200_OK)


# 【新增】手动处理解绑的 API 视图
class SocialAccountDisconnectView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # account_id 将从 URL 中捕获
        account_id = self.kwargs.get('account_id')
        if not account_id:
            return Response({"error": "Account ID not provided."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 确保用户只能解绑自己的社交账户
            social_account = SocialAccount.objects.get(id=account_id, user=request.user)
            social_account.delete()
            return Response({"message": "账户已成功解绑。"}, status=status.HTTP_200_OK)
        except SocialAccount.DoesNotExist:
            return Response({"error": "请求的社交账户不存在或不属于您。"}, status=status.HTTP_404_NOT_FOUND)