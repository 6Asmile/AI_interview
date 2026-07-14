from django.contrib import admin
from django.utils import timezone

from .models import (
    KnowledgeChunk,
    KnowledgeChunkDraft,
    KnowledgeDocument,
    KnowledgeDocumentRevision,
    KnowledgeImportBatch,
    KnowledgeImportFile,
)
from .tasks import reindex_knowledge_document


class KnowledgeChunkInline(admin.TabularInline):
    model = KnowledgeChunk
    extra = 0
    readonly_fields = (
        'id', 'parent_chunk', 'chunk_index', 'chunk_level', 'heading_path', 'page_start',
        'page_end', 'block_type', 'token_count', 'content_hash', 'semantic_group_id',
        'qdrant_point_id', 'embedding_model', 'indexed_at', 'created_at'
    )
    fields = (
        'chunk_index', 'chunk_level', 'parent_chunk', 'block_type', 'heading_path',
        'page_start', 'page_end', 'token_count', 'content', 'metadata',
        'qdrant_point_id', 'embedding_model', 'indexed_at'
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'visibility', 'approval_status', 'status', 'parse_status', 'source_type',
        'difficulty', 'chunk_count', 'draft_revision', 'published_revision',
        'created_by', 'approved_by', 'updated_at'
    )
    list_filter = (
        'visibility', 'approval_status', 'status', 'parse_status', 'parser_name', 'ocr_enabled', 'source_type',
        'difficulty', 'created_by', 'approved_by'
    )
    search_fields = ('title', 'content')
    readonly_fields = (
        'status', 'chunk_count', 'error_message', 'created_by', 'created_at', 'updated_at',
        'submitted_at', 'approved_at', 'approved_by', 'last_indexed_at', 'last_retrieved_at',
        'retrieval_count', 'import_batch', 'parse_status', 'parser_name', 'parser_version',
        'parser_fallback_reason', 'parsed_content', 'ocr_enabled'
    )
    inlines = [KnowledgeChunkInline]
    actions = [
        'submit_for_review',
        'approve_and_reindex',
        'reject_documents',
        'archive_documents',
        'reindex_documents',
    ]

    @admin.action(description='提交审核')
    def submit_for_review(self, request, queryset):
        updated = 0
        for document in queryset.select_related('draft_revision'):
            revision = document.draft_revision
            if revision and revision.status in {KnowledgeDocumentRevision.Status.DRAFT, KnowledgeDocumentRevision.Status.REJECTED}:
                revision.status = KnowledgeDocumentRevision.Status.PENDING_REVIEW
                revision.submitted_at = timezone.now()
                revision.rejection_reason = ''
                revision.save(update_fields=['status', 'submitted_at', 'rejection_reason', 'updated_at'])
                if not document.published_revision_id:
                    document.approval_status = KnowledgeDocument.ApprovalStatus.PENDING_REVIEW
                document.submitted_at = revision.submitted_at
                document.save(update_fields=['approval_status', 'submitted_at', 'updated_at'])
                updated += 1
        self.message_user(request, f'已提交 {updated} 个知识库版本审核。')

    @admin.action(description='审批通过并重建索引')
    def approve_and_reindex(self, request, queryset):
        count = 0
        for document in queryset.select_related('draft_revision'):
            revision = document.draft_revision
            if not revision or revision.status != KnowledgeDocumentRevision.Status.PENDING_REVIEW:
                continue
            revision.status = KnowledgeDocumentRevision.Status.APPROVED
            revision.approved_by = request.user
            revision.approved_at = timezone.now()
            revision.rejection_reason = ''
            revision.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])
            document.approved_by = request.user
            document.approved_at = revision.approved_at
            document.rejection_reason = ''
            document.save(update_fields=['approved_by', 'approved_at', 'rejection_reason', 'updated_at'])
            try:
                reindex_knowledge_document.delay(str(document.id), str(revision.id))
            except Exception:
                from .services import index_document
                index_document(document, revision=revision)
            count += 1
        self.message_user(request, f'已审批并提交 {count} 条知识库索引任务。')

    @admin.action(description='拒绝审核')
    def reject_documents(self, request, queryset):
        updated = 0
        for document in queryset.select_related('draft_revision'):
            revision = document.draft_revision
            if not revision or revision.status != KnowledgeDocumentRevision.Status.PENDING_REVIEW:
                continue
            revision.status = KnowledgeDocumentRevision.Status.REJECTED
            revision.rejection_reason = '管理员后台批量拒绝'
            revision.save(update_fields=['status', 'rejection_reason', 'updated_at'])
            if not document.published_revision_id:
                document.approval_status = KnowledgeDocument.ApprovalStatus.REJECTED
                document.status = KnowledgeDocument.Status.DRAFT
            document.rejection_reason = revision.rejection_reason
            document.save(update_fields=['approval_status', 'status', 'rejection_reason', 'updated_at'])
            updated += 1
        self.message_user(request, f'已拒绝 {updated} 个知识库版本。')

    @admin.action(description='归档下线')
    def archive_documents(self, request, queryset):
        updated = queryset.update(
            approval_status=KnowledgeDocument.ApprovalStatus.ARCHIVED,
            status=KnowledgeDocument.Status.DRAFT,
            updated_at=timezone.now(),
        )
        self.message_user(request, f'已归档 {updated} 条知识库。')

    @admin.action(description='重建索引')
    def reindex_documents(self, request, queryset):
        count = 0
        for document in queryset.filter(approval_status=KnowledgeDocument.ApprovalStatus.APPROVED):
            revision = document.published_revision
            if not revision:
                continue
            try:
                reindex_knowledge_document.delay(str(document.id), str(revision.id))
            except Exception:
                from .services import index_document
                index_document(document, revision=revision)
            count += 1
        self.message_user(request, f'已提交 {count} 条已审批知识库重建索引。')


