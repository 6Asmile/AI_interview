"""Disposable real-service probes. Never stop or consume application resources."""
import json
from pathlib import Path
import subprocess
import time
import uuid


class Infrastructure:
    def __init__(self):
        self.prefix = 'ifaceoff-eval-' + uuid.uuid4().hex[:12]
        self.owned = []
        self.ports = {}

    def docker(self, *args):
        result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError('docker_command_failed:' + args[0])
        return result.stdout.strip()

    def start(self, service, image, port, extra=()):
        name = self.prefix + '-' + service
        self.docker('run', '--pull', 'never', '-d', '--name', name, '--label', 'ifaceoff.evaluation=' + self.prefix,
                    '-p', f'127.0.0.1::{port}', *extra, image)
        self.owned.append(name)
        self.ports[service] = int(self.docker('port', name, f'{port}/tcp').split(':')[-1])

    def close(self):
        for name in reversed(self.owned):
            label = self.docker('inspect', '--format', '{{ index .Config.Labels "ifaceoff.evaluation" }}', name)
            if label != self.prefix:
                raise RuntimeError('container_ownership_mismatch')
            self.docker('rm', '-f', '-v', name)


def wait_for(action, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return action()
        except Exception:
            time.sleep(.5)
    raise TimeoutError('isolated_service_not_ready')


def evaluate(infra, rows=None):
    import redis
    from kombu import Connection, Exchange, Queue, Producer
    rows = rows if rows is not None else []
    r = redis.Redis(host='127.0.0.1', port=infra.ports['redis'], socket_timeout=2, socket_connect_timeout=2)
    wait_for(r.ping)
    key = infra.prefix + ':lease'
    assert r.set(key, 'owner-a', nx=True, px=1000)
    release = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
    assert r.eval(release, 1, key, 'owner-b') == 0 and r.get(key) == b'owner-a'
    assert r.eval(release, 1, key, 'owner-a') == 1
    assert r.set(key, 'expired', nx=True, px=100)
    time.sleep(.15)
    assert r.set(key, 'new-owner', nx=True, px=1000)
    rows.append({'name': '真实 Redis owner 校验与租约过期', 'status': 'passed'})
    r.set(infra.prefix + ':cache', 'synthetic', ex=30)
    started = time.perf_counter()
    infra.docker('stop', '-t', '1', infra.prefix + '-redis')
    try:
        r.ping()
    except redis.RedisError:
        pass
    else:
        raise AssertionError('redis_outage_not_observed')
    infra.docker('start', infra.prefix + '-redis')
    infra.ports['redis'] = int(infra.docker('port', infra.prefix + '-redis', '6379/tcp').split(':')[-1])
    r = redis.Redis(host='127.0.0.1', port=infra.ports['redis'], socket_timeout=2, socket_connect_timeout=2)
    wait_for(r.ping)
    assert r.get(infra.prefix + ':cache') is None
    assert r.set(key, 'restored', ex=5) and r.ttl(key) > 0
    rows.append({'name': '真实 Redis 停机拒绝连接及重启恢复写能力', 'status': 'passed', 'recovery_ms': round((time.perf_counter() - started) * 1000, 2), 'scope': '隔离实例，无持久化；不证明业务快照恢复'})

    url = f'amqp://evaluation:evaluation@127.0.0.1:{infra.ports["mq"]}//'
    def connect():
        c = Connection(url, connect_timeout=2, heartbeat=0, transport_options={'confirm_publish': True})
        c.connect()
        return c
    exchange = Exchange(infra.prefix, type='direct', durable=True)
    queue = Queue(infra.prefix, exchange=exchange, routing_key='probe', durable=True)
    c = wait_for(connect)
    channel = c.channel()
    queue(channel).declare()
    Producer(channel).publish({'probe_id': infra.prefix}, exchange=exchange, routing_key='probe', serializer='json', delivery_mode=2, mandatory=True, confirm_timeout=3)
    message = queue(channel).get(no_ack=False)
    assert message and message.payload['probe_id'] == infra.prefix
    channel.close()
    c.close()  # unacked delivery + consumer connection loss
    def redelivered():
        c = connect()
        message = queue(c.channel()).get(no_ack=False)
        if not message:
            c.close()
            raise RuntimeError('await_redelivery')
        assert message.delivery_info.get('redelivered')
        message.ack()
        c.close()
        return True
    wait_for(redelivered, timeout=15)
    rows.append({'name': '真实 RabbitMQ 未 ACK 断连后重新投递', 'status': 'passed', 'scope': '协议消费者断连，不是 Celery 业务 Worker 崩溃'})
    c = connect()
    Producer(c.channel()).publish({'probe_id': infra.prefix}, exchange=exchange, routing_key='probe', serializer='json', delivery_mode=2, mandatory=True, confirm_timeout=3)
    c.close()
    started = time.perf_counter()
    infra.docker('stop', '-t', '3', infra.prefix + '-mq')
    try:
        c = connect()
    except Exception:
        pass
    else:
        c.close()
        raise AssertionError('broker_outage_not_observed')
    infra.docker('start', infra.prefix + '-mq')
    infra.ports['mq'] = int(infra.docker('port', infra.prefix + '-mq', '5672/tcp').split(':')[-1])
    url = f'amqp://evaluation:evaluation@127.0.0.1:{infra.ports["mq"]}//'
    c = wait_for(connect)
    message = queue(c.channel()).get(no_ack=False)
    assert message and message.payload['probe_id'] == infra.prefix
    message.ack()
    c.close()
    rows.append({'name': '真实 RabbitMQ 重启后保留已确认持久消息', 'status': 'passed', 'recovery_ms': round((time.perf_counter() - started) * 1000, 2)})
    return rows
