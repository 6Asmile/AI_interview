from django.core.management.base import BaseCommand, CommandError

from staff_admin.models import StaffAccount, StaffRole


ROLE_PRESETS = {
    'super_admin': ('超级管理员', ['*']),
    'hr_ops': ('HR 运营', [
        'dashboard.view', 'interview.audit', 'interview.operate', 'template.manage',
        'candidate.support', 'candidate.private_access', 'tasks.manage', 'analytics.view',
        'agent_config.view',
    ]),
    'knowledge_reviewer': ('知识审核', [
        'dashboard.view', 'knowledge.review', 'knowledge.operate', 'knowledge_base.manage',
        'agent_config.view', 'tasks.manage',
    ]),
    'agent_config_admin': ('Agent 配置管理员', [
        'dashboard.view', 'agent_config.view', 'agent_config.manage',
        'agent_config.evaluate', 'agent_config.publish', 'knowledge_base.manage',
        'knowledge.review', 'template.manage', 'gateway.manage', 'interview.audit',
        'audit.view', 'tasks.manage',
    ]),
    'model_ops': ('模型运维', ['dashboard.view', 'gateway.manage', 'system.health', 'tasks.manage', 'analytics.view']),
    'moderator': ('社区审核', ['dashboard.view', 'moderation.manage', 'content.manage']),
    'support': ('客服', [
        'dashboard.view', 'candidate.support', 'candidate.private_access', 'privacy.manage',
        'tasks.manage', 'notifications.manage',
    ]),
    'auditor': ('只读审计', ['dashboard.view', 'audit.view', 'interview.audit', 'system.health', 'analytics.view']),
}


def ensure_roles():
    result = {}
    for slug, (name, permissions) in ROLE_PRESETS.items():
        result[slug], _ = StaffRole.objects.update_or_create(
            slug=slug, defaults={'name': name, 'permissions': permissions, 'is_system': True},
        )
    return result


class Command(BaseCommand):
    help = 'Create the isolated admin role presets and optionally bootstrap a super admin.'

    def add_arguments(self, parser):
        parser.add_argument('--email')
        parser.add_argument('--password')
        parser.add_argument('--name', default='系统管理员')

    def handle(self, *args, **options):
        roles = ensure_roles()
        email = options.get('email')
        if not email:
            self.stdout.write(self.style.SUCCESS(f'已同步 {len(roles)} 个员工角色。'))
            return
        password = options.get('password')
        if not password:
            raise CommandError('指定 --email 时必须同时指定 --password。')
        account, created = StaffAccount.objects.get_or_create(
            email=email.strip().lower(), defaults={'display_name': options['name'], 'status': StaffAccount.Status.ACTIVE},
        )
        account.set_password(password)
        account.status = StaffAccount.Status.ACTIVE
        account.must_change_password = True
        account.save()
        account.roles.add(roles['super_admin'])
        self.stdout.write(self.style.SUCCESS(f'员工超级管理员已{"创建" if created else "更新"}：{account.email}'))
