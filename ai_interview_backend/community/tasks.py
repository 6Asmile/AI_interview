import requests
from celery import shared_task
from django.conf import settings

from .models import CommunityContent, ModerationCase
from .services import database_public_content, inspect_and_redact


@shared_task
def rebuild_public_search_indexes():
    base_url = str(getattr(settings, 'MEILISEARCH_URL', '') or '').rstrip('/')
    api_key = str(getattr(settings, 'MEILISEARCH_API_KEY', '') or '')
    if not base_url or not api_key:
        raise RuntimeError('meilisearch_not_configured')
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    grouped = {'community_contents': [], 'public_blog': [], 'public_knowledge': [], 'community_topics': []}
    for item in database_public_content('', 10000):
        index_uid = item.pop('index')
        grouped[index_uid].append(item)
    result = {}
    for index_uid, documents in grouped.items():
        create_response = requests.post(
            f'{base_url}/indexes',
            json={'uid': index_uid, 'primaryKey': 'id'},
            headers=headers,
            timeout=10,
        )
        if create_response.status_code not in (200, 201, 202, 409):
            create_response.raise_for_status()
        settings_response = requests.patch(
            f'{base_url}/indexes/{index_uid}/settings',
            json={
                'searchableAttributes': ['title', 'excerpt'],
                'displayedAttributes': ['id', 'title', 'excerpt', 'url', 'published_at'],
                'sortableAttributes': ['published_at'],
            },
            headers=headers,
            timeout=10,
        )
        settings_response.raise_for_status()
        clear_response = requests.delete(
            f'{base_url}/indexes/{index_uid}/documents',
            headers=headers,
            timeout=30,
        )
        clear_response.raise_for_status()
        task = clear_response.json()
        if documents:
            response = requests.put(
                f'{base_url}/indexes/{index_uid}/documents',
                params={'primaryKey': 'id'},
                json=documents,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            task = response.json()
        result[index_uid] = {'count': len(documents), 'task': task}
    return result


@shared_task(acks_late=True, reject_on_worker_lost=True, soft_time_limit=50, time_limit=60)
def moderate_community_content(content_id: str):
    content = CommunityContent.objects.select_related('current_revision').get(pk=content_id)
    revision = content.current_revision
    if not revision:
        return {'content_id': content_id, 'status': 'no_revision'}
    redacted, findings, risk_level = inspect_and_redact(revision.body)
    CommunityContent.objects.filter(pk=content.pk).update(risk_level=risk_level)
    case, _ = ModerationCase.objects.get_or_create(
        content=content,
        revision=revision,
        defaults={'risk_level': risk_level, 'findings': findings},
    )
    return {'content_id': content_id, 'case_id': str(case.pk), 'risk_level': risk_level}


@shared_task(
    autoretry_for=(requests.ConnectionError, requests.Timeout),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def index_community_content(content_id: str):
    content = CommunityContent.objects.select_related('current_revision').prefetch_related('topics').get(pk=content_id)
    if content.status != CommunityContent.Status.PUBLISHED or not content.current_revision:
        return {'content_id': content_id, 'indexed': False}
    base_url = str(getattr(settings, 'MEILISEARCH_URL', '') or '').rstrip('/')
    if not base_url:
        return {'content_id': content_id, 'indexed': False, 'reason': 'meilisearch_not_configured'}
    headers = {'Content-Type': 'application/json'}
    api_key = str(getattr(settings, 'MEILISEARCH_API_KEY', '') or '')
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    response = requests.post(
        f'{base_url}/indexes/community_contents/documents',
        headers=headers,
        json=[{
            'id': str(content.pk),
            'content_type': content.content_type,
            'title': content.title,
            'body': content.current_revision.redacted_body,
            'topics': [topic.slug for topic in content.topics.all()],
            'target_roles': content.target_roles,
            'quality_score': float(content.quality_score),
            'published_at': content.published_at.isoformat() if content.published_at else None,
        }],
        timeout=5,
    )
    response.raise_for_status()
    return {'content_id': content_id, 'indexed': True}
