@echo off
setlocal

cd /d "%~dp0"

echo Starting Celery worker in a new window...
start "Celery Worker" cmd /k "cd /d %~dp0 && celery -A ai_interview_backend worker -l info -P solo"

echo Starting Celery beat in a new window...
start "Celery Beat" cmd /k "cd /d %~dp0 && celery -A ai_interview_backend beat -l info"

echo Celery worker and beat launched.

endlocal
