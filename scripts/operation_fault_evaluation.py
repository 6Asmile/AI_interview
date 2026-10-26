"""Owned PostgreSQL/RabbitMQ, real publisher/executor/export; injected worker exits."""
import argparse
from contextlib import ExitStack
from datetime import timedelta
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from real_infrastructure_evaluation import Infrastructure, wait_for

ROOT = Path(__file__).resolve().parents[1]


def evaluate_broker_dlq(broker, prefix, rows):
    """Protocol-only replay lab, NOT the currently unsupported admin replay API."""
    from kombu import Connection, Exchange, Queue, Producer
    exchange = Exchange(prefix + '.dlq.commands', type='direct', durable=True)
    dead_exchange = Exchange(prefix + '.dlx', type='direct', durable=True)
    source = Queue(prefix + '.poison', exchange, routing_key='probe', durable=True, queue_arguments={
        'x-queue-type': 'quorum', 'x-delivery-limit': 2, 'x-max-length': 1, 'x-overflow': 'reject-publish',
        'x-dead-letter-exchange': dead_exchange.name, 'x-dead-letter-routing-key': 'dead',
        'x-dead-letter-strategy': 'at-least-once'})
    dead = Queue(prefix + '.dead', dead_exchange, routing_key='dead', durable=True)
    def connect():
        return Connection(broker, connect_timeout=2, transport_options={'confirm_publish': True})
    with connect() as connection:
        channel = connection.channel()
        dead(channel).declare()
        source(channel).declare()
        def dead_count(expected):
            actual = channel.queue_declare(queue=dead.name, passive=True).message_count
            if actual != expected:
                raise RuntimeError(f'waiting_dead_count_{expected}_observed_{actual}')
            return True
        def publish(payload):
            Producer(channel).publish(payload, exchange=exchange, routing_key='probe', serializer='json',
                delivery_mode=2, mandatory=True, confirm_timeout=3)
        publish({'probe_id': prefix})
        rejected = 0
        for _ in range(10):
            message = source(channel).get(no_ack=False)
            if message:
                rejected += 1
                message.reject(requeue=True)
            time.sleep(.1)
            if channel.queue_declare(queue=dead.name, passive=True).message_count:
                break
        wait_for(lambda: dead_count(1), timeout=10)
        message = dead(channel).get(no_ack=False)
        death = message.headers['x-death'][0]
        assert death['queue'] == source.name and death['reason'] == 'delivery_limit'
        assert message.payload == {'probe_id': prefix}
        message.reject(requeue=True)  # dry-run must not delete the dead message.
        rows.append({'name': '真实Quorum（仲裁队列）投递耗尽进入DLQ（死信队列）与只读预演',
            'status': 'passed', 'rejected_deliveries': rejected, 'dead_message_count': 1, 'scope': 'Broker协议，不是管理端API'})
        # Quorum overflow is approximate; wait until the broker truly NACKs,
        # rather than assuming an exact one-message capacity boundary.
        from amqp.exceptions import MessageNacked
        full = False
        for index in range(10):
            try:
                publish({'probe_id': 'occupied-' + str(index)})
            except MessageNacked:
                full = True
                break
            time.sleep(.1)
        assert full, 'broker_overflow_not_observed'
        message = dead(channel).get(no_ack=False)
        failed = False
        try:
            publish(message.payload)  # Actual reject-publish/confirm NACK from the full queue.
        except Exception as error:
            from amqp.exceptions import MessageNacked
            if not isinstance(error, MessageNacked):
                raise
            failed = True
        assert failed, 'broker_did_not_nack_replay'
        message.reject(requeue=True)  # Never ACK the dead letter when republish fails.
        wait_for(lambda: dead_count(1), timeout=10)
        rows.append({'name': '真实重放NACK（发布拒绝）后保留原死信', 'status': 'passed', 'dead_message_count': 1})
        for _ in range(10):
            occupied = source(channel).get(no_ack=False)
            if not occupied:
                break
            assert occupied.payload['probe_id'].startswith('occupied-')
            occupied.ack()
        time.sleep(.2)
        message = dead(channel).get(no_ack=False)
        assert message.headers['x-death'][0]['queue'] == source.name
        publish(message.payload)
        message.ack()  # Original ACK occurs only after publisher confirmation succeeds.
        result = source(channel).get(no_ack=False)
        assert result.payload == {'probe_id': prefix}, 'replay_payload_mismatch'
        result.ack()
        wait_for(lambda: dead_count(0), timeout=10)
        rows.append({'name': '真实受控重放确认成功后才确认原死信', 'status': 'passed',
            'replayed_count': 1, 'dead_message_count': 0, 'scope': '单条合成消息，未覆盖管理权限与审计'})


