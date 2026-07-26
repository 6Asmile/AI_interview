from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from careers.models import JobMatchAnalysis, JobTarget
from careers.services import stable_hash
from careers.tasks import run_job_match_analysis
from core.admission import admit_expensive_operation
from core.idempotency import run_idempotent
from core.models import AsyncOperation


def legacy_job_match_response(request, *, resume_version, jd_text: str, job_target=None, scope: str):
    jd_text = str(jd_text or '').strip()
    if not jd_text:
        raise ValidationError({'jd_text': '请提供真实岗位 JD。'})
    admit_expensive_operation(request, scope='job-match')

    def create():
        nonlocal job_target
        with transaction.atomic():
            if not job_target:
                job_target = JobTarget.objects.create(
                    user=request.user,
                    company_name='未指定企业',
                    position_name='兼容接口导入岗位',
                    jd_text=jd_text,
                    source_type=JobTarget.SourceType.MANUAL,
                    jd_snapshot_hash=stable_hash({'jd_text': jd_text}),
                )
            operation = AsyncOperation.objects.create(
                user=request.user,
                operation_type='job_match_analysis',
                source_app='careers',
                source_model='JobTarget',
                source_id=f'{job_target.pk}:{resume_version.pk}:{timezone.now().timestamp()}',
                title=f'分析 {job_target.position_name} 岗位匹配度',
                metadata={'legacy_adapter': scope},
            )
            analysis = JobMatchAnalysis.objects.create(
                user=request.user,
                job_target=job_target,
                resume_version=resume_version,
                job_posting_revision=job_target.job_posting_revision,
                operation=operation,
                jd_snapshot=jd_text,
                jd_snapshot_hash=job_target.jd_snapshot_hash or stable_hash({'jd_text': jd_text}),
                config_snapshot={'engine': 'ifaceoff-resume-fit/1.0', 'legacy_adapter': scope},
                config_hash=stable_hash({'engine': 'ifaceoff-resume-fit/1.0'}),
            )
        try:
            run_job_match_analysis.delay(str(analysis.pk))
        except Exception as exc:
            operation.metadata = {**operation.metadata, 'dispatch_status': 'waiting_for_broker', 'dispatch_error': str(exc)[:500]}
            operation.retryable = True
            operation.save(update_fields=['metadata', 'retryable', 'updated_at'])
        return Response({
            'operation_id': str(operation.pk),
            'status': 'accepted',
            'events_url': f'/api/v2/operations/{operation.pk}/events/',
            'result_url': f'/api/v2/operations/{operation.pk}/',
            'analysis_id': str(analysis.pk),
            'deprecated_endpoint': True,
            'replacement': f'/api/v2/job-targets/{job_target.pk}/match-analyses/',
        }, status=status.HTTP_202_ACCEPTED)

    return run_idempotent(request, scope, create, required=True)
