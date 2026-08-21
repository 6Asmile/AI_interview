import asyncio
import json
import time
import uuid

from asgiref.sync import sync_to_async
from django.conf import settings
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import InterviewQuestion, InterviewSession, SpeechLatencyMetric
from .speech_services import SpeechResult, transcribe_bytes, transcribe_partial_bytes


class InterviewSpeechConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4401)
            return
        self.session = await self._get_allowed_session()
        if not self.session:
            await self.close(code=4403)
            return
        self.audio_chunks = []
        self.question_id = None
        self.mime_type = 'audio/webm'
        self.max_audio_bytes = getattr(settings, 'SPEECH_MAX_AUDIO_BYTES', 25 * 1024 * 1024)
        self.received_audio_bytes = 0
        self.utterance_id = ''
        self.language = None
        self.partial_task = None
        self.last_partial_at = 0.0
        self.last_partial_text = ''
        self.partial_sequence = 0
        self.first_audio_at = 0.0
        self.stop_requested_at = 0.0
        await self.accept()
        await self.send_json({'event': 'speech.connected', 'session_id': str(self.session_id)})

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None:
            self.received_audio_bytes += len(bytes_data)
            if self.received_audio_bytes > self.max_audio_bytes:
                self.audio_chunks = []
                await self.send_json({
                    'event': 'asr.error',
                    'error': 'audio_too_large',
                    'max_bytes': self.max_audio_bytes,
                })
                await self.close(code=4409)
                return
            self.audio_chunks.append(bytes_data)
            if not self.first_audio_at:
                self.first_audio_at = time.perf_counter()
            await self._schedule_partial_if_due()
            await self.send_json({
                'event': 'asr.status',
                'status': 'receiving',
                'chunk_count': len(self.audio_chunks),
            })
            return

        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_json({'event': 'asr.error', 'error': 'invalid_json'})
            return

        event = payload.get('event')
        if event == 'asr.start':
            self.audio_chunks = []
            self.received_audio_bytes = 0
            self.question_id = payload.get('question_id')
            self.mime_type = payload.get('mime_type') or 'audio/webm'
            self.language = payload.get('language') or None
            self.utterance_id = str(payload.get('utterance_id') or uuid.uuid4().hex)
            self.last_partial_at = 0.0
            self.last_partial_text = ''
            self.partial_sequence = 0
            self.first_audio_at = 0.0
            if self.question_id and not await self._question_exists(self.question_id):
                await self.send_json({'event': 'asr.error', 'error': 'question_not_found_or_forbidden'})
                return
            await self.send_json({'event': 'asr.started', 'utterance_id': self.utterance_id})
            return
        if event == 'asr.stop':
            await self._finalize_asr()
            return
        if event == 'asr.cancel':
            self.audio_chunks = []
            await self.send_json({'event': 'asr.cancelled'})
            return
        await self.send_json({'event': 'asr.error', 'error': 'unsupported_event'})

    async def _finalize_asr(self):
        if not self.audio_chunks:
            await self.send_json({'event': 'asr.error', 'error': 'audio_empty'})
            return
        self.stop_requested_at = time.perf_counter()
        if self.partial_task and not self.partial_task.done():
            self.partial_task.cancel()
        await self.send_json({'event': 'asr.status', 'status': 'transcribing', 'utterance_id': self.utterance_id})
        audio_bytes = b''.join(self.audio_chunks)
        result = await sync_to_async(self._transcribe_sync, thread_sensitive=False)(audio_bytes)
        if result.ok and result.artifact:
            finalization_latency_ms = round((time.perf_counter() - self.stop_requested_at) * 1000, 2)
            await self._record_metric(
                SpeechLatencyMetric.MetricType.ASR_FINAL,
                finalization_latency_ms,
            )
            await self.send_json({
                'event': 'asr.final',
                'artifact_id': str(result.artifact.id),
                'transcript': result.text,
                'confidence': result.confidence,
                'status': result.artifact.status,
                'utterance_id': self.utterance_id,
                'sequence': self.partial_sequence + 1,
                'finalization_latency_ms': finalization_latency_ms,
            })
        else:
            await self.send_json({
                'event': 'asr.error',
                'artifact_id': str(result.artifact.id) if result.artifact else '',
                'error': result.error or 'asr_failed',
            })
        self.audio_chunks = []

    async def _schedule_partial_if_due(self):
        interval = float(getattr(settings, 'ASR_PARTIAL_INTERVAL_SECONDS', 0.25))
        minimum_bytes = int(getattr(settings, 'ASR_PARTIAL_MIN_BYTES', 4_000))
        now = time.perf_counter()
        if self.received_audio_bytes < minimum_bytes or now - self.last_partial_at < interval:
            return
        if self.partial_task and not self.partial_task.done():
            return
        self.last_partial_at = now
        snapshot = b''.join(self.audio_chunks)
        self.partial_task = asyncio.create_task(self._emit_partial(snapshot))

    async def _emit_partial(self, audio_bytes: bytes):
        result = await sync_to_async(
            transcribe_partial_bytes,
            thread_sensitive=False,
        )(
            user=self.user,
            audio_bytes=audio_bytes,
            filename=f'partial-{self.utterance_id}.webm',
            mime_type=self.mime_type,
            language=self.language,
        )
        if not result.ok or not result.text or result.text == self.last_partial_text:
            return
        self.last_partial_text = result.text
        self.partial_sequence += 1
        first_partial_latency_ms = (
            round((time.perf_counter() - self.first_audio_at) * 1000, 2)
            if self.first_audio_at else None
        )
        if self.partial_sequence == 1 and first_partial_latency_ms is not None:
            await self._record_metric(
                SpeechLatencyMetric.MetricType.ASR_FIRST_PARTIAL,
                first_partial_latency_ms,
            )
        await self.send_json({
            'event': 'asr.partial',
            'utterance_id': self.utterance_id,
            'sequence': self.partial_sequence,
            'transcript': result.text,
            'first_partial_latency_ms': first_partial_latency_ms,
            'authoritative': False,
        })

    def _transcribe_sync(self, audio_bytes):
        question = None
        if self.question_id:
            try:
                question = InterviewQuestion.objects.get(id=self.question_id, session_id=self.session_id)
            except InterviewQuestion.DoesNotExist:
                return SpeechResult(ok=False, error='question_not_found_or_forbidden')
        return transcribe_bytes(
            session=self.session,
            question=question,
            user=self.user,
            audio_bytes=audio_bytes,
            filename=f'answer-{uuid.uuid4().hex}.webm',
            mime_type=self.mime_type,
            metadata={'transport': 'websocket', 'chunk_count': len(self.audio_chunks)},
        )

    async def disconnect(self, close_code):
        if self.partial_task and not self.partial_task.done():
            self.partial_task.cancel()

    @sync_to_async
    def _get_allowed_session(self):
        try:
            session = InterviewSession.objects.get(id=self.session_id)
        except InterviewSession.DoesNotExist:
            return None
        if session.user_id == self.user.id or self.user.is_staff:
            return session
        return None

    @sync_to_async
    def _question_exists(self, question_id):
        return InterviewQuestion.objects.filter(id=question_id, session_id=self.session_id).exists()

    @sync_to_async
    def _record_metric(self, metric_type, latency_ms):
        question_id = self.question_id if self.question_id else None
        SpeechLatencyMetric.objects.create(
            session=self.session,
            question_id=question_id,
            user=self.user,
            metric_type=metric_type,
            latency_ms=max(0, float(latency_ms or 0)),
            language=self.language or '',
            model_alias='speech.asr',
            metadata={'transport': 'websocket'},
        )

    async def send_json(self, payload: dict):
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))
