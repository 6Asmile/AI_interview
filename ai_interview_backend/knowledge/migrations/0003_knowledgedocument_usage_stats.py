from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('knowledge', '0002_knowledgedocument_visibility'),
    ]

    operations = [
        migrations.AddField(
            model_name='knowledgedocument',
            name='last_indexed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='最后索引时间'),
        ),
        migrations.AddField(
            model_name='knowledgedocument',
            name='last_retrieved_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='最后检索命中时间'),
        ),
        migrations.AddField(
            model_name='knowledgedocument',
            name='retrieval_count',
            field=models.PositiveIntegerField(default=0, verbose_name='检索命中次数'),
        ),
    ]
