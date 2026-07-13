param(
    [ValidateSet("up", "down", "restart", "logs", "ps", "build", "migrate")]
    [string]$Action = "up",
    [switch]$Follow
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env.docker"
$ExampleFile = Join-Path $Root ".env.docker.example"

if (!(Test-Path $EnvFile)) {
    Copy-Item $ExampleFile $EnvFile
    Write-Host "Created .env.docker from .env.docker.example. Review secrets before production use."
}

function Compose {
    docker compose --env-file $EnvFile @args
}

switch ($Action) {
    "up" {
        Compose up -d --build
        Compose ps
        Write-Host ""
        Write-Host "Ifaceoff is starting:"
        Write-Host "  Web:       http://localhost"
        Write-Host "  Backend:   http://localhost:8000/api/v1/schema/swagger-ui/"
        Write-Host "  RabbitMQ:  http://localhost:15672"
        Write-Host "  Qdrant:    http://localhost:6333/dashboard"
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
    "build" {
        Compose build
    }
    "migrate" {
        Compose exec backend python manage.py migrate
    }
}
