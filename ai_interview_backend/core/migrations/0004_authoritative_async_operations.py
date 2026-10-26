import uuid

import core.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F
from django.utils import timezone


def backfill_authoritative_operation_state(apps, schema_editor):
    operation_model = apps.get_model('core', 'AsyncOperation')
    idempotency_model = apps.get_model('core', 'IdempotencyRecord')
    now = timezone.now()

    # Legacy running rows pre-date leases. Give them an already-expired lease
    # so the recovery worker can make the retry/fail decision after deploy.
    running = operation_model.objects.filter(status='running')
    running.update(
        lease_owner='legacy-migration',
        lease_expires_at=now,
        heartbeat_at=now,
    )
    running.filter(attempt_count=0).update(attempt_count=1)

    # Terminal timestamps were optional in the old task projection. Preserve
    # their last known update time before enabling the terminal-state check.
    operation_model.objects.filter(
        status__in=['succeeded', 'failed', 'canceled'],
        completed_at__isnull=True,
    ).update(completed_at=F('updated_at'))
    operation_model.objects.filter(progress__gt=100).update(progress=100)

    # Best-effort binding of historical idempotency responses that already
    # returned an AsyncOperation UUID. Ownership is checked before linking.
    for record in idempotency_model.objects.filter(operation__isnull=True).iterator():
        body = record.response_body if isinstance(record.response_body, dict) else {}
        operation_id = body.get('operation_id')
        if not operation_id:
            continue
        try:
            operation_uuid = uuid.UUID(str(operation_id))
        except (TypeError, ValueError, AttributeError):
            continue
        operation = operation_model.objects.filter(
            pk=operation_uuid,
            user_id=record.user_id,
        ).first()
        if operation:
            record.operation_id = operation.pk
            record.save(update_fields=['operation'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_runtimepolicy_consumerinbox_integrationoutbox'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='asyncoperation',
            name='uniq_async_operation_source',
        ),
        migrations.RenameField(
            model_name='idempotencyrecord',
            old_name='operation_id',
            new_name='legacy_operation_id',
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='attempt_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='cancel_requested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='celery_task_id',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='correlation_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='fencing_token',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='heartbeat_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='idempotency_key_hash',
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='input_hash',
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='input_id',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='input_type',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='input_version',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='last_event_sequence',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='lease_expires_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='lease_owner',
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='max_attempts',
            field=models.PositiveSmallIntegerField(default=5),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='next_attempt_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='result_id',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='result_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='result_type',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='trace_id',
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name='asyncoperation',
            name='version',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='asyncoperation',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', '排队中'),
                    ('claimed', '已领取'),
                    ('running', '处理中'),
                    ('retrying', '等待重试'),
                    ('review_required', '待确认'),
                    ('cancel_requested', '取消中'),
                    ('succeeded', '已完成'),
                    ('failed', '失败'),
                    ('canceled', '已取消'),
                ],
                db_index=True,
                default='pending',
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name='idempotencyrecord',
            name='operation',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='idempotency_claims',
                to='core.asyncoperation',
            ),
        ),
        migrations.AddField(
            model_name='consumerinbox',
            name='claim_token',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='consumerinbox',
            name='fencing_token',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='consumerinbox',
            name='lease_expires_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='consumerinbox',
            name='lease_owner',
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name='consumerinbox',
            name='next_attempt_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.CreateModel(
            name='OperationDispatchOutbox',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('task_name', models.CharField(default='core.tasks.execute_operation', editable=False, max_length=200)),
                ('queue', models.CharField(default=core.models.default_operation_queue, max_length=80)),
                ('routing_key', models.CharField(blank=True, max_length=120)),
                ('payload', models.JSONField(blank=True, default=dict, editable=False)),
                ('status', models.CharField(choices=[('pending', '待投递'), ('publishing', '投递中'), ('published', '已投递'), ('failed', '待重试'), ('dead', '已进入死信'), ('canceled', '已取消')], db_index=True, default='pending', max_length=16)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('max_attempts', models.PositiveSmallIntegerField(default=12)),
                ('available_at', models.DateTimeField(db_index=True)),
                ('locked_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('celery_task_id', models.CharField(blank=True, max_length=80)),
                ('last_error', models.TextField(blank=True)),
                ('fencing_token', models.PositiveBigIntegerField(default=0)),
                ('version', models.PositiveBigIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('operation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dispatches', to='core.asyncoperation')),
            ],
            options={
                'ordering': ['created_at'],
                'indexes': [models.Index(fields=['status', 'available_at', 'created_at'], name='core_opdisp_ready_idx')],
                'constraints': [models.UniqueConstraint(fields=('operation', 'fencing_token'), name='uniq_operation_dispatch_fence')],
            },
        ),
        migrations.CreateModel(
            name='OperationEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('sequence', models.PositiveBigIntegerField()),
                ('event_type', models.CharField(db_index=True, max_length=120)),
                ('status', models.CharField(blank=True, max_length=24)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('operation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='core.asyncoperation')),
            ],
            options={
                'ordering': ['sequence'],
                'indexes': [models.Index(fields=['operation', 'created_at'], name='core_opevent_time_idx')],
                'constraints': [models.UniqueConstraint(fields=('operation', 'sequence'), name='uniq_operation_event_sequence')],
            },
        ),
        migrations.RunPython(backfill_authoritative_operation_state, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='asyncoperation',
            constraint=models.UniqueConstraint(
                condition=~models.Q(idempotency_key_hash=''),
                fields=('user', 'operation_type', 'idempotency_key_hash'),
                name='uniq_operation_business_idempotency',
            ),
        ),
        migrations.AddConstraint(
            model_name='asyncoperation',
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(status__in=['claimed', 'running'])
                    | (~models.Q(lease_owner='') & models.Q(lease_expires_at__isnull=False))
                ),
                name='operation_active_requires_lease',
            ),
        ),
        migrations.AddConstraint(
            model_name='asyncoperation',
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(status__in=['succeeded', 'failed', 'canceled'])
                    | models.Q(completed_at__isnull=False)
                ),
                name='operation_terminal_has_completed_at',
            ),
        ),
        migrations.AddConstraint(
            model_name='asyncoperation',
            constraint=models.CheckConstraint(
                condition=models.Q(attempt_count__lte=models.F('max_attempts')),
                name='operation_attempt_within_limit',
            ),
        ),
        migrations.AddConstraint(
            model_name='asyncoperation',
            constraint=models.CheckConstraint(
                condition=models.Q(progress__lte=100),
                name='operation_progress_valid',
            ),
        ),
    ]
