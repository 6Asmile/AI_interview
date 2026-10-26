from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from core.admission import (
    AdmissionController,
    RuntimePolicyConfigurationError,
    TokenDimension,
    _client_ip,
    runtime_policy_integer,
)
from core.cache_policy import CoordinationSingleFlight
from core.redis_keys import RedisKeyError, build_redis_key, opaque_identifier
from core.views import (
    consume_websocket_ticket,
    websocket_ticket_cache_key,
    websocket_ticket_claim_key,
)


@override_settings(
    IFACEOFF_ENV='test',
    SECRET_KEY='test-application-secret',
    REDIS_KEY_HMAC_SECRET='test-redis-key-secret',
)
class RedisKeyBuilderTests(SimpleTestCase):
    def test_key_has_canonical_domain_shape_and_hides_sensitive_parts(self):
        key = build_redis_key(
            domain='coordination',
            tenant='tenant-17',
            resource='rate-limit',
            version='v2',
            parts=('resume.preview',),
            opaque_parts=('candidate@example.com', '203.0.113.9'),
        )

        self.assertTrue(key.startswith('ifaceoff:test:coordination:tenant-17:rate-limit:v2:'))
        self.assertNotIn('candidate@example.com', key)
        self.assertNotIn('203.0.113.9', key)
        self.assertEqual(len([part for part in key.split(':') if part.startswith('h1_')]), 2)

    def test_opaque_identifier_is_stable_and_purpose_scoped(self):
        first = opaque_identifier('same-value', purpose='ticket')
        self.assertEqual(first, opaque_identifier('same-value', purpose='ticket'))
        self.assertNotEqual(first, opaque_identifier('same-value', purpose='email'))

    def test_plain_pii_or_unknown_domain_is_rejected(self):
        with self.assertRaises(RedisKeyError):
            build_redis_key(
                domain='coordination',
                resource='ticket',
                parts=('candidate@example.com',),
            )
        with self.assertRaises(RedisKeyError):
            build_redis_key(domain='business-data', resource='ticket')


@override_settings(
    IFACEOFF_ENV='test',
    SECRET_KEY='test-application-secret',
    REDIS_KEY_HMAC_SECRET='test-redis-key-secret',
    ADMISSION_USER_PER_MINUTE='19',
)
class AdmissionControllerTests(SimpleTestCase):
    def test_all_rate_dimensions_are_decided_by_one_lua_evaluation(self):
        redis = Mock()
        redis.eval.return_value = [1, 0, 0]
        controller = AdmissionController(redis=redis)

        decision = controller.consume_multi_tokens([
            TokenDimension('resume.preview.user', 'candidate-42', 10, 10),
            TokenDimension('resume.preview.ip', '203.0.113.8', 20, 20),
            TokenDimension('resume.preview.company', 'company-7', 30, 30),
        ])

        self.assertTrue(decision.allowed)
        redis.eval.assert_called_once()
        arguments = redis.eval.call_args.args
        self.assertEqual(arguments[1], 3)
        serialized_call = repr(arguments[2:])
        self.assertNotIn('candidate-42', serialized_call)
        self.assertNotIn('203.0.113.8', serialized_call)
        self.assertNotIn('company-7', serialized_call)

    def test_blocked_dimension_and_retry_are_returned(self):
        redis = Mock()
        redis.eval.return_value = [0, 2, 1750]
        decision = AdmissionController(redis=redis).consume_multi_tokens([
            TokenDimension('job-match.user', '1', 1, 1),
            TokenDimension('job-match.ip', '198.51.100.1', 1, 1),
        ])
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.blocked_index, 1)
        self.assertEqual(decision.retry_after_ms, 1750)

    def test_lease_renew_and_release_use_the_same_opaque_owner(self):
        redis = Mock()
        redis.eval.side_effect = [1, 1, 1]
        controller = AdmissionController(redis=redis)

        self.assertTrue(controller.acquire_lease(
            scope='model-deployment', identity='deployment-1', member='raw-owner', limit=2, lease_seconds=5
        ))
        self.assertTrue(controller.renew_lease(
            scope='model-deployment', identity='deployment-1', member='raw-owner', lease_seconds=5
        ))
        self.assertTrue(controller.release_lease(
            scope='model-deployment', identity='deployment-1', member='raw-owner'
        ))

        calls = redis.eval.call_args_list
        owner_values = (calls[0].args[-2], calls[1].args[-1], calls[2].args[-1])
        self.assertEqual(owner_values[0], owner_values[1])
        self.assertEqual(owner_values[1], owner_values[2])
        self.assertNotIn('raw-owner', repr(calls))

    def test_runtime_policy_values_are_strict_but_environment_fallback_accepts_digits(self):
        self.assertEqual(runtime_policy_integer(
            {},
            'user_per_minute',
            setting_name='ADMISSION_USER_PER_MINUTE',
            default=12,
            minimum=1,
            maximum=100,
        ), 19)
        with self.assertRaises(RuntimePolicyConfigurationError):
            runtime_policy_integer(
                {'user_per_minute': '19'},
                'user_per_minute',
                setting_name='ADMISSION_USER_PER_MINUTE',
                default=12,
                minimum=1,
                maximum=100,
            )
        with self.assertRaises(RuntimePolicyConfigurationError):
            runtime_policy_integer(
                {'user_per_minute': True},
                'user_per_minute',
                setting_name='ADMISSION_USER_PER_MINUTE',
                default=12,
                minimum=1,
                maximum=100,
            )

    @override_settings(ADMISSION_TRUSTED_PROXY_IPS=['10.0.0.0/8'])
    def test_forwarded_ip_is_used_only_for_a_trusted_proxy(self):
        trusted = Mock(META={
            'REMOTE_ADDR': '10.0.0.5',
            'HTTP_X_FORWARDED_FOR': '203.0.113.7, 10.0.0.4',
        })
        untrusted = Mock(META={
            'REMOTE_ADDR': '198.51.100.8',
            'HTTP_X_FORWARDED_FOR': '203.0.113.7',
        })
        self.assertEqual(_client_ip(trusted), '203.0.113.7')
        self.assertEqual(_client_ip(untrusted), '198.51.100.8')


