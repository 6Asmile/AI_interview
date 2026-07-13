from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('knowledge', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='knowledgedocument',
            name='visibility',
            field=models.CharField(choices=[('private', '私有'), ('public', '公共')], db_index=True, default='private', max_length=20, verbose_name='可见范围'),
        ),
    ]
