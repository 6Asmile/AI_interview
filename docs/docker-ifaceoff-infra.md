# Ifaceoff local infrastructure

This stack starts only the services required by a locally running backend:
MySQL, Redis, RabbitMQ, and Qdrant. It does not build or run Django, Celery, or Vue.

## Start and stop

```powershell
.\scripts\ifaceoff-infra.ps1 up
.\scripts\ifaceoff-infra.ps1 ps
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
```

The existing `docker-compose.yml` and `scripts/ifaceoff-docker.ps1` remain the
full-stack deployment. Use `docker-compose.infra.yml` and
`scripts/ifaceoff-infra.ps1` for local development dependencies only.
