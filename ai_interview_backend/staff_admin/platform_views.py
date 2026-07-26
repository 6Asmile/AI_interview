from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.response import Response

from careers.models import Company, CompanyVerification, JobPosting, SkillTaxonomy
from community.models import CommunityContent, ModerationCase, ModerationDecision, ReputationLedger
from core.models import ConsumerInbox, IntegrationOutbox, RuntimePolicy
from core.events import enqueue_integration_event
from resumes.models import ResumeArtifact
from resumes.rendering import RENDERER_NAME, RENDERER_VERSION
from resumes.schema import JSON_RESUME_SCHEMA_VERSION, schema_snapshot_hash
from resumes.templates import RESUME_TEMPLATES, template_catalog

from .idempotency import run_staff_idempotent
from .operations_views import operation_reason
from .views import StaffProtectedView, audit


class CareerConfigAdminView(StaffProtectedView):
    required_permissions = ['career_config.manage']

    def get(self, request):
        return Response({
            'skills': list(SkillTaxonomy.objects.values(
                'id', 'slug', 'name', 'category', 'aliases', 'description', 'is_active', 'updated_at',
            )),
            'policies': list(RuntimePolicy.objects.filter(
                key__startswith='career-',
            ).values('id', 'key', 'name', 'description', 'config', 'version', 'enabled', 'updated_at')),
        })

    def post(self, request):
        reason, error = operation_reason(request)
        if error:
            return error

        def apply():
            resource = str(request.data.get('resource') or '')
            if resource == 'skill':
                existing = SkillTaxonomy.objects.filter(slug=request.data['slug']).first()
                before = {
                    'name': existing.name, 'category': existing.category,
                    'aliases': existing.aliases, 'is_active': existing.is_active,
                } if existing else {}
                row, _ = SkillTaxonomy.objects.update_or_create(
                    slug=request.data['slug'],
                    defaults={
                        'name': request.data['name'],
                        'category': request.data.get('category', ''),
                        'aliases': request.data.get('aliases') or [],
                        'description': request.data.get('description', ''),
                        'is_active': bool(request.data.get('is_active', True)),
                    },
                )
                audit(
                    request, action='career_config.skill.update', resource_type='SkillTaxonomy',
                    resource_id=row.pk, reason=reason, before=before,
                    after={
                        'name': row.name, 'category': row.category,
                        'aliases': row.aliases, 'is_active': row.is_active,
                    },
                )
            elif resource == 'policy':
                row, created = RuntimePolicy.objects.get_or_create(
                    key=request.data['key'],
                    defaults={'name': request.data['name']},
                )
                before = {'version': row.version, 'config': row.config}
                row.name = request.data.get('name', row.name)
                row.description = request.data.get('description', row.description)
                row.config = request.data.get('config') or {}
                row.enabled = bool(request.data.get('enabled', True))
                row.version = row.version if created else row.version + 1
                row.updated_by_staff_id = request.user.pk
                row.save()
                audit(
                    request, action='career_config.update', resource_type='RuntimePolicy',
                    resource_id=row.pk, reason=reason, before=before,
                    after={'version': row.version, 'config': row.config},
                )
            else:
                return Response({'code': 'invalid_resource'}, status=400)
            return Response({'id': row.pk, 'resource': resource})

        return run_staff_idempotent(request, 'career-config', apply)