@override_settings(
    IFACEOFF_ENV='test',
    SECRET_KEY='test-application-secret',
    REDIS_KEY_HMAC_SECRET='test-redis-key-secret',
)
class CoordinationSingleFlightTests(SimpleTestCase):
    @patch('core.cache_policy.get_redis_connection')
    def test_lease_lives_in_coordination_and_release_is_owner_checked(self, connection):
        redis = connection.return_value
        redis.set.return_value = True
        redis.eval.return_value = 1

        lease = CoordinationSingleFlight(
            'private:cache:input',
            'reference_answer',
            ttl_seconds=30,
            wait_seconds=0,
        )
        self.assertTrue(lease.acquire())
        self.assertTrue(lease.release())

        connection.assert_called_once_with('coordination')
        lock_key = redis.set.call_args.args[0]
        self.assertNotIn('private:cache:input', lock_key)
        self.assertTrue(redis.set.call_args.kwargs['nx'])
        self.assertEqual(redis.set.call_args.kwargs['px'], 30_000)
        self.assertEqual(redis.eval.call_args.args[-1], redis.set.call_args.args[1])


class _TicketCache:
    def __init__(self, key, payload):
        self.values = {key: payload}

    def get(self, key):
        return self.values.get(key)

    def add(self, key, value, timeout=None):
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def delete(self, key):
        return bool(self.values.pop(key, None))


@override_settings(
    IFACEOFF_ENV='test',
    SECRET_KEY='test-application-secret',
    REDIS_KEY_HMAC_SECRET='test-redis-key-secret',
)
class WebSocketTicketConsumptionTests(SimpleTestCase):
    @patch('core.views.caches')
    def test_wrong_resource_does_not_burn_ticket_before_atomic_claim(self, caches):
        ticket = 'one-time-secret'
        payload = {
            'user_id': 7,
            'scope': 'chat',
            'resource_id': '42',
            'expires_at': (timezone.now() + timedelta(seconds=45)).isoformat(),
        }
        cache = _TicketCache(websocket_ticket_cache_key(ticket), payload)
        caches.__getitem__.return_value = cache

        denied = consume_websocket_ticket(
            ticket,
            expected_scope='chat',
            expected_resource='41',
        )
        accepted = consume_websocket_ticket(
            ticket,
            expected_scope='chat',
            expected_resource='42',
        )
        replay = consume_websocket_ticket(
            ticket,
            expected_scope='chat',
            expected_resource='42',
        )

        self.assertIsNone(denied)
        self.assertEqual(accepted, payload)
        self.assertIsNone(replay)
        self.assertIn(websocket_ticket_claim_key(ticket), cache.values)
