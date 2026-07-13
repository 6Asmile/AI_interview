import mimetypes
import os
import tempfile
import uuid
import hashlib
from dataclasses import dataclass

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from openai import OpenAI

from system.ai_config import resolve_ai_config
from system.models import AIModel

from .models import InterviewMediaArtifact, InterviewQuestion, InterviewSession


@dataclass
class SpeechResult:
    ok: bool
    artifact: InterviewMediaArtifact | None = None
    text: str = ''
    confidence: float | None = None
    file_url: str = ''
    error: str = ''


def _model_snapshot(model):
    if not model:
        return {'provider': '', 'model_slug': ''}
    return {'provider': model.provider or '', 'model_slug': model.model_slug or ''}


def _openai_client(api_key: str, model) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=model.base_url or None)


def _response_text(response) -> str:
    if isinstance(response, str):
        return response.strip()
    for attr in ('text', 'content'):
        value = getattr(response, attr, None)
        if value:
            return str(value).strip()
    if isinstance(response, dict):
        return str(response.get('text') or response.get('content') or '').strip()
    return ''


def create_answer_audio_artifact(
    *,
    session: InterviewSession,
    question: InterviewQuestion | None,
    user,
    audio_bytes: bytes,
    filename: str | None = None,
    mime_type: str = 'audio/webm',
    metadata: dict | None = None,
) -> InterviewMediaArtifact:
    filename = filename or f'answer-{uuid.uuid4().hex}.webm'
    artifact = InterviewMediaArtifact.objects.create(
        session=session,
        question=question,
        user=user,
        artifact_type=InterviewMediaArtifact.ArtifactType.ANSWER_AUDIO,
        status=InterviewMediaArtifact.Status.PENDING,
        mime_type=mime_type,
        metadata=metadata or {},
    )
    artifact.source_file.save(filename, ContentFile(audio_bytes), save=True)
    return artifact


def transcribe_artifact(artifact: InterviewMediaArtifact, *, user=None) -> SpeechResult:
    resolved = resolve_ai_config(user or artifact.user, AIModel.ModelType.ASR)
    snapshot = _model_snapshot(resolved.model)
    artifact.provider = snapshot['provider']
    artifact.model_slug = snapshot['model_slug']
    artifact.status = InterviewMediaArtifact.Status.PROCESSING
    artifact.error_message = ''
    artifact.save(update_fields=['provider', 'model_slug', 'status', 'error_message', 'updated_at'])

    if not resolved.model or not resolved.api_key:
        artifact.status = InterviewMediaArtifact.Status.FAILED
        artifact.error_message = 'asr_model_or_api_key_missing'
        artifact.save(update_fields=['status', 'error_message', 'updated_at'])
        return SpeechResult(ok=False, artifact=artifact, error=artifact.error_message)

    if not artifact.source_file:
        artifact.status = InterviewMediaArtifact.Status.FAILED
        artifact.error_message = 'audio_file_missing'
        artifact.save(update_fields=['status', 'error_message', 'updated_at'])
        return SpeechResult(ok=False, artifact=artifact, error=artifact.error_message)

    try:
        client = _openai_client(resolved.api_key, resolved.model)
        artifact.source_file.open('rb')
        try:
            response = client.audio.transcriptions.create(
                model=resolved.model.model_slug,
                file=artifact.source_file.file,
            )
        finally:
            artifact.source_file.close()
        text = _response_text(response)
        if not text:
            raise RuntimeError('asr_empty_transcript')
        artifact.transcript_text = text
        artifact.asr_confidence = None
        artifact.transcript_segments = []
        artifact.status = InterviewMediaArtifact.Status.COMPLETED
        artifact.metadata = {
            **(artifact.metadata or {}),
            'asr_source': resolved.source,
            'transcribed_at': timezone.now().isoformat(),
        }
        artifact.save(update_fields=[
            'transcript_text',
            'asr_confidence',
            'transcript_segments',
            'status',
            'metadata',
            'updated_at',
        ])
        return SpeechResult(ok=True, artifact=artifact, text=text, confidence=artifact.asr_confidence)
    except Exception as exc:
        artifact.status = InterviewMediaArtifact.Status.FAILED
        artifact.error_message = str(exc)[:1000]
        artifact.save(update_fields=['status', 'error_message', 'updated_at'])
        return SpeechResult(ok=False, artifact=artifact, error=artifact.error_message)


