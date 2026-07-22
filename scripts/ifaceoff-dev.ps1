param(
    [ValidateSet('up', 'down', 'restart', 'status')]
    [string]$Action = 'up',
    [ValidateSet('django', 'celery-worker', 'celery-beat', 'vite', 'admin-vite')]
    [string[]]$Components = @('django', 'celery-worker', 'celery-beat', 'vite', 'admin-vite')
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'ai_interview_backend'
$Frontend = Join-Path $Root 'ai-interview-frontend'
$AdminFrontend = Join-Path $Root 'ai-interview-admin'
$LogDir = Join-Path $Root 'logs\dev'
$PidFile = Join-Path $Root '.ifaceoff-dev-pids.json'
$Python = if ($env:IFACEOFF_PYTHON) { $env:IFACEOFF_PYTHON } else { (Get-Command python).Source }
$Npm = (Get-Command npm.cmd).Source

$InfraEnv = Join-Path $Root '.env.infra'
if (Test-Path $InfraEnv) {
    foreach ($line in Get-Content $InfraEnv) {
        if ($line -match '^\s*([^#][A-Za-z0-9_]*)=(.*)$') {
            $name = $matches[1]
            $value = $matches[2].Trim().Trim('"').Trim("'")
            if (!(Test-Path "env:$name")) { Set-Item "env:$name" $value }
        }
    }
}
$QdrantPort = if ($env:QDRANT_PORT) { $env:QDRANT_PORT } else { '6333' }
$MeiliPort = if ($env:MEILISEARCH_PORT) { $env:MEILISEARCH_PORT } else { '7700' }
$LiteLLMPort = if ($env:LITELLM_PORT) { $env:LITELLM_PORT } else { '4000' }
if (!$env:QDRANT_URL) { $env:QDRANT_URL = "http://127.0.0.1:$QdrantPort" }
if (!$env:MEILISEARCH_URL) { $env:MEILISEARCH_URL = "http://127.0.0.1:$MeiliPort" }
if (!$env:MEILISEARCH_API_KEY -and $env:MEILI_MASTER_KEY) { $env:MEILISEARCH_API_KEY = $env:MEILI_MASTER_KEY }
if (!$env:LITELLM_PROXY_URL) { $env:LITELLM_PROXY_URL = "http://127.0.0.1:$LiteLLMPort/v1" }

function Read-PidEntries {
    if (!(Test-Path $PidFile)) { return @() }
    $parsed = Get-Content $PidFile -Raw | ConvertFrom-Json
    $normalized = @()
    foreach ($entry in @($parsed)) {
        if ($entry.name -and $entry.pid) { $normalized += $entry; continue }
        foreach ($nested in @($entry.value)) {
            if ($nested.name -and $nested.pid) { $normalized += $nested }
        }
    }
    return $normalized
}

function Write-PidEntries($Entries) {
    $normalized = @()
    foreach ($entry in @($Entries)) {
        if ($entry.name -and $entry.pid) { $normalized += $entry; continue }
        foreach ($nested in @($entry.value)) {
            if ($nested.name -and $nested.pid) { $normalized += $nested }
        }
    }
    ConvertTo-Json -InputObject @($normalized) | Set-Content $PidFile -Encoding UTF8
}

function Test-Port([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connect = $client.ConnectAsync('127.0.0.1', $Port)
        return $connect.Wait(500) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Start-AppProcess([string]$Name, [string]$WorkingDirectory, [string]$Executable, [string[]]$Arguments) {
    $stdout = Join-Path $LogDir "$Name.out.log"
    $stderr = Join-Path $LogDir "$Name.err.log"
    $process = Start-Process $Executable -WindowStyle Hidden -PassThru `
        -WorkingDirectory $WorkingDirectory -ArgumentList $Arguments `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    return [pscustomobject]@{
        name = $Name
        pid = $process.Id
        started_at = $process.StartTime.ToUniversalTime().ToString('o')
    }
}

function Stop-DevProcesses([string[]]$Names) {
    $remaining = @()
    foreach ($entry in (Read-PidEntries)) {
        if ($entry.name -notin $Names) { $remaining += $entry; continue }
        $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        if ($process) {
            $expected = [datetime]::Parse($entry.started_at).ToUniversalTime()
            if ([math]::Abs(($process.StartTime.ToUniversalTime() - $expected).TotalSeconds) -lt 2) {
                Stop-Process -Id $entry.pid -Force -ErrorAction SilentlyContinue
            }
        }
    }
    if ($remaining.Count) { Write-PidEntries $remaining } elseif (Test-Path $PidFile) { Remove-Item $PidFile -Force }
}

function Show-Status {
    $entries = Read-PidEntries
    if (!$entries.Count) { Write-Host 'No application processes are managed by this script.' }
    foreach ($entry in $entries) {
        if (!$entry.pid) { continue }
        $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        Write-Host ("{0,-16} pid={1,-8} {2}" -f $entry.name, $entry.pid, $(if ($process) { 'running' } else { 'stopped' }))
    }
    Write-Host ("django-port      {0}" -f $(if (Test-Port 8000) { 'listening' } else { 'stopped' }))
    Write-Host ("vite-port        {0}" -f $(if (Test-Port 5173) { 'listening' } else { 'stopped' }))
    Write-Host ("admin-vite-port  {0}" -f $(if (Test-Port 5174) { 'listening' } else { 'stopped' }))
}

if ($Action -eq 'down') { Stop-DevProcesses $Components; Show-Status; exit }
if ($Action -eq 'status') { Show-Status; exit }
if ($Action -eq 'restart') { Stop-DevProcesses $Components }

try {
    & (Join-Path $PSScriptRoot 'ifaceoff-infra.ps1') status
} catch {
    Write-Warning "Infrastructure status check failed: $($_.Exception.Message)"
    Write-Warning 'Application processes will still be started; readiness will report unavailable dependencies.'
}
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$needsBackendPreflight = @('django', 'celery-worker', 'celery-beat') | Where-Object { $_ -in $Components }
if ($needsBackendPreflight) {
    Push-Location $Backend
    try {
        & $Python manage.py migrate --noinput
        if ($LASTEXITCODE -ne 0) { throw 'Django migrations failed.' }
        & $Python manage.py bootstrap_staff_admin
        if ($LASTEXITCODE -ne 0) { throw 'Staff role synchronization failed.' }
        & $Python manage.py sync_public_site
        if ($LASTEXITCODE -ne 0) { throw 'Django Site synchronization failed.' }
    } finally {
        Pop-Location
    }
}
$entries = @(Read-PidEntries | Where-Object { $_.pid -and (Get-Process -Id $_.pid -ErrorAction SilentlyContinue) })
$runningNames = @($entries | ForEach-Object { $_.name })

if ('django' -in $Components -and 'django' -notin $runningNames) {
    if (Test-Port 8000) { Write-Host 'django: port 8000 already in use; leaving existing server untouched.' }
    else { $entries += Start-AppProcess 'django' $Backend $Python @('manage.py', 'runserver', '127.0.0.1:8000') }
}
if ('celery-worker' -in $Components -and 'celery-worker' -notin $runningNames) {
    $entries += Start-AppProcess 'celery-worker' $Backend $Python @('-m', 'celery', '-A', 'ai_interview_backend', 'worker', '-l', 'info', '-P', 'solo', '-Q', 'celery,agent,documents,media,notifications')
}
if ('celery-beat' -in $Components -and 'celery-beat' -notin $runningNames) {
    $entries += Start-AppProcess 'celery-beat' $Backend $Python @('-m', 'celery', '-A', 'ai_interview_backend', 'beat', '-l', 'info')
}
if ('vite' -in $Components -and 'vite' -notin $runningNames) {
    if (Test-Port 5173) { Write-Host 'vite: port 5173 already in use; leaving existing server untouched.' }
    else { $entries += Start-AppProcess 'vite' $Frontend $Npm @('run', 'dev', '--', '--host', '127.0.0.1') }
}
if ('admin-vite' -in $Components -and 'admin-vite' -notin $runningNames) {
    if (Test-Port 5174) { Write-Host 'admin-vite: port 5174 already in use; leaving existing server untouched.' }
    else { $entries += Start-AppProcess 'admin-vite' $AdminFrontend $Npm @('run', 'dev', '--', '--host', '127.0.0.1') }
}

Write-PidEntries $entries
Start-Sleep -Seconds 3
Show-Status
Write-Host 'Frontend: http://127.0.0.1:5173'
Write-Host 'Admin:    http://127.0.0.1:5174'
Write-Host 'Backend:  http://127.0.0.1:8000'
Write-Host 'Readiness: http://127.0.0.1:8000/api/v1/system/readiness/'
