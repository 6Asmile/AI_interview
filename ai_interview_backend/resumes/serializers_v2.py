from __future__ import annotations

from rest_framework import serializers

from careers.models import CareerFact

from .models import (
    Resume, ResumeArtifact, ResumeDesignRevision, ResumeDraft, ResumeEvidenceLink,
    ResumeImportJob, ResumeQualityReport, ResumeShareLink, ResumeSuggestion, ResumeVersion,
)
from .schema import validate_resume
from .templates import validate_design


class ResumeVersionV2Serializer(serializers.ModelSerializer):
    evidence_links = serializers.SerializerMethodField()

    class Meta:
        model = ResumeVersion
        fields = (
            'id', 'version_number', 'parent', 'schema_version', 'content_hash', 'language',
            'resume_json', 'source', 'change_summary', 'created_at', 'evidence_links',
        )
        read_only_fields = fields

    def get_evidence_links(self, obj):
        return [
            {
                'json_pointer': link.json_pointer,
                'career_fact_id': link.career_fact_id,
                'fact_hash': link.fact_hash,
                'fact_snapshot': link.fact_snapshot,
            }
            for link in obj.evidence_links.all()
        ]


class ResumeDesignRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeDesignRevision
        fields = (
            'id', 'revision_number', 'parent', 'template_key', 'template_version',
            'language', 'page_size', 'design_json', 'design_hash', 'created_at',
        )
        read_only_fields = fields


class ResumeDraftSerializer(serializers.ModelSerializer):
    base_version_number = serializers.IntegerField(source='base_version.version_number', read_only=True)

    class Meta:
        model = ResumeDraft
        fields = (
            'id', 'base_version', 'base_version_number', 'resume_json', 'design_json',
            'revision', 'etag', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class ResumeV2Serializer(serializers.ModelSerializer):
    current_version = ResumeVersionV2Serializer(read_only=True)
    current_design_revision = ResumeDesignRevisionSerializer(read_only=True)
    draft_etag = serializers.CharField(source='draft.etag', read_only=True)

    class Meta:
        model = Resume
        fields = (
            'id', 'title', 'status', 'is_default', 'canonical_schema_version',
            'current_version', 'current_design_revision', 'draft_etag', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'canonical_schema_version', 'current_version', 'current_design_revision',
            'draft_etag', 'created_at', 'updated_at',
        )

    def validate_status(self, value):
        if value not in {Resume.Status.DRAFT, Resume.Status.READY, Resume.Status.ARCHIVED}:
            raise serializers.ValidationError('新版简历仅支持 draft、ready、archived。')
        return value


class DraftPatchSerializer(serializers.Serializer):
    resume_json = serializers.JSONField(required=False)
    design_json = serializers.JSONField(required=False)

    def validate_resume_json(self, value):
        return validate_resume(value)

    def validate_design_json(self, value):
        return validate_design(value)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError('至少提供 resume_json 或 design_json。')
        return attrs


class VersionCommitSerializer(serializers.Serializer):
    change_summary = serializers.CharField(max_length=255, required=False, default='创建简历版本')
    evidence_links = serializers.ListField(child=serializers.DictField(), required=False, default=list)

    def validate_evidence_links(self, value):
        fact_ids = set()
        for item in value:
            if 'fact_id' not in item:
                raise serializers.ValidationError('每条证据必须包含 fact_id。')
            pointer = str(item.get('json_pointer') or '')
            if not pointer.startswith('/'):
                raise serializers.ValidationError('json_pointer 必须以 / 开头。')
            fact_ids.add(int(item['fact_id']))
        user = self.context['request'].user
        confirmed = set(CareerFact.objects.filter(
            user=user,
            id__in=fact_ids,
            verification_status=CareerFact.VerificationStatus.CONFIRMED,
        ).values_list('id', flat=True))
        if confirmed != fact_ids:
            raise serializers.ValidationError('只能引用当前用户已确认的职业事实。')
        return value


class ResumeArtifactSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    content_version_number = serializers.IntegerField(source='content_version.version_number', read_only=True)
    design_revision_number = serializers.IntegerField(source='design_revision.revision_number', read_only=True)

    class Meta:
        model = ResumeArtifact
        fields = (
            'id', 'resume', 'content_version', 'content_version_number', 'design_revision',
            'design_revision_number', 'draft_etag', 'format', 'status', 'renderer_name',
            'renderer_version', 'page_count', 'file_url', 'error_code', 'error_message',
            'created_at', 'completed_at',
        )
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.asset_id or not obj.asset.file:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.asset.file.url) if request else obj.asset.file.url


class ResumeQualityReportSerializer(serializers.ModelSerializer):
    content_version_number = serializers.IntegerField(source='content_version.version_number', read_only=True)

    class Meta:
        model = ResumeQualityReport
        fields = (
            'id', 'resume', 'content_version', 'content_version_number', 'status',
            'schema_version', 'config_hash', 'score', 'report_json', 'error_message',
            'created_at', 'completed_at',
        )
        read_only_fields = fields


class ResumeShareLinkSerializer(serializers.ModelSerializer):
    is_revoked = serializers.SerializerMethodField()

    class Meta:
        model = ResumeShareLink
        fields = (
            'id', 'content_version', 'design_revision', 'token_hint', 'field_policy',
            'expires_at', 'revoked_at', 'is_revoked', 'allow_download', 'download_limit',
            'download_count', 'created_at',
        )
        read_only_fields = fields

    def get_is_revoked(self, obj):
        return bool(obj.revoked_at)


class ResumeSuggestionV2Serializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeSuggestion
        fields = (
            'id', 'base_version', 'patch', 'summary', 'rationale', 'evidence_fact_ids', 'evidence_links',
            'status', 'accepted_version', 'created_at', 'decided_at',
        )
        read_only_fields = ('status', 'accepted_version', 'created_at', 'decided_at')


class ResumeImportJobV2Serializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeImportJob
        fields = (
            'id', 'resume', 'status', 'parser_name', 'parser_version',
            'parser_fallback_reason', 'parsed_json', 'error_message',
            'started_at', 'completed_at', 'created_at', 'updated_at',
        )
        read_only_fields = fields
