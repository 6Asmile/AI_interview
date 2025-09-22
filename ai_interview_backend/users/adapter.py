from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_email
from django.contrib.auth import get_user_model
from allauth.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.urls import reverse

User = get_user_model()


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):
        """
        在第三方登录完成、但在本地系统创建或关联用户之前被调用。
        这是处理账户关联、冲突等所有逻辑的最佳位置。
        """
        # 从 sociallogin 中获取 GitHub 返回的用户数据
        github_user_data = sociallogin.account.extra_data
        email = github_user_data.get('email')

        # 如果 GitHub 没有返回邮箱，尝试从 allauth 的辅助函数获取
        if not email:
            email = user_email(sociallogin.user)

        # 如果最终还是没有邮箱，则中断流程 (这种情况很少见)
        if not email:
            # 您可以在这里重定向到一个错误页面
            # raise ImmediateHttpResponse(redirect('/login?error=no_email'))
            return

        # --- 核心逻辑 ---
        try:
            # 1. 尝试用邮箱查找系统中是否已存在用户
            user = User.objects.get(email__iexact=email)

            # 2. 如果找到了用户，但这个社交账户还没有关联到他身上
            if not sociallogin.is_existing:
                print(f"找到邮箱匹配的用户 {user.email}，将 GitHub 账户与其关联。")
                sociallogin.connect(request, user)

        except User.DoesNotExist:
            # 3. 如果系统中不存在这个邮箱的用户，则 allauth 会继续执行正常的“创建新用户”流程
            print(f"全新用户，allauth 将自动创建用户: {email}")
            pass

    def save_user(self, request, sociallogin, form=None):
        """
        在创建新用户时被调用。我们可以在这里覆盖默认行为。
        """
        user = super().save_user(request, sociallogin, form)
        # 可以在这里从 sociallogin.account.extra_data 中提取更多信息来填充 user 对象
        # 例如 user.avatar = sociallogin.account.get_avatar_url()
        return user