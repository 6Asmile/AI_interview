# Ifaceoff Docker 一键部署

本项目的 Docker Compose 项目名为 `ifaceoff`，容器名统一使用 `Ifaceoff-*`。

## 1. 准备环境

```powershell
copy .env.docker.example .env.docker
notepad .env.docker
```

至少建议修改：

- `SECRET_KEY`
- `IFACEOFF_DB_PASSWORD`、`AGENT_DB_PASSWORD`
- `FRONTEND_PORT`
- `BACKEND_PORT`
- `BAILIAN_API_KEY`、`BAILIAN_OPENAI_BASE_URL`、`BAILIAN_DASHSCOPE_BASE_URL`，如果要使用阿里云百炼模型网关

不要把 `.env.docker` 提交到 Git。

## 2. 一键启动

```powershell
.\scripts\ifaceoff-docker.ps1 up
```

启动后访问：

- Web: `http://localhost`
- Backend API Docs: `http://localhost:8000/api/v1/schema/swagger-ui/`
- RabbitMQ: `http://localhost:15672`
- Qdrant: `http://localhost:6333/dashboard`

## 3. 常用命令

```powershell
.\scripts\ifaceoff-docker.ps1 ps
.\scripts\ifaceoff-docker.ps1 logs -Follow
.\scripts\ifaceoff-docker.ps1 restart
.\scripts\ifaceoff-docker.ps1 down
```

手动执行迁移：

```powershell
.\scripts\ifaceoff-docker.ps1 migrate
```

## 4. 服务组成

- `Ifaceoff-frontend`: Nginx + Vue 静态资源
- `Ifaceoff-backend`: Django/DRF/Channels ASGI 服务
- `Ifaceoff-celery-worker`: 知识库解析、索引、报告、视频等异步任务
- `Ifaceoff-celery-beat`: 定时任务
- `Ifaceoff-agent-service`: LangGraph 内部控制面和可恢复事件流
- `Ifaceoff-postgres`: PostgreSQL 16，按数据库和角色隔离业务、Agent 与模型网关
- `Ifaceoff-redis`: Redis 缓存、Channels、Celery result backend
- `Ifaceoff-rabbitmq`: Celery broker
- `Ifaceoff-qdrant`: 向量库

## 5. 模型网关配置

当前后端已经有轻量 Model Gateway：

- 对话模型：OpenAI-compatible chat
- Embedding：OpenAI-compatible embeddings
- Rerank：DashScope/百炼原生 rerank payload
- 配置来源：用户 `AISetting` 优先，环境变量作为 fallback
- 安全策略：API Key 响应只返回掩码；掩码保存不会覆盖真实密钥
- 检测接口：`POST /api/v1/settings/ai/health/`

推荐流程：

1. 登录系统。
2. 进入“AI 设置”。
3. 分别选择 Chat、Embedding、Rerank、ASR、TTS 模型。
4. 为模型填入对应 API Key。
5. 点击“检测”，确认 Chat/Embedding/Rerank 可用。

如果要使用阿里云百炼 workspace：

- Chat/Embedding base URL 通常使用 OpenAI-compatible 地址。
- Rerank base URL 使用 DashScope `/api/v1/services/rerank/text-rerank/text-rerank`。
- API Key 不要写入代码；只写入 `.env.docker` 或后台用户设置。

## 6. 知识库/RAG 验证

1. 上传或创建知识库文档。
2. 提交审核。
3. HR/Admin 审批通过。
4. Celery 执行解析、切块、embedding、Qdrant upsert。
5. 面试时 RAG 只检索 `approval_status=approved` 且 `status=indexed` 的真实 chunk。

如果 Qdrant 或 embedding 不可用，系统会明确降级到关键词/BM25 fallback，不会伪造向量召回结果。
