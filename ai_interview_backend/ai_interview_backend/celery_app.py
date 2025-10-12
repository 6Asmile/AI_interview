# ai_interview_backend/ai_interview_backend/celery_app.py

import os
from celery import Celery

# 设置 Django 的 settings 模块环境变量
# 'ai_interview_backend.settings' 指向 ai_interview_backend/settings.py
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_interview_backend.settings')

# 创建 Celery 应用实例
# 'ai_interview_backend' 是项目名
app = Celery('ai_interview_backend')

# 从 Django 的 settings.py 中加载 Celery 配置
# namespace='CELERY' 意味着所有 Celery 配置项都必须以 'CELERY_' 开头
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动从所有已注册的 Django app 中发现 tasks.py 文件
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')