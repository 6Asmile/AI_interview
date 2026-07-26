from rest_framework import serializers

from .models import (
    Appeal,
    Bookmark,
    Challenge,
    ChallengeEnrollment,
    CommunityComment,
    CommunityContent,
    ContentReport,
    ContentRevision,
    GrowthEvent,
    Reaction,
    ReputationLedger,
    StreakState,
    Topic,
    TopicFollow,
    UserFollow,
)


class ContentRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentRevision
        fields = ('id', 'version', 'title', 'redacted_body', 'body_hash', 'created_at')


class CommunityContentSerializer(serializers.ModelSerializer):
    revision = ContentRevisionSerializer(source='current_revision', read_only=True)
    author = serializers.SerializerMethodField()
    body = serializers.CharField(write_only=True, required=False, allow_blank=False)
    topic_ids = serializers.PrimaryKeyRelatedField(
        source='topics', queryset=Topic.objects.filter(is_active=True), many=True, required=False,
    )

    class Meta:
        model = CommunityContent
        fields = (
            'id', 'author', 'content_type', 'title', 'body', 'excerpt', 'status',
            'is_anonymous', 'revision', 'topic_ids', 'target_roles', 'quality_score',
            'risk_level', 'published_at', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'excerpt', 'status', 'quality_score', 'risk_level', 'published_at',
            'created_at', 'updated_at',
        )

    def get_author(self, obj):
        request = self.context.get('request')
        if obj.is_anonymous and (not request or request.user != obj.author):
            return {'anonymous': True}
        return {'id': obj.author_id, 'username': obj.author.username, 'anonymous': False}

    def create(self, validated_data):
        from .services import create_revision
        body = validated_data.pop('body', '')
        topics = validated_data.pop('topics', [])
        content = CommunityContent.objects.create(author=self.context['request'].user, **validated_data)
        if topics:
            content.topics.set(topics)
        if body:
            create_revision(content=content, author=content.author, title=content.title, body=body)
        return content

    def update(self, instance, validated_data):
        from .services import create_revision
        body = validated_data.pop('body', None)
        topics = validated_data.pop('topics', None)
        previous_title = instance.title
        title = validated_data.pop('title', previous_title)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if topics is not None:
            instance.topics.set(topics)
        if body is not None or title != previous_title:
            create_revision(
                content=instance,
                author=self.context['request'].user,
                title=title,
                body=body if body is not None else instance.current_revision.body,
            )
        return instance


class CommunityCommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = CommunityComment
        fields = ('id', 'content', 'author', 'parent', 'body', 'is_anonymous', 'status', 'created_at', 'updated_at')
        read_only_fields = ('author', 'status', 'created_at', 'updated_at')

    def get_author(self, obj):
        request = self.context.get('request')
        if obj.is_anonymous and (not request or request.user != obj.author):
            return {'anonymous': True}
        return {'id': obj.author_id, 'username': obj.author.username, 'anonymous': False}

    def validate_parent(self, parent):
        content = self.context.get('content')
        if parent and content and parent.content_id != content.id:
            raise serializers.ValidationError('父评论不属于当前内容。')
        return parent


class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = '__all__'


class ContentReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentReport
        fields = ('id', 'content', 'reason', 'details', 'status', 'created_at')
        read_only_fields = ('status', 'created_at')


class ChallengeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Challenge
        fields = '__all__'


class GrowthEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = GrowthEvent
        exclude = ('user', 'dedup_key')
