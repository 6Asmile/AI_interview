from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import KnowledgeDocument, KnowledgeImportBatch, KnowledgeImportFile
from .serializers import (
    KnowledgeChunkPreviewSerializer,
    KnowledgeDocumentRejectSerializer,
    KnowledgeDocumentSerializer,
    KnowledgeImportBatchSerializer,
)
from .tasks import (
    process_import_file,
    process_knowledge_import_file,
    refresh_import_batch_stats,
    reindex_knowledge_document,
    reparse_knowledge_document,
)


def can_manage_knowledge_review(user) -> bool:
    return bool(user and user.is_authenticated and (
        user.is_staff or getattr(user, 'role', '') in ('admin', 'hr')
    ))


def can_publish_public_knowledge(user) -> bool:
    return bool(user and user.is_authenticated and (
        user.is_staff or getattr(user, 'role', '') == 'admin'
    ))


def _split_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        text = str(value)
        for separator in ['；', ';', '|', '，']:
            text = text.replace(separator, ',')
        items = text.split(',')
    return [str(item).strip() for item in items if str(item).strip()]


class KnowledgeDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = KnowledgeDocument.objects.select_related('created_by').prefetch_related('chunks')
        user = self.request.user
        if not can_manage_knowledge_review(user):
            queryset = queryset.filter(
                Q(visibility=KnowledgeDocument.Visibility.PUBLIC) |
                Q(visibility=KnowledgeDocument.Visibility.PRIVATE, created_by=user)
            )

        visibility = self.request.query_params.get('visibility')
        if visibility:
            queryset = queryset.filter(visibility=visibility)

        index_status = self.request.query_params.get('status')
        if index_status:
            queryset = queryset.filter(status=index_status)

        approval_status = self.request.query_params.get('approval_status')
        if approval_status:
            queryset = queryset.filter(approval_status=approval_status)

        difficulty = self.request.query_params.get('difficulty')
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        source_type = self.request.query_params.get('source_type')
        if source_type:
            queryset = queryset.filter(source_type=source_type)

        search = (self.request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(content__icontains=search))

        job_position = (self.request.query_params.get('job_position') or '').strip()
        if job_position:
            queryset = queryset.filter(job_positions__icontains=job_position)

        ability_tag = (self.request.query_params.get('ability_tag') or '').strip()
        if ability_tag:
            queryset = queryset.filter(ability_tags__icontains=ability_tag)

        return queryset

    def _ensure_can_edit(self, document: KnowledgeDocument):
        user = self.request.user
        if user.is_staff or getattr(user, 'role', '') == 'admin':
            return
        if document.visibility == KnowledgeDocument.Visibility.PUBLIC:
            raise PermissionDenied('公共知识库只能由管理员维护。')
        if document.created_by_id != user.id:
            raise PermissionDenied('只能管理自己的私有知识库。')

    def _ensure_can_review(self):
        if not can_manage_knowledge_review(self.request.user):
            raise PermissionDenied('只有 HR 或管理员可以审批知识库。')

    def perform_create(self, serializer):
        visibility = serializer.validated_data.get('visibility', KnowledgeDocument.Visibility.PRIVATE)
        if visibility == KnowledgeDocument.Visibility.PUBLIC and not can_publish_public_knowledge(self.request.user):
            raise PermissionDenied('只有管理员可以发布公共知识库。')
        serializer.save(
            created_by=self.request.user,
            approval_status=KnowledgeDocument.ApprovalStatus.DRAFT,
            status=KnowledgeDocument.Status.DRAFT,
            parse_status=KnowledgeDocument.ParseStatus.PARSED,
            parser_name='manual',
            parsed_content={
                'parser_name': 'manual',
                'blocks': [{
                    'block_type': 'manual',
                    'text': serializer.validated_data.get('content', ''),
                    'heading_path': [serializer.validated_data.get('title', '')],
                    'page_start': None,
                    'page_end': None,
                    'metadata': {},
                }],
            },
        )

    def perform_update(self, serializer):
        document = self.get_object()
        self._ensure_can_edit(document)
        visibility = serializer.validated_data.get('visibility', serializer.instance.visibility)
        if visibility == KnowledgeDocument.Visibility.PUBLIC and not can_publish_public_knowledge(self.request.user):
            raise PermissionDenied('只有管理员可以发布公共知识库。')
        watched_fields = {
            'title', 'content', 'source_type', 'visibility', 'job_positions',
            'ability_tags', 'difficulty', 'source_file', 'file_type',
        }
        should_reset_approval = bool(watched_fields & set(serializer.validated_data.keys()))
        if 'content' in serializer.validated_data:
            serializer.validated_data['parse_status'] = KnowledgeDocument.ParseStatus.PARSED
            serializer.validated_data['parser_name'] = 'manual'
            serializer.validated_data['parser_fallback_reason'] = ''
            serializer.validated_data['parsed_content'] = {
                'parser_name': 'manual',
                'blocks': [{
                    'block_type': 'manual',
                    'text': serializer.validated_data.get('content', ''),
                    'heading_path': [serializer.validated_data.get('title', document.title)],
                    'page_start': None,
                    'page_end': None,
                    'metadata': {},
                }],
            }
        document = serializer.save()
        if should_reset_approval:
            document.approval_status = KnowledgeDocument.ApprovalStatus.DRAFT
            document.status = KnowledgeDocument.Status.DRAFT
            document.rejection_reason = ''
            document.submitted_at = None
            document.approved_at = None
            document.approved_by = None
            document.error_message = ''
            document.chunks.all().delete()
            document.chunk_count = 0
            document.parse_status = serializer.validated_data.get('parse_status', document.parse_status)
            document.save(update_fields=[
                'approval_status', 'status', 'rejection_reason', 'submitted_at',
                'approved_at', 'approved_by', 'error_message', 'chunk_count',
                'parse_status', 'updated_at',
            ])

    def perform_destroy(self, instance):
        self._ensure_can_edit(instance)
        instance.delete()

    def _schedule_reindex(self, document: KnowledgeDocument):
        if document.approval_status != KnowledgeDocument.ApprovalStatus.APPROVED:
            raise PermissionDenied('知识库必须审批通过后才能重建上线索引。')
        document.status = KnowledgeDocument.Status.INDEXING
        document.error_message = ''
        document.save(update_fields=['status', 'error_message', 'updated_at'])
        try:
            reindex_knowledge_document.delay(str(document.id))
        except Exception:
            from .services import index_document
            index_document(document)

    @action(detail=True, methods=['post'], url_path='reindex')
    def reindex(self, request, pk=None):
        document = self.get_object()
        self._ensure_can_edit(document)
        self._schedule_reindex(document)
        document.refresh_from_db()
        if document.status == KnowledgeDocument.Status.INDEXING:
            return Response(
                {'message': '知识库索引任务已提交', 'document_id': str(document.id), 'status': document.status},
                status=status.HTTP_202_ACCEPTED
            )
        else:
            serializer = self.get_serializer(document)
            return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='submit-review')
    def submit_review(self, request, pk=None):
        document = self.get_object()
        self._ensure_can_edit(document)
        if document.approval_status == KnowledgeDocument.ApprovalStatus.APPROVED:
            return Response({'detail': '已上线知识库无需重复提交审核。'}, status=status.HTTP_400_BAD_REQUEST)
        document.approval_status = KnowledgeDocument.ApprovalStatus.PENDING_REVIEW
        document.rejection_reason = ''
        from django.utils import timezone
        document.submitted_at = timezone.now()
        document.save(update_fields=['approval_status', 'rejection_reason', 'submitted_at', 'updated_at'])
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reparse')
    def reparse(self, request, pk=None):
        document = self.get_object()
        self._ensure_can_edit(document)
        if not document.source_file:
            return Response({'detail': '只有文件导入的知识库可以重新解析。'}, status=status.HTTP_400_BAD_REQUEST)
        document.parse_status = KnowledgeDocument.ParseStatus.PARSING
        document.save(update_fields=['parse_status', 'updated_at'])
        try:
            reparse_knowledge_document.delay(str(document.id))
        except Exception:
            reparse_knowledge_document(str(document.id))
        return Response(self.get_serializer(document).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        document = self.get_object()
        self._ensure_can_review()
        if document.approval_status != KnowledgeDocument.ApprovalStatus.PENDING_REVIEW:
            return Response({'detail': '只有待审核知识库可以审批通过。'}, status=status.HTTP_400_BAD_REQUEST)
        if document.parse_status != KnowledgeDocument.ParseStatus.PARSED:
            return Response({'detail': '知识库解析完成后才能审批上线。'}, status=status.HTTP_400_BAD_REQUEST)
        from django.utils import timezone
        document.approval_status = KnowledgeDocument.ApprovalStatus.APPROVED
        document.approved_by = request.user
        document.approved_at = timezone.now()
        document.rejection_reason = ''
        document.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])
        self._schedule_reindex(document)
        document.refresh_from_db()
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        document = self.get_object()
        self._ensure_can_review()
        serializer = KnowledgeDocumentRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if document.approval_status != KnowledgeDocument.ApprovalStatus.PENDING_REVIEW:
            return Response({'detail': '只有待审核知识库可以拒绝。'}, status=status.HTTP_400_BAD_REQUEST)
        document.approval_status = KnowledgeDocument.ApprovalStatus.REJECTED
        document.rejection_reason = serializer.validated_data['rejection_reason']
        document.approved_by = None
        document.approved_at = None
        document.status = KnowledgeDocument.Status.DRAFT
        document.save(update_fields=[
            'approval_status', 'rejection_reason', 'approved_by', 'approved_at',
            'status', 'updated_at',
        ])
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, pk=None):
        document = self.get_object()
        self._ensure_can_edit(document)
        document.approval_status = KnowledgeDocument.ApprovalStatus.ARCHIVED
        document.status = KnowledgeDocument.Status.DRAFT
        document.save(update_fields=['approval_status', 'status', 'updated_at'])
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='preview-chunks')
    def preview_chunks(self, request):
        serializer = KnowledgeChunkPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .services import CHILD_MAX_TOKENS, CHILD_OVERLAP_TOKENS, build_chunk_preview, build_preview_parsed_content
        title = serializer.validated_data.get('title') or '切块预览'
        document = KnowledgeDocument(
            title=title,
            content=serializer.validated_data['content'],
            parsed_content=build_preview_parsed_content(serializer.validated_data['content'], title=title),
        )
        preview = build_chunk_preview(
            document,
            child_max_tokens=serializer.validated_data.get('chunk_size', CHILD_MAX_TOKENS),
            overlap_tokens=serializer.validated_data.get('overlap', CHILD_OVERLAP_TOKENS),
        )
        return Response(preview, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='preview-structured-chunks')
    def preview_structured_chunks(self, request, pk=None):
        document = self.get_object()
        from .services import CHILD_MAX_TOKENS, CHILD_OVERLAP_TOKENS, build_chunk_preview
        preview = build_chunk_preview(
            document,
            child_max_tokens=int(request.data.get('chunk_size') or CHILD_MAX_TOKENS),
            overlap_tokens=int(request.data.get('overlap') or CHILD_OVERLAP_TOKENS),
        )
        return Response(preview, status=status.HTTP_200_OK)


class KnowledgeImportBatchViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeImportBatchSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        queryset = KnowledgeImportBatch.objects.select_related('uploaded_by').prefetch_related('documents')
        if can_manage_knowledge_review(self.request.user):
            return queryset
        return queryset.filter(uploaded_by=self.request.user)

    def _build_options(self, request):
        visibility = request.data.get('visibility') or KnowledgeDocument.Visibility.PRIVATE
        if visibility == KnowledgeDocument.Visibility.PUBLIC and not can_publish_public_knowledge(request.user):
            raise PermissionDenied('只有管理员可以发布公共知识库。')
        return {
            'visibility': visibility,
            'title': request.data.get('title') or '',
            'source_type': request.data.get('source_type') or '',
            'job_positions': _split_list(request.data.get('job_positions')),
            'ability_tags': _split_list(request.data.get('ability_tags')),
            'difficulty': request.data.get('difficulty') or '',
        }

    def create(self, request, *args, **kwargs):
        files = request.FILES.getlist('files') or request.FILES.getlist('files[]')
        if not files:
            return Response({'files': ['请上传至少一个知识库文件。']}, status=status.HTTP_400_BAD_REQUEST)

        options = self._build_options(request)
        batch = KnowledgeImportBatch.objects.create(
            uploaded_by=request.user,
            status=KnowledgeImportBatch.Status.PROCESSING,
            source_files=[file.name for file in files],
            options=options,
            total_files=len(files),
        )
        for uploaded_file in files:
            import_file = KnowledgeImportFile.objects.create(
                batch=batch,
                source_file=uploaded_file,
                original_name=uploaded_file.name,
                status=KnowledgeImportFile.Status.PENDING,
            )
            try:
                process_knowledge_import_file.delay(str(import_file.id))
            except Exception as exc:
                try:
                    process_import_file(str(import_file.id))
                except Exception as inner_exc:
                    import_file.status = KnowledgeImportFile.Status.FAILED
                    import_file.error_message = f'{exc}; {inner_exc}'[:2000]
                    import_file.save(update_fields=['status', 'error_message', 'updated_at'])

        refresh_import_batch_stats(batch)
        serializer = self.get_serializer(batch)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='retry-failed')
    def retry_failed(self, request, pk=None):
        batch = self.get_object()
        for import_file in batch.import_files.filter(status=KnowledgeImportFile.Status.FAILED):
            try:
                process_knowledge_import_file.delay(str(import_file.id))
            except Exception as exc:
                try:
                    process_import_file(str(import_file.id))
                except Exception as inner_exc:
                    import_file.status = KnowledgeImportFile.Status.FAILED
                    import_file.error_message = f'{exc}; {inner_exc}'[:2000]
                    import_file.save(update_fields=['status', 'error_message', 'updated_at'])
        refresh_import_batch_stats(batch)
        return Response(self.get_serializer(batch).data, status=status.HTTP_200_OK)


class KnowledgeSearchDebugView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .services import search_knowledge_context
        result = search_knowledge_context(
            job_position=request.data.get('job_position', ''),
            user=request.user,
            current_stage=request.data.get('current_stage', ''),
            pending_topics=request.data.get('pending_topics') or [],
            last_evaluation=request.data.get('last_evaluation') or {},
            jd_text=request.data.get('jd_text', ''),
            difficulty=request.data.get('difficulty', ''),
            exclude_chunk_ids=request.data.get('exclude_chunk_ids') or [],
            limit=int(request.data.get('limit') or 4),
            return_trace=True,
        )
        return Response(result, status=status.HTTP_200_OK)
