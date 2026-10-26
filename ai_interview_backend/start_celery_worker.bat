@echo off
setlocal

cd /d "%~dp0"

echo Starting isolated Celery worker roles...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\ifaceoff-dev.ps1" -Action up -Components celery-worker

endlocal
