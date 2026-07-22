from django.test import SimpleTestCase

from ai_interview_backend.database import postgres_database_config


class PostgreSQLDatabaseConfigTests(SimpleTestCase):
    def test_parses_encoded_credentials_and_ssl_options(self):
        config = postgres_database_config(
            'postgresql://app%40user:p%2Fword@postgres:5432/ifaceoff_app?sslmode=require',
            pool_enabled=True,
        )

        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(config['NAME'], 'ifaceoff_app')
        self.assertEqual(config['USER'], 'app@user')
        self.assertEqual(config['PASSWORD'], 'p/word')
        self.assertEqual(config['OPTIONS']['sslmode'], 'require')
        self.assertEqual(config['OPTIONS']['pool']['max_size'], 10)
        self.assertTrue(config['DISABLE_SERVER_SIDE_CURSORS'])

    def test_rejects_non_postgresql_urls(self):
        with self.assertRaisesRegex(ValueError, 'postgresql'):
            postgres_database_config('sqlite:///tmp/ifaceoff.db')
