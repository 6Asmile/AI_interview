from django.utils import timezone
from rest_framework import serializers

from .models import (
    AbilitySnapshot,
    ApplicationEvent,
    CareerFact,
    CareerProfile,
    CareerTimelineEvent,
    Company,
    CompanyMember,
    JobApplication,
    JobMatchAnalysis,
    JobPosting,
    JobPostingRevision,
    JobTarget,
    LearningPlan,
    LearningTask,
    WeeklyCareerReport,
)


class CareerFactSerializer(serializers.ModelSerializer):
    class Meta:
        model = CareerFact
        fields = [
            'id', 'fact_type', 'title', 'organization', 'role', 'description',
            'start_date', 'end_date', 'skills', 'metrics', 'source_type',
            'source_url', 'source_metadata', 'verification_status', 'verified_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ('verified_at', 'created_at', 'updated_at')

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': '结束日期不能早于开始日期。'})
        if attrs.get('source_type') == CareerFact.SourceType.GITHUB and not attrs.get('source_url'):
            raise serializers.ValidationError({'source_url': 'GitHub 来源必须保留可核验链接。'})
        return attrs

    def update(self, instance, validated_data):
        evidence_fields = {'title', 'organization', 'role', 'description', 'start_date', 'end_date', 'skills', 'metrics', 'source_url'}
        if instance.verification_status == CareerFact.VerificationStatus.CONFIRMED and evidence_fields.intersection(validated_data):
            validated_data['verification_status'] = CareerFact.VerificationStatus.DRAFT
            validated_data['verified_at'] = None
        return super().update(instance, validated_data)


class JobTargetSerializer(serializers.ModelSerializer):
    application_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = JobTarget
        fields = [
            'id', 'source_type', 'job_posting', 'job_posting_revision',
            'company_name', 'position_name', 'jd_text', 'jd_snapshot_hash', 'source_url',
            'location', 'deadline', 'keywords', 'status', 'application_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = (
            'source_type', 'job_posting', 'job_posting_revision', 'jd_snapshot_hash',
            'created_at', 'updated_at', 'application_count',
        )

    def validate(self, attrs):
        if self.instance and self.instance.source_type == JobTarget.SourceType.COMPANY:
            frozen_fields = {'company_name', 'position_name', 'jd_text', 'location', 'keywords'}
            attempted = frozen_fields.intersection(getattr(self, 'initial_data', {}))
            if attempted:
                raise serializers.ValidationError({
                    field: '企业岗位目标使用已发布修订快照，不允许原地修改。'
                    for field in attempted
                })
        return attrs

    def update(self, instance, validated_data):
        if 'jd_text' in validated_data:
            from .services import stable_hash
            validated_data['jd_snapshot_hash'] = stable_hash({'jd_text': validated_data['jd_text']})
        return super().update(instance, validated_data)


class ApplicationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationEvent
        fields = ['id', 'event_type', 'stage', 'notes', 'occurred_at', 'metadata', 'created_at']
        read_only_fields = ('created_at',)


class JobApplicationSerializer(serializers.ModelSerializer):
    job_target_detail = JobTargetSerializer(source='job_target', read_only=True)
    events = ApplicationEventSerializer(many=True, read_only=True)
    resume_version_number = serializers.IntegerField(source='resume_version.version_number', read_only=True)

    class Meta:
        model = JobApplication
        fields = [
            'id', 'job_target', 'job_target_detail', 'resume_version', 'resume_version_number',
            'cover_letter', 'status', 'source', 'next_action_at', 'notes', 'applied_at',
            'events', 'created_at', 'updated_at',
        ]
        read_only_fields = ('created_at', 'updated_at')

    def validate_job_target(self, value):
        if value.user_id != self.context['request'].user.id:
            raise serializers.ValidationError('不能引用其他用户的岗位。')
        return value

    def validate_resume_version(self, value):
        if value and value.resume.user_id != self.context['request'].user.id:
            raise serializers.ValidationError('不能引用其他用户的简历版本。')
        return value

    def create(self, validated_data):
        if validated_data.get('status') == JobApplication.Status.APPLIED and not validated_data.get('applied_at'):
            validated_data['applied_at'] = timezone.now()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        new_status = validated_data.get('status')
        if new_status == JobApplication.Status.APPLIED and not instance.applied_at:
            validated_data['applied_at'] = timezone.now()
        return super().update(instance, validated_data)


class LearningTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningTask
        fields = [
            'id', 'plan', 'application', 'interview_session', 'title', 'dimension',
            'priority', 'status', 'evidence_refs', 'source_type', 'source_id',
            'due_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ('source_type', 'source_id', 'created_at', 'updated_at')

    def validate(self, attrs):
        user = self.context['request'].user
        application = attrs.get('application')
        session = attrs.get('interview_session')
        if application and application.user_id != user.id:
            raise serializers.ValidationError({'application': '不能引用其他用户的投递。'})
        if session and session.user_id != user.id:
            raise serializers.ValidationError({'interview_session': '不能引用其他用户的面试。'})
        return attrs


class CareerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CareerProfile
        exclude = ('user',)
        read_only_fields = ('profile_version', 'created_at', 'updated_at')

    def update(self, instance, validated_data):
        if validated_data:
            validated_data['profile_version'] = instance.profile_version + 1
        return super().update(instance, validated_data)


class AbilitySnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AbilitySnapshot
        exclude = ('user',)


class CareerTimelineEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CareerTimelineEvent
        exclude = ('user', 'dedup_key')


class WeeklyCareerReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeeklyCareerReport
        exclude = ('user',)


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            'id', 'name', 'slug', 'website', 'description', 'industry', 'size',
            'location', 'status', 'verified_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ('status', 'verified_at', 'created_at', 'updated_at')


class CompanyMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyMember
        fields = ('id', 'company', 'user', 'role', 'status', 'created_at')
        read_only_fields = ('created_at',)


class JobPostingRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobPostingRevision
        fields = [
            'id', 'version', 'title', 'jd_text', 'requirements', 'skills',
            'salary', 'content_hash', 'approved_at', 'created_at',
        ]
        read_only_fields = ('version', 'content_hash', 'approved_at', 'created_at')


class JobPostingSerializer(serializers.ModelSerializer):
    company_detail = CompanySerializer(source='company', read_only=True)
    revision = JobPostingRevisionSerializer(source='current_revision', read_only=True)

    class Meta:
        model = JobPosting
        fields = [
            'id', 'company', 'company_detail', 'title', 'location', 'work_mode',
            'employment_type', 'status', 'revision', 'published_at', 'closes_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ('status', 'published_at', 'created_at', 'updated_at')

    def validate_company(self, company):
        user = self.context['request'].user
        if not CompanyMember.objects.filter(
            company=company,
            user=user,
            status=CompanyMember.Status.ACTIVE,
            role__in=(CompanyMember.Role.OWNER, CompanyMember.Role.RECRUITER),
        ).exists():
            raise serializers.ValidationError('你不是该企业的招聘成员。')
        return company


class JobMatchAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobMatchAnalysis
        exclude = ('user',)


class LearningPlanSerializer(serializers.ModelSerializer):
    tasks = LearningTaskSerializer(many=True, read_only=True)

    class Meta:
        model = LearningPlan
        exclude = ('user',)
