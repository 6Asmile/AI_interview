import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='KnowledgeDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200, verbose_name='文档标题')),
                ('content', models.TextField(verbose_name='知识内容')),
                ('source_type', models.CharField(default='question_bank', max_length=50, verbose_name='来源类型')),
                ('job_positions', models.JSONField(blank=True, default=list, verbose_name='适用岗位')),
                ('ability_tags', models.JSONField(blank=True, default=list, verbose_name='能力标签')),
                ('difficulty', models.CharField(choices=[('any', '不限'), ('easy', '基础'), ('medium', '中等'), ('hard', '高阶')], default='any', max_length=20, verbose_name='难度')),
                ('status', models.CharField(choices=[('draft', '草稿'), ('indexing', '索引中'), ('indexed', '已索引'), ('failed', '索引失败')], db_index=True, default='draft', max_length=20, verbose_name='索引状态')),
                ('chunk_count', models.PositiveIntegerField(default=0, verbose_name='分片数量')),
                ('error_message', models.TextField(blank=True, verbose_name='错误信息')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='knowledge_documents', to=settings.AUTH_USER_MODEL, verbose_name='创建人')),
            ],
            options={
                'verbose_name': '知识库文档',
                'verbose_name_plural': '知识库文档',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='KnowledgeChunk',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('chunk_index', models.PositiveIntegerField(verbose_name='分片序号')),
                ('content', models.TextField(verbose_name='分片内容')),
                ('metadata', models.JSONField(blank=True, default=dict, verbose_name='检索元数据')),
                ('qdrant_point_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('embedding_model', models.CharField(blank=True, max_length=120, verbose_name='Embedding模型')),
                ('indexed_at', models.DateTimeField(blank=True, null=True, verbose_name='索引时间')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to='knowledge.knowledgedocument', verbose_name='所属文档')),
            ],
            options={
                'verbose_name': '知识库分片',
                'verbose_name_plural': '知识库分片',
                'ordering': ['document', 'chunk_index'],
                'unique_together': {('document', 'chunk_index')},
            },
        ),
    ]
