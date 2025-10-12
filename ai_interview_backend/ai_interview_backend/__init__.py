# ai_interview_backend/ai_interview_backend/__init__.py

# 这将确保在 Django 启动时，Celery app 总能被加载
from .celery_app import app as celery_app

__all__ = ('celery_app',)