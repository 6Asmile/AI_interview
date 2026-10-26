@echo off
setlocal

cd /d "%~dp0"

echo Starting isolated Celery workers and one beat instance...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0..\scripts\ifaceoff-dev.ps1' -Action up -Components @('celery-worker','celery-beat')"

endlocal
