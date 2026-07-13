import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interviews', '0006_interviewquestion_rag_context'),
    ]

    operations = [
        migrations.CreateModel(
            name='InterviewAgentTrace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event', models.CharField(default='submit_answer', max_length=50, verbose_name='事件')),
                ('stage', models.CharField(blank=True, max_length=32, verbose_name='阶段')),
                ('node_outputs', models.JSONField(blank=True, default=dict, verbose_name='节点输出')),
                ('answer_evaluation', models.JSONField(blank=True, default=dict, verbose_name='回答评估摘要')),
                ('rag_context', models.JSONField(blank=True, default=list, verbose_name='RAG来源')),
                ('question_plan', models.JSONField(blank=True, default=dict, verbose_name='题目计划')),
                ('generated_question', models.TextField(blank=True, verbose_name='最终问题')),
                ('fallback_reason', models.CharField(blank=True, max_length=200, verbose_name='降级原因')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('question', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='agent_traces', to='interviews.interviewquestion', verbose_name='关联问题')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_traces', to='interviews.interviewsession', verbose_name='面试会话')),
            ],
            options={
                'verbose_name': '面试Agent轨迹',
                'verbose_name_plural': '面试Agent轨迹',
                'ordering': ['created_at'],
            },
        ),
    ]
