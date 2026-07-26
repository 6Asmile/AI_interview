from django.db import migrations


def seed_roles(apps, schema_editor):
    StaffRole = apps.get_model('staff_admin', 'StaffRole')
    PlatformFeatureFlag = apps.get_model('staff_admin', 'PlatformFeatureFlag')
    db = schema_editor.connection.alias
    permissions = [
        'dashboard.view',
        'agent_config.view',
        'agent_config.manage',
        'agent_config.evaluate',
        'agent_config.publish',
        'knowledge_base.manage',
        'knowledge.review',
        'template.manage',
        'gateway.manage',
        'interview.audit',
        'audit.view',
        'tasks.manage',
    ]
    StaffRole.objects.using(db).update_or_create(
        slug='agent_config_admin',
        defaults={'name': 'Agent 配置管理员', 'permissions': permissions, 'is_system': True},
    )
    additions = {
        'hr_ops': ['agent_config.view'],
        'knowledge_reviewer': ['agent_config.view', 'knowledge_base.manage'],
    }
    for slug, extra in additions.items():
        role = StaffRole.objects.using(db).filter(slug=slug).first()
        if role:
            role.permissions = sorted(set((role.permissions or []) + extra))
            role.save(update_fields=['permissions', 'updated_at'])
    PlatformFeatureFlag.objects.using(db).update_or_create(
        key='agent-config-shadow',
        defaults={
            'name': 'Agent 配置解析影子对比',
            'description': '解析已发布配置并记录差异，但不改变新会话运行行为。',
            'enabled': True,
            'rollout_percentage': 100,
            'audience': {},
        },
    )
    PlatformFeatureFlag.objects.using(db).update_or_create(
        key='agent-config-new-sessions',
        defaults={
            'name': 'Agent 配置仅用于新会话',
            'description': '启用后仅新建会话冻结并使用 Agent 配置中心快照。',
            'enabled': False,
            'rollout_percentage': 0,
            'audience': {},
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ('staff_admin', '0003_staffaccount_recovery_codes_confirmed_at'),
    ]

    operations = [
        migrations.RunPython(seed_roles, migrations.RunPython.noop),
    ]
