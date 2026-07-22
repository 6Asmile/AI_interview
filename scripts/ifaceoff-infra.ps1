param(
    [ValidateSet("up", "down", "restart", "logs", "ps", "status", "pull", "config")]
    [string]$Action = "up",
    [switch]$Follow
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Root "docker-compose.infra.yml"
$EnvFile = Join-Path $Root ".env.infra"
$ExampleFile = Join-Path $Root ".env.infra.example"

if (!(Test-Path $EnvFile)) {
    Copy-Item $ExampleFile $EnvFile
    Write-Host "Created .env.infra from .env.infra.example."
}

function Compose {
    docker compose --env-file $EnvFile -f $ComposeFile @args
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed with exit code $LASTEXITCODE."
    }
}

switch ($Action) {
    "up" {
        Compose up -d --wait
        Compose ps
        Write-Host ""
        Write-Host "Ifaceoff infrastructure is ready:"
        Write-Host "  PostgreSQL: 127.0.0.1:5433"
        Write-Host "    DBs: ifaceoff_app, ifaceoff_agent, litellm, langfuse"
        Write-Host "  Redis:    127.0.0.1:6379"
        Write-Host "  RabbitMQ: 127.0.0.1:5672"
        Write-Host "  MQ Admin: http://127.0.0.1:15672"
        Write-Host "  Qdrant:   http://127.0.0.1:6333/dashboard"
        Write-Host "  LiteLLM:  http://127.0.0.1:4000"
        Write-Host "  Search:   http://127.0.0.1:7700"
        Write-Host "  ClamAV:   127.0.0.1:3310"
    }
    "down" {
        Compose down
    }
    "restart" {
        Compose restart
        Compose ps
    }
    "logs" {
        if ($Follow) {
            Compose logs -f
        } else {
            Compose logs --tail 200
        }
    }
    "ps" {
        Compose ps
    }
    "status" {
        Compose ps
    }
    "pull" {
        Compose pull
    }
    "config" {
        Compose config
    }
}
