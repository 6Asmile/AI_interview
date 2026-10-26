from __future__ import annotations

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from careers.models import JobMatchAnalysis, JobTarget
from careers.operation_service import create_job_match_operation
from careers.services import stable_hash
from core.admission import admit_expensive_operation
from core.idempotency import run_idempotent


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
            analysis = JobMatchAnalysis.objects.create(
                user=request.user,
                job_target=job_target,
                resume_version=resume_version,
                job_posting_revision=job_target.job_posting_revision,
                jd_snapshot=jd_text,
                jd_snapshot_hash=job_target.jd_snapshot_hash or stable_hash({'jd_text': jd_text}),
                config_snapshot={'engine': 'ifaceoff-resume-fit/1.0', 'legacy_adapter': scope},
                config_hash=stable_hash({'engine': 'ifaceoff-resume-fit/1.0'}),
            )
            operation = create_job_match_operation(
                analysis=analysis,
                title=f'分析 {job_target.position_name} 岗位匹配度',
                metadata={'legacy_adapter': scope},
            )
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
