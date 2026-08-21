from contextlib import contextmanager
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, TestCase

from .gateway_executor import (
    CircuitPermit,
    ExecutionTarget,
    GatewayCircuitOpen,
    GatewayDeadlineExceeded,
    GatewayExecutionError,
    GatewayExecutor,
    ModelCircuitBreaker,
    _OPENAI_CLIENTS,
    _OPENAI_CLIENTS_LOCK,
    _REQUESTS_LOCAL,
    _pooled_requests_session,
)
from .model_gateway import ModelGateway
from .models import AIModel, ModelAlias, ModelAttempt, ModelDeployment, ModelRequestLedger


class ProviderHTTPError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f'provider returned {status_code}')


class FakeCircuitBreaker:
    def __init__(self):
        self.before = []
        self.successes = []
        self.failures = []

    def before_call(self, deployment):
        self.before.append(deployment.pk)
        return CircuitPermit('closed')

    def record_success(self, deployment, permit):
        self.successes.append((deployment.pk, permit.state))

    def record_failure(self, deployment, permit):
        self.failures.append((deployment.pk, permit.state))


@contextmanager
def available_capacity(**_kwargs):
    yield 'lease-owner'


def chat_client(*, response=None, error=None):
    create = MagicMock()
    if error is not None:
        create.side_effect = error
    else:
        create.return_value = response
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def asr_client(*, response=None, error=None):
    create = MagicMock()
    if error is not None:
        create.side_effect = error
    else:
        create.return_value = response
    return SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))


def tts_client(*, response=None, error=None):
    create = MagicMock()
    if error is not None:
        create.side_effect = error
    else:
        create.return_value = response
    return SimpleNamespace(audio=SimpleNamespace(speech=SimpleNamespace(create=create)))


class FakeStreamingSpeechResponse:
    def __init__(self, chunks, request_id='stream-tts-request'):
        self.chunks = chunks
        self._request_id = request_id

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_bytes(self, chunk_size=4096):
        del chunk_size
        yield from self.chunks


def streaming_tts_client(response):
    create = MagicMock(return_value=response)
    streaming = SimpleNamespace(create=create)
    return SimpleNamespace(
        audio=SimpleNamespace(
            speech=SimpleNamespace(with_streaming_response=streaming),
        ),
    )


def stream_chunk(value, request_id='provider-request'):
    return SimpleNamespace(
        id=request_id,
        choices=[SimpleNamespace(delta=SimpleNamespace(content=value))],
    )


class GatewayClassificationTests(SimpleTestCase):
    def test_only_transient_provider_failures_are_retryable(self):
        executor = GatewayExecutor(circuit_breaker=FakeCircuitBreaker())

        self.assertFalse(executor._error_details(ProviderHTTPError(401)).retryable)
        self.assertFalse(executor._error_details(ProviderHTTPError(400)).retryable)
        self.assertTrue(executor._error_details(ProviderHTTPError(429)).retryable)
        self.assertTrue(executor._error_details(ProviderHTTPError(503)).retryable)
        self.assertTrue(executor._error_details(requests.Timeout()).retryable)

    def test_remaining_timeout_is_shared_across_fallbacks(self):
        target = SimpleNamespace(timeout=30, total_timeout=5)

        with patch('system.gateway_executor.time.perf_counter', return_value=104.25):
            self.assertEqual(GatewayExecutor._remaining_timeout(100, target), 0.75)
        with patch('system.gateway_executor.time.perf_counter', return_value=105):
            with self.assertRaises(GatewayDeadlineExceeded):
                GatewayExecutor._remaining_timeout(100, target)

    def test_openai_clients_are_reused_and_disable_sdk_retries(self):
        deployment = SimpleNamespace(pk=7, base_url='https://provider.example/v1')
        target = ExecutionTarget(
            alias=SimpleNamespace(),
            deployment=deployment,
            api_key='sk-pool-test',
            timeout=10,
            total_timeout=20,
        )
        with _OPENAI_CLIENTS_LOCK:
            _OPENAI_CLIENTS.clear()

        with patch('system.gateway_executor.OpenAI') as constructor:
            constructor.return_value = MagicMock()
            first = GatewayExecutor(circuit_breaker=FakeCircuitBreaker())._client(target)
            second = GatewayExecutor(circuit_breaker=FakeCircuitBreaker())._client(target)

        self.assertIs(first, second)
        constructor.assert_called_once_with(
            api_key='sk-pool-test',
            base_url='https://provider.example/v1',
            max_retries=0,
        )

    def test_rerank_http_session_is_reused_per_worker_thread(self):
        if hasattr(_REQUESTS_LOCAL, 'session'):
            del _REQUESTS_LOCAL.session

        self.assertIs(_pooled_requests_session(), _pooled_requests_session())

    @patch('system.model_gateway.GatewayExecutor.chat_json', return_value=None)
    def test_model_gateway_does_not_issue_a_legacy_second_request(self, execute):
        result = ModelGateway().chat_json([{'role': 'user', 'content': 'test'}])

        self.assertIsNone(result)
        execute.assert_called_once()

    @patch('system.model_gateway.GatewayExecutor.transcribe_audio', return_value=('text', {}))
    def test_model_gateway_uses_existing_canonical_speech_alias(self, execute):
        result = ModelGateway().transcribe_audio(b'audio')

        self.assertEqual(result, ('text', {}))
        self.assertEqual(execute.call_args.args[:2], ('speech.asr', b'audio'))


