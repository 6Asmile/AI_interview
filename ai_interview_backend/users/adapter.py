# users/adapter.py
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        在第三方登录完成、但在本地系统创建或关联用户之前被调用。
        这是处理账户关联逻辑的最佳位置。
        """
        user = sociallogin.user
        # 如果 GitHub 用户没有提供邮箱，则直接返回
        if not user.email:
            return

        # 尝试根据邮箱查找系统中是否已存在用户
        try:
            existing_user = User.objects.get(email__iexact=user.email)
            # 如果找到了，说明用户之前可能用邮箱注册过
            # 将当前的 sociallogin 关联到这个已存在的用户
            sociallogin.connect(request, existing_user)
        except User.DoesNotExist:
            # 如果没找到，则 allauth 会继续执行正常的创建新用户流程
            pass