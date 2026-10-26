from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0004_authoritative_async_operations'),
        ('interviews', '0025_agent_execution_lease_and_fencing'),
    ]

    operations = [
        migrations.AddField(
            model_name='interviewagentexecution',
            name='operation',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='interview_agent_execution',
                to='core.asyncoperation',
                verbose_name='平台异步操作',
            ),
        ),
    ]
