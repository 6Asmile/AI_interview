import requests
from celery import shared_task
from django.conf import settings

from .services import database_public_content


@shared_task
def rebuild_public_search_indexes():
    base_url = str(getattr(settings, 'MEILISEARCH_URL', '') or '').rstrip('/')
    api_key = str(getattr(settings, 'MEILISEARCH_API_KEY', '') or '')
    if not base_url or not api_key:
        raise RuntimeError('meilisearch_not_configured')
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    grouped = {'public_blog': [], 'public_knowledge': [], 'community_topics': []}
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