@admin.register(KnowledgeChunk)
class KnowledgeChunkAdmin(admin.ModelAdmin):
    list_display = ('document', 'chunk_index', 'chunk_level', 'block_type', 'token_count', 'embedding_model', 'indexed_at')
    list_filter = ('chunk_level', 'block_type', 'embedding_model')
    search_fields = ('document__title', 'content')
    readonly_fields = (
        'document', 'parent_chunk', 'chunk_index', 'chunk_level', 'heading_path',
        'page_start', 'page_end', 'block_type', 'token_count', 'content_hash',
        'semantic_group_id', 'content', 'metadata', 'qdrant_point_id',
        'embedding_model', 'indexed_at', 'created_at'
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class KnowledgeChunkDraftInline(admin.TabularInline):
    model = KnowledgeChunkDraft
    extra = 0
    fields = ('order', 'block_type', 'heading_path', 'page_start', 'page_end', 'is_excluded', 'token_count', 'content')
    ordering = ('order',)


@admin.register(KnowledgeDocumentRevision)
class KnowledgeDocumentRevisionAdmin(admin.ModelAdmin):
    list_display = ('document', 'version_number', 'status', 'created_by', 'approved_by', 'updated_at')
    list_filter = ('status', 'created_by', 'approved_by')
    search_fields = ('document__title', 'source_content')
    readonly_fields = ('document', 'version_number', 'created_by', 'approved_by', 'submitted_at', 'approved_at', 'published_at', 'created_at', 'updated_at')
    inlines = [KnowledgeChunkDraftInline]

    def has_add_permission(self, request):
        return False


@admin.register(KnowledgeChunkDraft)
class KnowledgeChunkDraftAdmin(admin.ModelAdmin):
    list_display = ('revision', 'order', 'block_type', 'is_excluded', 'token_count', 'updated_at')
    list_filter = ('block_type', 'is_excluded', 'revision__status')
    search_fields = ('revision__document__title', 'content')
    readonly_fields = ('revision', 'content_hash', 'token_count', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False


class KnowledgeImportFileInline(admin.TabularInline):
    model = KnowledgeImportFile
    extra = 0
    readonly_fields = ('id', 'original_name', 'status', 'document', 'error_message', 'created_at', 'updated_at')
    fields = ('original_name', 'status', 'document', 'error_message', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(KnowledgeImportBatch)
class KnowledgeImportBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'uploaded_by', 'total_files', 'success_count', 'failed_count', 'created_at')
    list_filter = ('status', 'uploaded_by')
    search_fields = ('id', 'source_files', 'error_log')
    readonly_fields = (
        'id', 'status', 'uploaded_by', 'source_files', 'options', 'total_files',
        'success_count', 'failed_count', 'error_log', 'created_at', 'updated_at'
    )
    inlines = [KnowledgeImportFileInline]
    actions = ['retry_failed_batches']

    @admin.action(description='重试失败文件')
    def retry_failed_batches(self, request, queryset):
        from .views import KnowledgeImportBatchViewSet
        helper = KnowledgeImportBatchViewSet()
        retried = 0
        for batch in queryset:
            for import_file in batch.import_files.filter(status=KnowledgeImportFile.Status.FAILED):
                try:
                    helper._create_document_from_import_file(import_file, batch.options or {}, batch.uploaded_by or request.user)
                    retried += 1
                except Exception as exc:
                    import_file.status = KnowledgeImportFile.Status.FAILED
                    import_file.error_message = str(exc)[:2000]
                    import_file.save(update_fields=['status', 'error_message', 'updated_at'])
            helper._refresh_batch_stats(batch)
        self.message_user(request, f'已重试 {retried} 个失败文件。')
