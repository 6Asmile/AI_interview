from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from users import services


@override_settings(
    IFACEOFF_ENV='test',
    SECRET_KEY='test-application-secret',
    REDIS_KEY_HMAC_SECRET='test-redis-key-secret',
    DEFAULT_FROM_EMAIL='noreply@example.test',
    EMAIL_VERIFICATION_CODE_TTL_SECONDS=300,
)
class VerificationCodeRedisTests(SimpleTestCase):
    @patch('users.services.send_mail', return_value=1)
    @patch('users.services.get_redis_connection')
    @patch('users.services.generate_email_code', return_value='123456')
    def test_code_and_ttl_are_written_atomically_without_exposing_email_or_code(
        self, generate_code, connection, send_mail
    ):
        redis = connection.return_value
        redis.eval.return_value = 'generation'

        self.assertTrue(services.send_verification_code('Candidate@Example.com'))

        redis.eval.assert_called_once()
        arguments = redis.eval.call_args.args
        self.assertIs(arguments[0], services._STORE_CODE_SCRIPT)
        self.assertIn("'HSET'", arguments[0])
        self.assertIn("'PEXPIRE'", arguments[0])
        self.assertNotIn('candidate@example.com', arguments[2])
        self.assertNotIn('123456', repr(arguments))
        self.assertEqual(arguments[-1], 300_000)

    @patch('users.services.send_mail', return_value=1)
    @patch('users.services.get_redis_connection')
    def test_each_resend_uses_a_new_generation(self, connection, send_mail):
        redis = connection.return_value
        redis.eval.return_value = 'generation'

        self.assertTrue(services.send_verification_code('candidate@example.com'))
        self.assertTrue(services.send_verification_code('candidate@example.com'))

        first_generation = redis.eval.call_args_list[0].args[-2]
        second_generation = redis.eval.call_args_list[1].args[-2]
        self.assertNotEqual(first_generation, second_generation)

    @patch('users.services.send_mail', side_effect=RuntimeError('mail unavailable'))
    @patch('users.services.get_redis_connection')
    def test_mail_failure_only_deletes_the_generation_owned_by_that_send(self, connection, send_mail):
        redis = connection.return_value
        redis.eval.return_value = 1

        self.assertFalse(services.send_verification_code('candidate@example.com'))

        self.assertEqual(redis.eval.call_count, 2)
        store_call, cleanup_call = redis.eval.call_args_list
        self.assertIs(cleanup_call.args[0], services._DELETE_GENERATION_SCRIPT)
        self.assertEqual(store_call.args[-2], cleanup_call.args[-1])
        redis.delete.assert_not_called()
