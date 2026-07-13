@echo off
setlocal

cd /d "%~dp0"

echo Starting Celery worker...
celery -A ai_interview_backend worker -l info -P solo

endlocal
