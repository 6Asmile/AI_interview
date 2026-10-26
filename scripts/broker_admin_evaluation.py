"""Real admin API + owned PostgreSQL/RabbitMQ. No production resource access."""
import json
import sys
import tempfile
import time
from pathlib import Path

from real_infrastructure_evaluation import Infrastructure, wait_for
from operation_fault_evaluation import setup, write_report


def evaluate(broker, prefix, rows):
    from django.conf import settings
    from django.test.utils import override_settings
    from kombu import Connection, Exchange, Producer, Queue
    from rest_framework.test import APIClient
    from staff_admin.models import AdminAuditEvent, StaffAccount, StaffRole

    exchange = Exchange(prefix + '.commands', type='direct', durable=True)
    dlx = Exchange(prefix + '.dlx', type='direct', durable=True)
    source = Queue(prefix + '.source', exchange, routing_key='resume.render', durable=True,
        queue_arguments={'x-queue-type': 'quorum', 'x-max-length': 1, 'x-overflow': 'reject-publish',
                         'x-dead-letter-exchange': dlx.name, 'x-dead-letter-routing-key': 'dead'})
    dead = Queue(source.name + '.dlq', dlx, routing_key='dead', durable=True)
    role = StaffRole.objects.create(slug=prefix, name='合成死信管理员', permissions=['platform_events.view', 'platform_events.replay'])
    staff = StaffAccount.objects.create_account(email=prefix + '@example.test', password='synthetic-only', display_name='合成账户', status='active')
    staff.roles.add(role)
    client = APIClient()
    client.force_authenticate(staff)
    url = '/api/admin/v1/operations/broker-dlq/'
    body = {'queue': dead.name, 'limit': 2, 'dry_run': True, 'operation_reason': '专属组件合成验收'}
    def post(key, **extra):
        return client.post(url, {**body, **extra}, format='json', HTTP_IDEMPOTENCY_KEY=key)
    with override_settings(ALLOWED_HOSTS=['testserver'], CELERY_BROKER_URL=broker, CELERY_TASK_QUEUES=(source, dead), CELERY_DLQ_NAMES=(dead.name,)), \
         Connection(broker, connect_timeout=3, transport_options={'confirm_publish': True}) as connection:
        channel = connection.channel()
        source(channel).declare()
        dead(channel).declare()
        def depth(queue):
            return channel.queue_declare(queue=queue.name, passive=True).message_count
        def count(expected):
            assert depth(dead) == expected
            return True
        def poison(task):
            Producer(channel).publish([['synthetic-op'], {}, None], exchange=exchange, routing_key=source.routing_key,
                serializer='json', headers={'task': task, 'id': prefix, 'argsrepr': 'PRIVATE-SYNTHETIC'},
                delivery_mode=2, mandatory=True, confirm_timeout=3)
            holder = []
            def obtain():
                row = source(channel).get(no_ack=False)
                assert row
                holder.append(row)
                return True
            wait_for(obtain, timeout=5)
            holder[0].reject(requeue=False)
        poison('core.tasks.execute_operation')
        poison('legacy.unsafe_task')
        wait_for(lambda: count(2), timeout=5)
        from staff_admin.broker_dlq import inspect_queue
        assert inspect_queue(dead.name)['ready'] == 2
        result = client.get(url, {'queue': dead.name})
        assert result.status_code == 200 and result.data['ready'] == 2, result.data
        from staff_admin.broker_dlq import replay_batch
        replay_batch(dead.name, limit=2, dry_run=True, record_confirm=lambda summary: None)
        wait_for(lambda: count(2), timeout=5)
        result = post('preview')
        assert result.status_code == 200 and result.data['retained'] == 2, result.data
        assert sorted(row['status'] for row in result.data['messages']) == ['eligible', 'retained']
        assert 'PRIVATE-SYNTHETIC' not in str(result.data)
        wait_for(lambda: count(2), timeout=5)
        rows.append({'name': '管理API真实读取与试运行，未知任务保留且不泄漏正文', 'status': 'passed', 'dead_count': 2})

        # Unbind while keeping the original exchange/queue: mandatory return,
        # not a missing queue error, must prevent original ACK.
        channel.queue_unbind(queue=source.name, exchange=exchange.name, routing_key=source.routing_key)
        result = post('unroutable', dry_run=False)
        assert result.status_code == 200 and result.data['replayed'] == 0 and not result.data['complete'], result.data
        wait_for(lambda: count(2), timeout=5)
        rows.append({'name': '管理API Mandatory（强制路由）不可达保留原死信', 'status': 'passed'})
        channel.queue_bind(queue=source.name, exchange=exchange.name, routing_key=source.routing_key)

        from amqp.exceptions import MessageNacked
        full = False
        for index in range(10):
            try:
                Producer(channel).publish({'occupied': index}, exchange=exchange, routing_key=source.routing_key,
                                         serializer='json', delivery_mode=2, mandatory=True, confirm_timeout=3)
            except MessageNacked:
                full = True
                break
            time.sleep(.1)
        assert full
        result = post('nack', dry_run=False)
        assert result.status_code == 200 and result.data['replayed'] == 0 and not result.data['complete'], result.data
        wait_for(lambda: count(2), timeout=5)
        rows.append({'name': '管理API真实发布NACK（拒绝）不确认原死信', 'status': 'passed'})
        while depth(source):
            message = source(channel).get(no_ack=False)
            if message:
                message.ack()
            time.sleep(.05)
        result = post('confirmed', dry_run=False)
        assert result.status_code == 200 and result.data['replayed'] == 1 and result.data['retained'] == 1, result.data
        wait_for(lambda: count(1), timeout=5)
        receipts = AdminAuditEvent.objects.filter(action='broker_dlq.publish_confirmed').count()
        assert receipts == 1, receipts
        same = post('confirmed', dry_run=False)
        assert same.status_code == 200 and same['X-Idempotent-Replay'] == 'true'
        assert same.data == result.data and depth(source) == 1
        assert AdminAuditEvent.objects.filter(action='broker_dlq.publish_confirmed').count() == receipts
        received = source(channel).get(no_ack=False)
        assert received.payload == [['synthetic-op'], {}, None]
        assert received.headers['id'] == prefix and 'x-death' not in received.headers
        received.ack()
        rows.append({'name': '管理API确认发布、审计与原死信ACK；同幂等键只执行一次', 'status': 'passed', 'replayed': 1, 'unknown_retained': 1})
        role.permissions = ['platform_events.view']
        role.save()
        assert post('forbidden', dry_run=False).status_code == 403
        assert depth(dead) == 1
        rows.append({'name': '真实组件管理API只读角色禁止重放', 'status': 'passed'})


