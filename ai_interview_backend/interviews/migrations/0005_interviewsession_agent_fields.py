from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interviews', '0004_interviewsession_recording_enabled_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='interviewsession',
            name='covered_topics',
            field=models.JSONField(blank=True, default=list, verbose_name='已覆盖话题'),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='current_stage',
            field=models.CharField(choices=[('opening', '开场定位'), ('resume_deep_dive', '简历深挖'), ('technical_deep_dive', '技术深挖'), ('scenario_challenge', '场景挑战'), ('wrap_up', '收尾复盘')], default='opening', max_length=32, verbose_name='当前面试阶段'),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='memory_summary',
            field=models.JSONField(blank=True, default=dict, verbose_name='短期记忆摘要'),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='pending_topics',
            field=models.JSONField(blank=True, default=list, verbose_name='待追问话题'),
        ),
        migrations.AddField(
            model_name='interviewsession',
            name='perception_summary',
            field=models.JSONField(blank=True, default=dict, verbose_name='感知摘要'),
        ),
    ]
