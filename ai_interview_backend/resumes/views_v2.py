from __future__ import annotations

import hashlib
import io
import os
import warnings
from copy import deepcopy

from django.conf import settings
from django.core.files.base import ContentFile
from django.http import FileResponse
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from PIL import Image, ImageOps, UnidentifiedImageError

from core.admission import admit_expensive_operation
from core.idempotency import run_idempotent
from core.models import AsyncOperation
from core.throttles import UploadRateThrottle
from core.uploads import validate_uploaded_file

from .json_resume import legacy_resume_to_json_resume
from .models import (
    Resume, ResumeArtifact, ResumeAsset, ResumeImportJob, ResumeQualityReport,
    ResumeShareAccess, ResumeShareLink, ResumeSuggestion, ResumeVersion,
)
from .rendering import RENDERER_NAME, RENDERER_VERSION, artifact_cache_key
from .schema import sha256_json, strip_internal_metadata, validate_resume
from .serializers_v2 import (
    DraftPatchSerializer, ResumeArtifactSerializer, ResumeDraftSerializer,
    ResumeImportJobV2Serializer, ResumeQualityReportSerializer, ResumeShareLinkSerializer,
    ResumeSuggestionV2Serializer, ResumeV2Serializer, ResumeVersionV2Serializer,
    VersionCommitSerializer,
)
from .sharing import create_share_link, redact_shared_resume, resolve_share, shared_render_snapshot
from .studio import commit_draft, ensure_studio, update_draft
from .tasks import (
    confirm_resume_import, generate_resume_suggestion_task, process_resume_import_job,
    render_resume_artifact, review_resume_quality,
)
from .templates import default_design, design_hash, template_catalog
from .versioning import accept_suggestion, create_resume_version


ALLOWED_RESUME_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.json'}


def operation_response(operation, *, http_status=status.HTTP_202_ACCEPTED, extra=None):
    data = {
        'operation_id': str(operation.id),
        'status': 'accepted',
        'events_url': f'/api/v2/operations/{operation.id}/events/',
        'result_url': f'/api/v2/operations/{operation.id}/',
    }
    data.update(extra or {})
    return Response(data, status=http_status)


def _create_operation(*, user, operation_type, source_model, source_id, title, metadata=None):
    return AsyncOperation.objects.create(
        user=user,
        operation_type=operation_type,
        source_app='resumes',
        source_model=source_model,
        source_id=str(source_id),
        title=title,
        metadata=metadata or {},
    )


def _dispatch(task, args, operation):
    try:
        task.delay(*args, str(operation.id))
    except Exception as exc:
        operation.metadata = {
            **(operation.metadata or {}),
            'dispatch_status': 'waiting_for_broker',
            'dispatch_error': str(exc)[:500],
        }
        operation.retryable = True
        operation.save(update_fields=['metadata', 'retryable', 'updated_at'])


def _json_diff(before, after, path=''):
    changes = []
    if type(before) is not type(after):
        return [{'op': 'replace', 'path': path or '/', 'before': before, 'after': after}]
    if isinstance(before, dict):
        for key in sorted(before.keys() - after.keys()):
            changes.append({'op': 'remove', 'path': f'{path}/{key}', 'before': before[key]})
        for key in sorted(after.keys() - before.keys()):
            changes.append({'op': 'add', 'path': f'{path}/{key}', 'after': after[key]})
        for key in sorted(before.keys() & after.keys()):
            changes.extend(_json_diff(before[key], after[key], f'{path}/{key}'))
    elif isinstance(before, list):
        before_ids = {
            item.get('x-ifaceoff', {}).get('id'): item
            for item in before if isinstance(item, dict) and item.get('x-ifaceoff', {}).get('id')
        }
        after_ids = {
            item.get('x-ifaceoff', {}).get('id'): item
            for item in after if isinstance(item, dict) and item.get('x-ifaceoff', {}).get('id')
        }
        if before_ids and after_ids:
            for item_id in before_ids.keys() - after_ids.keys():
                changes.append({'op': 'remove', 'path': f'{path}/@{item_id}', 'before': before_ids[item_id]})
            for item_id in after_ids.keys() - before_ids.keys():
                changes.append({'op': 'add', 'path': f'{path}/@{item_id}', 'after': after_ids[item_id]})
            for item_id in before_ids.keys() & after_ids.keys():
                changes.extend(_json_diff(before_ids[item_id], after_ids[item_id], f'{path}/@{item_id}'))
            before_order = list(before_ids)
            after_order = list(after_ids)
            if before_order != after_order:
                changes.append({'op': 'reorder', 'path': path or '/', 'before': before_order, 'after': after_order})
        elif before != after:
            changes.append({'op': 'replace', 'path': path or '/', 'before': before, 'after': after})
    elif before != after:
        changes.append({'op': 'replace', 'path': path or '/', 'before': before, 'after': after})
    return changes