def run_dlq_only():
    infra = Infrastructure()
    report = {'status': 'partial', 'scope': 'owned_broker_dlq_protocol', 'cases': [],
        'limitations': ['单节点3.13 Broker协议实验，不是管理端权限/幂等/审计/人工重放API验收。']}
    try:
        infra.start('mq', 'rabbitmq:3.13-management-alpine', 5672, ('-e', 'RABBITMQ_DEFAULT_USER=evaluation', '-e', 'RABBITMQ_DEFAULT_PASS=evaluation'))
        broker = f'amqp://evaluation:evaluation@127.0.0.1:{infra.ports["mq"]}//'
        from kombu import Connection
        def ready():
            with Connection(broker, connect_timeout=2) as connection:
                connection.connect()
                return True
        wait_for(ready)
        evaluate_broker_dlq(broker, infra.prefix, report['cases'])
    except Exception as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error)[:180])
    finally:
        infra.close()
    return write_report(report)


def setup(config):
    sys.path.insert(0, str(ROOT / 'ai_interview_backend'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'ai_interview_backend.test_settings'
    from django.conf import settings
    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'evaluation',
        'USER': 'postgres', 'HOST': '127.0.0.1', 'PORT': config['pg_port']}}
    settings.MEDIA_ROOT = config['media']
    settings.CELERY_BROKER_URL = config['broker']
    settings.CELERY_RESULT_BACKEND = 'cache+memory://'
    settings.CELERY_BROKER_CONNECTION_TIMEOUT = 2
    settings.OPERATION_LEASE_SECONDS = 15
    settings.CELERY_RESUME_RENDER_QUEUE = config['queue']
    settings.CACHES = {alias: {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': alias}
                       for alias in ('default', 'coordination', 'realtime')}
    import django
    django.setup()
    from ai_interview_backend.celery_app import app
    from kombu import Exchange, Queue
    exchange = Exchange(config['exchange'], type='direct', durable=True)
    settings.CELERY_TASK_QUEUES = (Queue(config['queue'], exchange, routing_key='resume.render', durable=True),)
    settings.CELERY_TASK_ROUTES = {}
    settings.CELERY_TASK_DEFAULT_QUEUE = config['queue']
    settings.CELERY_TASK_DEFAULT_EXCHANGE = config['exchange']
    settings.CELERY_TASK_DEFAULT_ROUTING_KEY = 'resume.render'
    settings.CELERY_BROKER_TRANSPORT_OPTIONS = {'confirm_publish': True}
    app.conf.update(broker_url=config['broker'], broker_connection_timeout=2, broker_heartbeat=0,
        task_default_queue=config['queue'], task_default_exchange=config['exchange'],
        task_default_exchange_type='direct', task_default_routing_key='resume.render',
        task_queues=(Queue(config['queue'], exchange, routing_key='resume.render', durable=True),),
        task_routes={}, task_create_missing_queues=False, worker_prefetch_multiplier=1,
        task_acks_late=True, task_reject_on_worker_lost=True, task_ignore_result=True,
        broker_transport_options={'confirm_publish': True}, broker_native_delayed_delivery_queue_type='classic')
    # Django task imports may have populated Kombu's cached production queue map.
    app.amqp.queues = app.amqp.Queues(app.conf.task_queues, create_missing=False)
    # Suppress only noncritical wakeups. Each test explicitly invokes the real publisher.
    import core.operations as operations
    operations._kick_dispatch_publisher_on_commit = lambda: None
    return app


def child(mode, config, target):
    app = setup(config)
    if mode == 'migrate':
        from django.core.management import call_command
        call_command('migrate', interactive=False, verbosity=0)
    elif mode in ('publish', 'publish_crash'):
        from core.tasks import publish_operation_dispatch_outbox
        if mode == 'publish_crash':
            from core.tasks import execute_operation
            original_publish = execute_operation.apply_async
            def confirmed_then_exit(*args, **kwargs):
                original_publish(*args, **kwargs)
                os._exit(24)  # Real broker confirm returned; dispatch still publishing.
            execute_operation.apply_async = confirmed_then_exit
        Path(target).write_text(json.dumps(publish_operation_dispatch_outbox.run()), encoding='utf-8')
    elif mode == 'duplicate':
        from core.tasks import execute_operation
        execute_operation.apply_async(args=[config['duplicate_operation_id']], queue=config['queue'], routing_key='resume.render')
    else:
        from celery.signals import task_postrun
        @task_postrun.connect(weak=False)
        def completed_delivery(sender=None, args=None, **_kwargs):
            if sender and sender.name == 'core.tasks.execute_operation' and args:
                receipt = Path(config['media']) / (str(args[0]) + '-consumed')
                count = int(receipt.read_text()) if receipt.exists() else 0
                receipt.write_text(str(count + 1), encoding='ascii')
        from core.operation_registry import get_operation_handler, register_operation_handler, unregister_operation_handler
        import core.operations as operations
        original = get_operation_handler('resume.export')
        def once(operation_id, phase):
            marker = Path(config['media']) / (str(operation_id) + '-' + phase)
            if marker.exists():
                return False
            marker.touch()
            return True
        def handler(context):
            mode = context.get_operation().metadata.get('evaluation_fault', '')
            if mode == 'before_result' and once(context.operation_id, mode):
                os._exit(23)
            if mode == 'cancel_hold':
                while True:
                    context.raise_if_canceled()
                    time.sleep(.1)
            if mode == 'retry_exhaust':
                raise operations.RetryableOperationError('evaluation_transient', retry_after_seconds=.1)
            result = original(context)
            if mode == 'after_artifact' and once(context.operation_id, mode):
                os._exit(23)
            return result
        unregister_operation_handler('resume.export')
        register_operation_handler('resume.export', handler)
        original_complete = operations.complete_operation
        def complete(claim, **kwargs):
            result = original_complete(claim, **kwargs)
            if result.metadata.get('evaluation_fault') == 'after_commit' and once(result.pk, 'after_commit'):
                os._exit(23)  # PostgreSQL succeeded, Celery has not ACKed this delivery.
            return result
        operations.complete_operation = complete
        app.worker_main(['worker', '-l', 'warning', '--pool', 'solo', '--concurrency', '1',
                         '--queues', config['queue'], '--without-mingle', '--without-gossip', '--without-heartbeat'])


def run():
    infra = Infrastructure()
    rows = []
    processes = []
    handles = []
    def stop_processes():
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for handle in handles:
            if not handle.closed:
                handle.close()
    report = {'status': 'failed', 'scope': 'real_owned_services_resume_json_operation_faults', 'cases': rows,
              'limitations': ['单节点 RabbitMQ 3.13、JSON 导出，不证明4.3集群、所有领域或外部模型正确性。',
                              '实际运行生产 Publisher/execute_operation；Publisher由测试显式调用，未测Beat可用性。',
                              '取消耗时测DB状态和合作式处理器停止，不证明FFmpeg/OCR外部进程取消。']}
    try:
        with ExitStack() as stack:
            directory = stack.enter_context(tempfile.TemporaryDirectory(prefix='ifaceoff-operation-faults-'))
            stack.callback(stop_processes)
            workspace = Path(directory)
            media = workspace / 'media'
            media.mkdir()
            infra.start('pg', 'postgres:16-alpine', 5432, ('-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_DB=evaluation'))
            infra.start('mq', 'rabbitmq:3.13-management-alpine', 5672, ('-e', 'RABBITMQ_DEFAULT_USER=evaluation', '-e', 'RABBITMQ_DEFAULT_PASS=evaluation'))
            import psycopg
            def pg_ready():
                with psycopg.connect(host='127.0.0.1', port=infra.ports['pg'], user='postgres', dbname='evaluation', connect_timeout=2):
                    return True
            wait_for(pg_ready)
            config = {'pg_port': infra.ports['pg'], 'broker': f'amqp://evaluation:evaluation@127.0.0.1:{infra.ports["mq"]}//',
                      'media': str(media), 'queue': infra.prefix + '.worker', 'exchange': infra.prefix}
            from kombu import Connection, Exchange, Queue
            def mq_ready():
                with Connection(config['broker'], connect_timeout=2) as connection:
                    connection.connect()
                    Queue(config['queue'], Exchange(config['exchange'], type='direct', durable=True), routing_key='resume.render')(connection.channel()).declare()
                    return True
            wait_for(mq_ready)
            config_path = workspace / 'config.json'
            config_path.write_text(json.dumps(config), encoding='utf-8')
            def invoke(mode):
                target = workspace / 'result.json'
                result = subprocess.run([sys.executable, __file__, '--child', mode, '--config', str(config_path), '--result', str(target)],
                    capture_output=True, timeout=60, env={**os.environ, 'PYTHONUTF8': '1'})
                if mode == 'publish_crash' and result.returncode == 24:
                    return True
                if result.returncode:
                    raise RuntimeError('isolated_' + mode + '_failed')
                return json.loads(target.read_text()) if mode == 'publish' else None
            invoke('migrate')
            app = setup(config)
            from django.utils import timezone
            from users.models import User
            from resumes.models import Resume, ResumeArtifact, ResumeAsset
            from resumes.versioning import create_resume_version
            from resumes.studio import ensure_studio
            from resumes.operation_service import create_resume_operation
            from core.models import AsyncOperation, OperationDispatchOutbox
            from core.operations import recover_stale_operations, request_operation_cancel, OperationClaim, complete_operation, OperationLeaseLost
            user = User.objects.create_user(username='evaluation-operation', email='operation@example.invalid')
            def make(fault=''):
                resume = Resume.objects.create(user=user, title='合成异步故障验收')
                version = create_resume_version(resume=resume, user=user, resume_json={'basics': {'name': '合成候选人'}}, change_summary='合成')
                _, design = ensure_studio(resume, user)
                import uuid
                artifact = ResumeArtifact.objects.create(resume=resume, content_version=version, design_revision=design,
                    format='json', cache_key=uuid.uuid4().hex, renderer_version='2.8')
                operation, _ = create_resume_operation(user=user, resume=resume, operation_type='resume.export', title='合成导出', artifact=artifact)
                AsyncOperation.objects.filter(pk=operation.pk).update(metadata={**operation.metadata, 'evaluation_fault': fault})
                return operation, artifact
            def state(operation):
                operation.refresh_from_db()
                return operation
            def until(operation, status, timeout=30):
                return wait_for(lambda: state(operation) if state(operation).status == status else (_ for _ in ()).throw(RuntimeError('waiting')), timeout)
            def spawn():
                log = (workspace / f'worker-{len(processes)}.log').open('wb')
                handles.append(log)
                process = subprocess.Popen([sys.executable, __file__, '--child', 'worker', '--config', str(config_path)],
                    stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), env={**os.environ, 'PYTHONUTF8': '1'})
                processes.append(process)
                def ready():
                    if process.poll() is not None:
                        log.flush()
                        tail = Path(log.name).read_text(encoding='utf-8', errors='replace').splitlines()[-12:]
                        raise RuntimeError('isolated_worker_exited: ' + ' | '.join(line for line in tail if '://' not in line)[-140:])
                    with Connection(config['broker'], connect_timeout=2) as connection:
                        count = connection.channel().queue_declare(queue=config['queue'], passive=True).consumer_count
                        if not count:
                            raise RuntimeError('waiting_consumer')
                    return process
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        return ready()  # Preserve the concrete worker startup error.
                    try:
                        return ready()
                    except Exception:
                        time.sleep(.2)
                raise TimeoutError('isolated_worker_consumer_not_ready')
            def unique_result(operation, artifact):
                artifact.refresh_from_db()
                assert artifact.status == 'ready' and ResumeAsset.objects.filter(resume=artifact.resume).count() == 1
                assert state(operation).result_id == str(artifact.pk)
                assert operation.events.filter(event_type='operation.succeeded').count() == 1
            def drained():
                with Connection(config['broker'], connect_timeout=2) as connection:
                    info = connection.channel().queue_declare(queue=config['queue'], passive=True)
                    if info.message_count:
                        raise RuntimeError('waiting_queue_drain')
                return True
            def consumed(operation, minimum=1):
                receipt = media / (str(operation.pk) + '-consumed')
                if not receipt.exists() or int(receipt.read_text()) < minimum:
                    raise RuntimeError('waiting_consumer_completion')
                return True
            # The broker is absent during durable command creation and first publish.
            infra.docker('stop', '-t', '1', infra.prefix + '-mq')
            operation, artifact = make()
            assert invoke('publish')['failed'] == 1 and state(operation).status == 'pending'
            started = time.perf_counter()
            infra.docker('start', infra.prefix + '-mq')
            infra.ports['mq'] = int(infra.docker('port', infra.prefix + '-mq', '5672/tcp').split(':')[-1])
            config['broker'] = f'amqp://evaluation:evaluation@127.0.0.1:{infra.ports["mq"]}//'
            from django.conf import settings
            settings.CELERY_BROKER_URL = config['broker']
            config_path.write_text(json.dumps(config), encoding='utf-8')
            wait_for(mq_ready)
            # Fast-forward only the publisher's persisted retry schedule, not an execution lease.
            OperationDispatchOutbox.objects.filter(operation=operation).update(available_at=timezone.now())
            worker = spawn()
            invoke('publish')
            until(operation, 'succeeded')
            wait_for(lambda: consumed(operation))
            unique_result(operation, artifact)
            rows.append({'name': 'Broker停机后保留命令并恢复真实JSON结果', 'status': 'passed', 'recovery_ms': round((time.perf_counter()-started)*1000, 3), 'retry_clock_accelerated': True})
            # Duplicate Celery delivery uses the same public Operation UUID.
            config['duplicate_operation_id'] = str(operation.pk)
            config_path.write_text(json.dumps(config), encoding='utf-8')
            invoke('duplicate')
            wait_for(lambda: consumed(operation, minimum=2))
            wait_for(drained, timeout=10)
            time.sleep(.2)
            unique_result(operation, artifact)
            rows.append({'name': '重复投递业务结果和成功事件不重复', 'status': 'passed', 'business_result_count': 1})
            # No consumer until both confirmed copies exist: test the precise publisher gap.
            worker.terminate()
            worker.wait(timeout=5)
            operation, artifact = make()
            assert invoke('publish_crash') is True
            dispatch = OperationDispatchOutbox.objects.get(operation=operation)
            assert dispatch.status == 'publishing' and state(operation).status == 'pending'
            with Connection(config['broker'], connect_timeout=2) as connection:
                assert connection.channel().queue_declare(queue=config['queue'], passive=True).message_count == 1
            started = time.perf_counter()
            OperationDispatchOutbox.objects.filter(pk=dispatch.pk).update(locked_at=timezone.now() - timedelta(minutes=6))
            assert invoke('publish')['published'] == 1
            with Connection(config['broker'], connect_timeout=2) as connection:
                assert connection.channel().queue_declare(queue=config['queue'], passive=True).message_count == 2
            worker = spawn()
            until(operation, 'succeeded')
            wait_for(lambda: consumed(operation, minimum=2))
            unique_result(operation, artifact)
            assert state(operation).attempt_count == 1
            rows.append({'name': 'Publisher（投递器）确认后、Outbox（命令表）更新前崩溃', 'status': 'passed',
                'confirmed_message_count': 2, 'business_result_count': 1, 'business_attempt_count': 1,
                'publisher_stale_clock_accelerated': True, 'recovery_ms': round((time.perf_counter()-started)*1000, 3)})
            for fault in ('before_result', 'after_artifact', 'after_commit'):
                operation, artifact = make(fault)
                invoke('publish')
                wait_for(lambda: worker.poll() if worker.poll() is not None else (_ for _ in ()).throw(RuntimeError('waiting_exit')))
                assert worker.returncode == 23
                old = state(operation)
                claim = OperationClaim(old.pk, old.lease_owner, old.fencing_token, old.lease_expires_at)
                started = time.perf_counter()
                if fault != 'after_commit':
                    while old.lease_expires_at > timezone.now():
                        time.sleep(.2)
                    recover_stale_operations()
                    invoke('publish')
                worker = spawn()
                until(operation, 'succeeded')
                wait_for(lambda: consumed(operation))
                wait_for(drained, timeout=10)
                time.sleep(.2)
                unique_result(operation, artifact)
                rejected = None
                if fault != 'after_commit':
                    try:
                        complete_operation(claim, result_type='invalid')
                    except OperationLeaseLost:
                        rejected = True
                    assert rejected and operation.fencing_token > claim.fencing_token
                labels = {'before_result': '结果生成前', 'after_artifact': '产物落库后', 'after_commit': '操作成功提交后、消费确认前'}
                rows.append({'name': 'Worker（任务进程）真实崩溃-' + labels[fault], 'status': 'passed', 'recovery_ms': round((time.perf_counter()-started)*1000, 3),
                             'business_result_count': 1, 'old_fence_rejected': rejected, 'attempt_count': operation.attempt_count})
            operation, artifact = make('cancel_hold')
            invoke('publish')
            until(operation, 'running')
            started = time.perf_counter()
            request_operation_cancel(operation.pk, user=user)
            until(operation, 'canceled')
            cancel_ms = round((time.perf_counter()-started)*1000,3)
            time.sleep(.3)
            assert ResumeAsset.objects.filter(resume=artifact.resume).count() == 0
            rows.append({'name': '运行中取消拒绝旧Worker结果', 'status': 'passed', 'cancel_to_db_terminal_ms': cancel_ms, 'business_result_count': 0})
            operation, artifact = make('retry_exhaust')
            started = time.perf_counter()
            deadline = time.monotonic() + 30
            while state(operation).status != 'failed' and time.monotonic() < deadline:
                invoke('publish')
                time.sleep(.2)
            assert state(operation).status == 'failed' and operation.attempt_count == operation.max_attempts
            rows.append({'name': '业务重试耗尽终止', 'status': 'passed', 'attempt_count': operation.attempt_count,
                         'duration_ms': round((time.perf_counter()-started)*1000, 3)})
            evaluate_broker_dlq(config['broker'], infra.prefix, rows)
            report['status'] = 'partial'
    except Exception as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error)[:180])
    finally:
        stop_processes()
        infra.close()
    return write_report(report)


def write_report(report):
    target = ROOT / 'output/evaluation' / ('operation-faults-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(target))
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', choices=('migrate', 'publish', 'publish_crash', 'duplicate', 'worker'))
    parser.add_argument('--config')
    parser.add_argument('--result')
    parser.add_argument('--dlq-only', action='store_true')
    args = parser.parse_args()
    if args.child:
        child(args.child, json.loads(Path(args.config).read_text()), args.result)
    elif args.dlq_only:
        raise SystemExit(run_dlq_only())
    else:
        raise SystemExit(run())
