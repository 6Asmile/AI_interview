from rest_framework import serializers

from .models import KnowledgeDocument, KnowledgeChunk, KnowledgeImportBatch, KnowledgeImportFile


class KnowledgeChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeChunk
        fields = [
            'id',
            'chunk_index',
            'parent_chunk',
            'chunk_level',
            'heading_path',
            'page_start',
            'page_end',
            'block_type',
            'token_count',
            'content_hash',
            'semantic_group_id',
            'content',
            'metadata',
            'embedding_model',
            'indexed_at',
        ]
        read_only_fields = fields


class KnowledgeDocumentSerializer(serializers.ModelSerializer):
    chunks = KnowledgeChunkSerializer(many=True, read_only=True)
    can_edit = serializers.SerializerMethodField()
    can_submit_review = serializers.SerializerMethodField()
    can_approve = serializers.SerializerMethodField()
    auto_index = serializers.BooleanField(write_only=True, required=False, default=False)
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True)
    import_batch_id = serializers.UUIDField(source='import_batch.id', read_only=True)
    source_file_url = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeDocument
        fields = [
            'id',
            'title',
            'content',
            'source_type',
            'source_file',
            'source_file_url',
            'file_type',
            'parse_status',
            'parser_name',
            'parser_version',
            'parser_fallback_reason',
            'parsed_content',
            'ocr_enabled',
            'visibility',
            'job_positions',
            'ability_tags',
            'difficulty',
            'status',
            'approval_status',
            'chunk_count',
            'last_indexed_at',
            'last_retrieved_at',
            'retrieval_count',
            'error_message',
            'rejection_reason',
            'submitted_at',
            'approved_at',
            'approved_by',
            'approved_by_username',
            'import_batch',
            'import_batch_id',
            'created_by',
            'created_at',
            'updated_at',
            'can_edit',
            'can_submit_review',
            'can_approve',
            'chunks',
            'auto_index',
        ]
        read_only_fields = [
            'id',
            'source_file_url',
            'status',
            'parse_status',
            'parser_name',
            'parser_version',
            'parser_fallback_reason',
            'parsed_content',
            'ocr_enabled',
            'approval_status',
            'chunk_count',
            'last_indexed_at',
            'last_retrieved_at',
            'retrieval_count',
            'error_message',
            'rejection_reason',
            'submitted_at',
            'approved_at',
            'approved_by',
            'approved_by_username',
            'import_batch',
            'import_batch_id',
            'created_by',
            'created_at',
            'updated_at',
            'can_edit',
            'can_submit_review',
            'can_approve',
            'chunks',
        ]

    def _can_manage(self, user):
        return bool(user and user.is_authenticated and (
            user.is_staff or getattr(user, 'role', '') in ('admin', 'hr')
        ))

    def _can_publish_public(self, user):
        return bool(user and user.is_authenticated and (
            user.is_staff or getattr(user, 'role', '') == 'admin'
        ))

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        return bool(
            request.user.is_staff
            or getattr(request.user, 'role', '') == 'admin'
            or obj.created_by_id == request.user.id
        )

    def get_can_submit_review(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        return bool(
            (request.user.is_staff or obj.created_by_id == request.user.id)
            and obj.approval_status in [
                KnowledgeDocument.ApprovalStatus.DRAFT,
                KnowledgeDocument.ApprovalStatus.REJECTED,
            ]
        )

    def get_can_approve(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        return bool(
            self._can_manage(request.user)
            and obj.approval_status == KnowledgeDocument.ApprovalStatus.PENDING_REVIEW
        )

    def get_source_file_url(self, obj):
        request = self.context.get('request')
        if not obj.source_file:
            return ''
        url = obj.source_file.url
        return request.build_absolute_uri(url) if request else url

    def validate_visibility(self, value):
        request = self.context.get('request')
        if value == KnowledgeDocument.Visibility.PUBLIC and (
            not request or not self._can_publish_public(request.user)
        ):
            raise serializers.ValidationError('只有管理员可以发布公共知识库。')
        return value

    def create(self, validated_data):
        validated_data.pop('auto_index', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop('auto_index', None)
        return super().update(instance, validated_data)


class KnowledgeChunkPreviewSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False)
    title = serializers.CharField(required=False, allow_blank=True, max_length=200)
    chunk_size = serializers.IntegerField(required=False, min_value=200, max_value=3000)
    overlap = serializers.IntegerField(required=False, min_value=0, max_value=1000)


class KnowledgeDocumentRejectSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=True, allow_blank=False, max_length=2000)


class KnowledgeImportBatchSerializer(serializers.ModelSerializer):
    documents = KnowledgeDocumentSerializer(many=True, read_only=True)
    import_files = serializers.SerializerMethodField()
    files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
        allow_empty=False,
    )

    class Meta:
        model = KnowledgeImportBatch
        fields = [
            'id',
            'status',
            'uploaded_by',
            'source_files',
            'options',
            'total_files',
            'success_count',
            'failed_count',
            'error_log',
            'import_files',
            'documents',
            'files',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'uploaded_by',
            'source_files',
            'options',
            'total_files',
            'success_count',
            'failed_count',
            'error_log',
            'import_files',
            'documents',
            'created_at',
            'updated_at',
        ]

    def get_import_files(self, obj):
        return [
            {
                'id': str(item.id),
                'original_name': item.original_name,
                'status': item.status,
                'error_message': item.error_message,
                'document_id': str(item.document_id) if item.document_id else None,
                'created_at': item.created_at,
                'updated_at': item.updated_at,
            }
            for item in obj.import_files.all()
        ]
