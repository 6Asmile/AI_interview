from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0004_authoritative_async_operations'),
        ('interviews', '0026_agent_execution_operation_projection'),
    ]

    operations = [
        migrations.AddField(
            model_name='evaluationrun',
            name='operation',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='evaluation_run',
                to='core.asyncoperation',
                verbose_name='平台异步操作',
            ),
        ),
    ]
