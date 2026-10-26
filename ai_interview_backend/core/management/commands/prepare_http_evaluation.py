"""Create local synthetic identities; never print tokens or use existing users."""
import datetime
import json
from pathlib import Path
import uuid
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from rest_framework_simplejwt.tokens import AccessToken


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--users', type=int, default=4, choices=range(1, 17))
        parser.add_argument('--verify', help='核对本轮合成 HTTP 写入，禁止使用真实账号')
        parser.add_argument('--profile', help='仅测文件中的合成账号，统计应用内耗时与 SQL 数，不输出 SQL 正文')

    def handle(self, **options):
        from users.models import User
        from resumes.models import Resume
        from resumes.versioning import create_resume_version
        if options['profile']:
            from django.test import Client
            from django.db import connection
            identities = json.loads(Path(options['profile']).read_text(encoding='utf-8'))
            identity = identities[0]
            user = User.objects.get(pk=identity['user_id'])
            if not user.username.startswith('evaluation-http-') or not user.email.endswith('@example.invalid'):
                raise ValueError('synthetic_profile_only')
            client = Client(HTTP_HOST='127.0.0.1', HTTP_AUTHORIZATION='Bearer ' + identity['access_token'])
            routes = []
            for path in ('/api/v2/resume-templates/', '/api/v2/resumes/'):
                samples = []
                for _ in range(5):
                    sql_times = []
                    def measure(execute, sql, params, many, context):
                        started = time.perf_counter()
                        try:
                            return execute(sql, params, many, context)
                        finally:
                            sql_times.append((time.perf_counter() - started) * 1000)
                    started = time.perf_counter()
                    with connection.execute_wrapper(measure):
                        response = client.get(path)
                    if response.status_code != 200:
                        raise ValueError('synthetic_profile_http_failed')
                    data = response.json()
                    if path.endswith('resumes/'):
                        entries = data if isinstance(data, list) else data.get('results', [])
                        if len(entries) != 1 or entries[0]['id'] != identity['resume_id']:
                            raise ValueError('synthetic_profile_contract_failed')
                    elif len(data.get('templates', [])) != 6:
                        raise ValueError('synthetic_profile_contract_failed')
                    samples.append({'app_ms': round((time.perf_counter()-started)*1000, 3),
                        'sql_count': len(sql_times), 'sql_ms': round(sum(sql_times), 3)})
                routes.append({'path': path, 'samples': samples})
            before_count = Resume.objects.filter(user=user).count()
            samples = []
            for _ in range(5):
                sql_times = []
                sql_kinds = {}
                def measure_write(execute, sql, params, many, context):
                    kind = sql.strip().split(None, 1)[0].upper()
                    sql_kinds[kind] = sql_kinds.get(kind, 0) + 1
                    started = time.perf_counter()
                    try:
                        return execute(sql, params, many, context)
                    finally:
                        sql_times.append((time.perf_counter() - started) * 1000)
                started = time.perf_counter()
                with connection.execute_wrapper(measure_write), transaction.atomic():
                    response = client.post('/api/v2/resumes/', {'title': '合成回滚耗时样本', 'status': 'draft'}, content_type='application/json')
                    if response.status_code != 201 or not response.json().get('current_design_revision'):
                        raise ValueError('synthetic_write_profile_failed')
                    transaction.set_rollback(True)
                samples.append({'app_ms': round((time.perf_counter()-started)*1000, 3),
                    'sql_count': len(sql_times), 'sql_ms': round(sum(sql_times), 3), 'sql_kinds': sql_kinds, 'rolled_back': True})
            if Resume.objects.filter(user=user).count() != before_count:
                raise ValueError('synthetic_profile_rollback_failed')
            routes.append({'path': '/api/v2/resumes/', 'method': 'POST', 'samples': samples,
                'rollback_verified': True, 'limitations': ['外层事务回滚，包含额外保存点，不测真实COMMIT/连接池排队；不计业务TPS。']})
            Path(options['output']).write_text(json.dumps({'routes': routes, 'evidence_level': 'in_process_real_database_middleware',
                'limitations': ['串行5样本含首次加载；不含TCP、服务线程排队或并发锁等待；只记录默认数据库。']}, ensure_ascii=False), encoding='utf-8')
            self.stdout.write('合成应用内 SQL 与请求耗时已记录，无 SQL 正文或凭据。')
            return
        if options['verify']:
            rows = json.loads(Path(options['verify']).read_text(encoding='utf-8'))
            for row in rows:
                resume = Resume.objects.select_related('user', 'current_version', 'current_design_revision').get(pk=row['resume_id'], user_id=row['user_id'])
                if not resume.user.username.startswith('evaluation-http-') or not resume.user.email.endswith('@example.invalid') or not resume.current_version_id or not resume.current_design_revision_id:
                    raise ValueError('synthetic_write_verification_failed')
                if resume.current_version.resume_id != resume.pk or resume.current_design_revision.resume_id != resume.pk:
                    raise ValueError('synthetic_version_design_ownership_failed')
            Path(options['output']).write_text(json.dumps({'verified_count': len(rows)}), encoding='utf-8')
            self.stdout.write('本轮合成业务写入已从主库核对。')
            return
        identities = []
        with transaction.atomic():
            for _ in range(options['users']):
                tag = 'evaluation-http-' + uuid.uuid4().hex[:12]
                user = User.objects.create_user(username=tag, email=tag + '@example.invalid')
                resume = Resume.objects.create(user=user, title='HTTP合成验收简历')
                create_resume_version(resume=resume, user=user, resume_json={'basics': {'name': '合成候选人'}}, change_summary='HTTP合成初始化')
                token = AccessToken.for_user(user)
                token.set_exp(lifetime=datetime.timedelta(minutes=5))
                identities.append({'user_id': user.pk, 'access_token': str(token), 'resume_id': resume.pk})
        Path(options['output']).write_text(json.dumps(identities), encoding='utf-8')
        self.stdout.write('合成账号已准备，短期令牌仅写入本地临时文件。')
