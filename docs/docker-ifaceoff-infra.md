# Ifaceoff local infrastructure

This stack starts only the services required by a locally running backend:
MySQL, Redis, RabbitMQ, Qdrant, LiteLLM with PostgreSQL, Meilisearch, and
ClamAV. It does not build or run Django, Celery, or Vue.

## Start and stop

```powershell
.\scripts\ifaceoff-infra.ps1 up
.\scripts\ifaceoff-infra.ps1 status
.\scripts\ifaceoff-infra.ps1 logs -Follow
.\scripts\ifaceoff-infra.ps1 down
```

`down` keeps all named volumes. Data is preserved across restarts.

## Local backend connection values

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3307
DB_NAME=ai_interview_db
DB_USER=root
DB_PASSWORD=root
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
RABBITMQ_HOST=127.0.0.1
QDRANT_URL=http://127.0.0.1:6333
LITELLM_PROXY_URL=http://127.0.0.1:4000
MEILISEARCH_URL=http://127.0.0.1:7700
CLAMAV_HOST=127.0.0.1
CLAMAV_PORT=3310
```

Service ports:

| Service | Address |
| --- | --- |
| MySQL | `127.0.0.1:3307` |
| Redis | `127.0.0.1:6379` |
| RabbitMQ | `127.0.0.1:5672` (`15672` for management) |
| Qdrant | `127.0.0.1:6333` |
| LiteLLM | `127.0.0.1:4000` |
| LiteLLM PostgreSQL | `127.0.0.1:5433` |
| Meilisearch | `127.0.0.1:7700` |
| ClamAV | `127.0.0.1:3310` |

The first LiteLLM startup applies its PostgreSQL migrations and can take a few
minutes. Wait for `docker compose ... ps` to report every service as healthy.
The example pins the verified LiteLLM 1.93.0 image digest; set
`LITELLM_IMAGE` explicitly when testing an upgrade.
Discourse is intentionally not part of this stack; deploy it independently
using its official `discourse_docker` launcher and configure SSO/webhooks.

The existing `docker-compose.yml` and `scripts/ifaceoff-docker.ps1` remain the
full-stack deployment. Use `docker-compose.infra.yml` and
`scripts/ifaceoff-infra.ps1` for local development dependencies only.
