import hashlib
import json
import logging
import math
import os
import re
import requests
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from django.conf import settings
from django.db import connections, transaction
from django.db.models import F, Max, Q
from django.utils import timezone
from openai import OpenAI
from system.ai_config import resolve_ai_config
from system.model_gateway import ModelGateway
from system.models import AIModel

from .models import KnowledgeChunk, KnowledgeChunkDraft, KnowledgeDocument, KnowledgeDocumentRevision

logger = logging.getLogger(__name__)


DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120
PARENT_MAX_TOKENS = 1800
CHILD_MAX_TOKENS = 700
CHILD_MIN_TOKENS = 120
CHILD_OVERLAP_TOKENS = 100
RRF_K = 60
MEILI_TIMEOUT_SECONDS = 3


class RequiredRAGContextUnavailable(RuntimeError):
    """Recoverable stop used when an interview template requires grounded generation."""


def split_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    text = re.sub(r'\s+', ' ', (text or '').strip())
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


def _normalize_terms(values: Iterable[str] | None) -> list[str]:
    terms = []
    for value in values or []:
        if value is None:
            continue
        value = str(value).strip().lower()
        if value:
            terms.append(value)
    return terms


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r'[\w\u4e00-\u9fff]+', (text or '').lower()))


def _keyword_terms(text: str) -> list[str]:
    try:
        import jieba
        words = list(jieba.cut(text or ''))
    except Exception:
        words = re.findall(r'[\w\u4e00-\u9fff]+', text or '')
    terms = []
    for word in words:
        word = str(word).strip().lower()
        if len(word) > 1:
            terms.append(word)
    return terms


def _estimate_tokens(text: str) -> int:
    text = text or ''
    cjk = len(re.findall(r'[\u4e00-\u9fff]', text))
    non_cjk_terms = len(re.findall(r'[A-Za-z0-9_]+', text))
    return max(1, cjk + non_cjk_terms)


def _embedding_client(user=None) -> tuple[OpenAI | None, str]:
    resolved = resolve_ai_config(user, AIModel.ModelType.EMBEDDING)
    model = resolved.model
    api_key = resolved.api_key or getattr(settings, 'EMBEDDING_API_KEY', '') or os.getenv('EMBEDDING_API_KEY')
    if not api_key:
        return None, ''
    base_url = (model.base_url if model else '') or getattr(settings, 'EMBEDDING_BASE_URL', '') or os.getenv('EMBEDDING_BASE_URL') or None
    model_slug = (model.model_slug if model else '') or getattr(settings, 'EMBEDDING_MODEL', 'text-embedding-v3')
    return OpenAI(api_key=api_key, base_url=base_url), model_slug


def _embed_text(text: str, user=None) -> tuple[list[float] | None, str]:
    try:
        vector, model_slug, _snapshot = ModelGateway(user).embed_text(text)
        return vector, model_slug
    except Exception as exc:
        raise exc


def _qdrant_client():
    url = getattr(settings, 'QDRANT_URL', '') or os.getenv('QDRANT_URL')
    if not url:
        return None
    try:
        from qdrant_client import QdrantClient
    except Exception:
        logger.warning('qdrant-client is not installed; knowledge search will use SQL fallback.')
        return None
    return QdrantClient(url=url)


def _qdrant_vector_size(collection_info) -> int | None:
    vectors = getattr(getattr(getattr(collection_info, 'config', None), 'params', None), 'vectors', None)
    if isinstance(vectors, dict):
        vectors = next(iter(vectors.values()), None)
    return getattr(vectors, 'size', None)


def _qdrant_alias_target(client, alias_name: str) -> str:
    response = client.get_aliases()
    for item in getattr(response, 'aliases', []) or []:
        if getattr(item, 'alias_name', '') == alias_name:
            return str(getattr(item, 'collection_name', '') or '')
    return ''


def _create_qdrant_physical_collection(client, alias_name: str, vector_size: int) -> str:
    from qdrant_client.models import Distance, VectorParams

    suffix = timezone.now().strftime('%Y%m%d%H%M%S%f')
    physical_name = f'{alias_name}_d{vector_size}_{suffix}'
    client.create_collection(
        collection_name=physical_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    return physical_name


def _ensure_qdrant_collection(client, vector_size: int) -> tuple[str, bool]:
    """Return a writable physical collection and whether its alias must be switched.

    Only a confirmed missing collection leads to creation. Transport, auth, and timeout
    failures propagate and can never trigger a destructive recreate.
    """
    alias_name = getattr(settings, 'QDRANT_COLLECTION', 'interview_knowledge')
    alias_target = _qdrant_alias_target(client, alias_name)
    if alias_target:
        info = client.get_collection(alias_target)
        if _qdrant_vector_size(info) == vector_size:
            return alias_target, False
        raise RuntimeError(
            f'Qdrant alias {alias_name} targets dimension {_qdrant_vector_size(info)}; '
            f'run a full collection rebuild before switching to {vector_size}.'
        )

    if client.collection_exists(alias_name):
        info = client.get_collection(alias_name)
        existing_size = _qdrant_vector_size(info)
        if existing_size != vector_size:
            raise RuntimeError(
                f'Qdrant legacy physical collection {alias_name} has dimension '
                f'{existing_size}; migrate it to an alias before changing to {vector_size}.'
            )
        return alias_name, False
    return _create_qdrant_physical_collection(client, alias_name, vector_size), True


def _switch_qdrant_alias(client, physical_name: str) -> None:
    from qdrant_client.models import (
        CreateAlias,
        CreateAliasOperation,
        DeleteAlias,
        DeleteAliasOperation,
    )

    alias_name = getattr(settings, 'QDRANT_COLLECTION', 'interview_knowledge')
    operations = []
    if _qdrant_alias_target(client, alias_name):
        operations.append(DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias_name)))
    operations.append(CreateAliasOperation(
        create_alias=CreateAlias(collection_name=physical_name, alias_name=alias_name),
    ))
    client.update_collection_aliases(
        change_aliases_operations=operations,
    )


def _upsert_qdrant_chunk(
    client,
    chunk: KnowledgeChunk,
    vector: list[float],
    *,
    collection_name: str | None = None,
) -> None:
    collection = collection_name or getattr(settings, 'QDRANT_COLLECTION', 'interview_knowledge')
    from qdrant_client.models import PointStruct
    payload = {
        'chunk_id': str(chunk.id),
        'document_id': str(chunk.document_id),
        'revision_id': str(chunk.revision_id) if chunk.revision_id else '',
        'title': chunk.document.title,
        'job_positions': chunk.document.job_positions,
        'ability_tags': chunk.document.ability_tags,
        'difficulty': chunk.document.difficulty,
        'source_type': chunk.document.source_type,
        'visibility': chunk.document.visibility,
        'approval_status': chunk.document.approval_status,
        'owner_user_id': chunk.document.created_by_id,
        'chunk_level': chunk.chunk_level,
        'heading_path': chunk.heading_path,
        'page_start': chunk.page_start,
        'page_end': chunk.page_end,
        'block_type': chunk.block_type,
    }
    client.upsert(
        collection_name=collection,
        points=[PointStruct(id=str(chunk.qdrant_point_id), vector=vector, payload=payload)],
    )


def _meili_headers() -> dict:
    api_key = getattr(settings, 'MEILISEARCH_API_KEY', '') or os.getenv('MEILISEARCH_API_KEY', '')
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    return headers


def _meili_base_url() -> str:
    return (getattr(settings, 'MEILISEARCH_URL', '') or os.getenv('MEILISEARCH_URL', '')).rstrip('/')


def _meili_index_name() -> str:
    return getattr(settings, 'MEILISEARCH_KNOWLEDGE_INDEX', 'interview_knowledge_chunks')


def _wait_for_meili_task(response, *, timeout_seconds: int = 15) -> None:
    """Wait until an asynchronous Meilisearch mutation is durably applied."""
    response.raise_for_status()
    payload = response.json() or {}
    task_uid = payload.get('taskUid') or payload.get('uid')
    if task_uid is None:
        return
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        task_response = requests.get(
            f'{_meili_base_url()}/tasks/{task_uid}',
            headers=_meili_headers(),
            timeout=MEILI_TIMEOUT_SECONDS,
        )
        task_response.raise_for_status()
        task = task_response.json() or {}
        status = task.get('status')
        if status == 'succeeded':
            return
        if status in {'failed', 'canceled'}:
            error = task.get('error') or {}
            raise RuntimeError(
                f'Meilisearch task {task_uid} {status}: '
                f'{error.get("message") or error or "unknown error"}'
            )
        time.sleep(0.05)
    raise TimeoutError(f'Meilisearch task {task_uid} did not finish within {timeout_seconds}s.')


def _ensure_meili_knowledge_index() -> None:
    base_url = _meili_base_url()
    if not base_url:
        raise RuntimeError('Meilisearch URL is not configured.')
    headers = _meili_headers()
    index_name = _meili_index_name()
    response = requests.get(
        f'{base_url}/indexes/{index_name}',
        headers=headers,
        timeout=MEILI_TIMEOUT_SECONDS,
    )
    if response.status_code == 404:
        created = requests.post(
            f'{base_url}/indexes',
            headers=headers,
            data=json.dumps({'uid': index_name, 'primaryKey': 'chunk_id'}),
            timeout=MEILI_TIMEOUT_SECONDS,
        )
        _wait_for_meili_task(created)
    else:
        response.raise_for_status()
    settings_response = requests.patch(
        f'{base_url}/indexes/{index_name}/settings',
        headers=headers,
        data=json.dumps({
            'searchableAttributes': ['content', 'heading_text', 'title', 'ability_tags', 'job_positions'],
            'filterableAttributes': [
                'document_id', 'revision_id', 'visibility', 'approval_status',
                'owner_user_id', 'difficulty', 'job_positions', 'chunk_level',
            ],
        }),
        timeout=MEILI_TIMEOUT_SECONDS,
    )
    _wait_for_meili_task(settings_response)


