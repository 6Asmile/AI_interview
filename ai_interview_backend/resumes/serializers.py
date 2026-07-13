from django.db import transaction
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
            'id', 'resume', 'base_version', 'patch', 'summary', 'rationale', 'evidence_fact_ids',
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
        nested_fields = {
            'skills': (Skill, validated_data.pop('skills', None)),
            'educations': (Education, validated_data.pop('educations', None)),
            'work_experiences': (WorkExperience, validated_data.pop('work_experiences', None)),
            'project_experiences': (ProjectExperience, validated_data.pop('project_experiences', None)),
        }
        versioned_change = bool({'content_json', 'full_name', 'phone', 'email', 'job_title', 'city', 'summary'}.intersection(validated_data))
        versioned_change = versioned_change or any(items is not None for _, items in nested_fields.values())
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        for field_name, (model_class, data_list) in nested_fields.items():
            if data_list is None:
                continue
            current_ids = []
            for item_data in data_list:
                item_id = item_data.pop('id', None)
                if item_id:
                    updated = model_class.objects.filter(id=item_id, resume=instance).update(**item_data)
                    if not updated:
                        raise serializers.ValidationError({field_name: f'关联项 {item_id} 不存在。'})
                    current_ids.append(item_id)
                else:
                    current_ids.append(model_class.objects.create(resume=instance, **item_data).id)
            getattr(instance, field_name).exclude(id__in=current_ids).delete()

        if versioned_change:
            request = self.context.get('request')
            create_resume_version(
                resume=instance,
                resume_json=legacy_resume_to_json_resume(instance),
                layout_json=instance.content_json or {},
                user=getattr(request, 'user', instance.user),
                source=ResumeVersion.Source.EDITOR,
                change_summary='通过兼容编辑器保存简历',
            )
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
