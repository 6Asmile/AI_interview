"""Exercise real RabbitMQ with synthetic work and temporary isolated queues."""
import os
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import nullcontext
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = '使用合成任务验证简历长任务不阻塞面试、媒体和发布；不调用业务模型或 AI。'

    def handle(self, **options):
        from django.conf import settings
        from core.worker_roles import worker_arguments

        prefix = f'ifaceoff.verify.{uuid.uuid4().hex}'
        environment = dict(os.environ, IFACEOFF_ISOLATION_PREFIX=prefix,
                           IFACEOFF_ISOLATION_BROKER_URL=settings.CELERY_BROKER_URL)
        # This command owns a separate app, not the application's task registry.
        os.environ['IFACEOFF_ISOLATION_PREFIX'] = prefix
        os.environ['IFACEOFF_ISOLATION_BROKER_URL'] = settings.CELERY_BROKER_URL
        from core.isolation_probe import probe_app, synthetic_work, ROLES

        processes, logs = [], []
        temporary = tempfile.TemporaryDirectory(prefix='ifaceoff-worker-probe-')
        try:
            with nullcontext(temporary.name) as directory:
                for role in ROLES:
                    log = open(Path(directory) / f'{role}.log', 'wb')
                    logs.append(log)
                    arguments = worker_arguments(role, pool='solo', hostname=f'{prefix}.{role}@%h')
                    arguments[arguments.index('--queues') + 1] = f'{prefix}.{role}'
                    processes.append(subprocess.Popen(
                        [sys.executable, '-m', 'celery', '-A', 'core.isolation_probe:probe_app', *arguments],
                        env=environment, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    ))
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    replies = probe_app.control.inspect(timeout=1).ping() or {}
                    owned_workers = [name for name in replies if name.startswith(prefix + '.')]
                    if len(owned_workers) >= len(ROLES):
                        break
                    if any(process.poll() is not None for process in processes):
                        raise CommandError('合成 Worker 启动失败')
                else:
                    raise CommandError('合成 Worker 启动超时')
                with probe_app.connection_for_read() as connection:
                    with connection.SimpleQueue(f'{prefix}.replies', queue_opts={'durable': False, 'auto_delete': True}) as replies:
                        started = time.monotonic()
                        for role in ROLES:
                            synthetic_work.apply_async(args=(8 if role == 'resume-render' else 0, role),
                                queue=f'{prefix}.{role}', routing_key=role, mandatory=True)
                        received = {}
                        for _ in ROLES:
                            message = replies.get(timeout=15)
                            received[message.payload['role']] = time.monotonic() - started
                            message.ack()
                        if any(received[role] >= 5 for role in ROLES if role != 'resume-render'):
                            raise CommandError('短任务被阻塞，未达到隔离验收阈值')
                        for role, elapsed in sorted(received.items()):
                            self.stdout.write(f'{role}: {elapsed:.3f} 秒')
                        self.stdout.write(self.style.SUCCESS('真实 RabbitMQ 合成隔离验证通过（不等同于业务全链路或生产压测）'))
                probe_app.control.broadcast('shutdown', destination=owned_workers)
                for process in processes:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=5)
                for log in logs:
                    log.close()
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
            for log in logs:
                if not log.closed:
                    log.close()
            # Remove only this run's known ephemeral queues; no namespace scans
            # or application queues are touched.
            with probe_app.connection_for_write() as connection:
                channel = connection.channel()
                for name in [*(f'{prefix}.{role}' for role in ROLES), f'{prefix}.replies']:
                    channel.queue_delete(queue=name)
                channel.exchange_delete(exchange=prefix)
            temporary.cleanup()
