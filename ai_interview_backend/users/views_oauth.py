from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from allauth.socialaccount.models import SocialAccount, SocialToken
from rest_framework_simplejwt.tokens import RefreshToken
from requests.exceptions import HTTPError
from django.contrib.auth import get_user_model

User = get_user_model()

class GitHubLogin(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request, *args, **kwargs):
        code = request.data.get('code')
        if not code:
            return Response({"error": "Code not provided"}, status=status.HTTP_400_BAD_REQUEST)

        adapter = GitHubOAuth2Adapter(request)
        provider = adapter.get_provider()
        # 【最终修正】确保回调 URL 统一
        callback_url = "http://localhost:5173/oauth/callback"
        client = OAuth2Client(
            request, provider.app.client_id, provider.app.secret,
            adapter.access_token_method, adapter.access_token_url,
            callback_url, provider.get_scope(),
        )
        try:
            access_token_data = client.get_access_token(code)
            access_token = access_token_data['access_token']
            social_token = SocialToken(app=provider.app, token=access_token)
            login = adapter.complete_login(request, provider.app, social_token)
            github_uid = login.account.extra_data.get('id')
            email = login.account.extra_data.get('email')
            username = login.account.extra_data.get('login')
            if not email:
                return Response({'error': '无法从您的 GitHub 账户获取已验证的邮箱。'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                social_account = SocialAccount.objects.get(provider='github', uid=github_uid)
                user = social_account.user
            except SocialAccount.DoesNotExist:
                try:
                    user = User.objects.get(email__iexact=email)
                except User.DoesNotExist:
                    if User.objects.filter(username__iexact=username).exists():
                        username = f"{username}_{github_uid}"
                    user = User.objects.create_user(username=username, email=email)
                SocialAccount.objects.create(user=user, provider='github', uid=github_uid, extra_data=login.account.extra_data)
            refresh = RefreshToken.for_user(user)
            return Response({'access': str(refresh.access_token), 'refresh': str(refresh)}, status=status.HTTP_200_OK)
        except HTTPError as e: return Response({"error": "与 GitHub 通信失败"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e: import traceback; traceback.print_exc(); return Response({"error": f"发生意外错误: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class GitHubConnect(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, *args, **kwargs):
        code = request.data.get('code')
        if not code:
            return Response({"error": "Code not provided"}, status=status.HTTP_400_BAD_REQUEST)
        adapter = GitHubOAuth2Adapter(request)
        provider = adapter.get_provider()
        # 【最终修正】确保回调 URL 统一
        callback_url = "http://localhost:5173/oauth/callback"
        client = OAuth2Client(
            request, provider.app.client_id, provider.app.secret,
            adapter.access_token_method, adapter.access_token_url,
            callback_url, provider.get_scope(),
        )
        try:
            access_token_data = client.get_access_token(code)
            access_token = access_token_data['access_token']
            social_token = SocialToken(app=provider.app, token=access_token)
            login = adapter.complete_login(request, provider.app, social_token)
            if SocialAccount.objects.filter(provider='github', uid=login.account.uid).exists():
                return Response({"error": "此 GitHub 账户已被其他用户绑定。"}, status=status.HTTP_400_BAD_REQUEST)
            login.connect(request, request.user)
            return Response({"message": "GitHub 账户成功绑定！"}, status=status.HTTP_200_OK)
        except HTTPError as e: return Response({"error": "与 GitHub 通信失败"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e: import traceback; traceback.print_exc(); return Response({"error": f"发生意外错误: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)