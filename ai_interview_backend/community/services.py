import base64
import hashlib
import hmac
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlencode

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.events import enqueue_integration_event

from .models import ContentRevision, CommunityContent, ModerationCase


def database_public_content(query: str = '', limit: int = 20) -> list[dict]:
    from blog.models import Post
    from knowledge.models import KnowledgeDocument
    from .models import CommunityContent, CommunityTopicLink

    query = (query or '').strip()
    posts = Post.objects.filter(status=Post.PostStatus.PUBLISHED)
    documents = KnowledgeDocument.objects.filter(
        visibility=KnowledgeDocument.Visibility.PUBLIC,
        approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
        status=KnowledgeDocument.Status.INDEXED,
    )
    if query:
        posts = posts.filter(Q(title__icontains=query) | Q(excerpt__icontains=query) | Q(content__icontains=query))
        documents = documents.filter(Q(title__icontains=query) | Q(content__icontains=query))
    native = CommunityContent.objects.filter(
        status=CommunityContent.Status.PUBLISHED,
        current_revision__isnull=False,
    ).select_related('current_revision')
    if query:
        native = native.filter(
            Q(title__icontains=query) |
            Q(excerpt__icontains=query) |
            Q(current_revision__redacted_body__icontains=query)
        )
    results = [{
        'index': 'community_contents', 'id': str(item.pk), 'title': item.title,
        'excerpt': item.excerpt or item.current_revision.redacted_body[:220],
        'url': f'/dashboard/community?content={item.pk}',
        'published_at': item.published_at,
    } for item in native.order_by('-quality_score', '-published_at')[:limit]]
    results.extend({
        'index': 'public_blog', 'id': item.id, 'title': item.title,
        'excerpt': item.excerpt or item.content[:220], 'url': f'/dashboard/blog/{item.id}',
        'published_at': item.published_at or item.created_at,
    } for item in posts.order_by('-is_featured', '-published_at', '-created_at')[:limit])
    results.extend({
        'index': 'public_knowledge', 'id': str(item.id), 'title': item.title,
        'excerpt': item.content[:220], 'url': '', 'published_at': item.approved_at or item.updated_at,
    } for item in documents.order_by('-approved_at', '-updated_at')[:limit])
    topics = CommunityTopicLink.objects.exclude(topic_url='')
    if query:
        topics = topics.filter(metadata__icontains=query)
    results.extend({
        'index': 'community_topics', 'id': item.discourse_topic_id,
        'title': (item.metadata or {}).get('title') or item.topic_slug,
        'excerpt': (item.metadata or {}).get('excerpt') or '', 'url': item.topic_url,
        'published_at': item.last_posted_at or item.updated_at,
    } for item in topics.order_by('-last_posted_at', '-updated_at')[:limit])
    results.sort(key=lambda item: item.get('published_at') or '', reverse=True)
    for item in results:
        value = item.get('published_at')
        item['published_at'] = value.isoformat() if hasattr(value, 'isoformat') else value
    return results[:limit]


class CommunityIntegrationError(RuntimeError):
    pass


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)


def build_discourse_sso_response(user, encoded_payload: str, signature: str) -> dict:
    secret = str(getattr(settings, 'DISCOURSE_CONNECT_SECRET', '') or '')
    if not secret:
        raise CommunityIntegrationError('discourse_connect_not_configured')
    raw_payload = encoded_payload.encode('ascii')
    if not verify_signature(raw_payload, signature, secret):
        raise CommunityIntegrationError('invalid_sso_signature')
    try:
        decoded = base64.b64decode(encoded_payload).decode('utf-8')
        params = parse_qs(decoded)
        nonce = params['nonce'][0]
    except (ValueError, KeyError, UnicodeDecodeError) as exc:
        raise CommunityIntegrationError('invalid_sso_payload') from exc
    response = {
        'nonce': nonce,
        'email': user.email,
        'external_id': str(user.id),
        'username': user.username,
        'name': user.username,
        'admin': 'true' if user.is_superuser or user.role == 'admin' else 'false',
        'moderator': 'true' if user.is_staff or user.role in ('admin', 'hr') else 'false',
        'require_activation': 'false',
    }
    avatar = getattr(user, 'avatar', None)
    if avatar:
        response['avatar_url'] = avatar.url
    encoded = base64.b64encode(urlencode(response).encode('utf-8')).decode('ascii')
    return {'sso': encoded, 'sig': hmac.new(secret.encode('utf-8'), encoded.encode('ascii'), hashlib.sha256).hexdigest()}


