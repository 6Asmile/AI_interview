from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('interviews', '0012_composite_agent_audit_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='interviewquestion',
            name='generation_mode',
            field=models.CharField(blank=True, default='legacy', max_length=32, verbose_name='生成模式'),
        ),
        migrations.AddField(
            model_name='interviewquestion',
            name='question_plan',
            field=models.JSONField(blank=True, default=dict, verbose_name='题目生成计划'),
        ),
        migrations.AddField(
            model_name='interviewquestion',
            name='question_signature',
            field=models.CharField(blank=True, db_index=True, max_length=64, verbose_name='题目语义签名'),
        ),
        migrations.AddField(
            model_name='interviewquestion',
            name='target_dimension',
            field=models.CharField(blank=True, db_index=True, max_length=80, verbose_name='目标能力维度'),
        ),
        migrations.AddField(
            model_name='interviewquestion',
            name='validation_status',
            field=models.CharField(blank=True, default='not_validated', max_length=32, verbose_name='校验状态'),
        ),
        migrations.CreateModel(
            name='InterviewAgentRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('event', models.CharField(db_index=True, max_length=50, verbose_name='事件')),
                ('request_hash', models.CharField(db_index=True, max_length=64, verbose_name='幂等请求哈希')),
                ('engine_name', models.CharField(default='composite_v2', max_length=40, verbose_name='Agent引擎')),
                ('status', models.CharField(choices=[('pending', '待运行'), ('running', '运行中'), ('waiting_generation', '等待生成'), ('completed', '已完成'), ('degraded', '降级完成'), ('failed', '失败')], db_index=True, default='pending', max_length=32)),
                ('state_schema_version', models.PositiveSmallIntegerField(default=2)),
                ('current_node', models.CharField(blank=True, db_index=True, max_length=80)),
                ('attempt_count', models.PositiveSmallIntegerField(default=0)),
                ('state_snapshot', models.JSONField(blank=True, default=dict)),
                ('fallback_reason', models.CharField(blank=True, max_length=200)),
                ('error_message', models.TextField(blank=True)),
                ('model_config_snapshot', models.JSONField(blank=True, default=dict)),
                ('prompt_version', models.CharField(blank=True, db_index=True, max_length=80)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_runs', to='interviews.interviewsession', verbose_name='面试会话')),
                ('trigger_question', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='agent_runs', to='interviews.interviewquestion', verbose_name='触发问题')),
            ],
            options={'verbose_name': '面试Agent运行', 'verbose_name_plural': '面试Agent运行', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='InterviewAgentNodeRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('node_name', models.CharField(db_index=True, max_length=80)),
                ('subagent_name', models.CharField(db_index=True, max_length=80)),
                ('status', models.CharField(choices=[('running', '运行中'), ('succeeded', '成功'), ('skipped', '跳过'), ('degraded', '降级'), ('failed', '失败')], db_index=True, default='running', max_length=20)),
                ('attempt', models.PositiveSmallIntegerField(default=1)),
                ('input_hash', models.CharField(blank=True, max_length=64)),
                ('output_summary', models.JSONField(blank=True, default=dict)),
                ('error_message', models.TextField(blank=True)),
                ('fallback_reason', models.CharField(blank=True, max_length=200)),
                ('latency_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('token_usage', models.JSONField(blank=True, default=dict)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='node_runs', to='interviews.interviewagentrun', verbose_name='Agent运行')),
            ],
            options={'verbose_name': '面试Agent节点运行', 'verbose_name_plural': '面试Agent节点运行', 'ordering': ['created_at', 'id']},
        ),
        migrations.AddField(
            model_name='interviewagenttrace',
            name='agent_run',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='traces', to='interviews.interviewagentrun', verbose_name='Agent运行'),
        ),
        migrations.AddConstraint(
            model_name='interviewagentrun',
            constraint=models.UniqueConstraint(fields=('session', 'event', 'request_hash'), name='uniq_interview_agent_run_request'),
        ),
        migrations.AddIndex(
            model_name='interviewagentrun',
            index=models.Index(fields=['session', 'status', 'updated_at'], name='interviews__session_988adb_idx'),
        ),
        migrations.AddIndex(
            model_name='interviewagentrun',
            index=models.Index(fields=['session', 'event', 'created_at'], name='interviews__session_3ff784_idx'),
        ),
        migrations.AddConstraint(
            model_name='interviewagentnoderun',
            constraint=models.UniqueConstraint(fields=('run', 'node_name', 'attempt'), name='uniq_interview_agent_node_attempt'),
        ),
        migrations.AddIndex(
            model_name='interviewagentnoderun',
            index=models.Index(fields=['run', 'status', 'created_at'], name='interviews__run_id_f87a57_idx'),
        ),
        migrations.AddIndex(
            model_name='interviewagentnoderun',
            index=models.Index(fields=['subagent_name', 'status', 'created_at'], name='interviews__subagen_e03953_idx'),
        ),
    ]
