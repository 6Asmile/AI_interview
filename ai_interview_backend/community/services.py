import base64
import hashlib
import hmac
from urllib.parse import parse_qs, urlencode

import requests
from django.conf import settings


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
        return {'results': [], 'degraded': True, 'reason': 'meilisearch_not_configured'}
    headers = {'Content-Type': 'application/json'}
    api_key = str(getattr(settings, 'MEILISEARCH_API_KEY', '') or '')
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    try:
        response = requests.post(
            f'{url}/multi-search',
            json={'queries': [
                {'indexUid': 'public_blog', 'q': query, 'limit': limit},
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
        return {'results': [], 'degraded': True, 'reason': f'meilsearch_unavailable:{type(exc).__name__}'}

