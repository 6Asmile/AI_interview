import mimetypes
import uuid
import hashlib
from dataclasses import dataclass

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from system.model_gateway import ModelGateway

from .models import InterviewMediaArtifact, InterviewQuestion, InterviewSession


@dataclass
class SpeechResult:
    ok: bool
    artifact: InterviewMediaArtifact | None = None
    text: str = ''
    confidence: float | None = None
    file_url: str = ''
    error: str = ''


def _public_speech_error(exc: Exception, capability: str) -> str:
    """Keep the stable media error contract while the gateway owns routing."""

    error = str(exc or '')[:1000]
    if error.startswith(f'no_available_deployment:speech.{capability}'):
        return f'{capability}_model_or_api_key_missing'
    return error


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
    artifact.status = InterviewMediaArtifact.Status.PROCESSING
    artifact.error_message = ''
    artifact.save(update_fields=['status', 'error_message', 'updated_at'])

    if not artifact.source_file:
        artifact.status = InterviewMediaArtifact.Status.FAILED
        artifact.error_message = 'audio_file_missing'
        artifact.save(update_fields=['status', 'error_message', 'updated_at'])
        return SpeechResult(ok=False, artifact=artifact, error=artifact.error_message)

    try:
        artifact.source_file.open('rb')
        try:
            text, gateway_metadata = ModelGateway(user or artifact.user).transcribe_audio(
                artifact.source_file.file,
                filename=(artifact.source_file.name or 'audio.webm').replace('\\', '/').rsplit('/', 1)[-1],
                content_type=artifact.mime_type or 'application/octet-stream',
                alias_slug='speech.asr',
            )
        finally:
            artifact.source_file.close()
        if not text:
            raise RuntimeError('asr_empty_transcript')
        artifact.provider = str(gateway_metadata.get('provider') or '')[:50]
        artifact.model_slug = str(gateway_metadata.get('model') or '')[:100]
        artifact.transcript_text = text
        artifact.asr_confidence = None
        artifact.transcript_segments = []
        artifact.status = InterviewMediaArtifact.Status.COMPLETED
        artifact.metadata = {
            **(artifact.metadata or {}),
            'asr_source': 'model_gateway',
            'gateway_alias': gateway_metadata.get('alias', 'speech.asr'),
            'gateway_deployment': gateway_metadata.get('deployment', ''),
            'transcribed_at': timezone.now().isoformat(),
        }
        artifact.save(update_fields=[
            'provider',
            'model_slug',
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
        artifact.error_message = _public_speech_error(exc, 'asr')
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
    try:
        voice = getattr(settings, 'TTS_DEFAULT_VOICE', 'alloy')
        response_format = getattr(settings, 'TTS_RESPONSE_FORMAT', 'mp3')
        content, gateway_metadata = ModelGateway(user).synthesize_speech(
            text,
            voice=voice,
            response_format=response_format,
            alias_slug='speech.tts',
        )
        suffix = response_format if response_format.startswith('.') else f'.{response_format}'
        if not content:
            raise RuntimeError('tts_empty_audio')
        artifact.provider = str(gateway_metadata.get('provider') or '')[:50]
        artifact.model_slug = str(gateway_metadata.get('model') or '')[:100]
        artifact.source_file.save(f'question-{question.id}-{uuid.uuid4().hex}{suffix}', ContentFile(content), save=False)
        artifact.mime_type = mimetypes.types_map.get(suffix, 'audio/mpeg')
        artifact.status = InterviewMediaArtifact.Status.COMPLETED
        artifact.metadata = {
            'tts_source': 'model_gateway',
            'gateway_alias': gateway_metadata.get('alias', 'speech.tts'),
            'gateway_deployment': gateway_metadata.get('deployment', ''),
            'voice': voice,
            'synthesized_at': timezone.now().isoformat(),
            'text_hash': text_hash,
        }
        artifact.save(update_fields=[
            'provider',
            'model_slug',
            'source_file',
            'mime_type',
            'status',
            'metadata',
            'updated_at',
        ])
        return SpeechResult(ok=True, artifact=artifact, file_url=artifact.source_file.url)
    except Exception as exc:
        artifact.status = InterviewMediaArtifact.Status.FAILED
        artifact.error_message = _public_speech_error(exc, 'tts')
        artifact.save(update_fields=['status', 'error_message', 'updated_at'])
        return SpeechResult(ok=False, artifact=artifact, error=artifact.error_message)