def _meili_chunk_document(chunk: KnowledgeChunk) -> dict:
    document = chunk.document
    return {
        'chunk_id': str(chunk.id),
        'parent_chunk_id': str(chunk.parent_chunk_id or ''),
        'chunk_index': chunk.chunk_index,
        'document_id': str(chunk.document_id),
        'revision_id': str(chunk.revision_id or ''),
        'title': document.title,
        'content': chunk.content,
        'heading_text': ' / '.join(chunk.heading_path or []),
        'ability_tags': document.ability_tags or [],
        'job_positions': document.job_positions or [],
        'difficulty': document.difficulty,
        'visibility': document.visibility,
        'approval_status': document.approval_status,
        'owner_user_id': str(document.created_by_id or ''),
        'chunk_level': chunk.chunk_level,
    }


def _upsert_meili_chunks(chunks: list[KnowledgeChunk]) -> None:
    if not chunks:
        return
    _ensure_meili_knowledge_index()
    response = requests.post(
        f'{_meili_base_url()}/indexes/{_meili_index_name()}/documents',
        headers=_meili_headers(),
        data=json.dumps([_meili_chunk_document(chunk) for chunk in chunks], ensure_ascii=False),
        timeout=max(MEILI_TIMEOUT_SECONDS, 10),
    )
    _wait_for_meili_task(response, timeout_seconds=30)


def rebuild_qdrant_collection(*, user=None) -> dict:
    """Build every published child chunk in a new collection, then atomically switch the alias."""
    client = _qdrant_client()
    if not client:
        raise RuntimeError('Qdrant is not configured or qdrant-client is unavailable.')
    chunks = list(
        KnowledgeChunk.objects.select_related('document').filter(
            document__approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
            document__status=KnowledgeDocument.Status.INDEXED,
            revision=F('document__published_revision'),
            chunk_level=2,
        ).order_by('document_id', 'chunk_index')
    )
    if not chunks:
        raise RuntimeError('No published knowledge chunks are available for a full rebuild.')

    target = ''
    vector_size = 0
    indexed = 0
    model_slug = ''
    for chunk in chunks:
        vector, resolved_model = _embed_text(chunk.content, user=user or chunk.document.created_by)
        if not vector:
            raise RuntimeError(f'Embedding returned no vector for chunk {chunk.id}.')
        if not target:
            vector_size = len(vector)
            target = _create_qdrant_physical_collection(
                client,
                getattr(settings, 'QDRANT_COLLECTION', 'interview_knowledge'),
                vector_size,
            )
        elif len(vector) != vector_size:
            raise RuntimeError(
                f'Embedding dimension changed during rebuild: expected {vector_size}, got {len(vector)}.'
            )
        _upsert_qdrant_chunk(client, chunk, vector, collection_name=target)
        indexed += 1
        model_slug = resolved_model or model_slug

    info = client.get_collection(target)
    point_count = int(getattr(info, 'points_count', 0) or 0)
    if point_count < indexed:
        raise RuntimeError(
            f'Qdrant rebuild validation failed: expected {indexed} points, found {point_count}.'
        )
    _switch_qdrant_alias(client, target)
    return {
        'collection': target,
        'alias': getattr(settings, 'QDRANT_COLLECTION', 'interview_knowledge'),
        'indexed_points': indexed,
        'vector_size': vector_size,
        'embedding_model': model_slug,
    }


def index_document(document: KnowledgeDocument, revision: KnowledgeDocumentRevision | None = None) -> KnowledgeDocument:
    if revision is None and document.draft_revision_id and document.draft_revision.status == KnowledgeDocumentRevision.Status.APPROVED:
        revision = document.draft_revision
    revision = revision or document.published_revision or document.draft_revision
    if not revision and document.approval_status == KnowledgeDocument.ApprovalStatus.APPROVED:
        revision = create_document_revision(document, document.created_by)
        revision.status = KnowledgeDocumentRevision.Status.APPROVED
        revision.approved_by = document.approved_by
        revision.approved_at = document.approved_at or timezone.now()
        revision.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    if not revision or revision.status not in {
        KnowledgeDocumentRevision.Status.APPROVED,
        KnowledgeDocumentRevision.Status.PUBLISHED,
    }:
        document.status = KnowledgeDocument.Status.DRAFT
        document.error_message = '知识库版本必须审批通过后才能建立上线索引。'
        document.save(update_fields=['status', 'error_message', 'updated_at'])
        raise ValueError(document.error_message)

    document.status = KnowledgeDocument.Status.INDEXING
    document.error_message = ''
    document.save(update_fields=['status', 'error_message', 'updated_at'])
    document.chunks.filter(revision=revision).delete()

    chunk_specs = build_structured_chunk_specs(document, revision=revision)
    client = _qdrant_client()
    embedding_model = getattr(settings, 'EMBEDDING_MODEL', 'text-embedding-v3')
    embedding_errors = []
    keyword_index_errors = []
    qdrant_target = ''
    qdrant_alias_switch_pending = False
    searchable_chunks: list[KnowledgeChunk] = []

    try:
        indexed_count = 0
        chunk_index = 0
        for parent_spec in chunk_specs:
            parent_hash = hashlib.sha256(parent_spec['content'].encode('utf-8')).hexdigest()
            parent_chunk = KnowledgeChunk.objects.create(
                document=document,
                revision=revision,
                chunk_index=chunk_index,
                chunk_level=1,
                heading_path=parent_spec.get('heading_path') or [],
                page_start=parent_spec.get('page_start'),
                page_end=parent_spec.get('page_end'),
                block_type=parent_spec.get('block_type') or 'section',
                token_count=_estimate_tokens(parent_spec['content']),
                content_hash=parent_hash,
                semantic_group_id=parent_hash[:16],
                content=parent_spec['content'],
                metadata={
                    'title': document.title,
                    'job_positions': document.job_positions,
                    'ability_tags': document.ability_tags,
                    'difficulty': document.difficulty,
                    'source_type': document.source_type,
                    'visibility': document.visibility,
                    'approval_status': document.approval_status,
                    'owner_user_id': document.created_by_id,
                    'heading_path': parent_spec.get('heading_path') or [],
                    'page_start': parent_spec.get('page_start'),
                    'page_end': parent_spec.get('page_end'),
                    'block_type': parent_spec.get('block_type') or 'section',
                    'content_hash': parent_hash,
                },
            )
            chunk_index += 1
            indexed_count += 1
            child_texts = recursive_split(parent_spec['content'], max_tokens=CHILD_MAX_TOKENS, overlap_tokens=CHILD_OVERLAP_TOKENS)
            child_texts = semantic_merge_short_chunks(child_texts, min_tokens=CHILD_MIN_TOKENS, max_tokens=CHILD_MAX_TOKENS)
            for child_content in child_texts:
                content_hash = hashlib.sha256(child_content.encode('utf-8')).hexdigest()
                chunk = KnowledgeChunk.objects.create(
                    document=document,
                    revision=revision,
                    parent_chunk=parent_chunk,
                    chunk_index=chunk_index,
                    chunk_level=2,
                    heading_path=parent_spec.get('heading_path') or [],
                    page_start=parent_spec.get('page_start'),
                    page_end=parent_spec.get('page_end'),
                    block_type=parent_spec.get('block_type') or 'section',
                    token_count=_estimate_tokens(child_content),
                    content_hash=content_hash,
                    semantic_group_id=parent_hash[:16],
                    content=child_content,
                    metadata={
                        'title': document.title,
                        'job_positions': document.job_positions,
                        'ability_tags': document.ability_tags,
                        'difficulty': document.difficulty,
                        'source_type': document.source_type,
                        'visibility': document.visibility,
                        'approval_status': document.approval_status,
                        'owner_user_id': document.created_by_id,
                        'heading_path': parent_spec.get('heading_path') or [],
                        'page_start': parent_spec.get('page_start'),
                        'page_end': parent_spec.get('page_end'),
                        'block_type': parent_spec.get('block_type') or 'section',
                        'content_hash': content_hash,
                        'parent_content_hash': parent_hash,
                    },
                )
                try:
                    vector, resolved_embedding_model = _embed_text(child_content, user=document.created_by)
                except Exception as exc:
                    vector, resolved_embedding_model = None, ''
                    if len(embedding_errors) < 3:
                        embedding_errors.append(str(exc)[:500])
                embedding_model = resolved_embedding_model or embedding_model
                if client and vector:
                    if not qdrant_target:
                        qdrant_target, qdrant_alias_switch_pending = _ensure_qdrant_collection(
                            client, len(vector),
                        )
                    _upsert_qdrant_chunk(
                        client,
                        chunk,
                        vector,
                        collection_name=qdrant_target,
                    )
                    chunk.embedding_model = embedding_model
                chunk.indexed_at = timezone.now()
                chunk.save(update_fields=['embedding_model', 'indexed_at'])
                searchable_chunks.append(chunk)
                chunk_index += 1
                indexed_count += 1

        if client and qdrant_target:
            client.get_collection(qdrant_target)
            if qdrant_alias_switch_pending:
                _switch_qdrant_alias(client, qdrant_target)
        try:
            _upsert_meili_chunks(searchable_chunks)
        except Exception as exc:
            keyword_index_errors.append(str(exc)[:500])
            logger.warning('Meilisearch indexing unavailable; SQL fallback remains available: %s', exc)

        previous_revision = document.published_revision
        if previous_revision and previous_revision.id != revision.id:
            previous_revision.status = KnowledgeDocumentRevision.Status.SUPERSEDED
            previous_revision.save(update_fields=['status', 'updated_at'])
        revision.status = KnowledgeDocumentRevision.Status.PUBLISHED
        revision.published_at = timezone.now()
        revision.save(update_fields=['status', 'published_at', 'updated_at'])
        document.status = KnowledgeDocument.Status.INDEXED
        document.approval_status = KnowledgeDocument.ApprovalStatus.APPROVED
        document.published_revision = revision
        document.chunk_count = indexed_count
        document.last_indexed_at = timezone.now()
        document.error_message = (
            ' | '.join(filter(None, [
                (
                    'Embedding unavailable; indexed for keyword/BM25 fallback only: '
                    + ' | '.join(embedding_errors)
                ) if embedding_errors else '',
                (
                    'Meilisearch unavailable; SQL fallback enabled: '
                    + ' | '.join(keyword_index_errors)
                ) if keyword_index_errors else '',
            ]))
        )[:2000]
        document.save(update_fields=[
            'status', 'approval_status', 'published_revision', 'chunk_count',
            'last_indexed_at', 'error_message', 'updated_at',
        ])
        return document
    except Exception as exc:
        document.status = KnowledgeDocument.Status.FAILED
        document.error_message = str(exc)[:2000]
        document.save(update_fields=['status', 'error_message', 'updated_at'])
        raise


