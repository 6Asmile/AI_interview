"""Creates exclusively synthetic fixtures; no model or retrieval invocation."""
import json
from pathlib import Path
import secrets
import uuid
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = '预置浏览器非 AI 验收合成账号、简历与录像面试；保留数据用于定位。'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--resume-only', action='store_true')

    def handle(self, **options):
        from users.models import User
        from resumes.models import Resume
        from resumes.versioning import create_resume_version
        if not options['resume_only']:
            from interviews.models import InterviewSession, InterviewQuestion
        from allauth.account.models import EmailAddress
        tag = 'evaluation-' + uuid.uuid4().hex[:12]
        password = secrets.token_urlsafe(24)
        with transaction.atomic():
            user = User.objects.create_user(username=tag, email=tag + '@example.invalid', password=password,
                onboarding_step='completed', onboarding_completed_at=timezone.now())
            EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
            resume = Resume.objects.create(user=user, title='真实链路合成验收简历')
            create_resume_version(resume=resume, user=user, resume_json={'basics': {'name': '合成验收候选人', 'summary': '只用于功能验收，不是真实经历。'}}, change_summary='合成初始化')
            session = None
            if not options['resume_only']:
                session = InterviewSession.objects.create(user=user, resume=resume, job_position='合成录像验收',
                    status='running', recording_enabled=True, question_count=1, started_at=timezone.now())
                InterviewQuestion.objects.create(session=session, question_text='合成录制测试，不提交回答，不调用模型。', sequence=1)
        path = Path(options['output']).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {'email': user.email, 'password': password, 'resume_id': resume.pk,
            'session_id': str(session.pk) if session else None, 'resume_only': options['resume_only'], 'user_id': user.pk}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        self.stdout.write('合成浏览器 fixture 已准备；凭据仅保存在本地临时文件，不写入报告。')
