# core/asgi.py
import os
from django.core.asgi import get_asgi_application
from fastapi import FastAPI
from starlette.routing import Mount

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_interview_backend.settings')

# Django ASGI application
django_app = get_asgi_application()

# FastAPI application
fastapi_app = FastAPI()

# 在这里可以引入你的FastAPI路由
# from some_fastapi_router_file import router as fastapi_router
# fastapi_app.include_router(fastapi_router, prefix="/api/v1/fast")

@fastapi_app.get("/health")
async def health_check():
    return {"status": "FastAPI is running"}

# 将 Django 和 FastAPI 组合起来
# 注意：这里的路由挂载顺序很重要，建议将 Django 作为根路径的备选
application = FastAPI(
    routes=[
        Mount("/api/fast", fastapi_app), # 所有 /api/fast 开头的请求由 FastAPI 处理
        Mount("/", django_app),          # 其他所有请求由 Django 处理
    ]
)