def build_structured_chunk_specs(
    document: KnowledgeDocument,
    revision: KnowledgeDocumentRevision | None = None,
) -> list[dict]:
    if revision and revision.chunk_drafts.exists():
        return [
            {
                'content': chunk.content,
                'heading_path': chunk.heading_path,
                'page_start': chunk.page_start,
                'page_end': chunk.page_end,
                'block_type': chunk.block_type,
                'metadata': chunk.metadata,
            }
            for chunk in revision.chunk_drafts.filter(is_excluded=False).order_by('order')
            if chunk.content.strip()
        ]
    parsed = (revision.parsed_content if revision else document.parsed_content) or {}
    blocks = parsed.get('blocks') or []
    specs = []
    if blocks:
        for block in blocks:
            text = (block.get('text') or '').strip()
            if not text:
                continue
            block_type = block.get('block_type') or 'paragraph'
            heading_path = block.get('heading_path') or []
            if block_type == 'heading':
                continue
            specs.append({
                'content': text,
                'heading_path': heading_path,
                'page_start': block.get('page_start'),
                'page_end': block.get('page_end'),
                'block_type': block_type,
                'metadata': block.get('metadata') or {},
            })
    else:
        for index, text in enumerate(split_text(document.content, chunk_size=1600, overlap=160)):
            specs.append({
                'content': text,
                'heading_path': [document.title],
                'page_start': None,
                'page_end': None,
                'block_type': 'legacy_text' if index else 'section',
            })
    return merge_parent_specs(specs)


def merge_parent_specs(specs: list[dict], max_tokens: int = PARENT_MAX_TOKENS) -> list[dict]:
    merged = []
    current = None
    for spec in specs:
        if not current:
            current = dict(spec)
            continue
        same_path = current.get('heading_path') == spec.get('heading_path')
        same_type = current.get('block_type') == spec.get('block_type') and spec.get('block_type') not in {'table', 'faq', 'ocr'}
        combined = f"{current['content']}\n\n{spec['content']}"
        if same_path and same_type and _estimate_tokens(combined) <= max_tokens:
            current['content'] = combined
            current['page_end'] = spec.get('page_end') or current.get('page_end')
        else:
            merged.append(current)
            current = dict(spec)
    if current:
        merged.append(current)
    return merged


