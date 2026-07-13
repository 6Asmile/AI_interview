from django.contrib import admin
from django.utils import timezone

from .models import KnowledgeDocument, KnowledgeChunk, KnowledgeImportBatch, KnowledgeImportFile
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
        'difficulty', 'chunk_count', 'created_by', 'approved_by', 'updated_at'
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
        updated = queryset.exclude(approval_status=KnowledgeDocument.ApprovalStatus.APPROVED).update(
            approval_status=KnowledgeDocument.ApprovalStatus.PENDING_REVIEW,
            rejection_reason='',
            submitted_at=timezone.now(),
            updated_at=timezone.now(),
        )
        self.message_user(request, f'已提交 {updated} 条知识库审核。')

    @admin.action(description='审批通过并重建索引')
    def approve_and_reindex(self, request, queryset):
        count = 0
        for document in queryset:
            document.approval_status = KnowledgeDocument.ApprovalStatus.APPROVED
            document.approved_by = request.user
            document.approved_at = timezone.now()
            document.rejection_reason = ''
            document.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])
            try:
                reindex_knowledge_document.delay(str(document.id))
            except Exception:
                from .services import index_document
                index_document(document)
            count += 1
        self.message_user(request, f'已审批并提交 {count} 条知识库索引任务。')

    @admin.action(description='拒绝审核')
    def reject_documents(self, request, queryset):
        updated = queryset.update(
            approval_status=KnowledgeDocument.ApprovalStatus.REJECTED,
            status=KnowledgeDocument.Status.DRAFT,
            rejection_reason='管理员后台批量拒绝',
            approved_by=None,
            approved_at=None,
            updated_at=timezone.now(),
        )
        self.message_user(request, f'已拒绝 {updated} 条知识库。')

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
            try:
                reindex_knowledge_document.delay(str(document.id))
            except Exception:
                from .services import index_document
                index_document(document)
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
