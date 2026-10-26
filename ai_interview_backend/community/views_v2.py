from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.idempotency import run_idempotent
from core.admission import admit_expensive_operation

from .models import (
    Bookmark,
    Challenge,
    ChallengeEnrollment,
    CommunityComment,
    CommunityContent,
    ContentReport,
    GrowthEvent,
    Reaction,
    Topic,
    TopicFollow,
    UserFollow,
)
from .serializers_v2 import (
    ChallengeSerializer,
    CommunityCommentSerializer,
    CommunityContentSerializer,
    ContentReportSerializer,
    GrowthEventSerializer,
    TopicSerializer,
)
from .operation_handlers import operation_envelope
from .services import submit_content


class CommunityContentViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    serializer_class = CommunityContentSerializer
    filterset_fields = ('content_type', 'status', 'topics')
    search_fields = ('title', 'excerpt', 'current_revision__redacted_body')

    def get_queryset(self):
        queryset = CommunityContent.objects.select_related('author', 'current_revision').prefetch_related('topics')
        if self.request.user.is_authenticated:
            return queryset.filter(
                Q(status=CommunityContent.Status.PUBLISHED) | Q(author=self.request.user)
            ).distinct()
        return queryset.filter(status=CommunityContent.Status.PUBLISHED)

    def perform_destroy(self, instance):
        if instance.author_id != self.request.user.id:
            self.permission_denied(self.request)
        instance.status = CommunityContent.Status.HIDDEN
        instance.save(update_fields=['status', 'updated_at'])

    def perform_update(self, serializer):
        if serializer.instance.author_id != self.request.user.id:
            self.permission_denied(self.request)
        serializer.save()

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        content = self.get_object()
        def publish_content():
            admit_expensive_operation(request, scope='community-publish')
            submitted = submit_content(content=content, user=request.user)
            payload = dict(self.get_serializer(submitted).data)
            operation = getattr(submitted, '_accepted_operation', None)
            if operation:
                payload['operation'] = operation_envelope(operation)
            return Response(
                payload,
                status=(
                    status.HTTP_202_ACCEPTED
                    if submitted.status == CommunityContent.Status.PENDING
                    else status.HTTP_200_OK
                ),
            )

        return run_idempotent(
            request,
            f'community.content.{content.pk}.publish',
            publish_content,
            required=True,
        )

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        content = self.get_object()
        if request.method == 'GET':
            rows = content.comments.filter(status='published').select_related('author')
            return Response(CommunityCommentSerializer(rows, many=True, context={'request': request}).data)
        serializer = CommunityCommentSerializer(
            data={**request.data, 'content': str(content.pk)},
            context={'request': request, 'content': content},
        )
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(author=request.user, content=content)
        return Response(
            CommunityCommentSerializer(comment, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post', 'delete'])
    def reactions(self, request, pk=None):
        content = self.get_object()
        kind = str(request.data.get('kind') or 'like')[:20]
        if request.method == 'DELETE':
            Reaction.objects.filter(user=request.user, content=content, kind=kind).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        reaction, created = Reaction.objects.get_or_create(user=request.user, content=content, kind=kind)
        return Response({'kind': reaction.kind, 'created': created}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['post', 'delete'])
    def bookmarks(self, request, pk=None):
        content = self.get_object()
        if request.method == 'DELETE':
            Bookmark.objects.filter(user=request.user, content=content).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        _, created = Bookmark.objects.get_or_create(user=request.user, content=content)
        return Response({'bookmarked': True, 'created': created}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reports(self, request, pk=None):
        content = self.get_object()
        serializer = ContentReportSerializer(data={**request.data, 'content': str(content.pk)})
        serializer.is_valid(raise_exception=True)
        report = serializer.save(reporter=request.user, content=content)
        return Response(ContentReportSerializer(report).data, status=status.HTTP_201_CREATED)


class CommunityFeedViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    serializer_class = CommunityContentSerializer

    def get_queryset(self):
        queryset = CommunityContent.objects.filter(
            status=CommunityContent.Status.PUBLISHED,
        ).select_related('author', 'current_revision').prefetch_related('topics').annotate(
            reaction_count=Count('reactions'),
        )
        user = self.request.user
        if user.is_authenticated:
            followed_users = UserFollow.objects.filter(follower=user).values('followed_id')
            followed_topics = TopicFollow.objects.filter(user=user).values('topic_id')
            queryset = queryset.annotate(
                followed_rank=Count(
                    'id',
                    filter=Q(author_id__in=followed_users) | Q(topics__id__in=followed_topics),
                ),
            ).order_by('-followed_rank', '-quality_score', '-published_at')
        else:
            queryset = queryset.order_by('-quality_score', '-published_at')
        return queryset.distinct()


class TopicViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Topic.objects.filter(is_active=True)
    serializer_class = TopicSerializer


class ChallengeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    serializer_class = ChallengeSerializer

    def get_queryset(self):
        now = timezone.now()
        return Challenge.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now)

    @action(detail=True, methods=['post'])
    def enroll(self, request, pk=None):
        challenge = self.get_object()
        enrollment, created = ChallengeEnrollment.objects.get_or_create(challenge=challenge, user=request.user)
        return Response({'enrollment_id': enrollment.pk, 'created': created})


class GrowthEventViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = GrowthEventSerializer

    def get_queryset(self):
        return GrowthEvent.objects.filter(user=self.request.user)
