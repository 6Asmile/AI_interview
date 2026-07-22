#!/usr/bin/env sh
set -eu

wait_for_tcp() {
  host="$1"
  port="$2"
  name="$3"
  python - "$host" "$port" "$name" <<'PY'
import socket
import sys
import time

host, port, name = sys.argv[1], int(sys.argv[2]), sys.argv[3]
deadline = time.time() + 90
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=3):
            print(f"{name} is ready at {host}:{port}")
            sys.exit(0)
    except OSError:
        time.sleep(2)
print(f"Timed out waiting for {name} at {host}:{port}", file=sys.stderr)
sys.exit(1)
PY
}

if [ "${IFACEOFF_WAIT_FOR_SERVICES:-1}" = "1" ]; then
  wait_for_tcp "${POSTGRES_HOST:-postgres}" "${POSTGRES_PORT:-5432}" "postgresql"
  wait_for_tcp "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}" "redis"
  wait_for_tcp "${RABBITMQ_HOST:-rabbitmq}" "5672" "rabbitmq"
fi

if [ "${IFACEOFF_RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi

if [ "${IFACEOFF_SETUP_AGENT_CHECKPOINT:-0}" = "1" ]; then
  python manage.py setup_agent_checkpoint
fi

if [ "${IFACEOFF_COLLECTSTATIC:-0}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
