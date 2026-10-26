import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interviews', '0027_evaluation_run_operation_projection'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SpeechLatencyMetric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metric_type', models.CharField(choices=[('asr_first_partial', 'ASR 首个部分文本'), ('asr_final', 'ASR 最终文本'), ('tts_first_audio', 'TTS 首音频'), ('barge_in_stop', '用户插话停止播放'), ('transcript_duplicate', '转写重复')], db_index=True, max_length=40)),
                ('latency_ms', models.FloatField(default=0)),
                ('language', models.CharField(blank=True, max_length=20)),
                ('network_profile', models.CharField(blank=True, max_length=32)),
                ('model_alias', models.CharField(blank=True, max_length=100)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('question', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='speech_latency_metrics', to='interviews.interviewquestion')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='speech_latency_metrics', to='interviews.interviewsession')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='speech_latency_metrics', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'indexes': [models.Index(fields=['metric_type', 'created_at'], name='speech_metric_type_time')]},
        ),
    ]
