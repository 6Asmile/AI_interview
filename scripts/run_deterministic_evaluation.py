#!/usr/bin/env python3
"""Offline, isolated evaluation. Never equate test timings with production SLOs."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import hashlib
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    'render_matrix': ['resumes.test_render_matrix_evaluation'],
    'operation': ['core.test_operations'],
    'broker_admin': ['staff_admin.test_broker_dlq'],
    'redis_contract': ['core.test_redis_resilience'],
    'worker_contract': ['core.test_worker_isolation'],
    'resume': ['resumes.tests', 'resumes.test_preview_scheduling'],
    'video_contract': ['video_uploads.test_operation_integration'],
    'api_measurement': ['core.test_deterministic_measurements'],
    'platform': [
        'users.tests.PersonalSecurityApiTests', 'users.tests.BrowserCookieAuthTests',
        'users.tests.GitHubOAuthFlowTests',
        'careers.tests.CareerWorkspaceApiTests.test_career_facts_are_private_and_can_be_confirmed',
        'careers.tests.CareerWorkspaceApiTests.test_application_rejects_another_users_job_target',
        'careers.tests.CareerWorkspaceApiTests.test_dashboard_uses_real_owned_records',
        'careers.tests.CareerWorkspaceApiTests.test_published_company_job_is_frozen_when_saved',
        'community.tests.CommunityIntegrationTests', 'community.test_operation_integration.CommunityOperationIntegrationTests',
        'chat.tests.ReliableChatTests',
        'staff_admin.tests.StaffIdentityIsolationTests', 'staff_admin.tests.StaffOperationsReadSmokeTests',
        'staff_admin.test_authoritative_operation_dispatch.StaffDurableCommandTests.test_global_search_rebuild_requires_and_reuses_linked_admin_principal',
        'resumes.tests.ResumeParsingServiceTests',
        *[f'resumes.tests.ResumeIntelligenceTests.{name}' for name in (
            'test_schema_snapshot_and_internal_ids_are_stable_exports',
            'test_legacy_blank_email_and_url_are_removed_before_strict_validation',
            'test_six_curated_templates_only', 'test_old_design_gets_new_sections_and_can_hide_them',
            'test_six_templates_map_to_distinct_server_owned_rendercv_themes',
            'test_rendercv_keeps_non_international_phone_without_rejecting_resume',
            'test_six_template_payloads_match_reviewed_golden_contract',
            'test_version_and_design_revision_are_immutable',
            'test_studio_can_lock_resume_with_nullable_current_relations',
            'test_draft_etag_conflict_and_commit', 'test_only_one_default_resume_per_user',
            'test_evidence_link_requires_confirmed_owned_fact', 'test_quality_flags_unverified_metrics',
            'test_share_is_hashed_redacted_password_protected_and_revocable',
            'test_share_download_artifact_uses_redacted_snapshot', 'test_artifact_cache_is_namespaced_per_resume',
            'test_json_and_docx_artifacts_use_same_snapshot', 'test_markdown_export_covers_extended_sections_and_bullets',
            'test_png_export_stacks_multiple_server_pages', 'test_renderer_rejects_typst_commands_images_and_html',
            'test_resume_create_response_contains_content_and_design_snapshots',
            'test_avatar_is_normalized_bound_to_draft_and_removed_from_standard_export',
            'test_import_confirmation_creates_immutable_snapshot_idempotently',
            'test_extract_text_falls_back_to_text_reader_when_parser_fails',
        )],
    ],
}
DEFAULT_GROUPS = ('operation', 'redis_contract', 'worker_contract', 'api_measurement', 'platform')

COVERAGE_MATRIX = [
    ('账号与认证', 'platform（API）; browser-platform（真实浏览器）', 'Cookie 会话/账号安全 API；刷新与新标签真实浏览器恢复；GitHub OAuth 仅 Mock', '真实 GitHub 授权、验证码邮件投递与外部供应商延迟'),
    ('简历 Studio', 'platform（API）; browser-platform（真实浏览器）', '版本/ETag/导入导出/分享契约；真实浏览器自动保存并核对 PostgreSQL 草稿', '六模板完整语言/纸张/多页黄金渲染与长时并发编辑'),
    ('求职工作台与企业岗位', 'platform', '职业事实隔离、投递归属、岗位 JD 快照冻结', '企业跨成员攻击集、完整审核页面与大数据量查询延迟'),
    ('社区、私信与管理端', 'platform', 'PII 脱敏、匿名作者隐藏、Chat 去重/隔离、Staff RBAC 与审计契约', '真实页面全流程、迁移对账、消息推送重连端到端'),
    ('确定性 HTTP/API', 'api_measurement + http-benchmark', 'APIClient 分位数/顺序业务写 TPS；本机 HTTP QPS/p95/p99 与 429', '多实例/固定到达率、代理/TLS、500 在线用户生产容量'),
    ('PostgreSQL/异步基础设施', 'real-infra', '隔离 PostgreSQL 真实事务/并发测试；Redis/Rabbit 协议停机、租约、重投递', '真实 Outbox 到业务 Worker 端到端崩溃补偿、PITR/RPO/RTO'),
    ('文档与对象存储', 'resume deterministic tests; media optional', '文本提取 fallback、标准产物快照契约；可选真实 FFmpeg 合成文件', '对象存储断连/校验/清理、恶意文件沙箱和大文件上传韧性'),
    ('容量与长稳', 'http-benchmark; repeat', '有限时长本机闭环请求率、延迟分位数、重复回归', '长时间资源增长、真实队列排队/吞吐、500 用户和灾备演练'),
]


def percentile(values, q):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * q) - 1)] if values else None


def summarize(rows):
    counts = {key: sum(row['status'] == key for row in rows)
              for key in ('passed', 'failed', 'error', 'skipped', 'expected_failure')}
    executed = counts['passed'] + counts['failed'] + counts['error']
    return {**counts, 'total': len(rows), 'executed': executed,
            'pass_rate': counts['passed'] / executed if executed else None,
            'coverage_status': 'partial' if not rows or counts['skipped'] or counts['expected_failure'] else 'executed',
            'status': 'failed' if counts['failed'] or counts['error'] else ('partial' if not rows or counts['skipped'] or counts['expected_failure'] else 'passed')}


def isolated_run(args):
    """Child process owns its disposable database, files, network guard and runner."""
    os.environ['DJANGO_SETTINGS_MODULE'] = 'ai_interview_backend.test_settings'
    os.environ['IFACEOFF_MEASUREMENT_SAMPLES'] = str(args.samples)
    sys.path.insert(0, str(ROOT / 'ai_interview_backend'))
    from django.conf import settings
    pg_port = os.environ.get('IFACEOFF_EVALUATION_PG_PORT')
    if pg_port:
        settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'evaluation',
            'USER': 'postgres', 'HOST': '127.0.0.1', 'PORT': pg_port, 'TEST': {'NAME': 'test_ifaceoff_' + os.environ['IFACEOFF_EVALUATION_PG_SUFFIX']}}}
    # Bind all aliases before app/URL imports cache a backend in module globals.
    settings.CACHES = {alias: {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'evaluation-' + alias}
                       for alias in ('default', 'coordination', 'realtime')}
    import django
    django.setup()
    import socket
    import unittest
    from unittest.mock import patch
    from django.test.runner import DiscoverRunner
    from django.test.utils import override_settings

    rows = []

    class Result(unittest.TextTestResult):
        def startTest(self, test):
            self.started = time.perf_counter()
            self.row = {'test': test.id(), 'status': 'passed'}
            super().startTest(test)

        def addFailure(self, test, err):
            self.row['status'] = 'failed'
            self.row['error_type'] = err[0].__name__
            super().addFailure(test, err)

        def addError(self, test, err):
            self.row['status'] = 'error'
            self.row['error_type'] = err[0].__name__
            super().addError(test, err)

        def addSkip(self, test, reason):
            self.row.update(status='skipped', reason=reason)
            super().addSkip(test, reason)

        def addExpectedFailure(self, test, err):
            self.row['status'] = 'expected_failure'
            super().addExpectedFailure(test, err)

        def addUnexpectedSuccess(self, test):
            self.row.update(status='failed', error_type='UnexpectedSuccess')
            super().addUnexpectedSuccess(test)

        def addSubTest(self, test, subtest, err):
            if err:
                self.row.update(status='failed' if issubclass(err[0], test.failureException) else 'error', error_type=err[0].__name__)
            super().addSubTest(test, subtest, err)

        def stopTest(self, test):
            self.row['test_duration_ms'] = round((time.perf_counter() - self.started) * 1000, 3)
            self.row['measurements'] = getattr(test, 'measurements', [])
            rows.append(self.row.copy())
            super().stopTest(test)

    class TextRunner(unittest.TextTestRunner):
        resultclass = Result

    class Runner(DiscoverRunner):
        test_runner = TextRunner

    original_connect = socket.socket.connect
    def deny_network(sock, address):
        if pg_port and isinstance(address, tuple) and address[0] == '127.0.0.1' and address[1] == int(pg_port):
            return original_connect(sock, address)
        raise RuntimeError('OFFLINE_EVALUATION_NETWORK_FORBIDDEN')

    with tempfile.TemporaryDirectory(prefix='ifaceoff-evaluation-') as workspace:
        if not pg_port:
            settings.DATABASES['default']['TEST']['NAME'] = str(Path(workspace) / 'evaluation.sqlite3')
        with override_settings(MEDIA_ROOT=str(Path(workspace) / 'media')):
            from django.core.cache import caches
            from rest_framework.throttling import SimpleRateThrottle
            # DRF caches a class-level backend during import. Rebind it explicitly.
            with patch.object(SimpleRateThrottle, 'cache', caches['default']), patch.object(socket.socket, 'connect', deny_network), patch.object(socket.socket, 'connect_ex', deny_network):
                runner = Runner(verbosity=1, interactive=False, keepdb=False, parallel=0)
                failures = runner.run_tests([label for group in args.groups.split(',') for label in SUITES[group]])
    Path(args.internal_result).write_text(json.dumps({'cases': rows, 'runner_failures': failures}, ensure_ascii=False, indent=2), encoding='utf-8')
    return 1 if failures else 0


def media_smoke():
    ffmpeg = shutil.which('ffmpeg')
    ffprobe = shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        return {'status': 'pending-verification', 'reason': 'FFmpeg/FFprobe 不在 PATH，未执行真实媒体验证'}
    with tempfile.TemporaryDirectory(prefix='ifaceoff-media-evaluation-') as directory:
        started = time.perf_counter()
        root = Path(directory)
        def run(command):
            result = subprocess.run(command, capture_output=True, timeout=60)
            if result.returncode:
                raise RuntimeError('media_command_failed')
            return result.stdout
        try:
            chunks = []
            for index in range(2):
                chunk = root / f'chunk-{index}.ts'
                run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=15',
                     '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100', '-t', '1', '-c:v', 'libx264',
                     '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-f', 'mpegts', str(chunk)])
                chunks.append(chunk)
            merged = root / 'merged.ts'
            # Generated binary fixture, not an application/source edit.
            merged.write_bytes(b''.join(chunk.read_bytes() for chunk in chunks))
            output = root / 'result.mp4'
            transcode_started = time.perf_counter()
            run([ffmpeg, '-nostdin', '-v', 'error', '-i', str(merged), '-c:v', 'libx264', '-c:a', 'aac', str(output)])
            processing_ms = (time.perf_counter() - transcode_started) * 1000
            info = json.loads(run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output)]))
            duration = float(info['format']['duration'])
            streams = [{'type': item['codec_type'], 'codec': item['codec_name']} for item in info['streams']]
            assert 1.8 <= duration <= 2.5 and {item['type'] for item in streams} == {'audio', 'video'}
            return {'status': 'passed', 'evidence_level': 'real_binary_synthetic_fixture', 'duration_seconds': duration,
                    'output_bytes': output.stat().st_size, 'streams': streams, 'transcode_ms': round(processing_ms, 2),
                    'processing_ratio': round(processing_ms / (duration * 1000), 4),
                    'total_ms': round((time.perf_counter() - started) * 1000, 2),
                    'scope': '仅真实二进制合并转码，不代表浏览器上传、Operation 或 Worker 链路'}
        except Exception as error:
            return {'status': 'failed', 'error_type': type(error).__name__}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='不调用模型/RAG的确定性功能与量化评估')
    parser.add_argument('--groups', default=','.join(DEFAULT_GROUPS), help='默认排除面试/视频和 AI/RAG 专项；可用组：' + ','.join(SUITES))
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--samples', type=int, default=20, help='每次测试的进程内 API 样本数；不是并发压测')
    parser.add_argument('--media', action='store_true', help='执行真实 FFmpeg 合成媒体验证')
    parser.add_argument('--real-infra', action='store_true', help='创建专属 Docker PostgreSQL/Redis/RabbitMQ，执行真实故障实验')
    parser.add_argument('--operation-faults', action='store_true', help='专属数据库/MQ真实导出Worker崩溃与恢复实验')
    parser.add_argument('--broker-admin-real', action='store_true', help='专属数据库/MQ真实管理API死信试运行、重放、NACK与幂等')
    parser.add_argument('--broker-dlq', action='store_true', help='只测专属Broker死信/发布NACK/重放协议，不等于管理端重放能力')
    parser.add_argument('--browser', action='store_true', help='对本地运行页面执行合成账号保存/登录恢复/录像测试（不调用模型）')
    parser.add_argument('--browser-platform', action='store_true', help='只测真实浏览器登录恢复和 Resume Studio 自动保存')
    parser.add_argument('--http-benchmark', action='store_true', help='对本地只读 HTTP 健康端点测 QPS/p95/p99；另行记录，不等于业务 TPS')
    parser.add_argument('--http-url', action='append', help='HTTP 只读 URL，可重复提供以分路由统计')
    parser.add_argument('--authenticated-http', action='store_true', help='合成 JWT 用户的本地只读 HTTP 测量')
    parser.add_argument('--http-duration', type=float, default=5, help='每路由测量秒数，1..120')
    parser.add_argument('--http-concurrency', type=int, default=4, help='HTTP 闭环并发数，1..64')
    parser.add_argument('--http-users', type=int, default=4, help='认证 HTTP 合成用户数，1..16')
    parser.add_argument('--http-arrival-rate', type=float, help='固定到达请求率，1..100；省略时闭环')
    parser.add_argument('--http-writes', action='store_true', help='追加最多40个合成简历写入与主库核对')
    parser.add_argument('--http-isolated-server', choices=('asgi', 'asgi-pooled'), help='专属单进程 ASGI 对照，不修改8000开发服务；可对照 PostgreSQL 连接池')
    parser.add_argument('--output', default='output/evaluation')
    parser.add_argument('--timeout', type=int, default=600, help='每轮后端测试超时秒数')
    parser.add_argument('--internal-result', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.broker_admin_real:
        return subprocess.call([sys.executable, str(ROOT / 'scripts' / 'broker_admin_evaluation.py')], cwd=ROOT)
    if not 1 <= args.repeat <= 20 or not 1 <= args.samples <= 200 or not 1 <= args.timeout <= 3600:
        parser.error('repeat 1..20；samples 1..200；timeout 1..3600')
    if any(group not in SUITES for group in args.groups.split(',')):
        parser.error('未知评估组')
    if not 1 <= args.http_duration <= 120 or not 1 <= args.http_concurrency <= 64 or not 1 <= args.http_users <= 16:
        parser.error('HTTP duration 1..120；concurrency 1..64；users 1..16')
    if args.http_arrival_rate is not None and not 1 <= args.http_arrival_rate <= 100:
        parser.error('HTTP arrival rate 1..100')
    if args.internal_result:
        return isolated_run(args)
    if args.broker_dlq:
        return subprocess.call([sys.executable, str(ROOT / 'scripts/operation_fault_evaluation.py'), '--dlq-only'])
    if args.operation_faults:
        # Run in a separate interpreter so Django state never crosses evaluation modes.
        return subprocess.call([sys.executable, str(ROOT / 'scripts/operation_fault_evaluation.py')])
    if args.authenticated_http:
        from authenticated_http_evaluation import run
        return run(duration=args.http_duration, concurrency=args.http_concurrency, users=args.http_users,
                   arrival_rate=args.http_arrival_rate, writes=args.http_writes, isolated_server=args.http_isolated_server)
    if args.browser:
        from browser_evaluation_runner import run
        browser_exit = run(repeat=args.repeat)
        if not args.real_infra:
            return browser_exit
    if args.browser_platform:
        from browser_evaluation_runner import run
        browser_exit = run(resume_only=True, repeat=args.repeat)
        if not args.real_infra:
            return browser_exit

    if args.real_infra:
        from real_infrastructure_evaluation import Infrastructure, evaluate, wait_for
        infra = Infrastructure()
        real_report = {'status': 'pending-verification', 'scope': 'isolated_single_node_protocol_and_postgresql_tests'}
        try:
            infra.start('pg', 'postgres:16-alpine', 5432, ('-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_DB=evaluation'))
            infra.start('redis', 'redis:7-alpine', 6379)
            import redis
            wait_for(redis.Redis(host='127.0.0.1', port=infra.ports['redis'], socket_timeout=2).ping)
            # No persistence for the deliberate cache-loss test.
            infra.docker('exec', infra.prefix + '-redis', 'redis-cli', 'CONFIG', 'SET', 'save', '')
            infra.start('mq', 'rabbitmq:3.13-management-alpine', 5672, ('-e', 'RABBITMQ_DEFAULT_USER=evaluation', '-e', 'RABBITMQ_DEFAULT_PASS=evaluation'))
            import psycopg
            def pg_ready():
                with psycopg.connect(host='127.0.0.1', port=infra.ports['pg'], user='postgres', dbname='evaluation', connect_timeout=2):
                    return True
            wait_for(pg_ready)
            env = {**os.environ, 'IFACEOFF_EVALUATION_PG_PORT': str(infra.ports['pg']),
                   'IFACEOFF_EVALUATION_PG_SUFFIX': infra.prefix.replace('-', '_')}
            command = [sys.executable, str(Path(__file__).resolve()), '--groups', args.groups, '--repeat', str(args.repeat), '--samples', str(args.samples), '--output', args.output]
            if args.media:
                command.append('--media')
            completed = subprocess.run(command, env=env, timeout=args.timeout * args.repeat + 120)
            real_report.update(status='failed' if completed.returncode else 'passed', postgresql_exit_code=completed.returncode, cases=[], rabbitmq_version='3.13', ha_verified=False)
            if args.browser:
                real_report['browser'] = json.loads((ROOT / 'output/playwright/live-browser-result.json').read_text(encoding='utf-8'))
                if browser_exit:
                    real_report['status'] = 'failed'
            evaluate(infra, real_report['cases'])
        except Exception as error:
            real_report.update(status='failed', error_type=type(error).__name__)
        finally:
            infra.close()
        real_path = ROOT / args.output / ('real-infra-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
        real_path.parent.mkdir(parents=True, exist_ok=True)
        real_path.write_text(json.dumps(real_report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('真实基础设施报告：' + str(real_path))
        return 1 if real_report['status'] == 'failed' or (args.browser and browser_exit) else 0

    directory = (ROOT / args.output / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ')).resolve()
    directory.mkdir(parents=True)
    selected_groups = set(args.groups.split(','))
    report = {'schema_version': 1, 'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'scope': 'offline_non_ai_non_rag_with_optional_local_http', 'database': 'disposable PostgreSQL' if os.environ.get('IFACEOFF_EVALUATION_PG_PORT') else 'disposable SQLite', 'groups': args.groups.split(','),
              'coverage_matrix': [{'area': area, 'entry': entry, 'measured_evidence': evidence,
                                   'remaining_gap': gap,
                                   'executed_in_this_run': {
                                       '账号与认证': 'platform' in selected_groups,
                                       '简历 Studio': 'platform' in selected_groups,
                                       '求职工作台与企业岗位': 'platform' in selected_groups,
                                       '社区、私信与管理端': 'platform' in selected_groups,
                                       '确定性 HTTP/API': 'api_measurement' in selected_groups and args.http_benchmark,
                                       'PostgreSQL/异步基础设施': False,
                                       '文档与对象存储': 'platform' in selected_groups and args.media,
                                       '容量与长稳': args.http_benchmark and args.repeat > 1,
                                   }[area]}
                                  for area, entry, evidence, gap in COVERAGE_MATRIX],
              'limitations': ['SQLite 不证明 PostgreSQL 行锁并发正确性', 'Mock 契约不证明真实 Redis/RabbitMQ 故障恢复',
                              'APIClient 时间不包含网络、反向代理和浏览器', '测试耗时不是业务 p95',
                              '完整录像上传/面试绑定与报告链路未在非面试范围内执行',
                              '不评估 AI、RAG、语音质量或生产 SLO'], 'runs': []}
    version = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    dirty = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, capture_output=True, text=True)
    report['code_version'] = {'commit': version.stdout.strip(), 'tracked_dirty': bool(dirty.stdout.strip()), 'python': sys.version.split()[0]}
    if os.environ.get('IFACEOFF_EVALUATION_PG_PORT'):
        report['limitations'][0] = '真实隔离 PostgreSQL 单节点测试，不证明生产 HA/PITR（高可用/时间点恢复）'
    sources = sorted((ROOT / 'ai_interview_backend').rglob('*.py')) + [Path(__file__).resolve()]
    digest = hashlib.sha256()
    for source in sources:
        if '__pycache__' not in source.parts:
            digest.update(source.relative_to(ROOT).as_posix().encode())
            digest.update(source.read_bytes())
    report['code_version']['backend_source_sha256'] = digest.hexdigest()
    for index in range(args.repeat):
        result_file = directory / f'run-{index + 1}.json'
        started = time.perf_counter()
        command = [sys.executable, str(Path(__file__).resolve()), '--internal-result', str(result_file),
                   '--groups', args.groups, '--samples', str(args.samples)]
        with (directory / f'run-{index + 1}.log').open('w', encoding='utf-8') as log:
            try:
                env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
                completed = subprocess.run(command, cwd=ROOT / 'ai_interview_backend', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
                run = json.loads(result_file.read_text(encoding='utf-8')) if result_file.exists() else {'cases': [], 'infrastructure_error': '测试进程未生成结果，检查本轮日志'}
                run['exit_code'] = completed.returncode
            except subprocess.TimeoutExpired:
                run = {'cases': [], 'exit_code': 2, 'infrastructure_error': '测试进程超时'}
        run.update(index=index + 1, duration_seconds=round(time.perf_counter() - started, 2))
        report['runs'].append(run)
    rows = [row for run in report['runs'] for row in run['cases']]
    report['summary'] = summarize(rows)
    report['groups_summary'] = {group: summarize([row for row in rows if any(row['test'].startswith(label + '.') for label in SUITES[group])]) for group in args.groups.split(',')}
    report['measurements'] = [measurement for row in rows for measurement in row.get('measurements', [])]
    report['http_benchmark'] = {'status': 'not-requested'}
    if args.http_benchmark:
        http_command = [sys.executable, str(ROOT / 'scripts/http_qps_evaluation.py')]
        http_command.extend(['--duration', str(args.http_duration), '--concurrency', str(args.http_concurrency)])
        for url in args.http_url or []:
            http_command.extend(['--url', url])
        http_result = subprocess.run(http_command, cwd=ROOT,
            capture_output=True, text=True, encoding='utf-8', timeout=180)
        report['http_benchmark'] = json.loads(http_result.stdout[:http_result.stdout.rfind('\n报告：')]) if http_result.stdout else {'status': 'failed', 'error': 'http_probe_empty'}
    report['media'] = media_smoke() if args.media else {'status': 'not-requested'}
    bad = any(run['exit_code'] for run in report['runs']) or report['media']['status'] == 'failed' or report['summary']['status'] == 'failed' or report['http_benchmark']['status'] == 'failed'
    report['status'] = 'failed' if bad else 'partial'  # explicitly incomplete system acceptance
    report['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = report['summary']
    lines = ['# 非 AI 确定性评估报告', '', f"总体：{report['status']}（仅限定范围，不是完整系统验收）", '',
             f"通过 {summary['passed']} / 执行 {summary['executed']}；失败 {summary['failed']}；错误 {summary['error']}；跳过 {summary['skipped']}。", '',
             '| 评估组 | 状态 | 通过 | 失败/错误 | 跳过 |', '| --- | --- | --- | --- | --- |']
    for group, item in report['groups_summary'].items():
        lines.append(f"| {group} | {item['status']} | {item['passed']} | {item['failed'] + item['error']} | {item['skipped']} |")
    lines += ['', '## 量化样本', '', '按 evidence_level（证据类型）区分进程内 API 与真实本地渲染；均不是生产 API 延迟。', '']
    for item in report['measurements']:
        line = f"- {item['name']}：n={item['sample_count']}，p50={item['p50_ms']}ms，p95={item['p95_ms']}ms，p99={item['p99_ms']}ms"
        if item.get('business_transactions_per_second') is not None:
            line += f"，本地顺序业务 TPS={item['business_transactions_per_second']}"
        lines.append(line + '。')
    if report['http_benchmark'].get('status') != 'not-requested':
        lines.append('- 只读 HTTP：' + json.dumps(report['http_benchmark'], ensure_ascii=False))
    lines += ['', '## 真实媒体验证', '', json.dumps(report['media'], ensure_ascii=False), '', '## 未验证与边界', '']
    lines += ['', '## 评估覆盖矩阵', '', '| 模块 | 已有评估入口 | 本轮是否执行 | 已量化/断言 | 主要缺口 |', '| --- | --- | --- | --- | --- |']
    for item in report['coverage_matrix']:
        lines.append(f"| {item['area']} | {item['entry']} | {'是' if item['executed_in_this_run'] else '否'} | {item['measured_evidence']} | {item['remaining_gap']} |")
    lines += ['- ' + item for item in report['limitations']]
    (directory / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"评估状态：{report['status']}；通过 {summary['passed']}，失败/错误 {summary['failed'] + summary['error']}，跳过 {summary['skipped']}")
    print(f'报告：{directory / "report.md"}')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
