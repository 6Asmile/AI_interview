"""Synthetic, standalone Celery app; never registered in the business app."""
import os
import time
from celery import Celery
from kombu import Exchange, Queue

BROKER = os.environ.get('IFACEOFF_ISOLATION_BROKER_URL', 'memory://')
PREFIX = os.environ.get('IFACEOFF_ISOLATION_PREFIX', 'ifaceoff.verify.unconfigured')
exchange = Exchange(PREFIX, type='direct', durable=False, auto_delete=True)
ROLES = ('resume-render', 'agent', 'media', 'publisher')
probe_app = Celery('ifaceoff-isolation-probe', broker=BROKER)
probe_app.conf.update(
    task_default_queue=f'{PREFIX}.publisher',
    task_default_exchange=PREFIX,
    task_default_exchange_type='direct',
    task_default_routing_key='publisher',
    control_exchange=f'{PREFIX}.control',
    task_queues=tuple(Queue(f'{PREFIX}.{role}', exchange=exchange, routing_key=role,
                          durable=False, auto_delete=True) for role in ROLES),
    task_create_missing_queues=False, task_ignore_result=True,
    worker_prefetch_multiplier=1, task_acks_late=True,
    broker_transport_options={'confirm_publish': True},
)


@probe_app.task(name='isolation.synthetic_work')
def synthetic_work(seconds, role):
    time.sleep(seconds)
    with probe_app.connection_for_write() as connection:
        with connection.SimpleQueue(f'{PREFIX}.replies', queue_opts={'durable': False, 'auto_delete': True}) as replies:
            replies.put({'role': role, 'finished_at': time.time()}, delivery_mode=1)