def search_public_content(query: str, limit: int = 20) -> dict:
    url = str(getattr(settings, 'MEILISEARCH_URL', '') or '').rstrip('/')
    if not url:
        return {'results': database_public_content(query, limit), 'degraded': True, 'reason': 'meilisearch_not_configured'}
    headers = {'Content-Type': 'application/json'}
    api_key = str(getattr(settings, 'MEILISEARCH_API_KEY', '') or '')
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    try:
        response = requests.post(
            f'{url}/multi-search',
            json={'queries': [
                {'indexUid': 'public_blog', 'q': query, 'limit': limit},
                {'indexUid': 'community_contents', 'q': query, 'limit': limit},
                {'indexUid': 'public_knowledge', 'q': query, 'limit': limit},
                {'indexUid': 'community_topics', 'q': query, 'limit': limit},
            ]},
            headers=headers,
            timeout=5,
        )
        response.raise_for_status()
        groups = response.json().get('results') or []
        results = []
        for group in groups:
            index_uid = group.get('indexUid', '')
            for hit in group.get('hits') or []:
                results.append({'index': index_uid, **hit})
        return {'results': results[:limit], 'degraded': False, 'reason': ''}
    except Exception as exc:
        return {
            'results': database_public_content(query, limit),
            'degraded': True,
            'reason': f'meilisearch_unavailable:{type(exc).__name__}',
        }


PII_PATTERNS = (
    ('phone', re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')),
    ('email', re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', re.I)),
    ('national_id', re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)')),
    ('precise_address', re.compile(r'[\u4e00-\u9fff]{2,}(?:路|街|巷|弄)\d{1,5}号')),
)
LINK_PATTERN = re.compile(r'https?://|www\.', re.I)
CONTACT_PATTERN = re.compile(r'(微信|vx|v信|QQ|联系我|手机号)', re.I)
COMPANY_NEGATIVE_PATTERN = re.compile(r'(欠薪|裁员|歧视|骚扰|违法|诈骗|黑名单)')


def inspect_and_redact(text: str) -> tuple[str, list[dict], str]:
    redacted = text or ''
    findings: list[dict] = []
    for kind, pattern in PII_PATTERNS:
        matches = list(pattern.finditer(redacted))
        if matches:
            findings.append({'type': kind, 'count': len(matches), 'action': 'redacted'})
            redacted = pattern.sub(f'[{kind.upper()}_REDACTED]', redacted)
    for kind, pattern in (
        ('external_link', LINK_PATTERN),
        ('contact_request', CONTACT_PATTERN),
        ('company_negative', COMPANY_NEGATIVE_PATTERN),
    ):
        count = len(pattern.findall(text or ''))
        if count:
            findings.append({'type': kind, 'count': count, 'action': 'review'})
    risk = 'high' if any(item['type'] in {'national_id', 'precise_address', 'company_negative'} for item in findings) else (
        'medium' if findings else 'low'
    )
    return redacted, findings, risk


def content_hash(title: str, body: str) -> str:
    return hashlib.sha256(f'{title}\0{body}'.encode('utf-8')).hexdigest()


@transaction.atomic
def create_revision(*, content: CommunityContent, author, title: str, body: str) -> ContentRevision:
    if content.author_id != author.id:
        raise PermissionError('不能修改其他用户的内容。')
    redacted, findings, risk_level = inspect_and_redact(body)
    version = (content.revisions.order_by('-version').values_list('version', flat=True).first() or 0) + 1
    revision = ContentRevision.objects.create(
        content=content,
        version=version,
        title=title,
        body=body,
        body_hash=content_hash(title, body),
        redacted_body=redacted,
        risk_findings=findings,
        created_by=author,
    )
    content.title = title
    content.excerpt = re.sub(r'\s+', ' ', redacted)[:500]
    content.current_revision = revision
    content.risk_level = risk_level
    if content.status != CommunityContent.Status.DRAFT:
        content.status = CommunityContent.Status.DRAFT
        content.published_at = None
    content.save(update_fields=[
        'title', 'excerpt', 'current_revision', 'risk_level',
        'status', 'published_at', 'updated_at',
    ])
    return revision


@transaction.atomic
def submit_content(*, content: CommunityContent, user) -> CommunityContent:
    if content.author_id != user.id:
        raise PermissionError('不能发布其他用户的内容。')
    if not content.current_revision:
        raise ValueError('请先创建内容修订。')
    is_new_user = user.date_joined >= timezone.now() - timedelta(days=14)
    requires_review = (
        is_new_user or
        content.risk_level != 'low' or
        content.content_type in {
            CommunityContent.ContentType.EXPERIENCE,
            CommunityContent.ContentType.RESUME_CLINIC,
        }
    )
    content.status = CommunityContent.Status.PENDING if requires_review else CommunityContent.Status.PUBLISHED
    content.published_at = None if requires_review else timezone.now()
    content.save(update_fields=['status', 'published_at', 'updated_at'])
    if requires_review:
        case, _created = ModerationCase.objects.get_or_create(
            content=content,
            revision=content.current_revision,
            defaults={
                'risk_level': content.risk_level,
                'findings': content.current_revision.risk_findings,
            },
        )
        from .operation_handlers import create_moderation_operation
        content._accepted_operation = create_moderation_operation(user=user, case=case)
    else:
        enqueue_integration_event(
            event_type='community.content.published',
            producer='community',
            aggregate_type='CommunityContent',
            aggregate_id=content.pk,
            actor_id=user.pk,
            payload={'content_id': str(content.pk), 'content_type': content.content_type},
        )
    return content
