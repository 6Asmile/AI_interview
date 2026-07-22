import uuid

from django.conf import settings
from django.db import models


class KnowledgeDocument(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = 'private', '私有'
        PUBLIC = 'public', '公共'

    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        INDEXING = 'indexing', '索引中'
        INDEXED = 'indexed', '已索引'
        FAILED = 'failed', '索引失败'

    class ApprovalStatus(models.TextChoices):
        DRAFT = 'draft', '草稿'
        PENDING_REVIEW = 'pending_review', '待审核'
        APPROVED = 'approved', '已上线'
        REJECTED = 'rejected', '已拒绝'
        ARCHIVED = 'archived', '已归档'

    class Difficulty(models.TextChoices):
        ANY = 'any', '不限'
        EASY = 'easy', '基础'
        MEDIUM = 'medium', '中等'
        HARD = 'hard', '高阶'

    class ParseStatus(models.TextChoices):
        PENDING = 'pending', '待解析'
        PARSING = 'parsing', '解析中'
        PARSED = 'parsed', '已解析'
        FAILED = 'failed', '解析失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_batch = models.ForeignKey(
        'KnowledgeImportBatch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
        verbose_name='导入批次'
    )
    title = models.CharField(max_length=200, verbose_name='文档标题')
    content = models.TextField(verbose_name='知识内容')
    source_type = models.CharField(max_length=50, default='question_bank', verbose_name='来源类型')
    source_file = models.FileField(upload_to='knowledge_sources/%Y/%m/', null=True, blank=True, verbose_name='源文件')
    file_type = models.CharField(max_length=20, blank=True, verbose_name='文件类型')
    parse_status = models.CharField(
        max_length=20,
        choices=ParseStatus.choices,
        default=ParseStatus.PARSED,
        db_index=True,
        verbose_name='解析状态'
    )
    parser_name = models.CharField(max_length=80, blank=True, verbose_name='解析器')
    parser_version = models.CharField(max_length=80, blank=True, verbose_name='解析器版本')
    parser_fallback_reason = models.TextField(blank=True, verbose_name='解析降级原因')
    parsed_content = models.JSONField(default=dict, blank=True, verbose_name='结构化解析结果')
    ocr_enabled = models.BooleanField(default=False, verbose_name='是否启用OCR')
    draft_revision = models.ForeignKey(
        'KnowledgeDocumentRevision', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='当前编辑版本'
    )
    published_revision = models.ForeignKey(
        'KnowledgeDocumentRevision', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='当前发布版本'
    )
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
        db_index=True,
        verbose_name='可见范围'
    )
    job_positions = models.JSONField(default=list, blank=True, verbose_name='适用岗位')
    ability_tags = models.JSONField(default=list, blank=True, verbose_name='能力标签')
    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        default=Difficulty.ANY,
        verbose_name='难度'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name='索引状态'
    )
    approval_status = models.CharField(
        max_length=30,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.DRAFT,
        db_index=True,
        verbose_name='审批状态'
    )
    chunk_count = models.PositiveIntegerField(default=0, verbose_name='分片数量')
    last_indexed_at = models.DateTimeField(null=True, blank=True, verbose_name='最后索引时间')
    last_retrieved_at = models.DateTimeField(null=True, blank=True, verbose_name='最后检索命中时间')
    retrieval_count = models.PositiveIntegerField(default=0, verbose_name='检索命中次数')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    rejection_reason = models.TextField(blank=True, verbose_name='拒绝原因')
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name='提交审核时间')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='审批通过时间')
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_knowledge_documents',
        verbose_name='审批人'
    )
    staff_approved_by = models.ForeignKey(
        'staff_admin.StaffAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_knowledge_documents', verbose_name='员工审批人'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='knowledge_documents',
        verbose_name='创建人'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '知识库文档'
        verbose_name_plural = verbose_name
        ordering = ['-updated_at']

    def __str__(self):
        return self.title


class KnowledgeDocumentRevision(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '编辑中'
        PENDING_REVIEW = 'pending_review', '待审核'
        APPROVED = 'approved', '已批准'
        PUBLISHED = 'published', '已发布'
        REJECTED = 'rejected', '已拒绝'
        SUPERSEDED = 'superseded', '已替换'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name='revisions')
    version_number = models.PositiveIntegerField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT, db_index=True)
    source_content = models.TextField(blank=True)
    parsed_content = models.JSONField(default=dict, blank=True)
    parser_snapshot = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='knowledge_revisions'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_knowledge_revisions'
    )
    staff_approved_by = models.ForeignKey(
        'staff_admin.StaffAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_knowledge_revisions'
    )
    rejection_reason = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-version_number']
        constraints = [
            models.UniqueConstraint(fields=['document', 'version_number'], name='uniq_knowledge_document_revision'),
        ]

    def __str__(self):
        return f'{self.document.title} v{self.version_number}'