class CircuitBreakerTests(SimpleTestCase):
    def test_open_circuit_rejects_with_retry_delay(self):
        redis = MagicMock()
        redis.eval.return_value = [0, b'open', b'', 2500]
        deployment = SimpleNamespace(pk=9, capabilities={})
        breaker = ModelCircuitBreaker(redis_connection=redis, clock_ms=lambda: 1000)

        with self.assertRaises(GatewayCircuitOpen) as raised:
            breaker.before_call(deployment)

        self.assertEqual(raised.exception.retry_after_ms, 2500)
        self.assertIn(':coordination:global:model-circuit:v1:9', redis.eval.call_args.args[2])

    def test_half_open_probe_is_owner_checked_on_success_and_failure(self):
        redis = MagicMock()
        redis.eval.return_value = [1, b'half_open', b'probe-owner', 0]
        deployment = SimpleNamespace(
            pk=11,
            capabilities={
                'circuit_failure_threshold': 4,
                'circuit_open_seconds': 20,
                'circuit_half_open_probe_seconds': 5,
            },
        )
        breaker = ModelCircuitBreaker(redis_connection=redis, clock_ms=lambda: 1000)

        permit = breaker.before_call(deployment)
        breaker.record_success(deployment, permit)
        breaker.record_failure(deployment, permit)

        self.assertEqual(permit, CircuitPermit('half_open', 'probe-owner'))
        success_args = redis.eval.call_args_list[1].args
        failure_args = redis.eval.call_args_list[2].args
        self.assertEqual(success_args[-1], 'probe-owner')
        self.assertEqual(failure_args[-3:], (4, 20_000, 'probe-owner'))


