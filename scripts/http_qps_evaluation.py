#!/usr/bin/env python3
"""Measure real local HTTP request rate on a read-only endpoint."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import math
import ssl
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def percentile(values, quantile):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)] if ordered else None


def evaluate(url, duration, concurrency, timeout, *, identities=None, response_validator=None,
             arrival_rate=None, method='GET', body_factory=None, max_requests=None):
    if identities and (urlsplit(url).scheme != 'http' or urlsplit(url).hostname not in ('127.0.0.1', 'localhost')):
        raise ValueError('synthetic_tokens_are_loopback_only')
    # Windows certificate enumeration is expensive. Never repeat it per request,
    # including plain HTTP; build_opener otherwise creates a default HTTPSHandler.
    tls_context = ssl.create_default_context() if identities else None
    client_local = threading.local()
    deadline = time.monotonic() + duration
    lock = threading.Lock()
    latencies = []
    statuses = Counter()
    accepted_latencies = []
    invalid_responses = []
    issued = 0
    dropped = 0
    scheduled_count = 0
    schedule_lags = []
    executor_waits = []
    slots = threading.BoundedSemaphore(concurrency)

    def perform(index):
        headers = identities[index % len(identities)] if identities else None
        if headers:
            if not hasattr(client_local, 'opener'):
                client_local.opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=tls_context))
            open_request = client_local.opener.open
        else:
            open_request = urllib.request.urlopen
        started = time.perf_counter()
        status = 'transport_error'
        valid_response = True
        try:
            data = body_factory(index) if body_factory else None
            request = urllib.request.Request(url, headers=headers or {}, data=data, method=method) if headers or data or method != 'GET' else url
            with open_request(request, timeout=timeout) as response:
                body = response.read()
                status = str(response.status)
                if response_validator and 200 <= response.status < 300:
                    try:
                        valid_response = bool(response_validator(index, body))
                    except (ValueError, TypeError, KeyError):
                        valid_response = False
        except urllib.error.HTTPError as error:
            status = str(error.code)
            error.read()
            error.close()
        except TimeoutError:
            status = 'timeout'
        except urllib.error.URLError as error:
            status = 'timeout' if isinstance(error.reason, TimeoutError) else 'transport_error'
        except OSError:
            status = 'transport_error'
        elapsed_ms = (time.perf_counter() - started) * 1000
        with lock:
            latencies.append(elapsed_ms)
            statuses[status] += 1
            if not valid_response:
                invalid_responses.append(1)
            if valid_response and status.isdigit() and 200 <= int(status) < 300:
                accepted_latencies.append(elapsed_ms)

    def worker(index):
        nonlocal issued
        while time.monotonic() < deadline:
            with lock:
                if max_requests is not None and issued >= max_requests:
                    return
                issued += 1
            perform(index)

    def arrival_worker(index, submitted_at):
        try:
            with lock:
                executor_waits.append((time.perf_counter() - submitted_at) * 1000)
            perform(index)
        finally:
            slots.release()

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        if arrival_rate:
            scheduled_count = int(duration * arrival_rate)
            if max_requests is not None:
                scheduled_count = min(scheduled_count, max_requests)
            schedule_start = time.perf_counter()
            futures = []
            for index in range(scheduled_count):
                delay = schedule_start + index / arrival_rate - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                schedule_lags.append(max(0, time.perf_counter() - (schedule_start + index / arrival_rate)) * 1000)
                if slots.acquire(blocking=False):
                    futures.append(pool.submit(arrival_worker, index, time.perf_counter()))
                else:
                    dropped += 1
        else:
            futures = [pool.submit(worker, index) for index in range(concurrency)]
        for future in futures:
            future.result()
    wall_seconds = time.perf_counter() - started
    completed = len(accepted_latencies)
    total = len(latencies)
    throttled = statuses.get('429', 0)
    server_errors = sum(value for key, value in statuses.items() if key.isdigit() and 500 <= int(key) < 600)
    accepted_p95 = percentile(accepted_latencies, .95)
    return {
        'status': ('partial' if throttled or dropped else 'passed')
                  if total and completed + throttled == total else 'failed',
        'evidence_level': 'real_http_read_only_local_endpoint' if method == 'GET' else 'real_http_local_write_endpoint',
        'url': url, 'duration_seconds': round(wall_seconds, 3), 'concurrency': concurrency,
        'load_model': 'fixed_arrival' if arrival_rate else 'closed_loop',
        'target_arrival_qps': arrival_rate, 'scheduled_requests': scheduled_count if arrival_rate else total,
        'client_backpressure_drops': dropped, 'method': method,
        'schedule_lag_ms': {'p95': percentile(schedule_lags, .95), 'max': max(schedule_lags) if schedule_lags else None},
        'executor_wait_ms': {'p95': percentile(executor_waits, .95), 'max': max(executor_waits) if executor_waits else None},
        'performance_checks': {'ordinary_api_p95_target_ms': 500,
            'ordinary_api_p95_met': accepted_p95 <= 500 if accepted_p95 is not None else None,
            'offered_load_complete': total == scheduled_count and dropped == 0 if arrival_rate else None},
        'authenticated_identity_count': len(identities) if identities else 0,
        'invalid_response_count': len(invalid_responses),
        'response_validation': 'executed' if response_validator else 'not-requested',
        'request_count': total, 'successful_requests': completed,
        'http_qps': round(total / wall_seconds, 3) if wall_seconds else None,
        'successful_http_qps': round(completed / wall_seconds, 3) if wall_seconds else None,
        'rate_limited_requests': throttled,
        'success_rate': completed / total if total else None,
        'offered_success_rate': completed / (scheduled_count if arrival_rate else total) if (scheduled_count if arrival_rate else total) else None,
        'rate_limited_rate': throttled / total if total else None,
        'server_error_rate': server_errors / total if total else None,
        'transport_error_rate': statuses.get('transport_error', 0) / total if total else None,
        'timeout_rate': statuses.get('timeout', 0) / total if total else None,
        'throttle_correctness': 'pending-verification',
        'business_tps': None,
        'business_tps_note': '仅发送只读 GET；TPS 不适用。' if method == 'GET' else 'HTTP 成功不等于事务验证，调用方须验证数据库结果后计算 TPS。',
        'http_status_counts': dict(statuses),
        'latency_ms': {'p50': round(percentile(latencies, .50), 3) if latencies else None,
                       'p95': round(percentile(latencies, .95), 3) if latencies else None,
                       'p99': round(percentile(latencies, .99), 3) if latencies else None,
                       'max': round(max(latencies), 3) if latencies else None},
        'accepted_latency_ms': {'p50': round(percentile(accepted_latencies, .50), 3) if accepted_latencies else None,
                                'p95': round(percentile(accepted_latencies, .95), 3) if accepted_latencies else None,
                                'p99': round(percentile(accepted_latencies, .99), 3) if accepted_latencies else None},
        'limitations': [('固定到达率、单机本地端点；不代表生产容量。' if arrival_rate else '闭环并发、单机本地端点；不代表固定到达率压力或生产容量。'),
                        '429 仅表示观测到限流；未验证用户/IP/企业隔离或阈值正确性。',
                        '不含 TLS 入口、反向代理及跨地域网络；认证和数据库验证由调用方单独记录。'],
    }


def main():
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='只读本地 HTTP QPS/p95/p99 基线')
    parser.add_argument('--url', action='append', help='可重复提供，只读路由分别生成指标；默认 CSRF 引导')
    parser.add_argument('--duration', type=float, default=10)
    parser.add_argument('--concurrency', type=int, default=8)
    parser.add_argument('--timeout', type=float, default=3)
    parser.add_argument('--output', default='output/evaluation/http-qps.json')
    args = parser.parse_args()
    if not 1 <= args.duration <= 120 or not 1 <= args.concurrency <= 64 or not 0.1 <= args.timeout <= 30:
        parser.error('duration 1..120 秒；concurrency 1..64；timeout 0.1..30 秒')
    results = [evaluate(url, args.duration, args.concurrency, args.timeout)
               for url in (args.url or ['http://127.0.0.1:8000/api/v1/auth/csrf/'])]
    result = results[0] if len(results) == 1 else {
        'status': 'failed' if any(row['status'] == 'failed' for row in results) else
                  ('partial' if any(row['status'] == 'partial' for row in results) else 'passed'),
        'routes': results,
        'limitations': ['路由按顺序测试，共享同一客户端 IP；限流维度隔离尚未验证。'],
    }
    result['measured_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    target = Path(args.output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('报告：' + str(target))
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
