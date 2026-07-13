from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interviews', '0005_interviewsession_agent_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='interviewquestion',
            name='rag_context',
            field=models.JSONField(blank=True, default=list, verbose_name='RAG题库上下文'),
        ),
    ]
