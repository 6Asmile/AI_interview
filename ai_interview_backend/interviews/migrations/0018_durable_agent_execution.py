import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('interviews', '0017_interviewagentexecution')]

    operations = [
        migrations.AlterField(
            model_name='interviewagentexecution',
            name='status',
            field=models.CharField(
                choices=[
                    ('accepted', '已接受'),
                    ('answer_persisted', '回答已持久化'),
                    ('evaluating', '评估中'),
                    ('evaluated', '评估完成'),
                    ('generating', '生成下一题'),
                    ('failed_retryable', '可重试失败'),
                    ('failed_terminal', '终止失败'),
                    ('pending', '待执行'),
                    ('running', '执行中'),
                    ('waiting', '等待生成或恢复'),
                    ('completed', '已完成'),
                    ('degraded', '降级完成'),
                    ('failed', '执行失败'),
                    ('canceled', '已取消'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='interviewagentexecution',
            name='version',
            field=models.PositiveIntegerField(default=0, verbose_name='状态版本'),
        ),
        migrations.AddField(
            model_name='interviewagentexecution',
            name='retry_count',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='重试次数'),
        ),
        migrations.AddField(
            model_name='interviewagentexecution',
            name='last_durable_sequence',
            field=models.PositiveIntegerField(default=0, verbose_name='最后持久化事件序号'),
        ),
        migrations.AddField(
            model_name='interviewagentexecution',
            name='state_metadata',
            field=models.JSONField(blank=True, default=dict, verbose_name='持久化状态摘要'),
        ),
        migrations.AddField(
            model_name='interviewagentexecution',
            name='result_question',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='result_agent_executions',
                to='interviews.interviewquestion',
                verbose_name='生成结果问题',
            ),
        ),
        migrations.CreateModel(
            name='InterviewAgentDispatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', '待投递'), ('published', '已投递'), ('failed', '投递失败'), ('canceled', '已取消')], db_index=True, default='pending', max_length=16)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('celery_task_id', models.CharField(blank=True, max_length=80)),
                ('error_code', models.CharField(blank=True, max_length=120)),
                ('error_message', models.TextField(blank=True)),
                ('next_attempt_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('execution', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='dispatch', to='interviews.interviewagentexecution')),
            ],
            options={
                'ordering': ['created_at'],
                'indexes': [models.Index(fields=['status', 'next_attempt_at', 'created_at'], name='interviews__status_48c674_idx')],
            },
        ),
        migrations.CreateModel(
            name='InterviewReferenceAnswer',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('prompt_version', models.CharField(max_length=80)),
                ('model_alias', models.CharField(max_length=120)),
                ('answer', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('pending', '生成中'), ('completed', '已完成'), ('failed', '失败')], db_index=True, default='pending', max_length=16)),
                ('error_code', models.CharField(blank=True, max_length=120)),
                ('source_hash', models.CharField(db_index=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reference_answers', to='interviews.interviewquestion')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='interview_reference_answers', to='users.user')),
            ],
            options={
                'indexes': [models.Index(fields=['user', 'status', 'updated_at'], name='interviews__user_id_a069a7_idx')],
                'constraints': [models.UniqueConstraint(fields=('question', 'user', 'prompt_version', 'model_alias'), name='uniq_interview_reference_answer_snapshot')],
            },
        ),
    ]