class GatewayExecutionLedgerTests(TestCase):
    def setUp(self):
        self.alias = ModelAlias.objects.create(
            slug='chat.reliability-test',
            name='Reliability test',
            model_type=AIModel.ModelType.CHAT,
        )
        self.primary = ModelDeployment.objects.create(
            name='gateway-primary-test',
            provider='openai_compatible',
            remote_model='primary-model',
            model_type=AIModel.ModelType.CHAT,
            base_url='https://primary.example/v1',
            input_price_per_million=Decimal('1.0'),
            output_price_per_million=Decimal('2.0'),
        )
        self.backup = ModelDeployment.objects.create(
            name='gateway-backup-test',
            provider='openai_compatible',
            remote_model='backup-model',
            model_type=AIModel.ModelType.CHAT,
            base_url='https://backup.example/v1',
            input_price_per_million=Decimal('2.0'),
            output_price_per_million=Decimal('4.0'),
        )

    def targets(self):
        return [
            ExecutionTarget(self.alias, self.primary, 'sk-primary', 20, 30),
            ExecutionTarget(self.alias, self.backup, 'sk-backup', 20, 30),
        ]

    def executor_with_clients(self, clients):
        circuit = FakeCircuitBreaker()
        executor = GatewayExecutor(circuit_breaker=circuit)
        executor.targets = MagicMock(return_value=self.targets())
        executor._client = MagicMock(side_effect=lambda target: clients[target.deployment.pk])
        return executor, circuit

    @patch('system.gateway_executor.concurrency_lease', available_capacity)
    def test_rate_limit_falls_back_and_records_every_provider_attempt(self):
        response = SimpleNamespace(
            id='backup-request-id',
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        )
        clients = {
            self.primary.pk: chat_client(error=ProviderHTTPError(429)),
            self.backup.pk: chat_client(response=response),
        }
        executor, circuit = self.executor_with_clients(clients)

        result = executor.chat_json(
            'chat.reliability-test',
            [{'role': 'user', 'content': 'hello'}],
        )

        self.assertEqual(result, {'ok': True})
        ledger = ModelRequestLedger.objects.get(alias=self.alias)
        attempts = list(ledger.attempts.order_by('attempt_number'))
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].error_category, 'rate_limit')
        self.assertTrue(attempts[0].retryable)
        self.assertEqual(attempts[1].provider_request_id, 'backup-request-id')
        self.assertEqual(attempts[1].estimated_cost, Decimal('0.000400'))
        self.assertEqual(ledger.estimated_cost, Decimal('0.000400'))
        self.assertEqual(ledger.fallback_count, 1)
        self.assertEqual(circuit.failures, [(self.primary.pk, 'closed')])
        self.assertEqual(circuit.successes, [(self.backup.pk, 'closed')])
        timeout = clients[self.backup.pk].chat.completions.create.call_args.kwargs['timeout']
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 20)

    @patch('system.gateway_executor.concurrency_lease', available_capacity)
    def test_chat_text_returns_plain_content_through_the_same_ledger(self):
        response = SimpleNamespace(
            id='plain-request-id',
            choices=[SimpleNamespace(message=SimpleNamespace(content='plain answer'))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3),
        )
        executor, circuit = self.executor_with_clients({
            self.primary.pk: chat_client(response=response),
            self.backup.pk: chat_client(response=MagicMock()),
        })

        result = executor.chat_text(
            'chat.reliability-test',
            [{'role': 'user', 'content': 'hello'}],
        )

        self.assertEqual(result, 'plain answer')
        attempt = ModelAttempt.objects.get(request__alias=self.alias)
        self.assertEqual(attempt.provider_request_id, 'plain-request-id')
        self.assertEqual(attempt.input_tokens, 12)
        self.assertEqual(attempt.output_tokens, 3)
        self.assertEqual(circuit.successes, [(self.primary.pk, 'closed')])

    @patch('system.gateway_executor.concurrency_lease', available_capacity)
    def test_authentication_error_does_not_retry_or_switch(self):
        clients = {
            self.primary.pk: chat_client(error=ProviderHTTPError(401)),
            self.backup.pk: chat_client(response=MagicMock()),
        }
        executor, _circuit = self.executor_with_clients(clients)

        with self.assertRaisesMessage(GatewayExecutionError, 'provider_authentication_error'):
            executor.chat_json(
                'chat.reliability-test',
                [{'role': 'user', 'content': 'hello'}],
            )

        ledger = ModelRequestLedger.objects.get(alias=self.alias)
        attempt = ledger.attempts.get()
        self.assertEqual(attempt.error_category, 'authentication')
        self.assertFalse(attempt.retryable)
        self.assertEqual(ledger.fallback_count, 0)
        clients[self.backup.pk].chat.completions.create.assert_not_called()

    @patch('system.gateway_executor.concurrency_lease', available_capacity)
    def test_stream_never_switches_after_first_content_token(self):
        def interrupted_stream():
            yield stream_chunk('first token', 'primary-stream-id')
            raise requests.Timeout('stream interrupted')

        primary_client = chat_client(response=interrupted_stream())
        backup_client = chat_client(response=iter([stream_chunk('backup')]))
        executor, _circuit = self.executor_with_clients({
            self.primary.pk: primary_client,
            self.backup.pk: backup_client,
        })

        stream = executor.chat_stream(
            'chat.reliability-test',
            [{'role': 'user', 'content': 'hello'}],
        )
        self.assertEqual(next(stream), 'first token')
        with self.assertRaisesMessage(GatewayExecutionError, 'provider_timeout'):
            next(stream)

        backup_client.chat.completions.create.assert_not_called()
        attempt = ModelAttempt.objects.get(request__alias=self.alias)
        self.assertEqual(attempt.provider_request_id, 'primary-stream-id')
        self.assertGreater(attempt.output_tokens, 0)

    @patch('system.gateway_executor.concurrency_lease', available_capacity)
    def test_stream_checks_wall_clock_deadline_between_continuous_chunks(self):
        primary_client = chat_client(response=iter([
            stream_chunk('first', 'deadline-stream-id'),
            stream_chunk('second', 'deadline-stream-id'),
        ]))
        backup_client = chat_client(response=iter([stream_chunk('backup')]))
        executor, _circuit = self.executor_with_clients({
            self.primary.pk: primary_client,
            self.backup.pk: backup_client,
        })
        executor._remaining_timeout = MagicMock(side_effect=[
            20,
            20,
            19,
            GatewayDeadlineExceeded('model_gateway_total_deadline_exceeded'),
        ])

        stream = executor.chat_stream(
            'chat.reliability-test',
            [{'role': 'user', 'content': 'hello'}],
        )
        self.assertEqual(next(stream), 'first')
        with self.assertRaisesMessage(GatewayExecutionError, 'total_deadline_exceeded'):
            next(stream)

        backup_client.chat.completions.create.assert_not_called()

    @patch('system.gateway_executor.concurrency_lease', available_capacity)
    def test_empty_stream_delta_is_not_a_first_token_and_can_fallback(self):
        def failed_before_content():
            yield stream_chunk('')
            raise requests.Timeout('failed before content')

        primary_client = chat_client(response=failed_before_content())
        backup_client = chat_client(response=iter([stream_chunk('backup token')]))
        executor, _circuit = self.executor_with_clients({
            self.primary.pk: primary_client,
            self.backup.pk: backup_client,
        })

        result = list(executor.chat_stream(
            'chat.reliability-test',
            [{'role': 'user', 'content': 'hello'}],
        ))

        self.assertEqual(result, ['backup token'])
        ledger = ModelRequestLedger.objects.get(alias=self.alias)
        self.assertEqual(ledger.fallback_count, 1)
        self.assertEqual(ledger.attempts.count(), 2)

    @patch('system.gateway_executor.concurrency_lease', available_capacity)
    def test_asr_accepts_file_input_without_persisting_audio_content(self):
        alias = ModelAlias.objects.create(
            slug='speech.asr.reliability-test',
            name='ASR reliability test',
            model_type=AIModel.ModelType.ASR,
        )
        deployment = ModelDeployment.objects.create(
            name='gateway-asr-test',
            provider='openai_compatible',
            remote_model='asr-model',
            model_type=AIModel.ModelType.ASR,
            base_url='https://asr.example/v1',
        )
        target = ExecutionTarget(alias, deployment, 'sk-asr', 20, 30)
        response = SimpleNamespace(
            id='asr-request-id',
            text='transcribed text',
            usage=SimpleNamespace(input_tokens=8, output_tokens=2),
        )
        client = asr_client(response=response)
        executor = GatewayExecutor(circuit_breaker=FakeCircuitBreaker())
        executor.targets = MagicMock(return_value=[target])
        executor._client = MagicMock(return_value=client)
        source = BytesIO(b'private-audio-bytes')

        transcript, metadata = executor.transcribe_audio(
            alias.slug,
            source,
            filename='../answer.webm',
            content_type='audio/webm',
        )

        self.assertEqual(transcript, 'transcribed text')
        self.assertEqual(metadata['deployment'], deployment.name)
        self.assertEqual(metadata['provider'], 'openai_compatible')
        self.assertEqual(source.tell(), 0)
        file_tuple = client.audio.transcriptions.create.call_args.kwargs['file']
        self.assertEqual(file_tuple[0], 'answer.webm')
        self.assertEqual(file_tuple[1], b'private-audio-bytes')
        ledger = ModelRequestLedger.objects.get(alias=alias)
        attempt = ledger.attempts.get()
        self.assertEqual(ledger.metadata['input_units'], len(b'private-audio-bytes'))
        self.assertEqual(ledger.metadata['input_unit'], 'bytes')
        self.assertEqual(attempt.metadata['input_bytes'], len(b'private-audio-bytes'))
        self.assertNotIn('private-audio-bytes', str(ledger.metadata))
        self.assertNotIn('private-audio-bytes', str(attempt.metadata))

    @patch('system.gateway_executor.concurrency_lease', available_capacity)
    def test_tts_returns_bytes_without_persisting_input_text(self):
        alias = ModelAlias.objects.create(
            slug='speech.tts.reliability-test',
            name='TTS reliability test',
            model_type=AIModel.ModelType.TTS,
        )
        deployment = ModelDeployment.objects.create(
            name='gateway-tts-test',
            provider='openai_compatible',
            remote_model='tts-model',
            model_type=AIModel.ModelType.TTS,
            base_url='https://tts.example/v1',
        )
        target = ExecutionTarget(alias, deployment, 'sk-tts', 20, 30)
        response = SimpleNamespace(
            _request_id='tts-request-id',
            read=MagicMock(return_value=b'generated-audio'),
            usage=SimpleNamespace(input_tokens=6, output_tokens=4),
        )
        client = tts_client(response=response)
        executor = GatewayExecutor(circuit_breaker=FakeCircuitBreaker())
        executor.targets = MagicMock(return_value=[target])
        executor._client = MagicMock(return_value=client)
        private_text = 'private candidate answer'

        audio, metadata = executor.synthesize_speech(
            alias.slug,
            private_text,
            voice='alloy',
            response_format='mp3',
        )

        self.assertEqual(audio, b'generated-audio')
        self.assertEqual(metadata['provider_request_id'], 'tts-request-id')
        self.assertEqual(metadata['provider'], 'openai_compatible')
        ledger = ModelRequestLedger.objects.get(alias=alias)
        attempt = ledger.attempts.get()
        self.assertEqual(ledger.metadata['input_units'], len(private_text))
        self.assertEqual(ledger.metadata['input_unit'], 'characters')
        self.assertEqual(attempt.metadata['output_bytes'], len(b'generated-audio'))
        self.assertNotIn(private_text, str(ledger.metadata))
        self.assertNotIn(private_text, str(attempt.metadata))

    @patch('system.gateway_executor.concurrency_lease', available_capacity)
    def test_tts_stream_yields_early_chunks_and_records_only_safe_metadata(self):
        alias = ModelAlias.objects.create(
            slug='speech.tts.stream-test',
            name='TTS stream test',
            model_type=AIModel.ModelType.TTS,
        )
        deployment = ModelDeployment.objects.create(
            name='gateway-tts-stream-test',
            provider='openai_compatible',
            remote_model='tts-stream-model',
            model_type=AIModel.ModelType.TTS,
            base_url='https://tts.example/v1',
        )
        target = ExecutionTarget(alias, deployment, 'sk-tts', 20, 30)
        client = streaming_tts_client(FakeStreamingSpeechResponse([b'first-', b'audio']))
        executor = GatewayExecutor(circuit_breaker=FakeCircuitBreaker())
        executor.targets = MagicMock(return_value=[target])
        executor._client = MagicMock(return_value=client)
        private_text = 'candidate private prompt'

        chunks, metadata = executor.synthesize_speech_stream(alias.slug, private_text, response_format='pcm')
        self.assertEqual(next(chunks), b'first-')
        self.assertEqual(list(chunks), [b'audio'])
        self.assertEqual(metadata['sample_rate'], 24000)
        attempt = ModelAttempt.objects.get(request__alias=alias)
        self.assertEqual(attempt.metadata['output_bytes'], len(b'first-audio'))
        self.assertNotIn(private_text, str(attempt.metadata))
        self.assertNotIn(private_text, str(attempt.request.metadata))