class ResumeConfigAdminView(StaffProtectedView):
    required_permissions = ['resume_config.manage']

    def get(self, request):
        policy = RuntimePolicy.objects.filter(key='resume-config').first()
        artifact_counts = dict(
            ResumeArtifact.objects.values('status').annotate(total=Count('id')).values_list('status', 'total')
        )
        return Response({
            'schema': {
                'version': JSON_RESUME_SCHEMA_VERSION,
                'snapshot_hash': schema_snapshot_hash(),
            },
            'renderer': {
                'name': RENDERER_NAME,
                'version': RENDERER_VERSION,
                'queue': 'resume.render',
                'network_access': False,
                'artifact_status': artifact_counts,
            },
            'templates': template_catalog(enabled_only=False),
            'policy': {
                'id': policy.pk if policy else None,
                'version': policy.version if policy else 0,
                'enabled': policy.enabled if policy else True,
                'config': policy.config if policy else {
                    'enabled_templates': list(RESUME_TEMPLATES),
                    'renderer_version': RENDERER_VERSION,
                    'ats_rules_version': '1.0.0',
                    'render_timeout_seconds': 20,
                    'max_input_bytes': 2_000_000,
                },
            },
            'privacy_contract': '管理员只能管理母版、规则和任务健康，不能读取用户简历正文。',
        })

    def post(self, request):
        reason, error = operation_reason(request)
        if error:
            return error

        def apply():
            config = request.data.get('config') or {}
            enabled_templates = config.get('enabled_templates', list(RESUME_TEMPLATES))
            if (
                not isinstance(enabled_templates, list)
                or not enabled_templates
                or any(key not in RESUME_TEMPLATES for key in enabled_templates)
            ):
                return Response({'code': 'invalid_resume_templates'}, status=400)
            if config.get('renderer_version', RENDERER_VERSION) != RENDERER_VERSION:
                return Response({
                    'code': 'renderer_version_not_deployed',
                    'deployed_version': RENDERER_VERSION,
                }, status=409)
            allowed = {
                'enabled_templates', 'renderer_version', 'ats_rules_version',
                'render_timeout_seconds', 'max_input_bytes',
            }
            if set(config) - allowed:
                return Response({'code': 'unsupported_resume_config_key'}, status=400)
            timeout_seconds = config.get('render_timeout_seconds', 20)
            max_input_bytes = config.get('max_input_bytes', 2_000_000)
            ats_rules_version = str(config.get('ats_rules_version', '1.0.0')).strip()
            if not isinstance(timeout_seconds, int) or not 5 <= timeout_seconds <= 60:
                return Response({'code': 'invalid_render_timeout'}, status=400)
            if not isinstance(max_input_bytes, int) or not 100_000 <= max_input_bytes <= 2_000_000:
                return Response({'code': 'invalid_resume_input_limit'}, status=400)
            if not ats_rules_version or len(ats_rules_version) > 40:
                return Response({'code': 'invalid_ats_rules_version'}, status=400)
            row, created = RuntimePolicy.objects.get_or_create(
                key='resume-config',
                defaults={'name': '简历配置', 'description': '简历母版、渲染器与 ATS 规则。'},
            )
            before = {'version': row.version, 'config': row.config, 'enabled': row.enabled}
            row.config = config
            row.enabled = bool(request.data.get('enabled', True))
            row.version = row.version if created else row.version + 1
            row.updated_by_staff_id = request.user.pk
            row.save()
            audit(
                request,
                action='resume_config.update',
                resource_type='RuntimePolicy',
                resource_id=row.pk,
                reason=reason,
                before=before,
                after={'version': row.version, 'config': row.config, 'enabled': row.enabled},
            )
            return Response({'id': row.pk, 'key': row.key, 'version': row.version})

        return run_staff_idempotent(request, 'resume-config', apply)


class CompanyReviewAdminView(StaffProtectedView):
    required_permissions = ['company.verify']

    def get(self, request):
        return Response(list(Company.objects.order_by('-created_at').values(
            'id', 'name', 'slug', 'industry', 'status', 'created_by_id', 'verified_at', 'created_at',
        )[:500]))

    def post(self, request, company_id, decision):
        reason, error = operation_reason(request)
        if error:
            return error

        def apply():
            company = Company.objects.get(pk=company_id)
            before = {'status': company.status}
            if decision == 'approve':
                company.status = Company.Status.VERIFIED
                company.verified_at = timezone.now()
            elif decision == 'reject':
                company.status = Company.Status.REJECTED
                company.verified_at = None
            elif decision == 'suspend':
                company.status = Company.Status.SUSPENDED
            else:
                return Response({'code': 'invalid_decision'}, status=400)
            company.save(update_fields=['status', 'verified_at', 'updated_at'])
            verification = company.verifications.filter(
                status=CompanyVerification.Status.SUBMITTED,
            ).order_by('-submitted_at', '-created_at').first()
            if verification and decision in {'approve', 'reject'}:
                verification.status = (
                    CompanyVerification.Status.APPROVED
                    if decision == 'approve'
                    else CompanyVerification.Status.REJECTED
                )
                verification.reviewed_by_staff_id = request.user.pk
                verification.review_reason = reason
                verification.reviewed_at = timezone.now()
                verification.save(update_fields=[
                    'status', 'reviewed_by_staff_id', 'review_reason', 'reviewed_at',
                ])
            audit(
                request, action=f'company.{decision}', resource_type='Company',
                resource_id=company.pk, reason=reason, before=before,
                after={'status': company.status},
            )
            return Response({'id': str(company.pk), 'status': company.status})

        return run_staff_idempotent(request, f'company.{company_id}.{decision}', apply)


