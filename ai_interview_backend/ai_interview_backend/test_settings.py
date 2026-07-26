from .settings import *  # noqa: F403


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # Tool handlers run in worker threads. A file-backed test database keeps
        # the schema visible to those independent Django connections.
        'NAME': BASE_DIR / '.ifaceoff-test.sqlite3',  # noqa: F405
        'TEST': {
            'NAME': BASE_DIR / '.ifaceoff-test.sqlite3',  # noqa: F405
        },
    },
}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_URL = 'memory://'
MEILISEARCH_URL = ''
QDRANT_URL = ''
