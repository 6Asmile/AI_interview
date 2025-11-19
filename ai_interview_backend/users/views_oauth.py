import os

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from allauth.socialaccount.models import SocialAccount, SocialToken
from rest_framework_simplejwt.tokens import RefreshToken
from requests.exceptions import HTTPError
from django.contrib.auth import get_user_model
import traceback
import requests  # 引入 requests 库

User = get_user_model()


class GitHubLogin(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        code = request.data.get('code')
        if not code:
            return Response({"error": "Code not provided"}, status=status.HTTP_400_BAD_REQUEST)

        print(f"--- [GitHubLogin] Start ---")

        adapter = GitHubOAuth2Adapter(request)
        provider = adapter.get_provider()

        # 务必与 GitHub 后台配置一致
        # 【核心修改】从环境变量获取回调地址，如果没配置则默认用本地的
        # 生产环境（Docker）需要在 .env 中配置 GITHUB_CALLBACK_URL
        default_callback = "http://localhost:5173/oauth/callback"
        callback_url = os.getenv("GITHUB_CALLBACK_URL", default_callback)

        client = OAuth2Client(
            request, provider.app.client_id, provider.app.secret,
            adapter.access_token_method, adapter.access_token_url,
            callback_url, provider.get_scope(),
        )

        try:
            # 1. 获取 Access Token
            access_token_data = client.get_access_token(code)
            if 'error' in access_token_data:
                return Response({"error": f"GitHub Error: {access_token_data.get('error_description')}"},
                                status=status.HTTP_400_BAD_REQUEST)

            access_token = access_token_data['access_token']
            social_token = SocialToken(app=provider.app, token=access_token)

            # 2. 完成登录，获取基础信息
            login = adapter.complete_login(request, provider.app, social_token)

            github_uid = login.account.extra_data.get('id')
            username = login.account.extra_data.get('login')
            email = login.account.extra_data.get('email')

            print(f"Initial Info: User={username}, Email={email}")

            # --- 【核心修复】如果邮箱为空，主动去请求私有邮箱接口 ---
            if not email:
                print("Email is hidden. Fetching from /user/emails...")
                try:
                    # 使用 Token 请求 GitHub 邮箱接口
                    email_resp = requests.get(
                        "https://api.github.com/user/emails",
                        headers={"Authorization": f"token {access_token}"}
                    )
                    if email_resp.status_code == 200:
                        emails = email_resp.json()
                        # 优先找主邮箱(primary)且已验证(verified)的
                        for e in emails:
                            if e.get('primary') and e.get('verified'):
                                email = e.get('email')
                                break
                        # 如果没找到主邮箱，找任意一个已验证的
                        if not email:
                            for e in emails:
                                if e.get('verified'):
                                    email = e.get('email')
                                    break
                    print(f"Fetched Private Email: {email}")
                except Exception as e:
                    print(f"Failed to fetch private email: {e}")
            # ------------------------------------------------------

            if not email:
                return Response({'error': '无法从您的 GitHub 账户获取有效的邮箱地址，请检查 GitHub 设置。'},
                                status=status.HTTP_400_BAD_REQUEST)

            # 3. 查找或创建用户逻辑
            try:
                # 先按 GitHub ID 找
                social_account = SocialAccount.objects.get(provider='github', uid=github_uid)
                user = social_account.user
            except SocialAccount.DoesNotExist:
                # 再按邮箱找
                try:
                    user = User.objects.get(email__iexact=email)
                except User.DoesNotExist:
                    # 都不存在，创建新用户
                    if User.objects.filter(username__iexact=username).exists():
                        username = f"{username}_{github_uid}"
                    user = User.objects.create_user(username=username, email=email)

                # 创建关联
                SocialAccount.objects.create(
                    user=user,
                    provider='github',
                    uid=github_uid,
                    extra_data=login.account.extra_data
                )

            # 4. 生成 JWT
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }, status=status.HTTP_200_OK)

        except HTTPError as e:
            return Response({"error": "与 GitHub 通信失败"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            traceback.print_exc()
            return Response({"error": f"发生意外错误: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GitHubConnect(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        code = request.data.get('code')
        if not code:
            return Response({"error": "Code not provided"}, status=status.HTTP_400_BAD_REQUEST)

        adapter = GitHubOAuth2Adapter(request)
        provider = adapter.get_provider()

        # 【核心修改】同上，使用环境变量
        default_callback = "http://localhost:5173/oauth/callback"
        callback_url = os.getenv("GITHUB_CALLBACK_URL", default_callback)

        client = OAuth2Client(
            request, provider.app.client_id, provider.app.secret,
            adapter.access_token_method, adapter.access_token_url,
            callback_url, provider.get_scope(),
        )

        try:
            access_token_data = client.get_access_token(code)
            if 'error' in access_token_data:
                return Response({"error": f"GitHub Error: {access_token_data.get('error_description')}"},
                                status=status.HTTP_400_BAD_REQUEST)

            access_token = access_token_data['access_token']
            social_token = SocialToken(app=provider.app, token=access_token)
            login = adapter.complete_login(request, provider.app, social_token)

            # 绑定时也不需要额外的邮箱检查，主要检查 UID 是否冲突
            if SocialAccount.objects.filter(provider='github', uid=login.account.uid).exists():
                return Response({"error": "此 GitHub 账户已被其他用户绑定。"}, status=status.HTTP_400_BAD_REQUEST)

            login.connect(request, request.user)
            return Response({"message": "GitHub 账户成功绑定！"}, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({"error": f"发生意外错误: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)