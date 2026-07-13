from django.utils import timezone
from rest_framework import serializers

from .models import ApplicationEvent, CareerFact, JobApplication, JobTarget, LearningTask


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
            'id', 'company_name', 'position_name', 'jd_text', 'source_url',
            'location', 'deadline', 'keywords', 'status', 'application_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ('created_at', 'updated_at', 'application_count')


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
            'id', 'application', 'interview_session', 'title', 'dimension',
            'priority', 'status', 'evidence_refs', 'due_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ('created_at', 'updated_at')

    def validate(self, attrs):
        user = self.context['request'].user
        application = attrs.get('application')
        session = attrs.get('interview_session')
        if application and application.user_id != user.id:
            raise serializers.ValidationError({'application': '不能引用其他用户的投递。'})
        if session and session.user_id != user.id:
            raise serializers.ValidationError({'interview_session': '不能引用其他用户的面试。'})
        return attrs

