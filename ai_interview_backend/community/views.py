import hashlib
import json

from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CommunityIdentity, CommunityTopicLink, CommunityWebhookEvent
from .services import CommunityIntegrationError, build_discourse_sso_response, search_public_content, verify_signature


class DiscourseConnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            result = build_discourse_sso_response(request.user, request.query_params.get('sso', ''), request.query_params.get('sig', ''))
        except CommunityIntegrationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class DiscourseWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        secret = str(getattr(settings, 'DISCOURSE_WEBHOOK_SECRET', '') or '')
        signature = request.headers.get('X-Discourse-Event-Signature', '')
        if not secret or not verify_signature(request.body, signature, secret):
            return Response({'detail': 'invalid_webhook_signature'}, status=status.HTTP_403_FORBIDDEN)
        event_id = request.headers.get('X-Discourse-Event-Id') or hashlib.sha256(request.body).hexdigest()
        event_type = request.headers.get('X-Discourse-Event') or 'unknown'
        payload = request.data if isinstance(request.data, dict) else {}
        event, created = CommunityWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={'event_type': event_type, 'payload': payload},
        )
        if not created:
            return Response({'status': event.status, 'duplicate': True})
        try:
            user_payload = payload.get('user') if isinstance(payload.get('user'), dict) else None
            if user_payload and user_payload.get('external_id'):
                from users.models import User
                user = User.objects.filter(id=user_payload['external_id']).first()
                if user:
                    CommunityIdentity.objects.update_or_create(
                        user=user,
                        defaults={
                            'discourse_user_id': user_payload.get('id'),
                            'discourse_username': user_payload.get('username', ''),
                            'trust_level': int(user_payload.get('trust_level') or 0),
                            'profile_snapshot': {key: user_payload.get(key) for key in ('name', 'username', 'avatar_template')},
                            'synced_at': timezone.now(),
                        },
                    )
            topic_payload = payload.get('topic') if isinstance(payload.get('topic'), dict) else None
            if topic_payload and topic_payload.get('id'):
                CommunityTopicLink.objects.update_or_create(
                    discourse_topic_id=topic_payload['id'],
                    defaults={
                        'topic_slug': topic_payload.get('slug', ''),
                        'topic_url': topic_payload.get('url', ''),
                        'metadata': {'title': topic_payload.get('title', ''), 'posts_count': topic_payload.get('posts_count')},
                        'last_posted_at': timezone.now(),
                    },
                )
            event.status = CommunityWebhookEvent.Status.PROCESSED
        except Exception as exc:
            event.status = CommunityWebhookEvent.Status.FAILED
            event.error_message = str(exc)[:2000]
        event.processed_at = timezone.now()
        event.save(update_fields=['status', 'error_message', 'processed_at'])
        return Response({'status': event.status}, status=status.HTTP_202_ACCEPTED)


class CommunityMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        identity = CommunityIdentity.objects.filter(user=request.user).first()
        return Response({
            'configured': bool(getattr(settings, 'DISCOURSE_BASE_URL', '')),
            'community_url': getattr(settings, 'DISCOURSE_BASE_URL', ''),
            'identity': {
                'discourse_user_id': identity.discourse_user_id,
                'username': identity.discourse_username,
                'trust_level': identity.trust_level,
                'reputation': identity.reputation,
                'synced_at': identity.synced_at,
            } if identity else None,
        })


class PublicSearchView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        query = str(request.query_params.get('q') or '').strip()
        if not query:
            return Response({'results': [], 'degraded': False, 'reason': ''})
        return Response(search_public_content(query, min(int(request.query_params.get('limit', 20)), 50)))

