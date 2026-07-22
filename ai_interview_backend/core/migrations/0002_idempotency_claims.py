import uuid

from django.db import migrations, models
from django.utils import timezone


def populate_operation_ids(apps, schema_editor):
    record_model = apps.get_model('core', 'IdempotencyRecord')
    for record in record_model.objects.filter(operation_id__isnull=True).iterator():
        record.operation_id = uuid.uuid4()
        record.save(update_fields=['operation_id'])


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='idempotencyrecord',
            name='status',
            field=models.CharField(
                choices=[('pending', '处理中'), ('completed', '已完成'), ('failed', '失败')],
                db_index=True,
                default='completed',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='idempotencyrecord',
            name='operation_id',
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.AddField(
            model_name='idempotencyrecord',
            name='claim_token',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='idempotencyrecord',
            name='error_code',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='idempotencyrecord',
            name='lease_expires_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='idempotencyrecord',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(populate_operation_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='idempotencyrecord',
            name='operation_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='idempotencyrecord',
            name='status',
            field=models.CharField(
                choices=[('pending', '处理中'), ('completed', '已完成'), ('failed', '失败')],
                db_index=True,
                default='pending',
                max_length=16,
            ),
        ),
    ]