def recursive_split(text: str, max_tokens: int = CHILD_MAX_TOKENS, overlap_tokens: int = CHILD_OVERLAP_TOKENS) -> list[str]:
    text = (text or '').strip()
    if not text:
        return []
    if _estimate_tokens(text) <= max_tokens:
        return [text]
    separators = ['\n\n', '\n', '。', '；', ';', '.', '，', ',']
    parts = [text]
    for separator in separators:
        next_parts = []
        changed = False
        for part in parts:
            if _estimate_tokens(part) <= max_tokens:
                next_parts.append(part)
                continue
            split_parts = [item.strip() for item in part.split(separator) if item.strip()]
            if len(split_parts) > 1:
                changed = True
                next_parts.extend(split_parts)
            else:
                next_parts.append(part)
        parts = next_parts
        if changed and all(_estimate_tokens(part) <= max_tokens for part in parts):
            break

    chunks = []
    buffer = ''
    for part in parts:
        candidate = f'{buffer}\n{part}'.strip() if buffer else part
        if _estimate_tokens(candidate) <= max_tokens:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer)
        if _estimate_tokens(part) <= max_tokens:
            buffer = part
        else:
            chars_per_token = max(1, len(part) // max(_estimate_tokens(part), 1))
            char_limit = max_tokens * chars_per_token
            overlap_chars = overlap_tokens * chars_per_token
            start = 0
            while start < len(part):
                end = min(len(part), start + char_limit)
                chunks.append(part[start:end].strip())
                if end >= len(part):
                    break
                start = max(0, end - overlap_chars)
            buffer = ''
    if buffer:
        chunks.append(buffer)
    return [chunk for chunk in chunks if chunk]


def semantic_merge_short_chunks(chunks: list[str], min_tokens: int = CHILD_MIN_TOKENS, max_tokens: int = CHILD_MAX_TOKENS) -> list[str]:
    merged = []
    buffer = ''
    for chunk in chunks:
        if not buffer:
            buffer = chunk
            continue
        candidate = f'{buffer}\n\n{chunk}'
        if _estimate_tokens(buffer) < min_tokens and _estimate_tokens(candidate) <= max_tokens:
            buffer = candidate
        else:
            merged.append(buffer)
            buffer = chunk
    if buffer:
        merged.append(buffer)
    return merged


def materialize_revision_drafts(revision: KnowledgeDocumentRevision) -> KnowledgeDocumentRevision:
    revision.chunk_drafts.all().delete()
    document = revision.document
    original_parsed = document.parsed_content
    document.parsed_content = revision.parsed_content or {}
    try:
        specs = build_structured_chunk_specs(document)
    finally:
        document.parsed_content = original_parsed

    order = 0
    for spec in specs:
        block_type = spec.get('block_type') or 'paragraph'
        contents = [spec['content']] if block_type in {'table', 'faq'} else recursive_split(
            spec['content'], max_tokens=CHILD_MAX_TOKENS, overlap_tokens=CHILD_OVERLAP_TOKENS
        )
        contents = semantic_merge_short_chunks(contents)
        for content in contents:
            content = content.strip()
            if not content:
                continue
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            KnowledgeChunkDraft.objects.create(
                revision=revision,
                order=order,
                block_type=block_type,
                heading_path=spec.get('heading_path') or [],
                page_start=spec.get('page_start'),
                page_end=spec.get('page_end'),
                content=content,
                table_data=(spec.get('metadata') or {}).get('table_data') or [],
                metadata=spec.get('metadata') or {},
                token_count=_estimate_tokens(content),
                content_hash=content_hash,
            )
            order += 1
    return revision


@transaction.atomic
def create_document_revision(
    document: KnowledgeDocument,
    user=None,
    *,
    parsed_content: dict | None = None,
    source_content: str | None = None,
) -> KnowledgeDocumentRevision:
    next_version = (
        KnowledgeDocumentRevision.objects.filter(document=document)
        .aggregate(value=Max('version_number'))['value'] or 0
    ) + 1
    revision = KnowledgeDocumentRevision.objects.create(
        document=document,
        version_number=next_version,
        status=KnowledgeDocumentRevision.Status.DRAFT,
        source_content=document.content if source_content is None else source_content,
        parsed_content=document.parsed_content if parsed_content is None else parsed_content,
        parser_snapshot={
            'parser_name': document.parser_name,
            'parser_version': document.parser_version,
            'parser_fallback_reason': document.parser_fallback_reason,
            'ocr_enabled': document.ocr_enabled,
        },
        created_by=user or document.created_by,
    )
    materialize_revision_drafts(revision)
    document.draft_revision = revision
    document.save(update_fields=['draft_revision', 'updated_at'])
    return revision


def build_preview_parsed_content(content: str, title: str = '切块预览') -> dict:
    """Build lightweight structured blocks for text entered before a document exists."""
    blocks = []
    heading_path: list[str] = []
    buffer: list[str] = []
    table_buffer: list[str] = []

    def flush_buffer(block_type: str = 'paragraph'):
        nonlocal buffer
        text = '\n'.join(item for item in buffer if item).strip()
        if text:
            blocks.append({
                'block_type': block_type,
                'text': text,
                'heading_path': list(heading_path) or ([title] if title else []),
                'page_start': None,
                'page_end': None,
                'metadata': {},
            })
        buffer = []

    def flush_table():
        nonlocal table_buffer
        text = '\n'.join(item for item in table_buffer if item).strip()
        if text:
            blocks.append({
                'block_type': 'table',
                'text': text,
                'heading_path': list(heading_path) or ([title] if title else []),
                'page_start': None,
                'page_end': None,
                'metadata': {'format': 'markdown_table'},
            })
        table_buffer = []

    for line in (content or '').splitlines():
        stripped = line.strip()
        if not stripped:
            flush_table()
            flush_buffer()
            continue
        if stripped.startswith('#'):
            flush_table()
            flush_buffer()
            level = len(stripped) - len(stripped.lstrip('#'))
            heading = stripped[level:].strip()
            heading_path[:] = heading_path[:max(level - 1, 0)]
            heading_path.append(heading)
            blocks.append({
                'block_type': 'heading',
                'text': heading,
                'heading_path': list(heading_path),
                'page_start': None,
                'page_end': None,
                'metadata': {'level': level},
            })
            continue
        if stripped.startswith('|') and stripped.endswith('|'):
            flush_buffer()
            table_buffer.append(stripped)
            continue
        flush_table()
        buffer.append(stripped)
    flush_table()
    flush_buffer()

    if not blocks and (content or '').strip():
        blocks.append({
            'block_type': 'paragraph',
            'text': content.strip(),
            'heading_path': [title] if title else [],
            'page_start': None,
            'page_end': None,
            'metadata': {},
        })
    return {
        'parser_name': 'preview_text',
        'parser_version': '',
        'blocks': blocks,
    }


def build_chunk_preview(
    document: KnowledgeDocument,
    *,
    child_max_tokens: int = CHILD_MAX_TOKENS,
    overlap_tokens: int = CHILD_OVERLAP_TOKENS,
) -> dict:
    child_max_tokens = max(120, int(child_max_tokens or CHILD_MAX_TOKENS))
    overlap_tokens = max(0, min(int(overlap_tokens or CHILD_OVERLAP_TOKENS), child_max_tokens // 2))
    parents = []
    flat_chunks = []
    flat_index = 0
    for parent_index, spec in enumerate(build_structured_chunk_specs(document)):
        children = semantic_merge_short_chunks(
            recursive_split(spec['content'], max_tokens=child_max_tokens, overlap_tokens=overlap_tokens),
            min_tokens=min(CHILD_MIN_TOKENS, child_max_tokens),
            max_tokens=child_max_tokens,
        )
        parent_preview = {
            'parent_index': parent_index,
            'block_type': spec.get('block_type'),
            'heading_path': spec.get('heading_path') or [],
            'page_start': spec.get('page_start'),
            'page_end': spec.get('page_end'),
            'token_count': _estimate_tokens(spec['content']),
            'content': spec['content'][:1200],
            'child_count': len(children),
            'children': [],
        }
        for child_index, child in enumerate(children):
            child_preview = {
                'chunk_index': flat_index,
                'parent_index': parent_index,
                'child_index': child_index,
                'block_type': spec.get('block_type'),
                'heading_path': spec.get('heading_path') or [],
                'page_start': spec.get('page_start'),
                'page_end': spec.get('page_end'),
                'token_count': _estimate_tokens(child),
                'content': child[:900],
                'length': len(child),
            }
            parent_preview['children'].append(child_preview)
            flat_chunks.append(child_preview)
            flat_index += 1
        parents.append(parent_preview)
    return {
        'strategy': 'hierarchical_recursive_semantic',
        'parent_count': len(parents),
        'chunk_count': len(flat_chunks),
        'parents': parents,
        'chunks': flat_chunks,
    }


def build_retrieval_query(
    job_position: str,
    current_stage: str = '',
    pending_topics: list | None = None,
    last_evaluation: dict | None = None,
    jd_text: str = '',
) -> str:
    last_evaluation = last_evaluation or {}
    return '\n'.join(filter(None, [
        f'岗位: {job_position}',
        f'当前阶段: {current_stage}',
        f'待追问话题: {", ".join(pending_topics or [])}',
        f'上一题追问目标: {last_evaluation.get("follow_up_target", "")}',
        f'上一题反馈: {last_evaluation.get("feedback", "")}',
        f'JD摘要: {(jd_text or "")[:1200]}',
    ]))


def build_multi_queries(
    job_position: str,
    current_stage: str = '',
    pending_topics: list | None = None,
    last_evaluation: dict | None = None,
    jd_text: str = '',
) -> list[str]:
    base = build_retrieval_query(job_position, current_stage, pending_topics, last_evaluation, jd_text)
    last_evaluation = last_evaluation or {}
    queries = [
        base,
        f'{job_position} {" ".join(pending_topics or [])}',
        f'{current_stage} {last_evaluation.get("follow_up_target", "")}',
        f'{last_evaluation.get("feedback", "")} {last_evaluation.get("risk_flags", "")}',
    ]
    if jd_text:
        queries.append(f'{job_position} JD 要求 {(jd_text or "")[:800]}')
    normalized = []
    for query in queries:
        query = re.sub(r'\s+', ' ', str(query or '')).strip()
        if query and query not in normalized:
            normalized.append(query)
    return normalized[:5]


def _plan_registered_queries(
    *,
    fallback_queries: list[str],
    query_count: int,
    agent_config_snapshot: dict | None,
    user=None,
    job_position: str = '',
    current_stage: str = '',
    pending_topics: list | None = None,
    last_evaluation: dict | None = None,
    jd_text: str = '',
) -> tuple[list[str], dict]:
    trace = {'status': 'heuristic', 'prompt_hash': '', 'error': ''}
    if not ((agent_config_snapshot or {}).get('prompts') or {}).get('rag.query_planner'):
        return fallback_queries[:query_count], trace
    try:
        from interviews.configuration import render_registered_prompt, validate_prompt_output

        rendered = render_registered_prompt(
            agent_config_snapshot,
            'rag.query_planner',
            {
                'context_json': json.dumps({
                    'job_position': job_position,
                    'current_stage': current_stage,
                    'pending_topics': pending_topics or [],
                    'last_evaluation': last_evaluation or {},
                    'job_description': jd_text or '',
                }, ensure_ascii=False),
                'query_count': query_count,
            },
        )
        if not rendered:
            return fallback_queries[:query_count], trace
        messages, metadata = rendered
        result = ModelGateway(user).chat_json(
            messages,
            max_tokens=metadata['max_output_tokens'],
            temperature=metadata['temperature'],
            alias_slug=metadata.get('model_alias') or 'chat.default',
        )
        validate_prompt_output(result, metadata.get('output_contract'))
        queries = []
        for value in result.get('queries') or []:
            query = re.sub(r'\s+', ' ', str(value or '')).strip()
            if query and query not in queries:
                queries.append(query[:1000])
        if not queries:
            raise ValueError('query planner returned no usable queries')
        return queries[:query_count], {
            'status': 'model',
            'prompt_hash': metadata.get('prompt_hash') or '',
            'retrieval_intent': bool(result.get('retrieval_intent', True)),
            'error': '',
        }
    except Exception as exc:
        logger.warning('Registered RAG query planner failed; using deterministic fallback: %s', exc)
        trace.update({'status': 'degraded', 'error': str(exc)[:300]})
        return fallback_queries[:query_count], trace


def _retrieval_scopes(agent_config_snapshot: dict | None) -> list[dict]:
    snapshot = agent_config_snapshot or {}
    bindings = snapshot.get('knowledge_bindings') or []
    if snapshot.get('source') == 'control_plane':
        scopes = []
        for binding in bindings:
            documents = binding.get('documents') or []
            scopes.append({
                'knowledge_base_id': str(binding.get('knowledge_base_id') or ''),
                'knowledge_base_revision_id': str(binding.get('knowledge_base_revision_id') or ''),
                'document_ids': {
                    str(item.get('document_id')) for item in documents if item.get('document_id')
                },
                'revision_ids': {
                    str(item.get('revision_id')) for item in documents if item.get('revision_id')
                },
                'retrieval_config': dict(binding.get('retrieval_config') or {}),
            })
        return scopes
    return [{
        'knowledge_base_id': '',
        'knowledge_base_revision_id': '',
        'document_ids': set(),
        'revision_ids': set(),
        'retrieval_config': {},
    }]


def _scope_allows_chunk(chunk: KnowledgeChunk, scope: dict | None) -> bool:
    scope = scope or {}
    document_ids = scope.get('document_ids') or set()
    revision_ids = scope.get('revision_ids') or set()
    if document_ids and str(chunk.document_id) not in document_ids:
        return False
    if revision_ids and str(chunk.revision_id or '') not in revision_ids:
        return False
    return True


def _tenant_document_filter(user=None):
    approved_filter = Q(
        document__approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
        document__status=KnowledgeDocument.Status.INDEXED,
    )
    if user and getattr(user, 'is_staff', False):
        return approved_filter
    public_filter = Q(document__visibility=KnowledgeDocument.Visibility.PUBLIC)
    if user and getattr(user, 'is_authenticated', False):
        return approved_filter & (public_filter | Q(
            document__visibility=KnowledgeDocument.Visibility.PRIVATE,
            document__created_by=user,
        ))
    return approved_filter & public_filter


def _tenant_document_allowed(document: KnowledgeDocument, user=None) -> bool:
    if user and getattr(user, 'is_staff', False):
        return True
    if document.visibility == KnowledgeDocument.Visibility.PUBLIC:
        return True
    return bool(user and getattr(user, 'is_authenticated', False) and document.created_by_id == user.id)


def _matches_document(document: KnowledgeDocument, job_position: str, pending_topics: list | None, difficulty: str = '', user=None) -> bool:
    if document.approval_status != KnowledgeDocument.ApprovalStatus.APPROVED:
        return False
    if document.status != KnowledgeDocument.Status.INDEXED:
        return False
    if not _tenant_document_allowed(document, user):
        return False
    job_terms = _normalize_terms(document.job_positions)
    target_job = (job_position or '').lower()

    job_ok = not job_terms or any(term in target_job or target_job in term for term in job_terms)
    difficulty_ok = document.difficulty in ('any', '', None) or not difficulty or document.difficulty == difficulty
    return job_ok and difficulty_ok


def _sql_fallback_search(
    query: str,
    job_position: str,
    user=None,
    current_stage: str = '',
    pending_topics: list | None = None,
    difficulty: str = '',
    exclude_chunk_ids: list | None = None,
    limit: int = 4,
    trace: dict | None = None,
    scope: dict | None = None,
) -> list[dict]:
    exclude_ids = {str(item) for item in (exclude_chunk_ids or [])}
    query_tokens = _tokenize(query)
    stage_tokens = _tokenize(current_stage)
    topic_tokens = _tokenize(' '.join(pending_topics or []))
    scored = []
    scanned_count = 0
    excluded_count = 0
    filter_counts = Counter()

    chunks_queryset = KnowledgeChunk.objects.select_related('document', 'parent_chunk').filter(
        _tenant_document_filter(user),
        document__status=KnowledgeDocument.Status.INDEXED,
    ).filter(
        Q(revision=F('document__published_revision'))
        | Q(revision__isnull=True, document__published_revision__isnull=True),
        chunk_level=2,
    )
    if scope and scope.get('document_ids'):
        chunks_queryset = chunks_queryset.filter(document_id__in=scope['document_ids'])
    if scope and scope.get('revision_ids'):
        chunks_queryset = chunks_queryset.filter(revision_id__in=scope['revision_ids'])
    chunks = chunks_queryset.order_by('-document__updated_at', 'chunk_index')[:300]
    for chunk in chunks:
        scanned_count += 1
        if str(chunk.id) in exclude_ids:
            excluded_count += 1
            continue
        document = chunk.document
        filter_reason = _candidate_filter_reason(
            chunk,
            job_position=job_position,
            pending_topics=pending_topics,
            difficulty=difficulty,
            user=user,
            scope=scope,
        )
        if filter_reason:
            filter_counts[filter_reason] += 1
            continue
        content_tokens = _tokenize(chunk.content)
        meta_tokens = _tokenize(' '.join(document.ability_tags or []) + ' ' + document.title)
        query_overlap = query_tokens & content_tokens
        topic_overlap = topic_tokens & (content_tokens | meta_tokens)
        stage_overlap = stage_tokens & (content_tokens | meta_tokens)
        score = len(query_overlap)
        score += 2 * len(topic_overlap)
        score += len(stage_overlap)
        metadata_boost = False
        if score <= 0 and (document.job_positions or document.ability_tags):
            score = 1
            metadata_boost = True
        scored.append((score, chunk, {
            'query_overlap': len(query_overlap),
            'topic_overlap': len(topic_overlap),
            'stage_overlap': len(stage_overlap),
            'metadata_boost': metadata_boost,
            'matched_terms': sorted(query_overlap | topic_overlap | stage_overlap)[:12],
        }))

    scored.sort(key=lambda item: item[0], reverse=True)
    contexts = []
    for score, chunk, score_detail in scored[:limit]:
        context = _context_from_chunk(chunk, score)
        context['sql_fallback_score_detail'] = score_detail
        contexts.append(context)
    if trace is not None:
        trace['sql_fallback'] = {
            'status': 'ok' if scored else 'empty',
            'scanned_count': scanned_count,
            'excluded_count': excluded_count,
            'candidate_count': len(scored),
            'returned_count': len(contexts),
            'filter_counts': dict(filter_counts),
            'top_matches': [
                {
                    'chunk_id': str(chunk.id),
                    'document_id': str(chunk.document_id),
                    'title': chunk.document.title,
                    'score': float(score),
                    'score_detail': score_detail,
                }
                for score, chunk, score_detail in scored[: min(limit, 5)]
            ],
        }
    return contexts


def _context_from_chunk(chunk: KnowledgeChunk, score: float) -> dict:
    document = chunk.document
    return {
        'document_id': str(document.id),
        'document_revision_id': str(chunk.revision_id or ''),
        'chunk_id': str(chunk.id),
        'parent_chunk_id': str(chunk.parent_chunk_id or ''),
        'semantic_group_id': chunk.semantic_group_id,
        'title': document.title,
        'source_type': document.source_type,
        'job_positions': document.job_positions,
        'ability_tags': document.ability_tags,
        'difficulty': document.difficulty,
        'visibility': document.visibility,
        'approval_status': document.approval_status,
        'heading_path': chunk.heading_path,
        'page_start': chunk.page_start,
        'page_end': chunk.page_end,
        'block_type': chunk.block_type,
        'chunk_level': chunk.chunk_level,
        'token_count': chunk.token_count,
        'score': float(score),
        'content': chunk.content,
        '_parent_content': chunk.parent_chunk.content if chunk.parent_chunk_id and chunk.parent_chunk else '',
        '_parent_token_count': (
            chunk.parent_chunk.token_count if chunk.parent_chunk_id and chunk.parent_chunk else 0
        ),
    }


def _mark_contexts_retrieved(contexts: list[dict]) -> None:
    document_ids = list({
        item.get('document_id')
        for item in contexts or []
        if item.get('document_id')
    })
    if not document_ids:
        return
    KnowledgeDocument.objects.filter(id__in=document_ids).update(
        last_retrieved_at=timezone.now(),
        retrieval_count=F('retrieval_count') + 1,
    )


def _rerank_contexts(query: str, contexts: list[dict], user=None, limit: int = 4, trace: dict | None = None) -> list[dict]:
    if not contexts:
        if trace is not None:
            trace['rerank'] = {'status': 'skipped', 'reason': 'no_candidates', 'candidate_count': 0}
        return []
    try:
        results, snapshot = ModelGateway(user).rerank(
            query,
            [item.get('content', '') for item in contexts],
            top_n=limit,
        )
        reranked = []
        for result in results:
            index = result.get('index')
            if index is None:
                continue
            if 0 <= int(index) < len(contexts):
                item = dict(contexts[int(index)])
                item['rerank_score'] = result.get('relevance_score') or result.get('score')
                reranked.append(item)
        if reranked:
            if trace is not None:
                trace['rerank'] = {
                    'status': 'ok',
                    'candidate_count': len(contexts),
                    'returned_count': len(reranked[:limit]),
                    'model': snapshot.get('model_slug', ''),
                    'provider': snapshot.get('provider', ''),
                    'endpoint': snapshot.get('endpoint', ''),
                    'top_scores': [
                        item.get('rerank_score')
                        for item in reranked[:limit]
                        if item.get('rerank_score') is not None
                    ],
                }
            return reranked[:limit]
    except Exception as exc:
        if trace is not None:
            trace['rerank'] = {
                'status': 'unavailable' if 'missing' in str(exc) else 'failed',
                'reason': str(exc)[:300],
                'candidate_count': len(contexts),
            }
        logger.warning('Rerank failed; keeping vector/SQL order: %s', exc)
    if trace is not None and 'rerank' not in trace:
        trace['rerank'] = {
            'status': 'empty_response',
            'candidate_count': len(contexts),
        }
    return contexts[:limit]


def _expand_parent_contexts(
    contexts: list[dict],
    *,
    enabled: bool,
    token_limit: int,
    limit: int,
) -> list[dict]:
    expanded = []
    seen_groups = set()
    used_tokens = 0
    for child in contexts:
        group_id = child.get('semantic_group_id') or child.get('parent_chunk_id') or child.get('chunk_id')
        if group_id in seen_groups:
            continue
        item = dict(child)
        retrieval_config = dict(item.pop('_retrieval_config', {}) or {})
        parent_content = item.pop('_parent_content', '') or ''
        parent_token_count = int(item.pop('_parent_token_count', 0) or 0)
        item_parent_expansion = bool(retrieval_config.get('parent_expansion', enabled))
        if item_parent_expansion and parent_content:
            item['matched_child_chunk_id'] = item.get('chunk_id')
            item['matched_child_content'] = item.get('content', '')
            item['chunk_id'] = item.get('parent_chunk_id') or item.get('chunk_id')
            item['chunk_level'] = 1
            item['content'] = parent_content
            item['token_count'] = parent_token_count or _estimate_tokens(parent_content)
            item['parent_expanded'] = True
        else:
            item['parent_expanded'] = False
        item_tokens = int(item.get('token_count') or _estimate_tokens(item.get('content', '')))
        if expanded and used_tokens + item_tokens > token_limit:
            continue
        if item_tokens > token_limit:
            item['content'] = _truncate_text_to_token_budget(item.get('content', ''), token_limit)
            item['token_count'] = _estimate_tokens(item['content'])
            item['token_trimmed'] = True
            item_tokens = item['token_count']
        expanded.append(item)
        seen_groups.add(group_id)
        used_tokens += item_tokens
        if len(expanded) >= limit or used_tokens >= token_limit:
            break
    return expanded


def _expand_adjacent_contexts(contexts: list[dict], *, default_count: int = 0) -> list[dict]:
    expanded = []
    for context in contexts:
        item = dict(context)
        config = item.get('_retrieval_config') or {}
        adjacent_count = max(0, min(int(config.get('adjacent_chunks', default_count) or 0), 3))
        if not adjacent_count or bool(config.get('parent_expansion', True)):
            expanded.append(item)
            continue
        try:
            chunk_index = int(item.get('chunk_index'))
        except (TypeError, ValueError):
            expanded.append(item)
            continue
        neighbors = KnowledgeChunk.objects.filter(
            document_id=item.get('document_id'),
            revision_id=item.get('document_revision_id') or None,
            chunk_level=2,
            chunk_index__gte=max(0, chunk_index - adjacent_count),
            chunk_index__lte=chunk_index + adjacent_count,
        )
        parent_chunk_id = item.get('parent_chunk_id') or None
        if parent_chunk_id:
            neighbors = neighbors.filter(parent_chunk_id=parent_chunk_id)
        ordered = list(neighbors.order_by('chunk_index').values('id', 'chunk_index', 'content'))
        if len(ordered) <= 1:
            expanded.append(item)
            continue
        item['matched_child_content'] = item.get('content', '')
        item['adjacent_chunk_ids'] = [
            str(neighbor['id'])
            for neighbor in ordered
            if str(neighbor['id']) != str(item.get('chunk_id'))
        ]
        item['content'] = '\n'.join(str(neighbor['content']) for neighbor in ordered)
        item['token_count'] = _estimate_tokens(item['content'])
        item['adjacent_expanded'] = True
        expanded.append(item)
    return expanded


def _truncate_text_to_token_budget(text: str, token_limit: int) -> str:
    text = text or ''
    if _estimate_tokens(text) <= token_limit:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _estimate_tokens(text[:middle]) <= token_limit:
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip()


def _candidate_filter_reason(
    chunk: KnowledgeChunk | None,
    *,
    job_position: str,
    pending_topics: list | None,
    difficulty: str = '',
    user=None,
    scope: dict | None = None,
) -> str:
    if not chunk:
        return 'missing_after_sql_guard'
    if chunk.chunk_level != 2:
        return 'not_child_chunk'
    document = chunk.document
    if document.approval_status != KnowledgeDocument.ApprovalStatus.APPROVED:
        return 'approval_not_approved'
    if document.status != KnowledgeDocument.Status.INDEXED:
        return 'document_not_indexed'
    if document.published_revision_id and chunk.revision_id != document.published_revision_id:
        return 'revision_not_published'
    if not document.published_revision_id and chunk.revision_id:
        return 'revision_not_published'
    if not _tenant_document_allowed(document, user):
        return 'tenant_scope_denied'
    if not _scope_allows_chunk(chunk, scope):
        return 'knowledge_base_scope_denied'

    job_terms = _normalize_terms(document.job_positions)
    target_job = (job_position or '').lower()
    if job_terms and not any(term in target_job or target_job in term for term in job_terms):
        return 'job_position_mismatch'
    if document.difficulty not in ('any', '', None) and difficulty and document.difficulty != difficulty:
        return 'difficulty_mismatch'
    return ''


def explain_retrieval_trace(trace: dict | None, contexts: list[dict] | None = None) -> dict:
    trace = trace or {}
    contexts = contexts or []
    vector_traces = trace.get('vector_query_traces') or []
    vector_status_counts = Counter(item.get('status') or 'unknown' for item in vector_traces)
    filter_counts = trace.get('filter_counts') or {}
    rerank = trace.get('rerank') or {}
    sql_fallback = trace.get('sql_fallback') or {}
    fallback_reason = trace.get('fallback_reason') or ''
    if not contexts and not fallback_reason:
        fallback_reason = 'no_approved_rag_context'

    steps = [
        {
            'name': 'multi_query',
            'status': 'ok' if trace.get('queries') else 'empty',
            'summary': f"生成 {len(trace.get('queries') or [])} 个检索 query",
        },
        {
            'name': 'vector_recall',
            'status': 'ok' if trace.get('vector_count') else 'degraded',
            'summary': f"向量召回去重候选 {trace.get('vector_count', 0)} 个",
            'detail': dict(vector_status_counts),
        },
        {
            'name': 'keyword_recall',
            'status': 'ok' if trace.get('keyword_count') else 'empty',
            'summary': f"关键词/BM25 召回去重候选 {trace.get('keyword_count', 0)} 个",
        },
        {
            'name': 'rrf_fusion',
            'status': 'ok' if trace.get('rrf_count') else 'fallback',
            'summary': f"RRF 融合候选 {trace.get('rrf_count', 0)} 个",
        },
        {
            'name': 'sql_fallback',
            'status': sql_fallback.get('status') or ('skipped' if trace.get('rrf_count') else 'empty'),
            'summary': (
                f"SQL fallback 扫描 {sql_fallback.get('scanned_count', 0)} 个 child chunk，"
                f"返回 {sql_fallback.get('returned_count', 0)} 个"
            ),
            'detail': sql_fallback,
        },
        {
            'name': 'policy_guard',
            'status': 'ok',
            'summary': f"PostgreSQL 二次校验过滤 {trace.get('filtered_count', 0)} 个候选",
            'detail': filter_counts,
        },
        {
            'name': 'rerank',
            'status': rerank.get('status') or ('ok' if trace.get('rerank_used') else 'unavailable'),
            'summary': f"Rerank 输入 {rerank.get('candidate_count', 0)} 个，输出 {rerank.get('returned_count', len(contexts))} 个",
            'detail': rerank,
        },
    ]
    if fallback_reason:
        steps.append({
            'name': 'fallback',
            'status': 'degraded',
            'summary': fallback_reason,
        })

    return {
        'query_variants': trace.get('queries') or [],
        'candidate_summary': {
            'eligible_chunk_count': trace.get('eligible_chunk_count', 0),
            'vector_unique_count': trace.get('vector_count', 0),
            'keyword_unique_count': trace.get('keyword_count', 0),
            'keyword_query_count': trace.get('keyword_query_count', 0),
            'rrf_count': trace.get('rrf_count', 0),
            'sql_fallback_candidate_count': sql_fallback.get('candidate_count', 0),
            'sql_fallback_returned_count': sql_fallback.get('returned_count', 0),
            'filtered_count': trace.get('filtered_count', 0),
            'final_count': len(contexts),
        },
        'vector_status_counts': dict(vector_status_counts),
        'keyword_query_traces': trace.get('keyword_query_traces') or [],
        'sql_fallback': sql_fallback,
        'filters': filter_counts,
        'rerank': rerank,
        'fallback_reason': fallback_reason,
        'steps': steps,
    }


def _qdrant_query_filter(
    *,
    scope: dict | None,
    user=None,
    job_position: str = '',
    difficulty: str = '',
):
    from qdrant_client.models import (
        FieldCondition,
        Filter,
        IsEmptyCondition,
        MatchAny,
        MatchText,
        MatchValue,
        PayloadField,
    )

    must = [
        FieldCondition(key='chunk_level', match=MatchValue(value=2)),
        FieldCondition(
            key='approval_status',
            match=MatchValue(value=KnowledgeDocument.ApprovalStatus.APPROVED),
        ),
    ]
    scope = scope or {}
    if scope.get('document_ids'):
        must.append(FieldCondition(
            key='document_id',
            match=MatchAny(any=sorted(scope['document_ids'])),
        ))
    if scope.get('revision_ids'):
        must.append(FieldCondition(
            key='revision_id',
            match=MatchAny(any=sorted(scope['revision_ids'])),
        ))
    if difficulty:
        must.append(FieldCondition(
            key='difficulty',
            match=MatchAny(any=[KnowledgeDocument.Difficulty.ANY, difficulty]),
        ))
    if job_position:
        must.append(Filter(should=[
            FieldCondition(key='job_positions', match=MatchText(text=job_position)),
            IsEmptyCondition(is_empty=PayloadField(key='job_positions')),
        ]))
    if not (user and getattr(user, 'is_staff', False)):
        visibility_should = [
            FieldCondition(
                key='visibility',
                match=MatchValue(value=KnowledgeDocument.Visibility.PUBLIC),
            ),
        ]
        if user and getattr(user, 'is_authenticated', False):
            visibility_should.append(Filter(must=[
                FieldCondition(
                    key='visibility',
                    match=MatchValue(value=KnowledgeDocument.Visibility.PRIVATE),
                ),
                FieldCondition(
                    key='owner_user_id',
                    match=MatchValue(value=getattr(user, 'id', None)),
                ),
            ]))
        must.append(Filter(should=visibility_should))
    return Filter(must=must)


def _vector_search_ranking(
    query: str,
    *,
    user=None,
    topn: int = 30,
    exclude_ids: set[str] | None = None,
    scope: dict | None = None,
    job_position: str = '',
    difficulty: str = '',
) -> tuple[list[tuple[str, int, float]], dict]:
    exclude_ids = exclude_ids or set()
    trace = {'query': query, 'status': 'skipped', 'candidate_count': 0, 'error': ''}
    try:
        client = _qdrant_client()
        if not client:
            trace.update({'status': 'qdrant_unavailable'})
            return [], trace
        vector, model = _embed_text(query, user=user)
        if not vector:
            trace.update({'status': 'embedding_unavailable', 'embedding_model': model})
            return [], trace
        collection = getattr(settings, 'QDRANT_COLLECTION', 'interview_knowledge')
        query_filter = _qdrant_query_filter(
            scope=scope,
            user=user,
            job_position=job_position,
            difficulty=difficulty,
        )
        search_result = client.search(
            collection_name=collection,
            query_vector=vector,
            query_filter=query_filter,
            limit=topn,
        )
        ranking = []
        for rank, point in enumerate(search_result, start=1):
            chunk_id = point.payload.get('chunk_id') if getattr(point, 'payload', None) else None
            if chunk_id and str(chunk_id) not in exclude_ids:
                ranking.append((str(chunk_id), rank, float(getattr(point, 'score', 0) or 0)))
        trace.update({
            'status': 'ok',
            'embedding_model': model,
            'candidate_count': len(ranking),
            'knowledge_base_revision_id': (scope or {}).get('knowledge_base_revision_id', ''),
        })
        return ranking, trace
    except Exception as exc:
        trace.update({'status': 'failed', 'error': str(exc)[:300]})
        logger.warning('Vector search failed for one query; continuing hybrid search: %s', exc)
        return [], trace


def _threaded_vector_search_ranking(*args, **kwargs):
    try:
        return _vector_search_ranking(*args, **kwargs)
    finally:
        # Django connections are thread-local and otherwise outlive short-lived
        # ThreadPoolExecutor workers (notably locking SQLite test databases).
        connections.close_all()


def _meili_filter_value(value) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _meili_search_ranking(
    query: str,
    *,
    user=None,
    topn: int = 30,
    exclude_ids: set[str] | None = None,
    scope: dict | None = None,
    job_position: str = '',
    difficulty: str = '',
) -> tuple[list[tuple[str, int, float]], dict]:
    exclude_ids = exclude_ids or set()
    trace = {'query': query, 'status': 'skipped', 'candidate_count': 0, 'error': ''}
    if not _meili_base_url():
        trace.update({'status': 'meilisearch_unavailable', 'error': 'not_configured'})
        return [], trace
    try:
        filters = [
            'chunk_level = 2',
            f'approval_status = {_meili_filter_value(KnowledgeDocument.ApprovalStatus.APPROVED)}',
        ]
        scope = scope or {}
        if scope.get('document_ids'):
            values = ', '.join(_meili_filter_value(item) for item in sorted(scope['document_ids']))
            filters.append(f'document_id IN [{values}]')
        if scope.get('revision_ids'):
            values = ', '.join(_meili_filter_value(item) for item in sorted(scope['revision_ids']))
            filters.append(f'revision_id IN [{values}]')
        if difficulty:
            values = ', '.join(_meili_filter_value(item) for item in [
                KnowledgeDocument.Difficulty.ANY,
                difficulty,
            ])
            filters.append(f'difficulty IN [{values}]')
        if job_position:
            filters.append(
                f'(job_positions = {_meili_filter_value(job_position)} OR job_positions IS EMPTY)'
            )
        if not (user and getattr(user, 'is_staff', False)):
            visibility = (
                f'visibility = {_meili_filter_value(KnowledgeDocument.Visibility.PUBLIC)}'
            )
            if user and getattr(user, 'is_authenticated', False):
                visibility = (
                    f'({visibility} OR '
                    f'(visibility = {_meili_filter_value(KnowledgeDocument.Visibility.PRIVATE)} '
                    f'AND owner_user_id = {_meili_filter_value(getattr(user, "id", ""))}))'
                )
            filters.append(visibility)
        response = requests.post(
            f'{_meili_base_url()}/indexes/{_meili_index_name()}/search',
            headers=_meili_headers(),
            data=json.dumps({
                'q': query,
                'limit': topn,
                'filter': ' AND '.join(filters),
                'showRankingScore': True,
            }, ensure_ascii=False),
            timeout=MEILI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        ranking = []
        for rank, item in enumerate(response.json().get('hits') or [], start=1):
            chunk_id = str(item.get('chunk_id') or '')
            if chunk_id and chunk_id not in exclude_ids:
                ranking.append((
                    chunk_id,
                    rank,
                    float(item.get('_rankingScore') or max(0.0, 1.0 - rank / max(topn, 1))),
                ))
        trace.update({
            'status': 'ok',
            'candidate_count': len(ranking),
            'knowledge_base_revision_id': scope.get('knowledge_base_revision_id', ''),
        })
        return ranking, trace
    except Exception as exc:
        trace.update({'status': 'failed', 'error': str(exc)[:300]})
        logger.warning('Meilisearch query failed; SQL/BM25 fallback will be audited: %s', exc)
        return [], trace


def search_knowledge_context(
    *,
    job_position: str,
    user=None,
    current_stage: str = '',
    pending_topics: list | None = None,
    last_evaluation: dict | None = None,
    jd_text: str = '',
    difficulty: str = '',
    exclude_chunk_ids: list | None = None,
    limit: int = 4,
    return_trace: bool = False,
    agent_config_snapshot: dict | None = None,
) -> list[dict]:
    scopes = _retrieval_scopes(agent_config_snapshot)
    if not scopes:
        empty_trace = {
            'queries': [],
            'vector_count': 0,
            'keyword_count': 0,
            'rrf_count': 0,
            'eligible_chunk_count': 0,
            'filtered_count': 0,
            'filter_counts': {},
            'vector_query_traces': [],
            'keyword_query_traces': [],
            'fallback_reason': 'no_published_knowledge_base_binding',
        }
        explanation = explain_retrieval_trace(empty_trace, [])
        if return_trace:
            return {
                'contexts': [],
                'retrieval_trace': empty_trace,
                'retrieval_explanation': explanation,
            }
        return []

    retrieval_configs = [scope.get('retrieval_config') or {} for scope in scopes]
    query_count = max(
        [int(config.get('query_count') or 5) for config in retrieval_configs] or [5]
    )
    fallback_queries = build_multi_queries(
        job_position, current_stage, pending_topics, last_evaluation, jd_text,
    )[:query_count]
    queries, query_planner_trace = _plan_registered_queries(
        fallback_queries=fallback_queries,
        query_count=query_count,
        agent_config_snapshot=agent_config_snapshot,
        user=user,
        job_position=job_position,
        current_stage=current_stage,
        pending_topics=pending_topics,
        last_evaluation=last_evaluation,
        jd_text=jd_text,
    )
    query = queries[0] if queries else build_retrieval_query(job_position, current_stage, pending_topics, last_evaluation, jd_text)
    topn = max(
        [int(config.get('vector_top_n') or config.get('keyword_top_n') or 30) for config in retrieval_configs]
        or [int(getattr(settings, 'HYBRID_SEARCH_TOPN', 30))]
    )
    topk = max(
        [int(config.get('final_top_k') or limit) for config in retrieval_configs]
        or [int(getattr(settings, 'HYBRID_SEARCH_TOPK', limit))]
    )
    limit = min(limit or topk, topk)
    exclude_ids = {str(item) for item in (exclude_chunk_ids or [])}
    vector_rankings = []
    keyword_rankings = []
    vector_ranking_weights = []
    keyword_ranking_weights = []
    trace = {
        'queries': queries,
        'query_planner': query_planner_trace,
        'vector_count': 0,
        'keyword_count': 0,
        'filtered_count': 0,
        'filter_counts': {},
        'vector_query_traces': [],
        'keyword_query_traces': [],
        'keyword_query_count': 0,
        'rrf_count': 0,
        'rerank_used': False,
        'rerank': {},
        'fallback_reason': '',
        'eligible_chunk_count': 0,
    }
    eligible_queryset = KnowledgeChunk.objects.filter(
        _tenant_document_filter(user),
        chunk_level=2,
    ).filter(
        Q(revision=F('document__published_revision'))
        | Q(revision__isnull=True, document__published_revision__isnull=True),
    )
    allowed_documents = set().union(*(scope.get('document_ids') or set() for scope in scopes))
    allowed_revisions = set().union(*(scope.get('revision_ids') or set() for scope in scopes))
    if allowed_documents:
        eligible_queryset = eligible_queryset.filter(document_id__in=allowed_documents)
    if allowed_revisions:
        eligible_queryset = eligible_queryset.filter(revision_id__in=allowed_revisions)
    trace['eligible_chunk_count'] = eligible_queryset.count()
    parallelism = int(getattr(settings, 'HYBRID_SEARCH_PARALLELISM', os.getenv('HYBRID_SEARCH_PARALLELISM', 4)) or 4)
    parallelism = max(1, min(parallelism, (len(queries) * len(scopes)) or 1))
    jobs = [(item_query, scope) for scope in scopes for item_query in queries]
    if jobs:
        if parallelism == 1:
            for item_query, scope in jobs:
                scope_topn = int((scope.get('retrieval_config') or {}).get('vector_top_n') or topn)
                ranking, vector_trace = _vector_search_ranking(
                    item_query,
                    user=user,
                    topn=scope_topn,
                    exclude_ids=exclude_ids,
                    scope=scope,
                    job_position=job_position,
                    difficulty=difficulty,
                )
                if ranking:
                    vector_rankings.append(ranking)
                    vector_ranking_weights.append(float(
                        (scope.get('retrieval_config') or {}).get('vector_weight', 1.0)
                    ))
                trace['vector_query_traces'].append(vector_trace)
        else:
            with ThreadPoolExecutor(max_workers=parallelism) as executor:
                future_to_query = {
                    executor.submit(
                        _threaded_vector_search_ranking,
                        item_query,
                        user=user,
                        topn=int((scope.get('retrieval_config') or {}).get('vector_top_n') or topn),
                        exclude_ids=exclude_ids,
                        scope=scope,
                        job_position=job_position,
                        difficulty=difficulty,
                    ): (item_query, scope)
                    for item_query, scope in jobs
                }
                for future in as_completed(future_to_query):
                    ranking, vector_trace = future.result()
                    if ranking:
                        vector_rankings.append(ranking)
                        _, scope = future_to_query[future]
                        vector_ranking_weights.append(float(
                            (scope.get('retrieval_config') or {}).get('vector_weight', 1.0)
                        ))
                    trace['vector_query_traces'].append(vector_trace)

    for scope in scopes:
        scope_topn = int((scope.get('retrieval_config') or {}).get('keyword_top_n') or topn)
        scope_meili_failed = False
        scope_rankings = []
        for item_query in queries:
            ranking, keyword_trace = _meili_search_ranking(
                item_query,
                user=user,
                topn=scope_topn,
                exclude_ids=exclude_ids,
                scope=scope,
                job_position=job_position,
                difficulty=difficulty,
            )
            trace['keyword_query_traces'].append(keyword_trace)
            if ranking:
                scope_rankings.append(ranking)
            if keyword_trace.get('status') != 'ok':
                scope_meili_failed = True
        keyword_rankings.extend(scope_rankings)
        keyword_ranking_weights.extend([
            float((scope.get('retrieval_config') or {}).get('keyword_weight', 1.0))
        ] * len(scope_rankings))
        if scope_meili_failed:
            trace['fallback_path'] = 'audited_sql_bm25_fallback'
            fallback_rankings = keyword_search_rankings(
                queries=queries,
                job_position=job_position,
                user=user,
                pending_topics=pending_topics,
                difficulty=difficulty,
                exclude_chunk_ids=exclude_chunk_ids,
                topn=scope_topn,
                scope=scope,
            )
            keyword_rankings.extend(fallback_rankings)
            keyword_ranking_weights.extend([
                float((scope.get('retrieval_config') or {}).get('keyword_weight', 1.0))
            ] * len(fallback_rankings))

    rrf_k = max([int(config.get('rrf_k') or RRF_K) for config in retrieval_configs] or [RRF_K])
    fused = rrf_fuse(
        vector_rankings=vector_rankings,
        keyword_rankings=keyword_rankings,
        rrf_k=rrf_k,
        vector_weights=vector_ranking_weights,
        keyword_weights=keyword_ranking_weights,
    )
    trace['vector_count'] = len({chunk_id for ranking in vector_rankings for chunk_id, _, _ in ranking})
    trace['keyword_count'] = len({chunk_id for ranking in keyword_rankings for chunk_id, _, _ in ranking})
    trace['keyword_query_count'] = len(keyword_rankings)
    trace['rrf_count'] = len(fused)
    if fused:
        candidate_ids = list(fused.keys())
        chunks = KnowledgeChunk.objects.select_related('document', 'parent_chunk').filter(
            id__in=candidate_ids,
            chunk_level=2,
        ).filter(
            Q(revision=F('document__published_revision'))
            | Q(revision__isnull=True, document__published_revision__isnull=True),
        )
        chunk_by_id = {str(chunk.id): chunk for chunk in chunks}
        filter_counts = Counter()
        contexts = []
        for chunk_id, scores in sorted(fused.items(), key=lambda item: item[1]['rrf_score'], reverse=True):
            chunk = chunk_by_id.get(chunk_id)
            matched_scope = next(
                (scope for scope in scopes if chunk and _scope_allows_chunk(chunk, scope)),
                None,
            )
            if matched_scope is None and (allowed_documents or allowed_revisions):
                matched_scope = {'document_ids': {'__denied__'}, 'revision_ids': {'__denied__'}}
            matched_config = (matched_scope or {}).get('retrieval_config') or {}
            score_threshold = float(matched_config.get('score_threshold') or 0)
            best_recall_score = max(
                float(scores.get('vector_score') or 0),
                float(scores.get('keyword_score') or 0),
            )
            if score_threshold and best_recall_score < score_threshold:
                trace['filtered_count'] += 1
                filter_counts['score_below_threshold'] += 1
                continue
            filter_reason = _candidate_filter_reason(
                chunk,
                job_position=job_position,
                pending_topics=pending_topics,
                difficulty=difficulty,
                user=user,
                scope=matched_scope,
            )
            if filter_reason:
                trace['filtered_count'] += 1
                filter_counts[filter_reason] += 1
                continue
            context = _context_from_chunk(chunk, scores['rrf_score'])
            context.update({
                'vector_score': scores.get('vector_score'),
                'keyword_score': scores.get('keyword_score'),
                'rrf_score': scores.get('rrf_score'),
                '_retrieval_config': matched_config,
            })
            contexts.append(context)
            if len(contexts) >= max(topk, limit):
                break
        trace['filter_counts'] = dict(filter_counts)
    else:
        trace['fallback_path'] = 'sql_keyword_fallback'
        contexts = _sql_fallback_search(
            query=query,
            job_position=job_position,
            user=user,
            current_stage=current_stage,
            pending_topics=pending_topics,
            difficulty=difficulty,
            exclude_chunk_ids=exclude_chunk_ids,
            limit=max(topk, limit),
            trace=trace,
            scope=scopes[0] if len(scopes) == 1 else {
                'document_ids': allowed_documents,
                'revision_ids': allowed_revisions,
            },
        )

    before_rerank_ids = [item.get('chunk_id') for item in contexts]
    rerank_enabled = any(config.get('rerank_enabled', True) for config in retrieval_configs)
    contexts = (
        _rerank_contexts(query, contexts, user=user, limit=limit, trace=trace)
        if rerank_enabled
        else contexts[:limit]
    )
    trace['rerank_used'] = [item.get('chunk_id') for item in contexts] != before_rerank_ids[:len(contexts)]
    parent_expansion = any(config.get('parent_expansion', True) for config in retrieval_configs)
    adjacent_chunks = max(
        [int(config.get('adjacent_chunks') or 0) for config in retrieval_configs] or [0]
    )
    rag_token_limit = min(
        [int(config.get('rag_token_limit') or 1800) for config in retrieval_configs] or [1800]
    )
    contexts = _expand_adjacent_contexts(contexts, default_count=adjacent_chunks)
    contexts = _expand_parent_contexts(
        contexts,
        enabled=parent_expansion,
        token_limit=rag_token_limit,
        limit=limit,
    )
    if not contexts:
        trace['fallback_reason'] = (
            'no_approved_rag_context'
            if trace['eligible_chunk_count'] == 0
            else 'no_relevant_context_after_filters'
        )
    retrieval_explanation = explain_retrieval_trace(trace, contexts)
    for context in contexts:
        context['retrieval_trace'] = trace
    _mark_contexts_retrieved(contexts)
    if return_trace:
        return {
            'contexts': contexts,
            'retrieval_trace': trace,
            'retrieval_explanation': retrieval_explanation,
        }
    return contexts


def keyword_search_rankings(
    *,
    queries: list[str],
    job_position: str,
    user=None,
    pending_topics: list | None = None,
    difficulty: str = '',
    exclude_chunk_ids: list | None = None,
    topn: int = 30,
    scope: dict | None = None,
) -> list[list[tuple[str, int, float]]]:
    exclude_ids = {str(item) for item in (exclude_chunk_ids or [])}
    chunks_queryset = KnowledgeChunk.objects.select_related('document').filter(
        _tenant_document_filter(user),
        document__status=KnowledgeDocument.Status.INDEXED,
        chunk_level=2,
    ).filter(
        Q(revision=F('document__published_revision'))
        | Q(revision__isnull=True, document__published_revision__isnull=True),
    )
    if scope and scope.get('document_ids'):
        chunks_queryset = chunks_queryset.filter(document_id__in=scope['document_ids'])
    if scope and scope.get('revision_ids'):
        chunks_queryset = chunks_queryset.filter(revision_id__in=scope['revision_ids'])
    chunks = list(chunks_queryset.order_by('-document__updated_at')[:500])
    chunks = [
        chunk for chunk in chunks
        if str(chunk.id) not in exclude_ids and _matches_document(chunk.document, job_position, pending_topics, difficulty, user=user)
    ]
    if not chunks:
        return []
    documents_terms = [_keyword_terms(f'{chunk.content} {" ".join(chunk.heading_path or [])} {chunk.document.title}') for chunk in chunks]
    doc_freq = Counter()
    for terms in documents_terms:
        for term in set(terms):
            doc_freq[term] += 1
    avgdl = sum(len(terms) for terms in documents_terms) / max(len(documents_terms), 1)
    rankings = []
    for query in queries:
        query_terms = _keyword_terms(query)
        scored = []
        for chunk, terms in zip(chunks, documents_terms):
            score = bm25_score(query_terms, terms, doc_freq, len(documents_terms), avgdl)
            if score > 0:
                scored.append((str(chunk.id), score))
        scored.sort(key=lambda item: item[1], reverse=True)
        rankings.append([(chunk_id, rank, score) for rank, (chunk_id, score) in enumerate(scored[:topn], start=1)])
    return rankings


def bm25_score(query_terms: list[str], doc_terms: list[str], doc_freq: Counter, total_docs: int, avgdl: float) -> float:
    if not query_terms or not doc_terms:
        return 0.0
    term_freq = Counter(doc_terms)
    k1 = 1.5
    b = 0.75
    score = 0.0
    doc_len = len(doc_terms)
    for term in query_terms:
        df = doc_freq.get(term, 0)
        if not df:
            continue
        idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
        tf = term_freq.get(term, 0)
        score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / max(avgdl, 1)))
    return score


def rrf_fuse(
    vector_rankings: list[list[tuple[str, int, float]]],
    keyword_rankings: list[list[tuple[str, int, float]]],
    *,
    rrf_k: int = RRF_K,
    vector_weights: list[float] | None = None,
    keyword_weights: list[float] | None = None,
) -> dict[str, dict]:
    fused = defaultdict(lambda: {'rrf_score': 0.0, 'vector_score': None, 'keyword_score': None})
    vector_weights = vector_weights or [1.0] * len(vector_rankings)
    keyword_weights = keyword_weights or [1.0] * len(keyword_rankings)
    for ranking, weight in zip(vector_rankings, vector_weights):
        for chunk_id, rank, score in ranking:
            fused[chunk_id]['rrf_score'] += float(weight) / (rrf_k + rank)
            fused[chunk_id]['vector_score'] = max(fused[chunk_id]['vector_score'] or 0, score)
    for ranking, weight in zip(keyword_rankings, keyword_weights):
        for chunk_id, rank, score in ranking:
            fused[chunk_id]['rrf_score'] += float(weight) / (rrf_k + rank)
            fused[chunk_id]['keyword_score'] = max(fused[chunk_id]['keyword_score'] or 0, score)
    return dict(fused)


def format_rag_context_for_prompt(contexts: list[dict] | None) -> str:
    if not contexts:
        return '未检索到可用的知识库题库上下文。'
    lines = ['以下是知识库/题库检索结果，只能作为出题参考，不能直接泄露给候选人：']
    for index, item in enumerate(contexts[:4], start=1):
        tags = ', '.join(item.get('ability_tags') or [])
        lines.append(
            f"{index}. 标题: {item.get('title', '')}\n"
            f"   标签: {tags or '未标注'}；难度: {item.get('difficulty', 'any')}\n"
            f"   证据: {item.get('content', '')}"
        )
    return '\n'.join(lines)
