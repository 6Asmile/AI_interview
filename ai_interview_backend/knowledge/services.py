import hashlib
import logging
import math
import os
import re
import requests
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from django.conf import settings
from django.db import transaction
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


def _ensure_qdrant_collection(client, vector_size: int) -> None:
    collection = getattr(settings, 'QDRANT_COLLECTION', 'interview_knowledge')
    try:
        from qdrant_client.models import Distance, VectorParams
        client.get_collection(collection)
    except Exception:
        client.recreate_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )


def _upsert_qdrant_chunk(client, chunk: KnowledgeChunk, vector: list[float]) -> None:
    collection = getattr(settings, 'QDRANT_COLLECTION', 'interview_knowledge')
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
                    _ensure_qdrant_collection(client, len(vector))
                    _upsert_qdrant_chunk(client, chunk, vector)
                    chunk.embedding_model = embedding_model
                chunk.indexed_at = timezone.now()
                chunk.save(update_fields=['embedding_model', 'indexed_at'])
                chunk_index += 1
                indexed_count += 1

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
            'Embedding unavailable; indexed for keyword/BM25 fallback only. '
            + ' | '.join(embedding_errors)
            if embedding_errors else ''
        )[:2000]
        document.save(update_fields=[
            'status', 'approval_status', 'published_revision', 'chunk_count',
            'last_indexed_at', 'error_message', 'updated_at',
        ])
        if previous_revision and previous_revision.id != revision.id:
            document.chunks.filter(revision=previous_revision).delete()
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
) -> list[dict]:
    exclude_ids = {str(item) for item in (exclude_chunk_ids or [])}
    query_tokens = _tokenize(query)
    stage_tokens = _tokenize(current_stage)
    topic_tokens = _tokenize(' '.join(pending_topics or []))
    scored = []
    scanned_count = 0
    excluded_count = 0
    filter_counts = Counter()

    chunks = KnowledgeChunk.objects.select_related('document').filter(
        _tenant_document_filter(user),
        document__status=KnowledgeDocument.Status.INDEXED,
    ).filter(
        Q(revision=F('document__published_revision'))
        | Q(revision__isnull=True, document__published_revision__isnull=True),
        chunk_level=2,
    ).order_by('-document__updated_at', 'chunk_index')[:300]
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
        'chunk_id': str(chunk.id),
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
        'content': chunk.content[:700],
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


