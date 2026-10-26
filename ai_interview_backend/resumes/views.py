import os

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .json_resume import legacy_resume_to_json_resume
from .models import Education, ProjectExperience, Resume, ResumeImportJob, ResumeSuggestion, ResumeVersion, Skill, WorkExperience
from .operation_service import create_resume_operation
from .serializers import (
    EducationSerializer,
    ProjectExperienceSerializer,
    ResumeCreateSerializer,
    ResumeDetailSerializer,
    ResumeImportJobSerializer,
    ResumeSuggestionSerializer,
    ResumeVersionCreateSerializer,
    ResumeVersionSerializer,
    SkillSerializer,
    WorkExperienceSerializer,
)
from .tasks import confirm_resume_import
from .versioning import accept_suggestion, create_resume_version, ensure_resume_version
from core.throttles import UploadRateThrottle
from core.uploads import validate_uploaded_file


ALLOWED_RESUME_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.json'}


class ResumeViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_throttles(self):
        if self.action == 'create' and getattr(self.request, 'FILES', None):
            return [UploadRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        return Resume.objects.filter(user=self.request.user).select_related('current_version').prefetch_related('import_jobs').order_by('-updated_at')

    def get_serializer_class(self):
        return ResumeCreateSerializer if self.action == 'create' else ResumeDetailSerializer

    def create(self, request, *args, **kwargs):
        if 'file' not in request.FILES:
            serializer = ResumeCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                resume = Resume.objects.create(
                    user=request.user,
                    title=serializer.validated_data['title'],
                    status=serializer.validated_data.get('status', Resume.Status.DRAFT),
                )
                create_resume_version(
                    resume=resume,
                    resume_json=legacy_resume_to_json_resume(
                        resume,
                        serializer.validated_data.get('content_json'),
                    ),
                    user=request.user,
                    source=ResumeVersion.Source.EDITOR,
                    change_summary='创建简历',
                )
            return Response(ResumeDetailSerializer(resume, context={'request': request}).data, status=status.HTTP_201_CREATED)

        file_obj = request.FILES['file']
        max_bytes = int(getattr(settings, 'RESUME_UPLOAD_MAX_BYTES', 15 * 1024 * 1024))
        validate_uploaded_file(file_obj, allowed_extensions=ALLOWED_RESUME_EXTENSIONS, max_bytes=max_bytes)
        with transaction.atomic():
            resume = Resume.objects.create(
                user=request.user,
                title=request.data.get('title') or os.path.splitext(file_obj.name)[0],
                file=file_obj,
                status=Resume.Status.PROCESSING,
            )
            job = ResumeImportJob.objects.create(resume=resume, user=request.user)
            operation, _ = create_resume_operation(
                user=request.user,
                resume=resume,
                operation_type='resume.import',
                title=f'导入简历：{resume.title}',
                import_job=job,
            )
        data = ResumeDetailSerializer(resume, context={'request': request}).data
        data['import_job'] = ResumeImportJobSerializer(job).data
        data.update({
            'operation_id': str(operation.id),
            'operation_status': 'accepted',
            'events_url': f'/api/v2/operations/{operation.id}/events/',
            'result_url': f'/api/v2/operations/{operation.id}/',
        })
        return Response(data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['get', 'post'], url_path='versions')
    def versions(self, request, pk=None):
        resume = self.get_object()
        if request.method == 'GET':
            ensure_resume_version(resume, request.user)
            return Response(ResumeVersionSerializer(resume.versions.all(), many=True).data)
        serializer = ResumeVersionCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        version = create_resume_version(
            resume=resume,
            resume_json=serializer.validated_data['resume_json'],
            layout_json=serializer.validated_data.get('layout_json'),
            user=request.user,
            source=ResumeVersion.Source.EDITOR,
            change_summary=serializer.validated_data.get('change_summary', '创建新版本'),
            evidence_fact_ids=serializer.validated_data.get('evidence_fact_ids'),
        )
        return Response(ResumeVersionSerializer(version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path=r'versions/(?P<version_id>\d+)/restore')
    def restore_version(self, request, pk=None, version_id=None):
        resume = self.get_object()
        try:
            source = resume.versions.get(pk=version_id)
        except ResumeVersion.DoesNotExist:
            return Response({'detail': '版本不存在。'}, status=status.HTTP_404_NOT_FOUND)
        restored = create_resume_version(
            resume=resume,
            resume_json=source.resume_json,
            layout_json=source.layout_json,
            user=request.user,
            source=ResumeVersion.Source.RESTORE,
            change_summary=f'恢复自 v{source.version_number}',
            parent=resume.current_version,
        )
        return Response(ResumeVersionSerializer(restored).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='fit-score')
    def fit_score(self, request, pk=None):
        resume = self.get_object()
        version = ensure_resume_version(resume, request.user)
        from .legacy import legacy_job_match_response
        return legacy_job_match_response(
            request,
            resume_version=version,
            jd_text=request.data.get('jd_text'),
            scope=f'legacy.resume.fit_score:{resume.pk}',
        )


class ResumeImportJobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ResumeImportJobSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ResumeImportJob.objects.filter(user=self.request.user).select_related('resume')

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        job = self.get_object()
        if job.status not in {ResumeImportJob.Status.FAILED, ResumeImportJob.Status.PENDING}:
            raise ValidationError('只有等待中或失败的任务可以重试。')
        with transaction.atomic():
            job.status = ResumeImportJob.Status.PENDING
            job.error_message = ''
            job.completed_at = None
            job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
            operation, _ = create_resume_operation(
                user=request.user,
                resume=job.resume,
                operation_type='resume.import.retry',
                title=f'重试导入简历：{job.resume.title}',
                import_job=job,
            )
        data = dict(self.get_serializer(job).data)
        data.update({
            'operation_id': str(operation.id),
            'operation_status': 'accepted',
            'events_url': f'/api/v2/operations/{operation.id}/events/',
            'result_url': f'/api/v2/operations/{operation.id}/',
        })
        return Response(data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        job = self.get_object()
        try:
            version = confirm_resume_import(job, request.user, request.data.get('resume_json'))
        except (PermissionError, ValueError) as exc:
            raise ValidationError(str(exc))
        return Response(ResumeVersionSerializer(version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        job = self.get_object()
        if job.status in {ResumeImportJob.Status.CONFIRMED, ResumeImportJob.Status.CANCELED}:
            raise ValidationError('任务已经结束。')
        job.status = ResumeImportJob.Status.CANCELED
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'completed_at', 'updated_at'])
        return Response(self.get_serializer(job).data)


class ResumeSuggestionViewSet(viewsets.ModelViewSet):
    serializer_class = ResumeSuggestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ResumeSuggestion.objects.filter(resume__user=self.request.user).select_related('resume', 'base_version', 'accepted_version')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        version = accept_suggestion(self.get_object(), request.user)
        return Response(ResumeVersionSerializer(version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        suggestion = self.get_object()
        if suggestion.status != ResumeSuggestion.Status.PENDING:
            raise ValidationError('该建议已经处理。')
        suggestion.status = ResumeSuggestion.Status.REJECTED
        suggestion.decided_at = timezone.now()
        suggestion.save(update_fields=['status', 'decided_at'])
        return Response(self.get_serializer(suggestion).data)


class BaseResumeDetailViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        resume_pk = self.kwargs.get('resume_pk')
        return self.queryset.filter(resume__user=self.request.user, resume_id=resume_pk) if resume_pk else self.queryset.none()

    def perform_create(self, serializer):
        resume = Resume.objects.filter(id=self.kwargs.get('resume_pk'), user=self.request.user).first()
        if not resume:
            raise ValidationError('简历不存在。')
        serializer.save(resume=resume)

    def _retired_write(self):
        return Response({
            'code': 'legacy_resume_relation_write_retired',
            'message': '旧关系表写入已冻结，请使用统一 Resume Studio。',
            'migration_url': f'/dashboard/resumes/{self.kwargs.get("resume_pk")}',
        }, status=status.HTTP_410_GONE)

    def create(self, request, *args, **kwargs):
        return self._retired_write()

    def update(self, request, *args, **kwargs):
        return self._retired_write()

    def partial_update(self, request, *args, **kwargs):
        return self._retired_write()

    def destroy(self, request, *args, **kwargs):
        return self._retired_write()


class EducationViewSet(BaseResumeDetailViewSet):
    queryset = Education.objects.all()
    serializer_class = EducationSerializer


class WorkExperienceViewSet(BaseResumeDetailViewSet):
    queryset = WorkExperience.objects.all()
    serializer_class = WorkExperienceSerializer


class ProjectExperienceViewSet(BaseResumeDetailViewSet):
    queryset = ProjectExperience.objects.all()
    serializer_class = ProjectExperienceSerializer


class SkillViewSet(BaseResumeDetailViewSet):
    queryset = Skill.objects.all()
    serializer_class = SkillSerializer
