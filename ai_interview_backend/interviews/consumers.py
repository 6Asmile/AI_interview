import json
import uuid

from asgiref.sync import sync_to_async
from django.conf import settings
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import InterviewQuestion, InterviewSession
from .speech_services import SpeechResult, transcribe_bytes


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
            if self.question_id and not await self._question_exists(self.question_id):
                await self.send_json({'event': 'asr.error', 'error': 'question_not_found_or_forbidden'})
                return
            await self.send_json({'event': 'asr.started'})
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
        await self.send_json({'event': 'asr.status', 'status': 'transcribing'})
        audio_bytes = b''.join(self.audio_chunks)
        result = await sync_to_async(self._transcribe_sync, thread_sensitive=False)(audio_bytes)
        if result.ok and result.artifact:
            await self.send_json({
                'event': 'asr.final',
                'artifact_id': str(result.artifact.id),
                'transcript': result.text,
                'confidence': result.confidence,
                'status': result.artifact.status,
            })
        else:
            await self.send_json({
                'event': 'asr.error',
                'artifact_id': str(result.artifact.id) if result.artifact else '',
                'error': result.error or 'asr_failed',
            })
        self.audio_chunks = []

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

    async def send_json(self, payload: dict):
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))
