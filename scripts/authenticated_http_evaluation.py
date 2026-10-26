"""Real loopback read load using newly created synthetic JWT identities."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import uuid
import socket
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from http_qps_evaluation import evaluate

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def owned_asgi_server(pooled=False):
    """Own one temporary read/write evaluation API, never restart the user's API."""
    with socket.socket() as port_socket:
        port_socket.bind(('127.0.0.1', 0))
        port = port_socket.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='ifaceoff-asgi-evaluation-') as directory:
        with (Path(directory) / 'server.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'ai_interview_backend.asgi:application',
                '--host', '127.0.0.1', '--port', str(port), '--workers', '1', '--no-access-log', '--lifespan', 'off'],
                cwd=ROOT / 'ai_interview_backend', stdout=log, stderr=log,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                env={**os.environ, 'PYTHONUTF8': '1', 'POSTGRES_POOL_ENABLED': str(pooled).lower(), 'POSTGRES_CONN_MAX_AGE': '0'})
            try:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('owned_asgi_start_failed')
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.5):
                            break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError('owned_asgi_start_timeout')
                        time.sleep(.1)
                yield f'http://127.0.0.1:{port}'
            finally:
                if process.poll() is None:
                    if os.name == 'nt':
                        # venv python.exe is a launcher; killing it alone leaves
                        # the actual interpreter holding the port and log open.
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10)
                    else:
                        process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


def run(base_url='http://127.0.0.1:8000', *, duration=5, concurrency=4, users=4, arrival_rate=None, writes=False,
        isolated_server=None, server_environment='existing_local_development_server'):
    if isolated_server:
        with owned_asgi_server(pooled=isolated_server == 'asgi-pooled') as url:
            return run(url, duration=duration, concurrency=concurrency, users=users, arrival_rate=arrival_rate,
                writes=writes, server_environment=isolated_server + '_owned_single_worker')
    parsed = urlsplit(base_url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.password:
        raise ValueError('synthetic_tokens_are_loopback_only')
    with tempfile.TemporaryDirectory(prefix='ifaceoff-http-evaluation-') as directory:
        fixture = Path(directory) / 'identities.json'
        prepared = subprocess.run([sys.executable, 'manage.py', 'prepare_http_evaluation', '--output', str(fixture), '--users', str(users)],
            cwd=ROOT / 'ai_interview_backend', env={**os.environ, 'PYTHONUTF8': '1'}, capture_output=True, timeout=45)
        if prepared.returncode:
            raise RuntimeError('synthetic_http_fixture_failed')
        identities = json.loads(fixture.read_text(encoding='utf-8'))
        profile_path = Path(directory) / 'profile.json'
        profiled = subprocess.run([sys.executable, 'manage.py', 'prepare_http_evaluation', '--profile', str(fixture), '--output', str(profile_path)],
            cwd=ROOT / 'ai_interview_backend', capture_output=True, timeout=45)
        if profiled.returncode:
            raise RuntimeError('synthetic_app_profile_failed')
        application_profile = json.loads(profile_path.read_text(encoding='utf-8'))
        headers = [{'Authorization': 'Bearer ' + row['access_token']} for row in identities]
        def templates_valid(_index, body):
            data = json.loads(body)
            return isinstance(data, dict) and len(data.get('templates', [])) == 6 and data.get('schema_version') == '1.3.1'

        def resumes_valid(index, body):
            data = json.loads(body)
            entries = data if isinstance(data, list) else data.get('results', [])
            return len(entries) == 1 and entries[0].get('id') == identities[index % len(identities)]['resume_id']

        results = [evaluate(base_url + path, duration, concurrency, 3, identities=headers, response_validator=validator, arrival_rate=arrival_rate)
                   for path, validator in (('/api/v2/resume-templates/', templates_valid), ('/api/v2/resumes/', resumes_valid))]
        write_result = {'status': 'not-requested'}
        if writes:
            created = []
            created_lock = threading.Lock()
            def created_valid(index, body):
                data = json.loads(body)
                valid = bool(data.get('id') and data.get('current_version', {}).get('schema_version') == '1.3.1'
                             and data.get('current_design_revision'))
                if valid:
                    with created_lock:
                        created.append({'user_id': identities[index % len(identities)]['user_id'], 'resume_id': data['id']})
                return valid
            write_result = evaluate(base_url + '/api/v2/resumes/', duration, concurrency, 5,
                identities=[{**header, 'Content-Type': 'application/json'} for header in headers],
                response_validator=created_valid, method='POST', max_requests=40, arrival_rate=arrival_rate,
                body_factory=lambda _index: json.dumps({'title': '合成写入验收-' + uuid.uuid4().hex, 'status': 'draft'}).encode())
            expected = Path(directory) / 'expected.json'
            expected.write_text(json.dumps(created), encoding='utf-8')
            verified = subprocess.run([sys.executable, 'manage.py', 'prepare_http_evaluation', '--verify', str(expected), '--output', str(Path(directory) / 'verified.json')],
                cwd=ROOT / 'ai_interview_backend', capture_output=True, timeout=30)
            valid_database = (verified.returncode == 0
                and json.loads((Path(directory) / 'verified.json').read_text())['verified_count'] == len(created)
                and len({row['resume_id'] for row in created}) == len(created))
            write_result.update(database_verified=valid_database, completed_business_transactions=len(created) if valid_database else 0,
                business_tps=round(len(created) / write_result['duration_seconds'], 3) if valid_database and write_result['duration_seconds'] else None,
                business_tps_note='以真实 PostgreSQL 核对 HTTP 创建的简历、内容版本与设计；单次最多40个合成写入。')
            if not valid_database:
                write_result['status'] = 'failed'
    report = {'status': 'failed' if any(row['status'] == 'failed' for row in results + [write_result]) else 'partial',
              'measured_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'routes': results,
              'writes': write_result,
              'application_profile': application_profile,
              'server_environment': server_environment,
              'limitations': ['本地真实 HTTP，短期 JWT 直接为合成账号签发；未压登录供应商。',
                              '少量合成数据，未验证企业配额、500 用户或生产容量；固定到达率需另看客户端丢弃数。']}
    target = ROOT / 'output/evaluation' / ('authenticated-http-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(target))
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(run())
