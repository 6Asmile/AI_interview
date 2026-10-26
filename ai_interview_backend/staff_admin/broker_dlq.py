"""Bounded, raw AMQP dead-letter replay. Never deserialize task arguments.

Closing the channel returns every unacknowledged original to its DLQ. Only
durable handlers are replayable; database operation retry is a separate action.
"""
import hashlib
import time

from django.conf import settings
from kombu import Connection, Producer, Queue


REPLAY_TASKS = frozenset({
    'core.tasks.execute_operation',
    'core.tasks.consume_integration_event',
    'interviews.tasks.run_interview_execution',
})


class DLQValidationError(ValueError):
    pass


def queue_target(queue_name):
    if queue_name not in settings.CELERY_DLQ_NAMES:
        raise DLQValidationError('invalid_dlq_queue')
    source_name = queue_name.removesuffix('.dlq')
    for queue in settings.CELERY_TASK_QUEUES:
        if queue.name == source_name:
            return queue
    raise DLQValidationError('unknown_source_queue')


def broker_connection():
    return Connection(
        settings.CELERY_BROKER_URL, connect_timeout=3,
        transport_options={'confirm_publish': True, 'read_timeout': 3, 'write_timeout': 3},
        heartbeat=10,
    )


def inspect_queue(queue_name):
    queue_target(queue_name)
    with broker_connection() as connection:
        channel = connection.channel()
        try:
            # Passive only: missing or mismatched topology must never be repaired here.
            _, count, consumers = channel.queue_declare(queue=queue_name, passive=True)
            return {'queue': queue_name, 'ready': count, 'consumers': consumers}
        finally:
            channel.close()


def message_route(message, target):
    headers = message.headers or {}
    if headers.get('task') not in REPLAY_TASKS:
        raise DLQValidationError('unsupported_durable_task')
    if message.content_type != 'application/json':
        raise DLQValidationError('unsupported_content_type')
    if headers.get('compression'):
        raise DLQValidationError('unsupported_compression')
    if len(message.body) > 2_000_000:
        raise DLQValidationError('message_too_large')
    deaths = headers.get('x-death')
    if not isinstance(deaths, (list, tuple)) or not deaths:
        raise DLQValidationError('missing_death_history')
    death = deaths[0]
    if not isinstance(death, dict) or death.get('queue') != target.name:
        raise DLQValidationError('source_queue_mismatch')
    if death.get('exchange') != target.exchange.name:
        raise DLQValidationError('source_exchange_mismatch')
    routes = death.get('routing-keys')
    if not isinstance(routes, (list, tuple)) or len(routes) != 1:
        raise DLQValidationError('ambiguous_original_route')
    route = routes[0]
    if not isinstance(route, str) or not route or len(route) > 255 or '*' in route or '#' in route:
        raise DLQValidationError('invalid_original_route')
    if target.routing_key != '#' and route != target.routing_key:
        raise DLQValidationError('original_route_mismatch')
    if target.routing_key == '#' and headers.get('task') != 'core.tasks.consume_integration_event':
        raise DLQValidationError('event_task_required')
    if target.routing_key != '#' and headers.get('task') == 'core.tasks.consume_integration_event':
        raise DLQValidationError('event_queue_required')
    return route


def replay_batch(queue_name, *, limit, dry_run, record_confirm):
    target = queue_target(queue_name)
    if type(limit) is not int or not 1 <= limit <= 100 or type(dry_run) is not bool:
        raise DLQValidationError('invalid_replay_options')
    result = {'queue': queue_name, 'dry_run': dry_run, 'examined': 0,
              'replayed': 0, 'retained': 0, 'messages': [], 'complete': True}
    deadline = time.monotonic() + 15
    with broker_connection() as connection:
        channel = connection.channel()
        try:
            channel.queue_declare(queue=queue_name, passive=True)
            channel.queue_declare(queue=target.name, passive=True)
            channel.exchange_declare(exchange=target.exchange.name, type=target.exchange.type, passive=True)
            producer = Producer(channel)
            for _ in range(limit):
                if time.monotonic() >= deadline:
                    result['complete'] = False
                    break
                message = Queue(queue_name, channel=channel).get(no_ack=False)
                if message is None:
                    break
                raw_body = message.body.encode(message.content_encoding or 'utf-8') if isinstance(message.body, str) else message.body
                digest = hashlib.sha256(raw_body).hexdigest()
                item = {'body_hash': digest, 'status': 'retained'}
                result['examined'] += 1
                result['messages'].append(item)
                try:
                    route = message_route(message, target)
                except DLQValidationError as exc:
                    item['code'] = str(exc)
                    result['retained'] += 1
                    continue
                item['routing_key'] = route
                if dry_run:
                    item['status'] = 'eligible'
                    result['retained'] += 1
                    continue
                try:
                    # Preserve Celery headers/task identity but reset broker delivery
                    # history. Bodies and private args never enter API/audit output.
                    headers = {k: v for k, v in (message.headers or {}).items()
                               if not k.startswith('x-death') and not k.startswith('x-first-death')
                               and not k.startswith('x-last-death') and k != 'x-delivery-count'}
                    properties = message.properties or {}
                    producer.publish(
                        message.body, exchange=target.exchange.name, routing_key=route,
                        headers=headers, content_type=message.content_type,
                        content_encoding=message.content_encoding, serializer=None,
                        delivery_mode=2, mandatory=True, retry=False,
                        confirm_timeout=min(3, max(.1, deadline - time.monotonic())),
                        correlation_id=properties.get('correlation_id'),
                        message_id=properties.get('message_id'),
                        reply_to=properties.get('reply_to'),
                    )
                    # Commit the receipt before ACK. Audit failure retains original.
                    record_confirm({'body_hash': digest, 'exchange': target.exchange.name,
                                    'routing_key': route})
                    message.ack()
                    item['status'] = 'replayed'
                    result['replayed'] += 1
                except Exception:
                    item['code'] = 'publish_or_receipt_failed'
                    result['retained'] += 1
                    result['complete'] = False
                    break
        finally:
            # Also requeues dry-run, validation failures and unconfirmed messages.
            channel.close()
    return result
