from django.db import migrations


def seed_permissions(apps, schema_editor):
    StaffRole = apps.get_model('staff_admin', 'StaffRole')
    PlatformFeatureFlag = apps.get_model('staff_admin', 'PlatformFeatureFlag')
    db = schema_editor.connection.alias
    permissions = [
        'career_config.manage',
        'company.verify',
        'job.review',
        'community.moderate',
        'community.policy.manage',
        'platform_events.view',
        'platform_events.replay',
        'reliability.manage',
    ]
    StaffRole.objects.using(db).update_or_create(
        slug='career_platform_admin',
        defaults={
            'name': '求职平台管理员',
            'permissions': permissions,
            'is_system': True,
        },
    )
    for key, name, description in (
        ('native-community-shadow', '原生社区影子读', '对比旧 Blog/Discourse 与统一内容库，不改变线上读取。'),
        ('native-community-write', '原生社区新写入', '启用统一内容库新写入。'),
        ('career-platform-new-users', '求职平台新用户', '逐步开放完整求职闭环与 PWA 首页。'),
    ):
        PlatformFeatureFlag.objects.using(db).update_or_create(
            key=key,
            defaults={
                'name': name,
                'description': description,
                'enabled': key == 'native-community-shadow',
                'rollout_percentage': 100 if key == 'native-community-shadow' else 0,
                'audience': {},
            },
        )


class Migration(migrations.Migration):
    dependencies = [('staff_admin', '0004_agent_config_permissions')]
    operations = [migrations.RunPython(seed_permissions, migrations.RunPython.noop)]