class JobReviewAdminView(StaffProtectedView):
    required_permissions = ['job.review']

    def get(self, request):
        return Response(list(JobPosting.objects.select_related('company', 'current_revision').order_by(
            '-created_at',
        ).values(
            'id', 'company_id', 'company__name', 'title', 'status',
            'current_revision_id', 'published_at', 'created_at',
        )[:500]))

    def post(self, request, job_id, decision):
        reason, error = operation_reason(request)
        if error:
            return error

        def apply():
            posting = JobPosting.objects.select_related('current_revision').get(pk=job_id)
            before = {'status': posting.status, 'revision_id': str(posting.current_revision_id or '')}
            if decision == 'approve':
                if not posting.current_revision:
                    return Response({'code': 'revision_required'}, status=409)
                posting.status = JobPosting.Status.PUBLISHED
                posting.published_at = timezone.now()
                posting.current_revision.approved_at = timezone.now()
                posting.current_revision.approved_by_staff_id = request.user.pk
                posting.current_revision.save(update_fields=['approved_at', 'approved_by_staff_id'])
            elif decision == 'reject':
                posting.status = JobPosting.Status.REJECTED
                posting.published_at = None
            elif decision == 'close':
                posting.status = JobPosting.Status.CLOSED
            else:
                return Response({'code': 'invalid_decision'}, status=400)
            posting.save(update_fields=['status', 'published_at', 'updated_at'])
            audit(
                request, action=f'job.{decision}', resource_type='JobPosting',
                resource_id=posting.pk, reason=reason, before=before,
                after={'status': posting.status, 'revision_id': str(posting.current_revision_id or '')},
            )
            return Response({'id': str(posting.pk), 'status': posting.status})

        return run_staff_idempotent(request, f'job.{job_id}.{decision}', apply)


class CommunityModerationAdminView(StaffProtectedView):
    required_permissions = ['community.moderate']

    def get(self, request):
        rows = ModerationCase.objects.select_related('content', 'revision').order_by('-created_at')
        if request.query_params.get('status'):
            rows = rows.filter(status=request.query_params['status'])
        return Response([{
            'id': str(row.pk), 'content_id': str(row.content_id), 'title': row.content.title,
            'content_type': row.content.content_type, 'anonymous': row.content.is_anonymous,
            'risk_level': row.risk_level, 'findings': row.findings, 'status': row.status,
            'preview': row.revision.redacted_body[:1000], 'created_at': row.created_at,
        } for row in rows[:500]])

    def post(self, request, case_id, decision):
        reason, error = operation_reason(request)
        if error:
            return error

        def apply():
            with transaction.atomic():
                case = ModerationCase.objects.select_for_update().select_related('content').get(pk=case_id)
                before = {'case_status': case.status, 'content_status': case.content.status}
                if decision == 'approve':
                    case.content.status = CommunityContent.Status.PUBLISHED
                    case.content.published_at = timezone.now()
                elif decision == 'reject':
                    case.content.status = CommunityContent.Status.REJECTED
                    case.content.published_at = None
                elif decision == 'hide':
                    case.content.status = CommunityContent.Status.HIDDEN
                    case.content.published_at = None
                else:
                    return Response({'code': 'invalid_decision'}, status=400)
                case.content.save(update_fields=['status', 'published_at', 'updated_at'])
                if decision == 'approve':
                    enqueue_integration_event(
                        event_type='community.content.published',
                        producer='community',
                        aggregate_type='CommunityContent',
                        aggregate_id=case.content.pk,
                        actor_id=case.content.author_id,
                        payload={
                            'content_id': str(case.content.pk),
                            'content_type': case.content.content_type,
                        },
                    )
                case.status = 'closed'
                case.closed_at = timezone.now()
                case.save(update_fields=['status', 'closed_at'])
                ModerationDecision.objects.create(
                    case=case,
                    decision=decision,
                    reason=reason,
                    decided_by_staff_id=request.user.pk,
                    before_snapshot=before,
                    after_snapshot={'case_status': case.status, 'content_status': case.content.status},
                )
                if decision in {'reject', 'hide'}:
                    ReputationLedger.objects.get_or_create(
                        dedup_key=f'moderation.{decision}:{case.pk}',
                        defaults={
                            'user': case.content.author,
                            'event_type': f'moderation.{decision}',
                            'points': -10,
                            'source_type': 'ModerationCase',
                            'source_id': str(case.pk),
                            'metadata': {'reason': reason},
                        },
                    )
                audit(
                    request, action=f'community.{decision}', resource_type='ModerationCase',
                    resource_id=case.pk, reason=reason, before=before,
                    after={'case_status': case.status, 'content_status': case.content.status},
                )
            return Response({'id': str(case.pk), 'status': case.status, 'content_status': case.content.status})

        return run_staff_idempotent(request, f'community.case.{case_id}.{decision}', apply)


