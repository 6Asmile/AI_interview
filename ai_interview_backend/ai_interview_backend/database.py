from __future__ import annotations

from urllib.parse import parse_qsl, unquote, urlsplit


def postgres_database_config(
    database_url: str,
    *,
    conn_max_age: int = 0,
    pool_enabled: bool = False,
    disable_server_side_cursors: bool = True,
) -> dict:
    """Build a Django PostgreSQL config without adding another URL parser dependency."""
    parsed = urlsplit((database_url or '').strip())
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError('IFACEOFF_DATABASE_URL must use postgresql://')
    if not parsed.hostname or not parsed.path.strip('/'):
        raise ValueError('IFACEOFF_DATABASE_URL must include a host and database name')

    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    options = {}
    for key in ('sslmode', 'sslcert', 'sslkey', 'sslrootcert', 'application_name', 'connect_timeout'):
        if query.get(key):
            options[key] = int(query[key]) if key == 'connect_timeout' else query[key]
    if pool_enabled:
        options['pool'] = {
            'min_size': 1,
            'max_size': 10,
            'timeout': 10,
        }

    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed.path.lstrip('/')),
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname,
        'PORT': str(parsed.port or 5432),
        'CONN_MAX_AGE': int(conn_max_age),
        'CONN_HEALTH_CHECKS': True,
        'DISABLE_SERVER_SIDE_CURSORS': bool(disable_server_side_cursors),
        'OPTIONS': options,
    }
