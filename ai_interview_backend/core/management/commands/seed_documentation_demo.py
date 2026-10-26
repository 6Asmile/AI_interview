import hashlib
import json
import os
import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from careers.models import (
    CareerFact,
    CareerProfile,
    Company,
    JobApplication,
    JobMatchAnalysis,
    JobPosting,
    JobPostingRevision,
    JobTarget,
    LearningPlan,
    LearningTask,
)
from chat.models import Conversation, Message
from community.models import CommunityComment, CommunityContent, ContentRevision, Topic
from core.models import AsyncOperation
from interviews.models import (
    InterviewAgentExecution,
    InterviewAgentNodeRun,
    InterviewAgentRun,
    InterviewAgentTrace,
    InterviewQuestion,
    InterviewRubric,
    InterviewSession,
    InterviewTemplate,
    RubricDimension,
    RubricLevelAnchor,
)
from knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentRevision
from notifications.models import Notification
from reports.models import ResumeAnalysisReport
from resumes.models import (
    Resume,
    ResumeDesignRevision,
    ResumeDraft,
    ResumeQualityReport,
    ResumeVersion,
)
from staff_admin.models import (
    AdminAuditEvent,
    PlatformFeatureFlag,
    StaffAccount,
    StaffMFADevice,
    StaffRole,
)
from staff_admin.security import encrypt_secret
from system.models import (
    ModelAlias,
    ModelDeployment,
    ModelRequestLedger,
    ProviderCredential,
    RoutePolicy,
    RoutePolicyTarget,
    UsageBudget,
)
from users.models import NotificationPreference, User