class PlatformEventsAdminView(StaffProtectedView):
    required_permissions = ['platform_events.view']

    def get(self, request):
        outbox_status = dict(IntegrationOutbox.objects.values('status').annotate(total=Count('id')).values_list('status', 'total'))
        inbox_status = dict(ConsumerInbox.objects.values('status').annotate(total=Count('id')).values_list('status', 'total'))
        oldest = IntegrationOutbox.objects.filter(
            status__in=[IntegrationOutbox.Status.PENDING, IntegrationOutbox.Status.FAILED],
        ).order_by('available_at').first()
        return Response({
            'outbox': outbox_status,
            'inbox': inbox_status,
            'oldest_pending_at': oldest.available_at if oldest else None,
            'dead_letters': list(IntegrationOutbox.objects.filter(
                status=IntegrationOutbox.Status.DEAD,
            ).values('id', 'event_id', 'event_type', 'attempts', 'last_error', 'created_at')[:200]),
        })

    def post(self, request, event_id):
        if not ({'platform_events.replay', '*'} & request.user.permission_set()):
            return Response({'code': 'permission_denied'}, status=403)
        reason, error = operation_reason(request)
        if error:
            return error

        def apply():
            event = IntegrationOutbox.objects.get(event_id=event_id)
            before = {'status': event.status, 'attempts': event.attempts}
            event.status = IntegrationOutbox.Status.PENDING
            event.available_at = timezone.now()
            event.locked_at = None
            event.last_error = ''
            event.save(update_fields=['status', 'available_at', 'locked_at', 'last_error', 'updated_at'])
            audit(
                request, action='platform_event.replay', resource_type='IntegrationOutbox',
                resource_id=event.event_id, reason=reason, before=before,
                after={'status': event.status, 'attempts': event.attempts},
            )
            return Response({'event_id': str(event.event_id), 'status': event.status})

        return run_staff_idempotent(request, f'platform-event.{event_id}.replay', apply)


class ReliabilityAdminView(StaffProtectedView):
    required_permissions = ['reliability.manage']

    def get(self, request):
        return Response({
            'policies': list(RuntimePolicy.objects.filter(
                key__startswith='reliability-',
            ).values('id', 'key', 'name', 'config', 'version', 'enabled', 'updated_at')),
            'degradation_contract': {
                'cache_redis': 'bypass_cache',
                'coordination_redis': 'fail_closed_for_sensitive_and_expensive_work',
                'realtime_redis': 'postgres_snapshot_and_polling',
                'rabbitmq': 'retain_outbox',
                'postgresql': 'stop_business_writes',
            },
        })

    def post(self, request):
        reason, error = operation_reason(request)
        if error:
            return error

        def apply():
            key = str(request.data.get('key') or '')
            if not key.startswith('reliability-'):
                return Response({'code': 'invalid_policy_key'}, status=400)
            row, created = RuntimePolicy.objects.get_or_create(key=key, defaults={'name': request.data.get('name', key)})
            before = {'version': row.version, 'config': row.config}
            row.name = request.data.get('name', row.name)
            row.config = request.data.get('config') or {}
            row.enabled = bool(request.data.get('enabled', True))
            row.version = row.version if created else row.version + 1
            row.updated_by_staff_id = request.user.pk
            row.save()
            audit(
                request, action='reliability.policy.update', resource_type='RuntimePolicy',
                resource_id=row.pk, reason=reason, before=before,
                after={'version': row.version, 'config': row.config},
            )
            return Response({'id': row.pk, 'key': row.key, 'version': row.version})

        return run_staff_idempotent(request, 'reliability-policy', apply)
