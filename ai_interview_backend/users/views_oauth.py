from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from allauth.socialaccount.models import SocialAccount, SocialLogin, SocialToken
from rest_framework_simplejwt.tokens import RefreshToken
from requests.exceptions import HTTPError
from django.contrib.auth import get_user_model
from .serializers import UserProfileSerializer, PasswordChangeSerializer # 导入新序列化器
User = get_user_model()


class GitHubLogin(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        code = request.data.get('code')
        if not code:
            return Response({"error": "Code not provided"}, status=status.HTTP_400_BAD_REQUEST)

        adapter = GitHubOAuth2Adapter(request)
        provider = adapter.get_provider()
        callback_url = "http://localhost:5173/login"
        client = OAuth2Client(
            request,
            provider.app.client_id,
            provider.app.secret,
            adapter.access_token_method,
            adapter.access_token_url,
            callback_url,
            provider.get_scope(),
        )

        try:
            # 1. 获取 Access Token
            access_token_data = client.get_access_token(code)
            access_token = access_token_data['access_token']

            # 2. 使用 Access Token 获取用户数据字典
            social_token = SocialToken(app=provider.app, token=access_token)
            login = adapter.complete_login(request, provider.app, social_token)
            user_data = login.account.extra_data
            github_uid = user_data.get('id')
            email = user_data.get('email')
            username = user_data.get('login')

            if not email:
                return Response({'error': '无法从您的 GitHub 账户获取已验证的邮箱。'},
                                status=status.HTTP_400_BAD_REQUEST)

            # 【终极核心修正】完全手动处理用户流程

            # 3. 首先，检查这个 GitHub 账户是否已经关联过
            try:
                social_account = SocialAccount.objects.get(provider='github', uid=github_uid)
                user = social_account.user
                print(f"找到已存在的社交账户，直接登录用户: {user.email}")
            except SocialAccount.DoesNotExist:
                # 4. 如果没有关联过，再用邮箱检查用户是否存在
                try:
                    user = User.objects.get(email__iexact=email)
                    print(f"找到邮箱匹配的已存在用户: {user.email}，准备关联新社交账户...")
                except User.DoesNotExist:
                    # 5. 如果邮箱也不存在，则创建全新的用户
                    print(f"全新用户，准备创建: {email}")
                    if User.objects.filter(username__iexact=username).exists():
                        username = f"{username}_{github_uid}"  # 使用唯一的 GitHub ID 避免用户名冲突
                    user = User.objects.create_user(username=username, email=email)

                # 6. 为新用户/已存在用户创建社交账户关联
                SocialAccount.objects.create(
                    user=user,
                    provider='github',
                    uid=github_uid,
                    extra_data=user_data
                )

            # 7. 为最终确定的用户生成 JWT
            refresh = RefreshToken.for_user(user)

            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_200_OK)

        except HTTPError as e:
            # ... (错误处理保持不变)
            return Response({"error": "与 GitHub 通信失败"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # ... (错误处理保持不变)
            import traceback
            traceback.print_exc()
            return Response({"error": f"发生意外错误: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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