def stable_hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class Command(BaseCommand):
    help = 'Seed an isolated, deterministic iFaceoff documentation demo dataset.'

    def add_arguments(self, parser):
        parser.add_argument('--namespace', default='ifaceoff-docs-v1')
        parser.add_argument('--purge', action='store_true')
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        namespace = str(options['namespace']).strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,39}', namespace):
            raise CommandError('namespace must match [a-z0-9][a-z0-9-]{2,39}')
        if not settings.DEBUG or os.getenv('ALLOW_DOCS_DEMO_DATA') != '1':
            raise CommandError(
                'Documentation demo data is disabled. Set DEBUG=true and ALLOW_DOCS_DEMO_DATA=1.'
            )

        with transaction.atomic():
            if options['purge']:
                deleted = self._purge(namespace)
                self._emit({'namespace': namespace, 'purged': deleted}, options['as_json'])
                return
            result = self._seed(namespace)
        self._emit(result, options['as_json'])

    def _emit(self, payload, as_json):
        if as_json:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
            return
        self.stdout.write(self.style.SUCCESS(f"Documentation demo namespace ready: {payload['namespace']}"))
        self.stdout.write(f"candidate_email={payload['candidate_email']}")
        self.stdout.write(f"staff_email={payload['staff_email']}")
        self.stdout.write(f"active_interview_id={payload['active_interview_id']}")
        self.stdout.write(f"completed_interview_id={payload['completed_interview_id']}")
        self.stdout.write(f"resume_report_id={payload['resume_report_id']}")

    def _purge(self, namespace):
        candidate_email = f'candidate-{namespace}@example.invalid'
        peer_email = f'peer-{namespace}@example.invalid'
        staff_email = f'staff-{namespace}@example.invalid'
        deleted = 0

        for model, filters in (
            (AdminAuditEvent, {'metadata__docs_namespace': namespace}),
            (PlatformFeatureFlag, {'key': f'{namespace}-agent-v4'}),
            (StaffAccount, {'email': staff_email}),
            (StaffRole, {'slug': f'{namespace}-admin'}),
            (KnowledgeDocument, {'title': f'[{namespace}] Agent与RAG工程手册'}),
            (CommunityContent, {'title': f'[{namespace}] 我如何复盘一次AI模拟面试'}),
            (Topic, {'slug': f'{namespace}-interview-review'}),
            (InterviewTemplate, {'name': f'[{namespace}] 后端与AI项目深挖'}),
            (InterviewRubric, {'name': f'[{namespace}] 项目深挖评分量表'}),
            (Company, {'slug': f'{namespace}-labs'}),
            (ModelAlias, {'slug': f'{namespace}-interview-chat'}),
            (ModelDeployment, {'name': f'{namespace}-local-stub'}),
            (ProviderCredential, {'name': f'{namespace}-no-secret'}),
            (User, {'email__in': [candidate_email, peer_email]}),
        ):
            count, _ = model.objects.filter(**filters).delete()
            deleted += count
        return deleted

    def _seed(self, namespace):
        now = timezone.now()
        candidate_password = os.getenv('IFACEOFF_DOCS_PASSWORD')
        staff_password = os.getenv('IFACEOFF_DOCS_STAFF_PASSWORD')
        totp_secret = os.getenv('IFACEOFF_DOCS_TOTP_SECRET')
        if not candidate_password or not staff_password or not totp_secret:
            raise CommandError(
                'Set IFACEOFF_DOCS_PASSWORD, IFACEOFF_DOCS_STAFF_PASSWORD, '
                'and IFACEOFF_DOCS_TOTP_SECRET in the process environment.'
            )

        candidate_email = f'candidate-{namespace}@example.invalid'
        peer_email = f'peer-{namespace}@example.invalid'
        staff_email = f'staff-{namespace}@example.invalid'

        candidate, _ = User.objects.update_or_create(
            email=candidate_email,
            defaults={
                'username': f'{namespace}-candidate',
                'role': User.Role.CANDIDATE,
                'headline': 'Python后端与AI应用工程师',
                'location': '上海',
                'years_experience': 3,
                'target_roles': ['Python后端工程师', 'AI应用工程师'],
                'skills_profile': ['Django', 'PostgreSQL', 'LangGraph', 'RAG'],
                'availability': '积极看机会',
                'onboarding_step': 'completed',
                'onboarding_completed_at': now,
                'profile_visibility': 'community',
                'is_active': True,
            },
        )
        candidate.set_password(candidate_password)
        candidate.save(update_fields=['password'])
        peer, _ = User.objects.update_or_create(
            email=peer_email,
            defaults={
                'username': f'{namespace}-peer',
                'role': User.Role.CANDIDATE,
                'headline': '平台工程师',
                'location': '杭州',
                'availability': '开放交流',
                'onboarding_step': 'completed',
                'onboarding_completed_at': now,
                'is_active': True,
            },
        )
        peer.set_unusable_password()
        peer.save(update_fields=['password'])
        NotificationPreference.objects.get_or_create(user=candidate)

        role, _ = StaffRole.objects.update_or_create(
            slug=f'{namespace}-admin',
            defaults={'name': '文档演示管理员', 'permissions': ['*'], 'is_system': False},
        )
        staff, _ = StaffAccount.objects.update_or_create(
            email=staff_email,
            defaults={
                'display_name': '文档演示管理员',
                'status': StaffAccount.Status.ACTIVE,
                'must_change_password': False,
                'recovery_codes_confirmed_at': now,
                'failed_login_count': 0,
                'locked_until': None,
            },
        )
        staff.set_password(staff_password)
        staff.save(update_fields=['password'])
        staff.roles.set([role])
        StaffMFADevice.objects.update_or_create(
            account=staff,
            name='文档截图验证器',
            defaults={'encrypted_secret': encrypt_secret(totp_secret), 'confirmed_at': now},
        )

        CareerProfile.objects.update_or_create(
            user=candidate,
            defaults={
                'target_roles': ['Python后端工程师', 'AI应用工程师'],
                'target_industries': ['企业服务', 'AI应用'],
                'preferred_locations': ['上海', '杭州', '远程'],
                'work_mode': CareerProfile.WorkMode.HYBRID,
                'seniority': 'mid',
                'salary_expectation': {'currency': 'CNY', 'min': 25000, 'max': 35000},
                'goals': ['补齐系统设计表达', '建立Agent工程证据', '完成三轮模拟面试'],
            },
        )
        fact, _ = CareerFact.objects.update_or_create(
            user=candidate,
            title=f'[{namespace}] iFaceoff全栈与AI项目',
            defaults={
                'fact_type': CareerFact.FactType.PROJECT,
                'organization': '个人项目',
                'role': '全栈与AI工程师',
                'description': (
                    '设计并实现覆盖职业画像、版本化简历、模拟面试、Agent、RAG、'
                    '模型网关和独立运营后台的求职训练平台。'
                ),
                'skills': ['Django', 'Vue 3', 'PostgreSQL', 'Celery', 'LangGraph', 'Qdrant'],
                'metrics': {'modules': 18, 'agent_state_schema': 4},
                'source_type': CareerFact.SourceType.MANUAL,
                'verification_status': CareerFact.VerificationStatus.CONFIRMED,
                'verified_at': now,
                'source_metadata': {'docs_namespace': namespace},
            },
        )

        company, _ = Company.objects.update_or_create(
            slug=f'{namespace}-labs',
            defaults={
                'name': '示例智能科技',
                'website': 'https://example.invalid',
                'description': '用于iFaceoff文档截图的合成企业，不对应真实公司。',
                'industry': 'AI应用',
                'size': '100-499人',
                'location': '上海',
                'status': Company.Status.VERIFIED,
                'created_by': candidate,
                'verified_at': now,
            },
        )
        posting, _ = JobPosting.objects.update_or_create(
            company=company,
            title='Python后端与AI应用工程师',
            defaults={
                'location': '上海',
                'work_mode': JobPosting.WorkMode.HYBRID,
                'employment_type': 'full_time',
                'status': JobPosting.Status.PUBLISHED,
                'published_at': now - timedelta(days=3),
                'closes_at': now + timedelta(days=27),
                'created_by': candidate,
            },
        )
        jd_text = (
            '负责Django业务服务、PostgreSQL数据建模、Celery异步任务以及基于LangGraph和RAG的'
            'AI应用开发；要求理解幂等、最终一致性、可观测性和故障恢复。'
        )
        posting_revision, _ = JobPostingRevision.objects.get_or_create(
            posting=posting,
            version=1,
            defaults={
                'title': posting.title,
                'jd_text': jd_text,
                'requirements': ['3年以上Python经验', '熟悉Django与PostgreSQL', '有Agent/RAG项目经验'],
                'skills': ['Python', 'Django', 'PostgreSQL', 'Celery', 'LangGraph', 'RAG'],
                'salary': {'currency': 'CNY', 'min': 25000, 'max': 35000},
                'content_hash': stable_hash(jd_text),
                'created_by': candidate,
                'approved_by_staff_id': staff.pk,
                'approved_at': now,
            },
        )
        JobPosting.objects.filter(pk=posting.pk).update(current_revision=posting_revision)
        target, _ = JobTarget.objects.update_or_create(
            user=candidate,
            company_name=company.name,
            position_name=posting.title,
            defaults={
                'job_posting': posting,
                'job_posting_revision': posting_revision,
                'source_type': JobTarget.SourceType.COMPANY,
                'jd_text': jd_text,
                'location': '上海',
                'deadline': (now + timedelta(days=27)).date(),
                'keywords': ['Django', 'PostgreSQL', 'LangGraph', 'RAG'],
                'jd_snapshot_hash': stable_hash(jd_text),
                'status': JobTarget.Status.ACTIVE,
            },
        )

        resume, _ = Resume.objects.update_or_create(
            user=candidate,
            title=f'[{namespace}] AI应用工程师简历',
            defaults={
                'full_name': '林同学',
                'email': candidate_email,
                'phone': '13800000000',
                'job_title': 'Python后端与AI应用工程师',
                'city': '上海',
                'summary': '专注可恢复AI工作流、RAG检索与可靠异步系统。',
                'template_name': 'modern',
                'canonical_schema_version': '1.3.1',
                'is_default': True,
                'status': Resume.Status.READY,
            },
        )
        resume_json = {
            'basics': {
                'name': '林同学',
                'label': 'Python后端与AI应用工程师',
                'email': candidate_email,
                'phone': '13800000000',
                'summary': '把AI能力做成可恢复、可审计、可演进的产品链路。',
                'location': {'city': '上海'},
            },
            'work': [{
                'name': '示例软件工作室',
                'position': '后端工程师',
                'startDate': '2023-07',
                'endDate': '',
                'summary': '负责Django服务与异步任务可靠性。',
                'highlights': ['落地Outbox/Inbox', '拆分Redis故障域'],
                'x-ifaceoff': {'id': 'work-docs-1'},
            }],
            'projects': [{
                'name': 'iFaceoff',
                'description': fact.description,
                'highlights': ['LangGraph V4 Checkpoint恢复', 'Qdrant与Meilisearch混合检索'],
                'keywords': ['Django', 'Vue 3', 'LangGraph', 'RAG'],
                'x-ifaceoff': {'id': 'project-docs-1'},
            }],
            'education': [],
            'skills': [
                {'name': 'Python', 'keywords': ['Django', 'Celery']},
                {'name': 'AI Engineering', 'keywords': ['LangGraph', 'RAG', 'LiteLLM']},
            ],
            'volunteer': [],
            'awards': [],
            'certificates': [],
            'publications': [],
            'languages': [],
            'interests': [],
            'references': [],
            'meta': {'schemaVersion': '1.3.1'},
            'x-ifaceoff': {'docsNamespace': namespace},
        }
        version, _ = ResumeVersion.objects.get_or_create(
            resume=resume,
            version_number=1,
            defaults={
                'schema_version': '1.3.1',
                'resume_json': resume_json,
                'content_hash': stable_hash(resume_json),
                'language': 'zh-CN',
                'layout_json': {},
                'evidence_snapshot': [{'career_fact_id': fact.pk, 'title': fact.title}],
                'source': ResumeVersion.Source.EDITOR,
                'change_summary': '文档演示基线版本',
                'created_by': candidate,
            },
        )
        design_json = {
            'template_key': 'modern-professional',
            'template_version': '1.0.0',
            'page_size': 'A4',
            'font': 'Noto Sans CJK SC',
            'color': '#1F2937',
            'density': 'balanced',
        }
        design, _ = ResumeDesignRevision.objects.get_or_create(
            resume=resume,
            revision_number=1,
            defaults={
                'template_key': 'modern-professional',
                'template_version': '1.0.0',
                'language': 'zh-CN',
                'page_size': 'A4',
                'design_json': design_json,
                'design_hash': stable_hash(design_json),
                'created_by': candidate,
            },
        )
        Resume.objects.filter(pk=resume.pk).update(
            current_version=version,
            current_design_revision=design,
        )
        draft_payload = {'resume_json': resume_json, 'design_json': design_json, 'revision': 1}
        ResumeDraft.objects.update_or_create(
            resume=resume,
            defaults={
                'base_version': version,
                'resume_json': resume_json,
                'design_json': design_json,
                'revision': 1,
                'etag': stable_hash(draft_payload),
                'updated_by': candidate,
            },
        )
        ResumeQualityReport.objects.update_or_create(
            resume=resume,
            content_version=version,
            defaults={
                'status': ResumeQualityReport.Status.COMPLETED,
                'config_hash': stable_hash({'rules': 'docs-v1'}),
                'score': 86,
                'report_json': {
                    'summary': '技术经历与目标岗位高度相关，建议补充容量指标和故障演练结果。',
                    'dimensions': [
                        {'name': '内容完整度', 'score': 90},
                        {'name': '岗位匹配度', 'score': 88},
                        {'name': '证据可追溯性', 'score': 80},
                    ],
                },
                'completed_at': now,
            },
        )
        application, _ = JobApplication.objects.update_or_create(
            user=candidate,
            job_target=target,
            defaults={
                'resume_version': version,
                'status': JobApplication.Status.INTERVIEW,
                'source': 'iFaceoff示例职位',
                'notes': '已完成首轮模拟面试，准备系统设计追问。',
                'applied_at': now - timedelta(days=5),
                'next_action_at': now + timedelta(days=2),
            },
        )
        operation, _ = AsyncOperation.objects.update_or_create(
            user=candidate,
            operation_type='career.job_match',
            source_app='careers',
            source_model='JobTarget',
            source_id=str(target.pk),
            defaults={
                'title': '目标岗位匹配分析',
                'status': AsyncOperation.Status.SUCCEEDED,
                'progress': 100,
                'metadata': {'docs_namespace': namespace},
                'started_at': now - timedelta(minutes=3),
                'completed_at': now - timedelta(minutes=2),
            },
        )
        match, _ = JobMatchAnalysis.objects.update_or_create(
            user=candidate,
            job_target=target,
            resume_version=version,
            defaults={
                'job_posting_revision': posting_revision,
                'operation': operation,
                'status': JobMatchAnalysis.Status.SUCCEEDED,
                'jd_snapshot': jd_text,
                'jd_snapshot_hash': stable_hash(jd_text),
                'score': 84,
                'dimensions': {'后端工程': 90, 'AI应用': 86, '系统设计': 76},
                'matched_skills': ['Python', 'Django', 'PostgreSQL', 'LangGraph'],
                'gaps': ['容量压测证据', '多租户隔离案例'],
                'evidence_refs': [{'resume_version_id': version.pk}],
                'recommendations': ['补充k6结果', '准备Redis故障域追问'],
                'config_snapshot': {'version': 'docs-v1'},
                'config_hash': stable_hash({'version': 'docs-v1'}),
                'completed_at': now,
            },
        )
        plan, _ = LearningPlan.objects.update_or_create(
            user=candidate,
            source_type='job_match',
            source_id=str(match.pk),
            defaults={
                'job_target': target,
                'match_analysis': match,
                'title': '两周AI应用工程师面试强化',
                'summary': '优先补齐系统设计、容量与故障恢复表达。',
                'status': LearningPlan.Status.ACTIVE,
                'version': 1,
                'config_snapshot': {'docs_namespace': namespace},
            },
        )
        for index, item in enumerate((
            ('复盘Agent Checkpoint恢复链路', 'Agent工程', LearningTask.Status.DOING),
            ('完成RAG混合召回评测', 'RAG', LearningTask.Status.TODO),
            ('整理PostgreSQL迁移复盘', '数据工程', LearningTask.Status.DONE),
        )):
            LearningTask.objects.update_or_create(
                user=candidate,
                plan=plan,
                title=item[0],
                defaults={
                    'dimension': item[1],
                    'priority': LearningTask.Priority.HIGH if index == 0 else LearningTask.Priority.MEDIUM,
                    'status': item[2],
                    'source_type': 'docs_demo',
                    'source_id': namespace,
                    'due_at': now + timedelta(days=index + 1),
                },
            )

        rubric, _ = InterviewRubric.objects.update_or_create(
            name=f'[{namespace}] 项目深挖评分量表',
            defaults={
                'description': '评价问题澄清、实现深度、取舍和故障恢复能力。',
                'version': 1,
                'visibility': InterviewRubric.Visibility.SHARED,
                'is_active': True,
                'created_by': candidate,
            },
        )
        for order, dimension_data in enumerate((
            ('architecture', '架构表达', '能从用户动作讲到持久化、异步和恢复', 35),
            ('consistency', '一致性设计', '能解释事务、幂等和最终一致性', 35),
            ('tradeoff', '技术取舍', '能说明替代方案及演进条件', 30),
        )):
            dimension, _ = RubricDimension.objects.update_or_create(
                rubric=rubric,
                key=dimension_data[0],
                defaults={
                    'name': dimension_data[1],
                    'description': dimension_data[2],
                    'weight': dimension_data[3],
                    'min_coverage': 1,
                    'order': order,
                },
            )
            RubricLevelAnchor.objects.update_or_create(
                dimension=dimension,
                level='strong',
                defaults={
                    'min_score': 80,
                    'max_score': 100,
                    'description': '回答包含真实代码证据、故障路径与清晰取舍。',
                },
            )
        template, _ = InterviewTemplate.objects.update_or_create(
            name=f'[{namespace}] 后端与AI项目深挖',
            defaults={
                'description': '围绕iFaceoff主链路进行项目深挖和系统设计追问。',
                'job_keywords': ['Django', 'PostgreSQL', 'Celery', 'Agent', 'RAG'],
                'rubric': rubric,
                'visibility': InterviewTemplate.Visibility.SHARED,
                'is_active': True,
                'version': 1,
                'require_rag': False,
                'interview_mode': InterviewTemplate.InterviewMode.PROJECT_WITH_FUNDAMENTALS,
                'target_duration_minutes': 30,
                'min_duration_minutes': 20,
                'hard_max_duration_minutes': 45,
                'min_turns': 5,
                'max_turns': 12,
                'candidate_question_minutes': 3,
                'style_profile': {'tone': 'professional', 'follow_up_depth': 3},
                'config': {'docs_namespace': namespace},
                'created_by': candidate,
            },
        )
        active_session, _ = InterviewSession.objects.update_or_create(
            user=candidate,
            job_position=f'[{namespace}] Python后端与AI应用工程师',
            status=InterviewSession.Status.RUNNING,
            defaults={
                'resume': resume,
                'resume_version': version,
                'job_target': target,
                'resume_snapshot': resume_json,
                'jd_snapshot': jd_text,
                'difficulty': InterviewSession.Difficulty.HARD,
                'question_count': 5,
                'target_duration_minutes': 30,
                'experience_mode': InterviewSession.ExperienceMode.REALISTIC,
                'interview_mode': template.interview_mode,
                'current_stage': InterviewSession.InterviewStage.PROJECT_DEEP_DIVE,
                'started_at': now - timedelta(minutes=12),
                'template': template,
                'session_plan': {'stages': ['opening', 'project_deep_dive', 'system_design', 'closing']},
                'template_snapshot': {'template_id': template.pk, 'version': template.version},
                'agent_config_snapshot': {'engine': 'composite_v4', 'state_schema_version': 4},
                'coverage_summary': {'architecture': 1, 'consistency': 1, 'tradeoff': 0},
                'memory_summary': {'candidate_strength': '能解释版本化和幂等', 'next_probe': '故障恢复'},
                'covered_topics': ['ResumeVersion', 'Outbox'],
                'pending_topics': ['Checkpoint恢复', 'RAG降级'],
                'last_activity_at': now,
            },
        )
        active_questions = (
            ('请用两分钟介绍iFaceoff，并说明最核心的业务闭环。', '项目定位', '我把它设计成从职业事实到简历、面试、评估和学习计划的证据闭环。', 86),
            ('ResumeVersion为什么设计成不可变，而不是直接覆盖Resume JSON？', '一致性设计', '不可变版本保证报告、投递和面试都能引用当时内容，避免历史解释漂移。', 90),
            ('如果Agent Worker在生成下一题时宕机，系统如何恢复？', '故障恢复', '', None),
        )
        questions = []
        for sequence, data in enumerate(active_questions, start=1):
            question, _ = InterviewQuestion.objects.update_or_create(
                session=active_session,
                sequence=sequence,
                defaults={
                    'question_text': data[0],
                    'target_dimension': data[1],
                    'answer_text': data[2],
                    'score': data[3],
                    'ai_feedback': {'summary': '回答有代码证据，可进一步量化恢复目标。'} if data[3] else None,
                    'rag_context': [{'source': 'docs-demo', 'title': 'iFaceoff项目事实'}],
                    'question_plan': {'stage': active_session.current_stage, 'reason': '根据上一轮证据追问'},
                    'question_signature': stable_hash(data[0]),
                    'generation_mode': 'composite_v4',
                    'validation_status': 'validated',
                    'answered_at': now - timedelta(minutes=10 - sequence) if data[2] else None,
                    'evaluated_at': now - timedelta(minutes=9 - sequence) if data[3] else None,
                },
            )
            questions.append(question)
        agent_run, _ = InterviewAgentRun.objects.update_or_create(
            session=active_session,
            request_hash=stable_hash({'session': str(active_session.pk), 'event': 'submit_answer'}),
            defaults={
                'trigger_question': questions[1],
                'event': 'submit_answer',
                'engine_name': 'composite_v4',
                'status': InterviewAgentRun.Status.COMPLETED,
                'state_schema_version': 4,
                'current_node': 'persist_result',
                'attempt_count': 1,
                'state_snapshot': {'stage': 'project_deep_dive', 'next_question_id': questions[2].pk},
                'model_config_snapshot': {'alias': f'{namespace}-interview-chat'},
                'prompt_version': 'interview-agent-v1',
                'agent_config_hash': stable_hash({'engine': 'composite_v4'}),
                'prompt_hashes': {'question_generation': stable_hash('docs-prompt')},
                'context_envelope_hash': stable_hash({'resume_version': version.pk}),
                'context_token_usage': {'used': 1840, 'budget': 6000},
                'started_at': now - timedelta(seconds=4),
                'completed_at': now - timedelta(seconds=1),
            },
        )
        execution_id = uuid.uuid5(uuid.NAMESPACE_URL, f'{namespace}:execution')
        execution, _ = InterviewAgentExecution.objects.update_or_create(
            pk=execution_id,
            defaults={
                'session': active_session,
                'trigger_question': questions[1],
                'legacy_run': agent_run,
                'thread_id': active_session.pk,
                'run_id': agent_run.pk,
                'event': 'submit_answer',
                'idempotency_key': f'{namespace}:turn:2',
                'request_hash': agent_run.request_hash,
                'checkpoint_namespace': 'interview',
                'engine_version': 'composite_v4',
                'state_schema_version': 4,
                'status': InterviewAgentExecution.Status.COMPLETED,
                'version': 3,
                'last_durable_sequence': 8,
                'state_metadata': {'checkpoint': 'persisted', 'docs_namespace': namespace},
                'result_question': questions[2],
                'last_event_id': '8-0',
                'started_at': now - timedelta(seconds=4),
                'completed_at': now - timedelta(seconds=1),
            },
        )
        for node_index, node in enumerate(('load_context', 'evaluate_answer', 'plan_next', 'persist_result'), start=1):
            InterviewAgentNodeRun.objects.update_or_create(
                run=agent_run,
                node_name=node,
                attempt=1,
                defaults={
                    'subagent_name': 'composite_v4',
                    'status': InterviewAgentNodeRun.Status.SUCCEEDED,
                    'input_hash': stable_hash({'node': node, 'run': str(agent_run.pk)}),
                    'output_summary': {'sequence': node_index, 'durable': node == 'persist_result'},
                    'latency_ms': 80 + node_index * 45,
                    'token_usage': {'input': 200 * node_index, 'output': 80 * node_index},
                    'started_at': now - timedelta(seconds=5 - node_index),
                    'completed_at': now - timedelta(seconds=4 - node_index),
                },
            )
        InterviewAgentTrace.objects.update_or_create(
            agent_run=agent_run,
            session=active_session,
            event='submit_answer',
            defaults={
                'question': questions[1],
                'stage': 'project_deep_dive',
                'node_outputs': {'evaluate_answer': {'score': 90}, 'plan_next': {'dimension': '故障恢复'}},
                'answer_evaluation': {'score': 90, 'evidence': ['ResumeVersion不可变约束']},
                'rag_context': [{'title': 'Agent恢复设计', 'score': 0.91}],
                'question_plan': {'next': questions[2].question_text},
                'generated_question': questions[2].question_text,
                'input_hash': agent_run.request_hash,
                'output_summary': {'execution_id': str(execution.pk), 'event_sequence': 8},
                'model_config_snapshot': {'alias': f'{namespace}-interview-chat'},
                'subagent_name': 'composite_v4',
                'context_budget': {'used': 1840, 'limit': 6000},
                'prompt_version': 'interview-agent-v1',
            },
        )

        completed_session, _ = InterviewSession.objects.update_or_create(
            user=candidate,
            job_position=f'[{namespace}] AI平台工程师复盘场',
            status=InterviewSession.Status.FINISHED,
            defaults={
                'resume': resume,
                'resume_version': version,
                'job_target': target,
                'resume_snapshot': resume_json,
                'jd_snapshot': jd_text,
                'difficulty': InterviewSession.Difficulty.MEDIUM,
                'question_count': 5,
                'target_duration_minutes': 30,
                'experience_mode': InterviewSession.ExperienceMode.COACHING,
                'interview_mode': template.interview_mode,
                'current_stage': InterviewSession.InterviewStage.CLOSING,
                'duration': 1680,
                'started_at': now - timedelta(days=1, minutes=28),
                'finished_at': now - timedelta(days=1),
                'template': template,
                'report': {
                    'overall_score': 87,
                    'summary': '项目链路完整，版本化与恢复设计表达突出。',
                    'dimensions': {'架构表达': 90, '一致性设计': 88, '技术取舍': 82},
                    'strengths': ['能从页面讲到数据层', '能区分事实源与加速层'],
                    'improvements': ['补充容量数据', '量化RTO/RPO'],
                },
                'coverage_summary': {'architecture': 3, 'consistency': 2, 'tradeoff': 2},
                'covered_topics': ['Career', 'Resume', 'Agent', 'RAG', 'Gateway'],
                'pending_topics': [],
                'last_activity_at': now - timedelta(days=1),
            },
        )

        resume_report, _ = ResumeAnalysisReport.objects.update_or_create(
            user=candidate,
            resume=resume,
            job_target=target,
            defaults={
                'resume_version': version,
                'resume_snapshot': resume_json,
                'model_config_snapshot': {'alias': f'{namespace}-interview-chat'},
                'evidence_sources': [{'career_fact_id': fact.pk}, {'resume_version_id': version.pk}],
                'jd_text': jd_text,
                'report_data': {
                    'overall_score': 84,
                    'summary': '后端与AI工程能力匹配，系统设计量化证据仍可加强。',
                    'strengths': ['Django/Celery工程经验', 'Agent与RAG链路完整'],
                    'gaps': ['容量压测', '跨区域容灾'],
                    'keyword_analysis': {
                        'matched': ['Django', 'PostgreSQL', 'Celery', 'LangGraph', 'RAG'],
                        'missing': ['Kubernetes', '多区域容灾'],
                    },
                    'suggestions': ['增加k6压测结果', '补充故障演练RTO'],
                },
                'overall_score': 84,
            },
        )

        knowledge_title = f'[{namespace}] Agent与RAG工程手册'
        knowledge, _ = KnowledgeDocument.objects.update_or_create(
            title=knowledge_title,
            defaults={
                'content': 'Agent恢复依赖持久Checkpoint、幂等执行记录和可续传事件游标。',
                'source_type': 'internal_docs',
                'file_type': 'markdown',
                'parse_status': KnowledgeDocument.ParseStatus.PARSED,
                'parser_name': 'docs-demo',
                'parser_version': '1',
                'parsed_content': {'headings': ['Agent恢复', 'RAG检索']},
                'visibility': KnowledgeDocument.Visibility.PUBLIC,
                'job_positions': ['AI应用工程师'],
                'ability_tags': ['Agent', 'RAG', '故障恢复'],
                'difficulty': KnowledgeDocument.Difficulty.MEDIUM,
                'status': KnowledgeDocument.Status.INDEXED,
                'approval_status': KnowledgeDocument.ApprovalStatus.APPROVED,
                'chunk_count': 3,
                'last_indexed_at': now,
                'created_by': candidate,
                'approved_by': candidate,
                'staff_approved_by': staff,
                'submitted_at': now - timedelta(days=2),
                'approved_at': now - timedelta(days=1),
            },
        )
        knowledge_revision, _ = KnowledgeDocumentRevision.objects.get_or_create(
            document=knowledge,
            version_number=1,
            defaults={
                'status': KnowledgeDocumentRevision.Status.PUBLISHED,
                'source_content': knowledge.content,
                'parsed_content': {'sections': ['Agent恢复', '混合检索', '降级策略']},
                'parser_snapshot': {'parser': 'docs-demo', 'version': 1},
                'created_by': candidate,
                'approved_by': candidate,
                'staff_approved_by': staff,
                'submitted_at': now - timedelta(days=2),
                'approved_at': now - timedelta(days=1),
                'published_at': now,
            },
        )
        KnowledgeDocument.objects.filter(pk=knowledge.pk).update(
            draft_revision=knowledge_revision,
            published_revision=knowledge_revision,
        )
        chunk_texts = (
            ('Agent恢复', 'Checkpoint保存图状态；Execution保存业务幂等状态；Redis Stream保存可续传事件。'),
            ('混合检索', 'Qdrant提供语义召回，Meilisearch提供关键词召回，结果通过RRF融合。'),
            ('降级策略', '外部向量或关键词引擎不可用时，返回可解释降级状态，必要时使用SQL有限检索。'),
        )
        for index, chunk_data in enumerate(chunk_texts):
            KnowledgeChunk.objects.update_or_create(
                document=knowledge,
                revision=knowledge_revision,
                chunk_index=index,
                defaults={
                    'chunk_level': 1,
                    'heading_path': [chunk_data[0]],
                    'block_type': 'paragraph',
                    'token_count': len(chunk_data[1]),
                    'content_hash': stable_hash(chunk_data[1]),
                    'semantic_group_id': f'{namespace}-{index}',
                    'content': chunk_data[1],
                    'metadata': {'docs_namespace': namespace, 'title': chunk_data[0]},
                    'embedding_model': 'text-embedding-3-small',
                    'indexed_at': now,
                },
            )

        topic, _ = Topic.objects.update_or_create(
            slug=f'{namespace}-interview-review',
            defaults={
                'name': '项目复盘',
                'description': '分享可验证的项目实现与面试复盘。',
                'target_roles': ['后端工程师', 'AI应用工程师'],
                'is_active': True,
            },
        )
        community_content, _ = CommunityContent.objects.update_or_create(
            title=f'[{namespace}] 我如何复盘一次AI模拟面试',
            defaults={
                'author': candidate,
                'content_type': CommunityContent.ContentType.PROJECT_REVIEW,
                'excerpt': '从产品动作一路追到Agent Checkpoint与RAG降级。',
                'status': CommunityContent.Status.PUBLISHED,
                'target_roles': ['AI应用工程师'],
                'quality_score': 91,
                'risk_level': 'low',
                'published_at': now - timedelta(hours=6),
            },
        )
        body = (
            '我用“页面入口—API—服务—数据—异步—恢复”的顺序复盘iFaceoff。'
            '这样回答不会只罗列技术名词，而能解释每个组件为什么存在。'
        )
        content_revision, _ = ContentRevision.objects.get_or_create(
            content=community_content,
            version=1,
            defaults={
                'title': community_content.title,
                'body': body,
                'body_hash': stable_hash(body),
                'redacted_body': body,
                'risk_findings': [],
                'created_by': candidate,
            },
        )
        CommunityContent.objects.filter(pk=community_content.pk).update(current_revision=content_revision)
        community_content.topics.set([topic])
        CommunityComment.objects.update_or_create(
            content=community_content,
            author=peer,
            legacy_source='docs_demo',
            legacy_id=namespace,
            defaults={'body': '这种复盘顺序很适合回答一致性和故障恢复追问。'},
        )

        conversation, _ = Conversation.objects.get_or_create_conversation(
            candidate,
            peer,
            title='项目复盘交流',
        )
        Message.objects.update_or_create(
            conversation=conversation,
            sender=peer,
            metadata__docs_namespace=namespace,
            defaults={
                'content': '你在面试中怎么解释ResumeVersion和Draft的区别？',
                'delivery_status': Message.DeliveryStatus.READ,
                'is_read': True,
                'metadata': {'docs_namespace': namespace},
            },
        )
        Message.objects.update_or_create(
            conversation=conversation,
            sender=candidate,
            metadata__docs_namespace=f'{namespace}-reply',
            defaults={
                'content': 'Version是不可变事实，Draft是带ETag的可编辑工作区，发布时再生成新Version。',
                'delivery_status': Message.DeliveryStatus.DELIVERED,
                'metadata': {'docs_namespace': f'{namespace}-reply'},
            },
        )
        actor_type = ContentType.objects.get_for_model(User)
        Notification.objects.update_or_create(
            recipient=candidate,
            actor_content_type=actor_type,
            actor_object_id=str(peer.pk),
            verb=f'回复了你的项目复盘 · {namespace}',
            defaults={'is_read': False},
        )

        credential, _ = ProviderCredential.objects.update_or_create(
            name=f'{namespace}-no-secret',
            defaults={
                'provider': 'openai_compatible',
                'scope': ProviderCredential.Scope.PLATFORM,
                'encrypted_secret': '',
                'secret_hint': '未配置',
                'is_active': False,
            },
        )
        deployment, _ = ModelDeployment.objects.update_or_create(
            name=f'{namespace}-local-stub',
            defaults={
                'provider': 'litellm',
                'remote_model': 'docs-deterministic-model',
                'model_type': 'chat',
                'base_url': 'http://127.0.0.1:4000/v1',
                'credential': credential,
                'capabilities': {'json_mode': True, 'streaming': True, 'docs_only': True},
                'context_window': 32000,
                'tokenizer_family': 'cl100k_base',
                'priority': 10,
                'timeout_seconds': 30,
                'is_active': False,
                'last_health_status': 'docs_fixture',
                'last_health_at': now,
            },
        )
        alias, _ = ModelAlias.objects.update_or_create(
            slug=f'{namespace}-interview-chat',
            defaults={
                'name': '文档演示面试模型',
                'model_type': 'chat',
                'description': '无真实凭据、不会被调用的截图配置。',
                'is_active': True,
            },
        )
        policy, _ = RoutePolicy.objects.update_or_create(
            alias=alias,
            defaults={
                'strategy': RoutePolicy.Strategy.PRIORITY,
                'total_timeout_seconds': 45,
                'max_attempts': 2,
                'is_active': True,
            },
        )
        RoutePolicyTarget.objects.update_or_create(
            policy=policy,
            deployment=deployment,
            defaults={'order': 0, 'weight': 100, 'retry_count': 1, 'is_active': False},
        )
        UsageBudget.objects.update_or_create(
            user=candidate,
            defaults={
                'monthly_token_limit': 1_000_000,
                'monthly_cost_limit': 100,
                'period_start': now.date().replace(day=1),
                'used_input_tokens': 42_000,
                'used_output_tokens': 12_000,
                'used_cost': 3.2,
                'is_active': True,
            },
        )
        ledger, _ = ModelRequestLedger.objects.update_or_create(
            task_name=f'docs_demo:{namespace}',
            user=candidate,
            defaults={
                'alias': alias,
                'deployment': deployment,
                'status': ModelRequestLedger.Status.SUCCEEDED,
                'input_tokens': 1840,
                'output_tokens': 420,
                'estimated_cost': 0.0312,
                'latency_ms': 1260,
                'fallback_count': 0,
                'metadata': {'docs_namespace': namespace, 'synthetic': True},
                'completed_at': now,
            },
        )
        PlatformFeatureFlag.objects.update_or_create(
            key=f'{namespace}-agent-v4',
            defaults={
                'name': 'Agent Composite V4',
                'description': '文档演示环境中的Agent V4灰度状态。',
                'enabled': True,
                'rollout_percentage': 100,
                'audience': {'environment': 'documentation'},
                'version': 1,
                'updated_by': staff,
            },
        )
        AdminAuditEvent.objects.update_or_create(
            actor=staff,
            action='docs_demo.seed',
            resource_type='DocumentationNamespace',
            resource_id=namespace,
            defaults={
                'operation_reason': '生成不含真实用户信息的文档截图数据',
                'request_id': f'docs-{namespace}',
                'before_summary': {},
                'after_summary': {'candidate_id': candidate.pk, 'ledger_id': ledger.pk},
                'metadata': {'docs_namespace': namespace, 'synthetic': True},
                'previous_hash': '',
                'event_hash': stable_hash({'namespace': namespace, 'action': 'docs_demo.seed'}),
            },
        )

        return {
            'namespace': namespace,
            'candidate_email': candidate_email,
            'staff_email': staff_email,
            'active_interview_id': active_session.pk,
            'completed_interview_id': completed_session.pk,
            'resume_id': resume.pk,
            'resume_report_id': resume_report.pk,
            'knowledge_document_id': knowledge.pk,
            'community_content_id': community_content.pk,
            'candidate_password_from_environment': True,
            'staff_password_from_environment': True,
            'totp_secret_from_environment': True,
        }
