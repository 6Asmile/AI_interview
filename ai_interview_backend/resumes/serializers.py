from django.db import transaction
from copy import deepcopy
from django.utils import timezone
from rest_framework import serializers

from careers.models import CareerFact

from .models import (
    Education,
    ProjectExperience,
    Resume,
    ResumeImportJob,
    ResumeSuggestion,
    ResumeVariant,
    ResumeVersion,
    Skill,
    WorkExperience,
)
from .versioning import create_resume_version, ensure_resume_version
from .json_resume import legacy_resume_to_json_resume, normalize_json_resume


class SkillSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = Skill
        fields = ['id', 'skill_name', 'proficiency']


class EducationSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = Education
        fields = ['id', 'school', 'degree', 'major', 'start_date', 'end_date']


class WorkExperienceSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    end_date = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = WorkExperience
        fields = ['id', 'company', 'position', 'start_date', 'end_date', 'description']


class ProjectExperienceSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    end_date = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = ProjectExperience
        fields = ['id', 'project_name', 'role', 'start_date', 'end_date', 'description']


class ResumeVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeVersion
        fields = [
            'id', 'resume', 'version_number', 'parent', 'schema_version', 'resume_json',
            'layout_json', 'evidence_snapshot', 'source', 'change_summary', 'created_by', 'created_at',
        ]
        read_only_fields = fields


class ResumeImportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeImportJob
        fields = [
            'id', 'resume', 'status', 'parser_name', 'parser_version', 'parser_fallback_reason',
            'parsed_text', 'parsed_json', 'error_message', 'started_at', 'completed_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class ResumeSuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeSuggestion
        fields = [
            'id', 'resume', 'base_version', 'patch', 'summary', 'rationale', 'evidence_fact_ids', 'evidence_links',
            'status', 'accepted_version', 'created_by', 'created_at', 'decided_at',
        ]
        read_only_fields = ('status', 'accepted_version', 'created_by', 'created_at', 'decided_at')

    def validate(self, attrs):
        request = self.context['request']
        resume = attrs.get('resume')
        version = attrs.get('base_version')
        if resume.user_id != request.user.id or version.resume_id != resume.id:
            raise serializers.ValidationError('简历与版本不匹配或无权访问。')
        fact_ids = attrs.get('evidence_fact_ids') or []
        confirmed = set(CareerFact.objects.filter(
            user=request.user,
            id__in=fact_ids,
            verification_status=CareerFact.VerificationStatus.CONFIRMED,
        ).values_list('id', flat=True))
        if confirmed != {int(item) for item in fact_ids}:
            raise serializers.ValidationError({'evidence_fact_ids': '建议只能引用已确认的职业事实。'})
        return attrs


class ResumeVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeVariant
        fields = ['id', 'resume', 'source_version', 'version', 'job_target', 'title', 'created_at']
        read_only_fields = ('version', 'created_at')


class ResumeCreateSerializer(serializers.ModelSerializer):
    content_json = serializers.JSONField(required=False, allow_null=True)
    template_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Resume
        fields = ['title', 'status', 'content_json', 'template_name']


class ResumeDetailSerializer(serializers.ModelSerializer):
    skills = SkillSerializer(many=True, required=False)
    educations = EducationSerializer(many=True, required=False)
    work_experiences = WorkExperienceSerializer(many=True, required=False)
    project_experiences = ProjectExperienceSerializer(many=True, required=False)
    current_version = ResumeVersionSerializer(read_only=True)
    latest_import_job = serializers.SerializerMethodField()
    version_count = serializers.IntegerField(source='versions.count', read_only=True)

    class Meta:
        model = Resume
        fields = [
            'id', 'title', 'status', 'parsed_content', 'file_url', 'file', 'template_name',
            'content_json', 'canonical_schema_version', 'current_version', 'version_count',
            'latest_import_job', 'full_name', 'phone', 'email', 'job_title', 'city', 'summary',
            'skills', 'educations', 'work_experiences', 'project_experiences',
            'is_default', 'created_at', 'updated_at',
        ]
        read_only_fields = ('file_url', 'file', 'canonical_schema_version', 'current_version', 'created_at', 'updated_at')

    def get_latest_import_job(self, obj):
        job = obj.import_jobs.order_by('-created_at').first()
        return ResumeImportJobSerializer(job).data if job else None

    @transaction.atomic
    def update(self, instance, validated_data):
        nested = {
            'skills': validated_data.pop('skills', None),
            'educations': validated_data.pop('educations', None),
            'work_experiences': validated_data.pop('work_experiences', None),
            'project_experiences': validated_data.pop('project_experiences', None),
        }
        legacy_content = validated_data.pop('content_json', None)
        legacy_scalars = {
            key: validated_data.pop(key)
            for key in ('full_name', 'phone', 'email', 'job_title', 'city', 'summary')
            if key in validated_data
        }
        template_name = validated_data.pop('template_name', None)
        for attr in ('title', 'status', 'is_default'):
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])
        instance.save(update_fields=[
            *[key for key in ('title', 'status', 'is_default') if key in validated_data],
            'updated_at',
        ])
        current = ensure_resume_version(instance, self.context.get('request').user)
        canonical = deepcopy(current.resume_json)
        basics = canonical.setdefault('basics', {})
        scalar_map = {
            'full_name': 'name', 'phone': 'phone', 'email': 'email',
            'job_title': 'label', 'summary': 'summary',
        }
        for source, target in scalar_map.items():
            if source in legacy_scalars:
                basics[target] = legacy_scalars[source]
        if 'city' in legacy_scalars:
            basics.setdefault('location', {})['city'] = legacy_scalars['city']
        if nested['educations'] is not None:
            canonical['education'] = [{
                'institution': item.get('school', ''),
                'area': item.get('major', ''),
                'studyType': item.get('degree', ''),
                'startDate': str(item.get('start_date') or ''),
                'endDate': str(item.get('end_date') or ''),
                'courses': [],
            } for item in nested['educations']]
        if nested['work_experiences'] is not None:
            canonical['work'] = [{
                'name': item.get('company', ''),
                'position': item.get('position', ''),
                'startDate': str(item.get('start_date') or ''),
                'endDate': str(item.get('end_date') or ''),
                'summary': item.get('description', ''),
                'highlights': [],
            } for item in nested['work_experiences']]
        if nested['project_experiences'] is not None:
            canonical['projects'] = [{
                'name': item.get('project_name', ''),
                'roles': [item.get('role')] if item.get('role') else [],
                'startDate': str(item.get('start_date') or ''),
                'endDate': str(item.get('end_date') or ''),
                'description': item.get('description', ''),
                'keywords': [],
                'highlights': [],
            } for item in nested['project_experiences']]
        if nested['skills'] is not None:
            canonical['skills'] = [{
                'name': item.get('skill_name', ''),
                'level': item.get('proficiency', ''),
                'keywords': [],
            } for item in nested['skills']]
        if legacy_content is not None:
            converted = legacy_resume_to_json_resume(instance, legacy_content)
            for key in ('basics', 'work', 'education', 'projects', 'skills'):
                if converted.get(key):
                    canonical[key] = converted[key]
        request = self.context.get('request')
        create_resume_version(
            resume=instance,
            resume_json=canonical,
            user=getattr(request, 'user', instance.user),
            source=ResumeVersion.Source.EDITOR,
            change_summary='通过 v1 兼容适配器保存到 Canonical JSON',
        )
        if template_name:
            from .studio import ensure_studio
            from .templates import RESUME_TEMPLATES
            draft, _ = ensure_studio(instance, getattr(request, 'user', instance.user))
            if template_name in RESUME_TEMPLATES:
                draft.design_json['template_key'] = template_name
                draft.save(update_fields=['design_json', 'updated_at'])
        return instance


class ResumeVersionCreateSerializer(serializers.Serializer):
    resume_json = serializers.JSONField()
    layout_json = serializers.JSONField(required=False, default=dict)
    change_summary = serializers.CharField(required=False, allow_blank=True, max_length=255)
    evidence_fact_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)

    def validate_resume_json(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('标准简历必须是 JSON 对象。')
        return normalize_json_resume(value)

    def validate_evidence_fact_ids(self, value):
        user = self.context['request'].user
        count = CareerFact.objects.filter(
            user=user,
            id__in=value,
            verification_status=CareerFact.VerificationStatus.CONFIRMED,
        ).count()
        if count != len(set(value)):
            raise serializers.ValidationError('只能引用当前用户已确认的职业事实。')
        return value