class ResumeV2ViewSet(viewsets.ModelViewSet):
    serializer_class = ResumeV2Serializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Resume.objects.filter(user=self.request.user).select_related(
            'current_version', 'current_design_revision', 'draft',
        ).prefetch_related('current_version__evidence_links').order_by('-updated_at')

    def perform_create(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get('is_default'):
                Resume.objects.filter(user=self.request.user, is_default=True).update(is_default=False)
            resume = serializer.save(user=self.request.user)
            version = create_resume_version(
                resume=resume,
                resume_json=validate_resume({}),
                user=self.request.user,
                source=ResumeVersion.Source.EDITOR,
                change_summary='创建简历',
            )
            ensure_studio(resume, self.request.user)
            resume.refresh_from_db()

    def perform_update(self, serializer):
        instance = serializer.instance
        with transaction.atomic():
            if serializer.validated_data.get('is_default'):
                Resume.objects.filter(user=self.request.user, is_default=True).exclude(pk=instance.pk).update(is_default=False)
            resume = serializer.save()

    @action(detail=True, methods=['get', 'post', 'delete'], url_path='avatar')
    def avatar(self, request, pk=None):
        resume = self.get_object()
        active = next((
            asset
            for asset in resume.assets.filter(kind=ResumeAsset.Kind.AVATAR).order_by('-created_at')
            if not (asset.metadata or {}).get('revoked_at')
        ), None)
        if request.method == 'GET':
            if not active:
                return Response({'avatar': None})
            return Response({
                'avatar': {
                    'id': active.id,
                    'url': request.build_absolute_uri(active.file.url),
                    'checksum_sha256': active.checksum_sha256,
                    'created_at': active.created_at,
                },
            })

        draft, _ = ensure_studio(resume, request.user)
        if request.method == 'DELETE':
            content = deepcopy(draft.resume_json)
            basics = content.get('basics') if isinstance(content.get('basics'), dict) else {}
            basics.pop('image', None)
            content['basics'] = basics
            updated = update_draft(
                resume=resume,
                user=request.user,
                if_match=request.headers.get('If-Match', ''),
                resume_json=content,
            )
            if active:
                active.metadata = {**(active.metadata or {}), 'revoked_at': timezone.now().isoformat()}
                active.save(update_fields=['metadata'])
            response = Response({'avatar': None, 'etag': updated.etag})
            response['ETag'] = f'"{updated.etag}"'
            return response

        file_obj = request.FILES.get('file')
        if not file_obj:
            raise ValidationError({'file': '请选择 JPG、PNG 或 WebP 头像。'})
        validate_uploaded_file(
            file_obj,
            allowed_extensions={'.jpg', '.jpeg', '.png', '.webp'},
            max_bytes=3 * 1024 * 1024,
        )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                source = Image.open(file_obj)
                source.verify()
                file_obj.seek(0)
                source = Image.open(file_obj)
                source = ImageOps.exif_transpose(source)
                if source.width > 4096 or source.height > 4096 or source.width * source.height > 16_000_000:
                    raise ValidationError({'file': '头像像素尺寸过大。'})
                source.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                source = source.convert('RGBA' if 'A' in source.getbands() else 'RGB')
                output = io.BytesIO()
                source.save(output, format='PNG', optimize=True)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValidationError({'file': '头像文件损坏或包含不安全的图像数据。'}) from exc
        content_bytes = output.getvalue()
        checksum = hashlib.sha256(content_bytes).hexdigest()
        with transaction.atomic():
            asset = ResumeAsset(
                resume=resume,
                kind=ResumeAsset.Kind.AVATAR,
                original_name=os.path.basename(file_obj.name),
                mime_type='image/png',
                size_bytes=len(content_bytes),
                checksum_sha256=checksum,
                metadata={'normalized': True, 'width': source.width, 'height': source.height},
            )
            asset.file.save(f'avatar-{resume.id}-{checksum[:12]}.png', ContentFile(content_bytes), save=False)
            asset.save()
            content = deepcopy(draft.resume_json)
            basics = content.get('basics') if isinstance(content.get('basics'), dict) else {}
            basics['image'] = f'asset:{asset.id}'
            content['basics'] = basics
            updated = update_draft(
                resume=resume,
                user=request.user,
                if_match=request.headers.get('If-Match', ''),
                resume_json=content,
            )
            if active:
                active.metadata = {**(active.metadata or {}), 'revoked_at': timezone.now().isoformat()}
                active.save(update_fields=['metadata'])
        response = Response({
            'avatar': {
                'id': asset.id,
                'url': request.build_absolute_uri(asset.file.url),
                'checksum_sha256': asset.checksum_sha256,
                'created_at': asset.created_at,
            },
            'etag': updated.etag,
        }, status=status.HTTP_201_CREATED)
        response['ETag'] = f'"{updated.etag}"'
        return response

    @action(detail=True, methods=['get', 'patch'], url_path='draft')
    def draft(self, request, pk=None):
        resume = self.get_object()
        draft, _ = ensure_studio(resume, request.user)
        if request.method == 'GET':
            response = Response(ResumeDraftSerializer(draft).data)
            response['ETag'] = f'"{draft.etag}"'
            return response
        serializer = DraftPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = update_draft(
            resume=resume,
            user=request.user,
            if_match=request.headers.get('If-Match', ''),
            **serializer.validated_data,
        )
        response = Response(ResumeDraftSerializer(draft).data)
        response['ETag'] = f'"{draft.etag}"'
        return response

    @action(detail=True, methods=['get', 'post'], url_path='versions')
    def versions(self, request, pk=None):
        resume = self.get_object()
        draft, _ = ensure_studio(resume, request.user)
        if request.method == 'GET':
            versions = resume.versions.prefetch_related('evidence_links').all()
            return Response(ResumeVersionV2Serializer(versions, many=True).data)
        serializer = VersionCommitSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        version, design, updated_draft = commit_draft(
            resume=resume,
            user=request.user,
            if_match=request.headers.get('If-Match', ''),
            change_summary=serializer.validated_data['change_summary'],
            source=ResumeVersion.Source.EDITOR,
            evidence_links=serializer.validated_data['evidence_links'],
        )
        response = Response(ResumeVersionV2Serializer(version).data, status=status.HTTP_201_CREATED)
        response['ETag'] = f'"{updated_draft.etag}"'
        return response

    @action(detail=True, methods=['get'], url_path=r'versions/(?P<version_id>\d+)/diff')
    def version_diff(self, request, pk=None, version_id=None):
        resume = self.get_object()
        version = resume.versions.filter(pk=version_id).first()
        if not version:
            raise NotFound('版本不存在。')
        against_id = request.query_params.get('against')
        against = resume.versions.filter(pk=against_id).first() if against_id else version.parent
        if not against:
            return Response({'from_version': None, 'to_version': version.id, 'changes': []})
        return Response({
            'from_version': against.id,
            'to_version': version.id,
            'changes': _json_diff(against.resume_json, version.resume_json),
        })

    @action(detail=True, methods=['post'], url_path='preview')
    def preview(self, request, pk=None):
        resume = self.get_object()

        def execute():
            admit_expensive_operation(request, scope='resume.preview')
            draft, _ = ensure_studio(resume, request.user)
            key = sha256_json({
                'resume_id': resume.id,
                'etag': draft.etag, 'format': ResumeArtifact.Format.PREVIEW,
                'renderer': RENDERER_VERSION,
            })
            artifact, _ = ResumeArtifact.objects.get_or_create(
                cache_key=key,
                defaults={
                    'resume': resume,
                    'draft_etag': draft.etag,
                    'preview_input': draft.resume_json,
                    'preview_design': draft.design_json,
                    'format': ResumeArtifact.Format.PREVIEW,
                    'renderer_name': RENDERER_NAME,
                    'renderer_version': RENDERER_VERSION,
                },
            )
            operation, created = AsyncOperation.objects.get_or_create(
                user=request.user,
                source_app='resumes',
                source_model='ResumeArtifact',
                source_id=str(artifact.id),
                defaults={'operation_type': 'resume.preview', 'title': f'生成预览：{resume.title}'},
            )
            if artifact.status == ResumeArtifact.Status.READY:
                operation.status = AsyncOperation.Status.SUCCEEDED
                operation.progress = 100
                operation.metadata = {'artifact_id': str(artifact.id), 'reused': True}
                operation.completed_at = timezone.now()
                operation.save()
            elif created:
                _dispatch(render_resume_artifact, [str(artifact.id)], operation)
            return operation_response(operation, extra={'artifact_id': str(artifact.id), 'etag': draft.etag})

        return run_idempotent(request, f'resume.preview:{resume.id}', execute, required=True)

    @action(detail=True, methods=['get', 'post'], url_path='exports')
    def exports(self, request, pk=None):
        resume = self.get_object()
        if request.method == 'GET':
            artifacts = resume.artifacts.exclude(format=ResumeArtifact.Format.PREVIEW).select_related(
                'asset', 'content_version', 'design_revision',
            )
            return Response(ResumeArtifactSerializer(artifacts, many=True, context={'request': request}).data)

        def execute():
            admit_expensive_operation(request, scope='resume.export')
            output_format = str(request.data.get('format') or '').lower()
            if output_format not in {
                ResumeArtifact.Format.PDF, ResumeArtifact.Format.DOCX, ResumeArtifact.Format.JSON,
            }:
                raise ValidationError({'format': '仅支持 pdf、docx、json。'})
            _, design = ensure_studio(resume, request.user)
            version_id = request.data.get('version_id')
            version = resume.versions.filter(pk=version_id).first() if version_id else resume.current_version
            if not version:
                raise ValidationError({'version_id': '简历版本不存在。'})
            key = artifact_cache_key(
                version.content_hash,
                design.design_hash,
                output_format,
                namespace=f'resume:{resume.pk}:owner',
            )
            artifact, _ = ResumeArtifact.objects.get_or_create(
                cache_key=key,
                defaults={
                    'resume': resume, 'content_version': version, 'design_revision': design,
                    'format': output_format, 'renderer_name': RENDERER_NAME,
                    'renderer_version': RENDERER_VERSION,
                },
            )
            operation, created = AsyncOperation.objects.get_or_create(
                user=request.user,
                source_app='resumes',
                source_model='ResumeArtifact',
                source_id=str(artifact.id),
                defaults={'operation_type': 'resume.export', 'title': f'导出简历：{resume.title}'},
            )
            if artifact.status == ResumeArtifact.Status.READY:
                operation.status = AsyncOperation.Status.SUCCEEDED
                operation.progress = 100
                operation.metadata = {'artifact_id': str(artifact.id), 'reused': True}
                operation.completed_at = timezone.now()
                operation.save()
            elif created:
                _dispatch(render_resume_artifact, [str(artifact.id)], operation)
            return operation_response(operation, extra={'artifact_id': str(artifact.id)})

        return run_idempotent(request, f'resume.export:{resume.id}', execute, required=True)

    @action(detail=True, methods=['get', 'post'], url_path='quality-reports')
    def quality_reports(self, request, pk=None):
        resume = self.get_object()
        if request.method == 'GET':
            reports = resume.quality_reports.select_related('content_version')
            return Response(ResumeQualityReportSerializer(reports, many=True).data)

        def execute():
            admit_expensive_operation(request, scope='resume.quality')
            version_id = request.data.get('version_id')
            version = resume.versions.filter(pk=version_id).first() if version_id else resume.current_version
            if not version:
                raise ValidationError({'version_id': '简历版本不存在。'})
            config_hash = sha256_json({'rules': 'resume-quality-1.0.0', 'content_hash': version.content_hash})
            report = ResumeQualityReport.objects.filter(
                resume=resume,
                content_version=version,
                config_hash=config_hash,
                status=ResumeQualityReport.Status.COMPLETED,
            ).first()
            if not report:
                report = ResumeQualityReport.objects.create(
                    resume=resume,
                    content_version=version,
                    config_hash=config_hash,
                )
            operation, created = AsyncOperation.objects.get_or_create(
                user=request.user,
                source_app='resumes',
                source_model='ResumeQualityReport',
                source_id=str(report.id),
                defaults={'operation_type': 'resume.quality_review', 'title': f'评审简历：{resume.title}'},
            )
            if report.status == ResumeQualityReport.Status.COMPLETED:
                operation.status = AsyncOperation.Status.SUCCEEDED
                operation.progress = 100
                operation.metadata = {'quality_report_id': report.id, 'reused': True}
                operation.completed_at = timezone.now()
                operation.save()
            elif created:
                _dispatch(review_resume_quality, [report.id], operation)
            return operation_response(operation, extra={'quality_report_id': report.id})

        return run_idempotent(request, f'resume.quality:{resume.id}', execute, required=True)

    @action(detail=True, methods=['get', 'post'], url_path='suggestions')
    def suggestions(self, request, pk=None):
        resume = self.get_object()
        if request.method == 'GET':
            return Response(ResumeSuggestionV2Serializer(resume.suggestions.all(), many=True).data)

        def execute():
            from .intelligence import RESUME_TASK_KEYS
            admit_expensive_operation(request, scope='resume.suggestion')
            task_key = str(request.data.get('task_key') or 'resume.rewrite_section')
            if task_key not in RESUME_TASK_KEYS:
                raise ValidationError({'task_key': '不支持的简历智能任务。'})
            version_id = request.data.get('base_version_id')
            version = resume.versions.filter(pk=version_id).first() if version_id else resume.current_version
            if not version:
                raise ValidationError({'base_version_id': '简历版本不存在。'})
            operation = _create_operation(
                user=request.user,
                operation_type=task_key,
                source_model='ResumeVersion',
                source_id=f'{version.pk}:{task_key}:{timezone.now().timestamp()}',
                title=f'生成简历建议：{resume.title}',
                metadata={'resume_id': resume.pk, 'base_version_id': version.pk, 'task_key': task_key},
            )
            _dispatch(
                generate_resume_suggestion_task,
                [
                    version.pk,
                    task_key,
                    str(request.data.get('instruction') or '')[:4000],
                    request.data.get('job_target_id'),
                ],
                operation,
            )
            return operation_response(operation)

        return run_idempotent(request, f'resume.suggestion:{resume.pk}', execute, required=True)

    @action(detail=True, methods=['post'], url_path=r'suggestions/(?P<suggestion_id>\d+)/accept')
    def accept_resume_suggestion(self, request, pk=None, suggestion_id=None):
        resume = self.get_object()
        suggestion = resume.suggestions.filter(pk=suggestion_id).first()
        if not suggestion:
            raise NotFound('建议不存在。')
        version = accept_suggestion(suggestion, request.user)
        return Response(ResumeVersionV2Serializer(version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path=r'suggestions/(?P<suggestion_id>\d+)/reject')
    def reject_resume_suggestion(self, request, pk=None, suggestion_id=None):
        resume = self.get_object()
        suggestion = resume.suggestions.filter(pk=suggestion_id).first()
        if not suggestion:
            raise NotFound('建议不存在。')
        suggestion.status = ResumeSuggestion.Status.REJECTED
        suggestion.decided_at = timezone.now()
        suggestion.save(update_fields=['status', 'decided_at'])
        return Response(ResumeSuggestionV2Serializer(suggestion).data)

    @action(detail=True, methods=['get', 'post'], url_path='share-links')
    def share_links(self, request, pk=None):
        resume = self.get_object()
        if request.method == 'GET':
            return Response(ResumeShareLinkSerializer(resume.share_links.all(), many=True).data)
        _, design = ensure_studio(resume, request.user)
        version_id = request.data.get('version_id')
        version = resume.versions.filter(pk=version_id).first() if version_id else resume.current_version
        if not version:
            raise ValidationError({'version_id': '简历版本不存在。'})
        expires_at = None
        if request.data.get('expires_at'):
            expires_at = parse_datetime(str(request.data['expires_at']))
            if expires_at and timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
            if not expires_at or expires_at <= timezone.now():
                raise ValidationError({'expires_at': '过期时间必须是未来的 ISO-8601 时间。'})
        field_policy = request.data.get('field_policy') or {}
        if not isinstance(field_policy, dict) or set(field_policy) - {'email', 'phone', 'address', 'image'}:
            raise ValidationError({'field_policy': '字段策略包含未知字段。'})
        download_limit = request.data.get('download_limit')
        if download_limit is not None and (not isinstance(download_limit, int) or download_limit < 1):
            raise ValidationError({'download_limit': '下载次数必须为正整数。'})
        link, token = create_share_link(
            resume=resume,
            content_version=version,
            design_revision=design,
            user=request.user,
            password=str(request.data.get('password') or ''),
            field_policy=field_policy,
            expires_at=expires_at,
            allow_download=bool(request.data.get('allow_download', False)),
            download_limit=download_limit,
        )
        if link.allow_download:
            shared_json, shared_design, key = shared_render_snapshot(
                resume=resume,
                content_version=version,
                design_revision=design,
                field_policy=link.field_policy,
            )
            artifact, artifact_created = ResumeArtifact.objects.get_or_create(
                cache_key=key,
                defaults={
                    'resume': resume,
                    'design_revision': design,
                    'draft_etag': f'share-{link.id}',
                    'preview_input': shared_json,
                    'preview_design': shared_design,
                    'format': ResumeArtifact.Format.PDF,
                    'renderer_name': RENDERER_NAME,
                    'renderer_version': RENDERER_VERSION,
                },
            )
            operation, operation_created = AsyncOperation.objects.get_or_create(
                user=request.user,
                source_app='resumes',
                source_model='ResumeArtifact',
                source_id=str(artifact.id),
                defaults={'operation_type': 'resume.share_export', 'title': f'准备分享下载：{resume.title}'},
            )
            if artifact.status != ResumeArtifact.Status.READY and operation_created:
                _dispatch(render_resume_artifact, [str(artifact.id)], operation)
        data = ResumeShareLinkSerializer(link).data
        data['token'] = token
        data['share_url'] = f'/resume-shares/{token}'
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path=r'share-links/(?P<share_id>\d+)/revoke')
    def revoke_share(self, request, pk=None, share_id=None):
        resume = self.get_object()
        link = resume.share_links.filter(pk=share_id).first()
        if not link:
            raise NotFound('分享链接不存在。')
        if not link.revoked_at:
            link.revoked_at = timezone.now()
            link.save(update_fields=['revoked_at'])
        return Response(ResumeShareLinkSerializer(link).data)


class ResumeArtifactViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ResumeArtifactSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ResumeArtifact.objects.filter(resume__user=self.request.user).select_related(
            'asset', 'content_version', 'design_revision',
        )


class ResumeImportV2ViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ResumeImportJobV2Serializer
    permission_classes = [permissions.IsAuthenticated]

    def get_throttles(self):
        return [UploadRateThrottle()] if self.action == 'create' else super().get_throttles()

    def get_queryset(self):
        return ResumeImportJob.objects.filter(user=self.request.user).select_related('resume')

    def create(self, request, *args, **kwargs):
        def execute():
            admit_expensive_operation(request, scope='resume.import')
            file_obj = request.FILES.get('file')
            if not file_obj:
                raise ValidationError({'file': '请上传 PDF、DOCX、TXT、Markdown 或 JSON。'})
            max_bytes = int(getattr(settings, 'RESUME_UPLOAD_MAX_BYTES', 15 * 1024 * 1024))
            validate_uploaded_file(file_obj, allowed_extensions=ALLOWED_RESUME_EXTENSIONS, max_bytes=max_bytes)
            checksum = hashlib.sha256()
            for chunk in file_obj.chunks():
                checksum.update(chunk)
            file_obj.seek(0)
            with transaction.atomic():
                resume = Resume.objects.create(
                    user=request.user,
                    title=request.data.get('title') or os.path.splitext(file_obj.name)[0],
                    file=file_obj,
                    status=Resume.Status.PROCESSING,
                )
                job = ResumeImportJob.objects.create(resume=resume, user=request.user)
                ResumeAsset.objects.create(
                    resume=resume,
                    import_job=job,
                    kind=ResumeAsset.Kind.SOURCE,
                    file=resume.file.name,
                    original_name=file_obj.name,
                    mime_type=getattr(file_obj, 'content_type', ''),
                    size_bytes=file_obj.size,
                    checksum_sha256=checksum.hexdigest(),
                    metadata={'legacy_file_pointer': resume.file.name},
                )
                operation = _create_operation(
                    user=request.user,
                    operation_type='resume.import',
                    source_model='ResumeImportJob',
                    source_id=job.id,
                    title=f'导入简历：{resume.title}',
                    metadata={'resume_id': resume.id, 'import_job_id': job.id},
                )
            _dispatch(process_resume_import_job, [job.id], operation)
            return operation_response(operation, extra={'resume_id': resume.id, 'import_job_id': job.id})

        return run_idempotent(request, 'resume.import', execute, required=True)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        def execute():
            job = self.get_object()
            edited_json = request.data.get('resume_json')
            if edited_json is not None:
                edited_json = validate_resume(edited_json)
            try:
                version = confirm_resume_import(job, request.user, edited_json)
            except PermissionError:
                raise NotFound('导入任务不存在。')
            except ValueError as exc:
                raise ValidationError({'code': str(exc), 'message': '当前导入任务不可确认。'})
            AsyncOperation.objects.filter(
                user=request.user,
                source_app='resumes',
                source_model='ResumeImportJob',
                source_id=str(job.id),
            ).exclude(status=AsyncOperation.Status.SUCCEEDED).update(
                status=AsyncOperation.Status.SUCCEEDED,
                progress=100,
                completed_at=timezone.now(),
                metadata={
                    'resume_id': job.resume_id,
                    'import_job_id': job.id,
                    'version_id': version.id,
                },
            )
            version = ResumeVersion.objects.prefetch_related('evidence_links').get(pk=version.pk)
            return Response(
                ResumeVersionV2Serializer(version, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )

        return run_idempotent(request, 'resume.import.confirm', execute, required=False)

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        def execute():
            job = self.get_object()
            if job.status not in {ResumeImportJob.Status.FAILED, ResumeImportJob.Status.PENDING}:
                raise ValidationError({'status': '只有等待中或失败的任务可以重试。'})
            job.status = ResumeImportJob.Status.PENDING
            job.error_message = ''
            job.completed_at = None
            job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
            operation = _create_operation(
                user=request.user,
                operation_type='resume.import.retry',
                source_model='ResumeImportJob',
                source_id=job.id,
                title=f'重试导入简历：{job.resume.title}',
                metadata={'resume_id': job.resume_id, 'import_job_id': job.id},
            )
            _dispatch(process_resume_import_job, [job.id], operation)
            return operation_response(
                operation,
                extra={'resume_id': job.resume_id, 'import_job_id': job.id},
            )

        return run_idempotent(request, 'resume.import.retry', execute, required=True)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        job = self.get_object()
        if job.status in {ResumeImportJob.Status.CONFIRMED, ResumeImportJob.Status.CANCELED}:
            raise ValidationError({'status': '任务已经结束。'})
        job.status = ResumeImportJob.Status.CANCELED
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'completed_at', 'updated_at'])
        job.resume.status = Resume.Status.DRAFT
        job.resume.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(job).data)


class ResumeTemplateListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({'schema_version': '1.3.1', 'templates': template_catalog()})


class PublicResumeShareView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'resume_share'

    def get(self, request, token):
        link = resolve_share(
            token=token,
            password=request.headers.get('X-Resume-Share-Password', ''),
            request=request,
        )
        return Response({
            'title': link.resume.title,
            'version': link.content_version.version_number,
            'resume_json': redact_shared_resume(link.content_version.resume_json, link.field_policy),
            'design': shared_render_snapshot(
                resume=link.resume,
                content_version=link.content_version,
                design_revision=link.design_revision,
                field_policy=link.field_policy,
            )[1],
            'allow_download': link.allow_download,
            'expires_at': link.expires_at,
        })


class PublicResumeShareDownloadView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'resume_share'

    def get(self, request, token):
        link = resolve_share(
            token=token,
            password=request.headers.get('X-Resume-Share-Password', ''),
            request=request,
            action=ResumeShareAccess.Action.DOWNLOAD,
            consume_download=False,
        )
        _, _, key = shared_render_snapshot(
            resume=link.resume,
            content_version=link.content_version,
            design_revision=link.design_revision,
            field_policy=link.field_policy,
        )
        artifact = ResumeArtifact.objects.filter(
            resume=link.resume,
            cache_key=key,
            format=ResumeArtifact.Format.PDF,
            status=ResumeArtifact.Status.READY,
        ).select_related('asset').first()
        if not artifact or not artifact.asset_id:
            return Response({
                'code': 'share_download_preparing',
                'message': '下载文件仍在生成，请稍后重试。',
                'retryable': True,
                'retry_after_ms': 2000,
            }, status=status.HTTP_409_CONFLICT)
        # Consume the download allowance only after a ready file exists.
        resolve_share(
            token=token,
            password=request.headers.get('X-Resume-Share-Password', ''),
            request=request,
            action=ResumeShareAccess.Action.DOWNLOAD,
            consume_download=True,
        )
        return FileResponse(
            artifact.asset.file.open('rb'),
            as_attachment=True,
            filename=artifact.asset.original_name or f'{link.resume.title}.pdf',
            content_type=artifact.asset.mime_type or 'application/pdf',
        )