def _candidate_filter_reason(
    chunk: KnowledgeChunk | None,
    *,
    job_position: str,
    pending_topics: list | None,
    difficulty: str = '',
    user=None,
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


def _vector_search_ranking(query: str, *, user=None, topn: int = 30, exclude_ids: set[str] | None = None) -> tuple[list[tuple[str, int, float]], dict]:
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
        search_result = client.search(collection_name=collection, query_vector=vector, limit=topn)
        ranking = []
        for rank, point in enumerate(search_result, start=1):
            chunk_id = point.payload.get('chunk_id') if getattr(point, 'payload', None) else None
            if chunk_id and str(chunk_id) not in exclude_ids:
                ranking.append((str(chunk_id), rank, float(getattr(point, 'score', 0) or 0)))
        trace.update({
            'status': 'ok',
            'embedding_model': model,
            'candidate_count': len(ranking),
        })
        return ranking, trace
    except Exception as exc:
        trace.update({'status': 'failed', 'error': str(exc)[:300]})
        logger.warning('Vector search failed for one query; continuing hybrid search: %s', exc)
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
) -> list[dict]:
    queries = build_multi_queries(job_position, current_stage, pending_topics, last_evaluation, jd_text)
    query = queries[0] if queries else build_retrieval_query(job_position, current_stage, pending_topics, last_evaluation, jd_text)
    topn = int(getattr(settings, 'HYBRID_SEARCH_TOPN', os.getenv('HYBRID_SEARCH_TOPN', 30)) or 30)
    topk = int(getattr(settings, 'HYBRID_SEARCH_TOPK', os.getenv('HYBRID_SEARCH_TOPK', limit)) or limit)
    limit = min(limit or topk, topk)
    exclude_ids = {str(item) for item in (exclude_chunk_ids or [])}
    vector_rankings = []
    trace = {
        'queries': queries,
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
    trace['eligible_chunk_count'] = KnowledgeChunk.objects.filter(
        _tenant_document_filter(user),
        chunk_level=2,
    ).filter(
        Q(revision=F('document__published_revision'))
        | Q(revision__isnull=True, document__published_revision__isnull=True),
    ).count()
    parallelism = int(getattr(settings, 'HYBRID_SEARCH_PARALLELISM', os.getenv('HYBRID_SEARCH_PARALLELISM', 4)) or 4)
    parallelism = max(1, min(parallelism, len(queries) or 1))
    if queries:
        if parallelism == 1:
            for item_query in queries:
                ranking, vector_trace = _vector_search_ranking(item_query, user=user, topn=topn, exclude_ids=exclude_ids)
                if ranking:
                    vector_rankings.append(ranking)
                trace['vector_query_traces'].append(vector_trace)
        else:
            with ThreadPoolExecutor(max_workers=parallelism) as executor:
                future_to_query = {
                    executor.submit(_vector_search_ranking, item_query, user=user, topn=topn, exclude_ids=exclude_ids): item_query
                    for item_query in queries
                }
                for future in as_completed(future_to_query):
                    ranking, vector_trace = future.result()
                    if ranking:
                        vector_rankings.append(ranking)
                    trace['vector_query_traces'].append(vector_trace)

    keyword_rankings = keyword_search_rankings(
        queries=queries,
        job_position=job_position,
        user=user,
        pending_topics=pending_topics,
        difficulty=difficulty,
        exclude_chunk_ids=exclude_chunk_ids,
        topn=topn,
    )
    trace['keyword_query_traces'] = [
        {
            'query': queries[index] if index < len(queries) else '',
            'status': 'ok',
            'candidate_count': len(ranking),
        }
        for index, ranking in enumerate(keyword_rankings)
    ]
    fused = rrf_fuse(vector_rankings=vector_rankings, keyword_rankings=keyword_rankings)
    trace['vector_count'] = len({chunk_id for ranking in vector_rankings for chunk_id, _, _ in ranking})
    trace['keyword_count'] = len({chunk_id for ranking in keyword_rankings for chunk_id, _, _ in ranking})
    trace['keyword_query_count'] = len(keyword_rankings)
    trace['rrf_count'] = len(fused)
    if fused:
        candidate_ids = list(fused.keys())
        chunks = KnowledgeChunk.objects.select_related('document').filter(
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
            filter_reason = _candidate_filter_reason(
                chunk,
                job_position=job_position,
                pending_topics=pending_topics,
                difficulty=difficulty,
                user=user,
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
        )

    before_rerank_ids = [item.get('chunk_id') for item in contexts]
    contexts = _rerank_contexts(query, contexts, user=user, limit=limit, trace=trace)
    trace['rerank_used'] = [item.get('chunk_id') for item in contexts] != before_rerank_ids[:len(contexts)]
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
) -> list[list[tuple[str, int, float]]]:
    exclude_ids = {str(item) for item in (exclude_chunk_ids or [])}
    chunks = list(KnowledgeChunk.objects.select_related('document').filter(
        _tenant_document_filter(user),
        document__status=KnowledgeDocument.Status.INDEXED,
        chunk_level=2,
    ).filter(
        Q(revision=F('document__published_revision'))
        | Q(revision__isnull=True, document__published_revision__isnull=True),
    ).order_by('-document__updated_at')[:500])
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


def rrf_fuse(vector_rankings: list[list[tuple[str, int, float]]], keyword_rankings: list[list[tuple[str, int, float]]]) -> dict[str, dict]:
    fused = defaultdict(lambda: {'rrf_score': 0.0, 'vector_score': None, 'keyword_score': None})
    for ranking in vector_rankings:
        for chunk_id, rank, score in ranking:
            fused[chunk_id]['rrf_score'] += 1 / (RRF_K + rank)
            fused[chunk_id]['vector_score'] = max(fused[chunk_id]['vector_score'] or 0, score)
    for ranking in keyword_rankings:
        for chunk_id, rank, score in ranking:
            fused[chunk_id]['rrf_score'] += 1 / (RRF_K + rank)
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
            f"   片段: {item.get('content', '')[:700]}"
        )
    return '\n'.join(lines)
