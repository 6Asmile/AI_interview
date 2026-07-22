import hashlib
import secrets
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from staff_admin.management.commands.bootstrap_staff_admin import ensure_roles
from staff_admin.models import StaffAccount, StaffInvitation
from users.models import User


class Command(BaseCommand):
    help = 'Create isolated staff invitations for legacy HR/admin candidate-domain accounts without copying passwords.'

    def handle(self, *args, **options):
        roles = ensure_roles()
        for user in User.objects.filter(role__in=[User.Role.HR, User.Role.ADMIN]):
            account, created = StaffAccount.objects.get_or_create(
                email=user.email.lower(), defaults={'display_name': user.username or user.email.split('@')[0]},
            )
            if not created or hasattr(account, 'invitation'):
                self.stdout.write(f'跳过 {user.email}：员工账号或邀请已存在。')
                continue
            account.roles.add(roles['super_admin' if user.role == User.Role.ADMIN else 'hr_ops'])
            raw = secrets.token_urlsafe(40)
            StaffInvitation.objects.create(
                account=account, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                expires_at=timezone.now() + timedelta(days=3),
            )
            self.stdout.write(self.style.SUCCESS(f'{user.email}\t{raw}'))
