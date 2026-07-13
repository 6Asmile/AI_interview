import os

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .fit_score import calculate_resume_fit
from .json_resume import legacy_resume_to_json_resume
from .models import Education, ProjectExperience, Resume, ResumeImportJob, ResumeSuggestion, ResumeVersion, Skill, WorkExperience
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
from .tasks import confirm_resume_import, process_resume_import_job
from .versioning import accept_suggestion, create_resume_version, ensure_resume_version


ALLOWED_RESUME_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.json'}


class ResumeViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Resume.objects.filter(user=self.request.user).select_related('current_version').prefetch_related('import_jobs').order_by('-updated_at')

    def get_serializer_class(self):
        return ResumeCreateSerializer if self.action == 'create' else ResumeDetailSerializer

    def create(self, request, *args, **kwargs):
        if 'file' not in request.FILES:
            serializer = ResumeCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                resume = serializer.save(user=request.user)
                create_resume_version(
                    resume=resume,
                    resume_json=legacy_resume_to_json_resume(resume),
                    layout_json=resume.content_json or {},
                    user=request.user,
                    source=ResumeVersion.Source.EDITOR,
                    change_summary='创建简历',
                )
            return Response(ResumeDetailSerializer(resume, context={'request': request}).data, status=status.HTTP_201_CREATED)

        file_obj = request.FILES['file']
        extension = os.path.splitext(file_obj.name)[1].lower()
        if extension not in ALLOWED_RESUME_EXTENSIONS:
            raise ValidationError({'file': f'仅支持 {", ".join(sorted(ALLOWED_RESUME_EXTENSIONS))}。'})
        max_bytes = int(getattr(settings, 'RESUME_UPLOAD_MAX_BYTES', 15 * 1024 * 1024))
        if file_obj.size > max_bytes:
            raise ValidationError({'file': f'文件不能超过 {max_bytes // 1024 // 1024}MB。'})
        with transaction.atomic():
            resume = Resume.objects.create(
                user=request.user,
                title=request.data.get('title') or os.path.splitext(file_obj.name)[0],
                file=file_obj,
                status=Resume.Status.PROCESSING,
            )
            job = ResumeImportJob.objects.create(resume=resume, user=request.user)
        try:
            process_resume_import_job.delay(job.id)
        except Exception as exc:
            job.error_message = f'任务队列暂不可用，可稍后重试：{str(exc)[:500]}'
            job.save(update_fields=['error_message', 'updated_at'])
        data = ResumeDetailSerializer(resume, context={'request': request}).data
        data['import_job'] = ResumeImportJobSerializer(job).data
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
        resume.content_json = source.layout_json or resume.content_json
        resume.save(update_fields=['content_json', 'updated_at'])
        return Response(ResumeVersionSerializer(restored).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='fit-score')
    def fit_score(self, request, pk=None):
        jd_text = str(request.data.get('jd_text') or '').strip()
        if not jd_text:
            raise ValidationError({'jd_text': '请提供真实岗位 JD。'})
        resume = self.get_object()
        version = ensure_resume_version(resume, request.user)
        return Response(calculate_resume_fit(version.resume_json, jd_text, version.evidence_snapshot))


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
        job.status = ResumeImportJob.Status.PENDING
        job.error_message = ''
        job.save(update_fields=['status', 'error_message', 'updated_at'])
        try:
            process_resume_import_job.delay(job.id)
        except Exception as exc:
            job.error_message = f'任务队列暂不可用：{str(exc)[:500]}'
            job.save(update_fields=['error_message', 'updated_at'])
        return Response(self.get_serializer(job).data, status=status.HTTP_202_ACCEPTED)

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
