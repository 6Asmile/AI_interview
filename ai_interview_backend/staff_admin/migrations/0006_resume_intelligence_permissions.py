from django.db import migrations


def seed_resume_intelligence(apps, schema_editor):
    StaffRole = apps.get_model('staff_admin', 'StaffRole')
    PlatformFeatureFlag = apps.get_model('staff_admin', 'PlatformFeatureFlag')
    db = schema_editor.connection.alias
    StaffRole.objects.using(db).update_or_create(
        slug='resume_intelligence_admin',
        defaults={
            'name': '简历智能管理员',
            'permissions': [
                'dashboard.view',
                'resume_config.manage',
                'resume_operations.view',
                'agent_config.view',
                'tasks.manage',
            ],
            'is_system': True,
        },
    )
    platform_role = StaffRole.objects.using(db).filter(slug='career_platform_admin').first()
    if platform_role:
        platform_role.permissions = sorted(set(
            (platform_role.permissions or []) + ['resume_config.manage', 'resume_operations.view']
        ))
        platform_role.save(update_fields=['permissions', 'updated_at'])
    PlatformFeatureFlag.objects.using(db).update_or_create(
        key='resume-studio-v2',
        defaults={
            'name': 'Resume Studio V2',
            'description': '按内部账号、5%、25%、100%逐步启用统一简历 Studio。',
            'enabled': False,
            'rollout_percentage': 0,
            'audience': {'internal_only': True},
        },
    )


class Migration(migrations.Migration):
    dependencies = [('staff_admin', '0005_career_platform_permissions')]
    operations = [migrations.RunPython(seed_resume_intelligence, migrations.RunPython.noop)]
