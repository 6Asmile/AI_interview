from __future__ import annotations

from contextlib import contextmanager

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def agent_database_url() -> str:
    url = str(getattr(settings, 'AGENT_DATABASE_URL', '') or '').strip()
    if not url:
        raise ImproperlyConfigured('AGENT_DATABASE_URL is required for composite_v4')
    return url


@contextmanager
def postgres_checkpointer():
    """Open a short-lived saver for one graph invocation.

    The compiled graph never owns a global database connection. This keeps the
    Django request path safe under ASGI and lets PgBouncer use transaction mode.
    """

    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(agent_database_url()) as saver:
        yield saver


def setup_checkpoint_schema() -> None:
    with postgres_checkpointer() as saver:
        saver.setup()