def transcribe_bytes(
    *,
    session: InterviewSession,
    question: InterviewQuestion | None,
    user,
    audio_bytes: bytes,
    filename: str | None = None,
    mime_type: str = 'audio/webm',
    metadata: dict | None = None,
) -> SpeechResult:
    artifact = create_answer_audio_artifact(
        session=session,
        question=question,
        user=user,
        audio_bytes=audio_bytes,
        filename=filename,
        mime_type=mime_type,
        metadata=metadata,
    )
    return transcribe_artifact(artifact, user=user)


def synthesize_question_tts(
    *,
    session: InterviewSession,
    question: InterviewQuestion,
    user,
    text: str,
) -> SpeechResult:
    text_hash = hashlib.sha256((text or '').encode('utf-8')).hexdigest()
    cache_seconds = getattr(settings, 'TTS_CACHE_SECONDS', 86400)
    cached_candidates = InterviewMediaArtifact.objects.filter(
        session=session,
        question=question,
        user=user,
        artifact_type=InterviewMediaArtifact.ArtifactType.QUESTION_TTS,
        status=InterviewMediaArtifact.Status.COMPLETED,
    ).order_by('-created_at')[:5]
    now = timezone.now()
    for cached in cached_candidates:
        metadata = cached.metadata or {}
        synthesized_at = parse_datetime(metadata.get('synthesized_at', '')) if metadata.get('synthesized_at') else None
        cache_alive = not synthesized_at or (now - synthesized_at).total_seconds() <= cache_seconds
        if cached.source_file and metadata.get('text_hash') == text_hash and cache_alive:
            return SpeechResult(ok=True, artifact=cached, file_url=cached.source_file.url)

    artifact = InterviewMediaArtifact.objects.create(
        session=session,
        question=question,
        user=user,
        artifact_type=InterviewMediaArtifact.ArtifactType.QUESTION_TTS,
        status=InterviewMediaArtifact.Status.PROCESSING,
        mime_type='audio/mpeg',
    )
    resolved = resolve_ai_config(user, AIModel.ModelType.TTS)
    snapshot = _model_snapshot(resolved.model)
    artifact.provider = snapshot['provider']
    artifact.model_slug = snapshot['model_slug']
    artifact.save(update_fields=['provider', 'model_slug', 'updated_at'])

    if not resolved.model or not resolved.api_key:
        artifact.status = InterviewMediaArtifact.Status.FAILED
        artifact.error_message = 'tts_model_or_api_key_missing'
        artifact.save(update_fields=['status', 'error_message', 'updated_at'])
        return SpeechResult(ok=False, artifact=artifact, error=artifact.error_message)

    try:
        client = _openai_client(resolved.api_key, resolved.model)
        voice = getattr(settings, 'TTS_DEFAULT_VOICE', 'alloy')
        response_format = getattr(settings, 'TTS_RESPONSE_FORMAT', 'mp3')
        response = client.audio.speech.create(
            model=resolved.model.model_slug,
            voice=voice,
            input=text,
            response_format=response_format,
        )
        suffix = response_format if response_format.startswith('.') else f'.{response_format}'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name
        try:
            if hasattr(response, 'write_to_file'):
                response.write_to_file(temp_path)
                with open(temp_path, 'rb') as audio_file:
                    content = audio_file.read()
            elif hasattr(response, 'read'):
                content = response.read()
            else:
                content = bytes(response)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        if not content:
            raise RuntimeError('tts_empty_audio')
        artifact.source_file.save(f'question-{question.id}-{uuid.uuid4().hex}{suffix}', ContentFile(content), save=False)
        artifact.mime_type = mimetypes.types_map.get(suffix, 'audio/mpeg')
        artifact.status = InterviewMediaArtifact.Status.COMPLETED
        artifact.metadata = {
            'tts_source': resolved.source,
            'voice': voice,
            'synthesized_at': timezone.now().isoformat(),
            'text_hash': text_hash,
        }
        artifact.save(update_fields=['source_file', 'mime_type', 'status', 'metadata', 'updated_at'])
        return SpeechResult(ok=True, artifact=artifact, file_url=artifact.source_file.url)
    except Exception as exc:
        artifact.status = InterviewMediaArtifact.Status.FAILED
        artifact.error_message = str(exc)[:1000]
        artifact.save(update_fields=['status', 'error_message', 'updated_at'])
        return SpeechResult(ok=False, artifact=artifact, error=artifact.error_message)
