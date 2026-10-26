from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('interviews', '0024_seed_resume_intelligence_prompts'),
    ]

    operations = [
        migrations.AddField(
            model_name='interviewagentexecution',
            name='fencing_token',
            field=models.PositiveBigIntegerField(default=0, verbose_name='执行栅栏令牌'),
        ),
        migrations.AddField(
            model_name='interviewagentexecution',
            name='heartbeat_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='最近心跳时间'),
        ),
        migrations.AddField(
            model_name='interviewagentexecution',
            name='lease_expires_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='租约过期时间'),
        ),
        migrations.AddField(
            model_name='interviewagentexecution',
            name='lease_owner',
            field=models.CharField(blank=True, db_index=True, max_length=128, verbose_name='租约持有者'),
        ),
        migrations.AddIndex(
            model_name='interviewagentexecution',
            index=models.Index(fields=['status', 'lease_expires_at'], name='interviews_status_lease_idx'),
        ),
    ]