class KnowledgeChunkDraft(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.ForeignKey(KnowledgeDocumentRevision, on_delete=models.CASCADE, related_name='chunk_drafts')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    order = models.PositiveIntegerField()
    block_type = models.CharField(max_length=40, default='paragraph', db_index=True)
    heading_path = models.JSONField(default=list, blank=True)
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)
    content = models.TextField()
    table_data = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    token_count = models.PositiveIntegerField(default=0)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    is_excluded = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['revision', 'order'], name='uniq_knowledge_revision_chunk_order'),
        ]

    def __str__(self):
        return f'{self.revision} #{self.order}'


class KnowledgeImportBatch(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待处理'
        PROCESSING = 'processing', '处理中'
        COMPLETED = 'completed', '已完成'
        PARTIAL_FAILED = 'partial_failed', '部分失败'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING, db_index=True, verbose_name='导入状态')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='knowledge_import_batches',
        verbose_name='上传人'
    )
    source_files = models.JSONField(default=list, blank=True, verbose_name='源文件列表')
    options = models.JSONField(default=dict, blank=True, verbose_name='导入选项')
    total_files = models.PositiveIntegerField(default=0, verbose_name='文件总数')
    success_count = models.PositiveIntegerField(default=0, verbose_name='成功数')
    failed_count = models.PositiveIntegerField(default=0, verbose_name='失败数')
    error_log = models.JSONField(default=list, blank=True, verbose_name='错误日志')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '知识库导入批次'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'导入批次 {self.id}'


class KnowledgeImportFile(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待处理'
        PROCESSING = 'processing', '处理中'
        IMPORTED = 'imported', '已导入'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(KnowledgeImportBatch, on_delete=models.CASCADE, related_name='import_files', verbose_name='导入批次')
    source_file = models.FileField(upload_to='knowledge_imports/%Y/%m/', verbose_name='上传文件')
    original_name = models.CharField(max_length=255, verbose_name='原始文件名')
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING, db_index=True, verbose_name='处理状态')
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='import_files',
        verbose_name='生成文档'
    )
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '知识库导入文件'
        verbose_name_plural = verbose_name
        ordering = ['batch', 'created_at']

    def __str__(self):
        return self.original_name


class KnowledgeChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name='chunks',
        verbose_name='所属文档'
    )
    revision = models.ForeignKey(
        KnowledgeDocumentRevision, on_delete=models.CASCADE, null=True, blank=True,
        related_name='published_chunks', verbose_name='发布版本'
    )
    parent_chunk = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='child_chunks',
        verbose_name='父级分片'
    )
    chunk_index = models.PositiveIntegerField(verbose_name='分片序号')
    chunk_level = models.PositiveSmallIntegerField(default=1, db_index=True, verbose_name='分片层级')
    heading_path = models.JSONField(default=list, blank=True, verbose_name='标题路径')
    page_start = models.PositiveIntegerField(null=True, blank=True, verbose_name='起始页')
    page_end = models.PositiveIntegerField(null=True, blank=True, verbose_name='结束页')
    block_type = models.CharField(max_length=40, blank=True, db_index=True, verbose_name='块类型')
    token_count = models.PositiveIntegerField(default=0, verbose_name='Token数量估算')
    content_hash = models.CharField(max_length=64, blank=True, db_index=True, verbose_name='内容哈希')
    semantic_group_id = models.CharField(max_length=64, blank=True, db_index=True, verbose_name='语义组')
    content = models.TextField(verbose_name='分片内容')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='检索元数据')
    qdrant_point_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    embedding_model = models.CharField(max_length=120, blank=True, verbose_name='Embedding模型')
    indexed_at = models.DateTimeField(null=True, blank=True, verbose_name='索引时间')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '知识库分片'
        verbose_name_plural = verbose_name
        ordering = ['document', 'chunk_index']
        constraints = [
            models.UniqueConstraint(fields=['revision', 'chunk_index'], name='uniq_knowledge_revision_chunk_index'),
        ]

    def __str__(self):
        return f'{self.document.title} #{self.chunk_index}'