def run():
    infra = Infrastructure()
    report = {'status': 'partial', 'scope': 'owned_broker_admin_api', 'cases': [],
        'limitations': ['单节点RabbitMQ 3.13，不证明4.3多节点HA。', 'APIClient身份注入；未覆盖真实浏览器Cookie/CSRF/页面链路。',
                        '合成Celery消息，无业务Worker；不替代Operation崩溃恢复实验。']}
    try:
        with tempfile.TemporaryDirectory(prefix='ifaceoff-dlq-admin-') as workspace:
            infra.start('pg', 'postgres:16-alpine', 5432, ('-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_DB=evaluation'))
            infra.start('mq', 'rabbitmq:3.13-management-alpine', 5672, ('-e', 'RABBITMQ_DEFAULT_USER=evaluation', '-e', 'RABBITMQ_DEFAULT_PASS=evaluation'))
            broker = f'amqp://evaluation:evaluation@127.0.0.1:{infra.ports["mq"]}//'
            from kombu import Connection
            def ready():
                with Connection(broker, connect_timeout=2) as connection:
                    connection.connect()
                return True
            wait_for(ready)
            setup({'pg_port': infra.ports['pg'], 'media': workspace, 'broker': broker,
                   'queue': infra.prefix + '.bootstrap', 'exchange': infra.prefix + '.bootstrap'})
            from django.core.management import call_command
            from django.db import connections
            wait_for(lambda: connections['default'].ensure_connection() or True)
            call_command('migrate', interactive=False, verbosity=0)
            evaluate(broker, infra.prefix, report['cases'])
            connections.close_all()
    except Exception as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error)[:180])
    finally:
        infra.close()
    return write_report(report)


if __name__ == '__main__':
    raise SystemExit(run())
