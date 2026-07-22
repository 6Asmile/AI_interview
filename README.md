# iFaceoff

> 以可信职业事实为起点，连接简历、岗位、模拟面试、评估报告和求职进度的 AI 求职平台。

[![Vue 3](https://img.shields.io/badge/Vue-3.4-42b883)](https://vuejs.org/)
[![Django](https://img.shields.io/badge/Django-5.2-092e20)](https://www.djangoproject.com/)
[![LangGraph](https://img.shields.io/badge/Agent-Composite_V4-111827)](https://github.com/langchain-ai/langgraph)
[![Qdrant](https://img.shields.io/badge/Vector-Qdrant-dc244c)](https://qdrant.tech/)
[![LiteLLM](https://img.shields.io/badge/Gateway-LiteLLM-16a34a)](https://docs.litellm.ai/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue)](LICENSE)

![iFaceoff current landing page](docs/images/landing-latest.png)

iFaceoff 不是单独的“AI 出题器”。系统围绕可验证的职业事实建立完整链路：简历内容必须来自用户确认的数据，面试问题可以引用经过审批的知识库证据，评分必须引用候选人的真实回答，模型不可用时明确降级而不是伪造结果。

## 产品闭环

```mermaid
flowchart LR
    FACT["职业事实库"] --> RESUME["主简历与版本"]
    RESUME --> JOB["目标岗位与真实 JD"]
    JOB --> MATCH["简历诊断与定制"]
    MATCH --> INTERVIEW["自适应模拟面试"]
    INTERVIEW --> REPORT["证据化评估报告"]
    REPORT --> PLAN["投递进度与补强任务"]
    PLAN --> FACT
```

- **事实优先**：AI 只能使用已确认的教育、工作、项目、技能、成果和真实 JD。
- **版本可复现**：面试和分析绑定不可变简历版本、JD 快照、模板版本和模型配置。
- **证据可审计**：题目、检索来源、评分、能力覆盖和报告结论均保存来源链路。
- **失败不伪装**：缺少模型、向量库、Rerank 或语音服务时进入可解释降级。

## 当前界面

<table>
  <tr>
    <td width="50%"><strong>求职工作台</strong><br><img src="docs/images/career-workspace-latest.png" alt="求职工作台"></td>
    <td width="50%"><strong>自适应面试入口</strong><br><img src="docs/images/interview-setup-latest.png" alt="模拟面试入口"></td>
  </tr>
  <tr>
    <td width="50%"><strong>解析后知识块编辑</strong><br><img src="docs/images/knowledge-chunks-latest.png" alt="知识块编辑器"></td>
    <td width="50%"><strong>真实简历与 JD 诊断</strong><br><img src="docs/images/resume-diagnosis-latest.png" alt="简历诊断"></td>
  </tr>
</table>

![技术社区真实内容 Feed](docs/images/community-feed-latest.png)

以上截图由 Playwright 在当前版本、真实本地服务和现有业务数据上重新生成，不使用前端 Mock 数据。

## 核心能力

| 模块 | 已实现能力 |
| --- | --- |
| 简历与职业事实 | JSON Resume 兼容结构、职业事实库、不可变 `ResumeVersion`、异步导入、人工确认、真实 JD 分析、证据来源与历史快照 |
| 求职工作台 | 目标岗位、JD、投递管道、面试安排、Offer、补强任务；模块独立加载，局部接口失败不会导致整页白屏 |
| Composite Agent V4 | 外部只有一个综合面试官；内部业务子图使用 LangGraph 编排，Pydantic 校验边界，PostgreSQL Checkpointer 负责恢复 |
| 自适应面试 | 目标时长与能力覆盖共同决定结束；依据回答证据执行澄清、验证、深挖、挑战、迁移、换题或收尾；支持主题栈与自然承接 |
| 企业级评估 | 规则评分与 AI 评分双轨、量表锚点、STAR/技术深度/证据质量、能力矩阵、风险标记、置信度、Trace 和明确降级模式 |
| 企业知识库 | 用户私有与系统公共隔离、HR/Admin 审批、导入批次、Docling/OCR、修订版本、逐 Chunk 编辑、冻结发布和历史版本保留 |
| Hybrid RAG | Multi Query、向量召回、中文关键词召回、RRF 融合、Rerank、已用块去重、租户和审批二次校验、检索 Trace |
| 模型网关 | Chat/Embedding/Rerank/ASR/TTS 模型类型、加密凭据、任务别名、路由策略、预算、调用账本和 LiteLLM 数据面 |
| 多模态体验 | 音频分片、ASR 转写与置信度确认、TTS 缓存与浏览器兜底、媒体记录；语音和表情不直接决定能力分数 |
| 社区与搜索 | 本地已发布文章和公共知识 Feed、Meilisearch 全量/增量索引、Discourse SSO/Webhook 扩展入口、私人内容不进入公开索引 |
| 私信与附件 | WebSocket 会话、文本与图片粘贴、Emoji、IME/组合键处理、附件上传、屏蔽举报以及可靠消息状态基础 |
| 账号与安全 | 候选人 HttpOnly Refresh Cookie、内存 Access Token、单次 WebSocket Ticket、独立员工账号/MFA/会话、租户隔离和敏感字段脱敏 |

## 系统架构

```mermaid
flowchart TB
    subgraph UX["交互层"]
        WEB["Vue 3 Web"]
        SPEECH["ASR / TTS / Media"]
    end

    subgraph APP["业务与 Agent 层"]
        API["Django REST API"]
        WS["Django Channels"]
        AGENT["Composite Agent V4 / LangGraph"]
        TOOLS["Agent Tool Executor"]
        MEMORY["Session / Event / Evidence Memory"]
    end

    subgraph DATA["数据与检索层"]
        PGAPP[(PostgreSQL / ifaceoff_app)]
        PGAGENT[(PostgreSQL / ifaceoff_agent)]
        REDIS[(Redis)]
        MQ[(RabbitMQ)]
        QDRANT[(Qdrant)]
        SEARCH[(Meilisearch)]
    end

    subgraph AI["模型与异步层"]
        WORKER["Celery Worker / Beat"]
        GATEWAY["LiteLLM Proxy"]
        PGLITELLM[(PostgreSQL / litellm)]
        SCAN["ClamAV"]
    end

    WEB --> API
    WEB <--> WS
    WEB --> SPEECH
    API --> AGENT
    AGENT --> TOOLS
    AGENT <--> MEMORY
    TOOLS --> GATEWAY
    TOOLS --> QDRANT
    API --> PGAPP
    AGENT --> PGAGENT
    API --> REDIS
    API --> SEARCH
    API --> SCAN
    WORKER --> MQ
    WORKER --> PGAPP
    WORKER --> QDRANT
    GATEWAY --> PGLITELLM
```

### 隐藏式多 SubAgent

候选人端始终只看到一个面试官。内部使用职责受限的 SubAgent 和统一状态 DTO，不允许任意节点修改整份状态：

```text
Observe
  -> Evaluate Evidence
  -> Guard Unsupported Claims
  -> Update Topic and Ability Confidence
  -> Decide Termination
  -> Select Next Action
  -> Retrieve if Needed
  -> Assemble Budgeted Context
  -> Generate Dialogue Turn
  -> Safety Validate
  -> Repair or Deterministic Fallback
  -> Persist, Reflect and Update Memory
```

`AgentToolExecutor` 统一处理工具权限、Schema 校验、超时、幂等重试、降级和审计。模型只参与需要语义判断的节点，租户权限、证据校验、重复题、多问题、阶段边界和发布状态由确定性规则兜底。

### State、Checkpoint 与记忆

- LangGraph State 使用 JSON-safe `TypedDict`，只保存 ID、状态增量和限长摘要，不保存 Django ORM、文件对象、API Key 或完整私有文档；API、评估结果、问题计划和 SSE 事件在边界处由 strict Pydantic 契约校验。
- 每轮业务执行由 `InterviewAgentExecution` 保存 `session/thread/run` 映射、幂等键、状态版本和最终问题；Prepare、Finalize、Report 图分别写入 `ifaceoff_agent` PostgreSQL Checkpoint。进程退出后从最后成功节点恢复，完成态重放不会重复评分、覆盖或出题。
- PostgreSQL 是问题、回答、评分、能力覆盖、RAG 证据和恢复状态的事实来源。Redis 仅保存短期 SSE 增量、Ticket、验证码和实时状态；Redis 丢失后仍可由业务状态和 Checkpoint 构造恢复快照。
- 工作记忆使用 `session.memory_summary` 保存当前主题栈、能力缺口、已问问题签名和已用知识块；事件记忆使用 `InterviewAgentMemoryEvent` 保存计划、观察、问题和覆盖事件；RAG 证据与检索 Trace 独立保存，避免把“对话记忆”和“事实证据”混为一层。
- 事件召回按类型使用不同半衰期：环境信号 5 分钟、检索观察 20 分钟、计划 45 分钟、问题 1 天、能力覆盖 7 天；重要度与时间衰减共同排序，并记录召回次数和最近召回时间。
- 去重同时覆盖事件内容哈希、问题规范化签名与近义检测、知识 Chunk ID 和 `semantic_group_id`。短期噪声设置硬 TTL，长期事件和 Checkpoint 由 `prune_agent_memory` 按保留策略清理。
- 不进入长期记忆的内容包括逐 Token 动画、typing 状态、临时 ASR 片段、WebSocket Ticket、验证码、原始密钥以及未经证据校验的模型推断。

### 自适应面试策略

- 默认以 **30 分钟目标时长**、最低时长、能力覆盖和异常轮次上限共同控制进度，不再固定为 10 题。
- 回答被结构化为 `insufficient / ambiguous / partial / solid / strong / contradictory` 证据状态。
- 弱回答先澄清，部分回答补齐链路，强回答追问边界或迁移场景；连续无证据后换题，避免死循环。
- 项目话题可穿插基础知识追问，再通过主题栈返回项目验证真实方案和个人贡献。
- 宽松、严格、八股、项目深挖等风格只改变语气、节奏和挑战率，不改变评分量表。
- 真实模拟隐藏过程分数和内部策略，训练模式可展示即时反馈。

### 知识库与 RAG

```mermaid
flowchart LR
    UPLOAD["PDF / DOCX / XLSX / MD / FAQ / Image"]
    PARSE["Docling + OCR + Fallback"]
    DRAFT["Revision + Editable Chunk Drafts"]
    REVIEW["Human Review"]
    PUBLISH["Freeze Published Revision"]
    INDEX["Embedding + Qdrant"]
    RETRIEVE["Multi Query + Vector + BM25"]
    FUSION["RRF + Rerank"]
    GUARD["PostgreSQL Tenant / Approval / Version Guard"]

    UPLOAD --> PARSE --> DRAFT --> REVIEW --> PUBLISH --> INDEX
    INDEX --> RETRIEVE --> FUSION --> GUARD
```

1. 大文件由 Celery 异步解析，任务状态和失败原因可查询、可重试。
2. Docling 优先保留标题、阅读顺序、页码、表格和图片结构；OCR 只补充真实识别文本。
3. 标题/FAQ/表格形成父块，超长内容递归切分，短块按相邻结构和语义合并。
4. 解析结果先进入 `KnowledgeChunkDraft`，支持编辑、拆分、合并、排序和排除。
5. 审批后冻结不可变发布版本；修改生成新草稿，旧线上版本在新版审批前继续服务。
6. Qdrant 结果必须经过 PostgreSQL 的租户、可见性、审批状态和发布版本二次校验。
7. 无向量或 Rerank 服务时可降级关键词检索；没有合法证据时面试继续，但报告不得声称使用题库覆盖。

## 技术栈

- **Frontend**：Vue 3、TypeScript、Vite、Element Plus、Pinia、ECharts、Playwright
- **Backend**：Python 3.12、Django 5.2、DRF、Channels、Celery、Uvicorn
- **Agent**：LangGraph、结构化 Prompt、节点契约、Trace、Context Budget、Tool Registry
- **Data**：PostgreSQL 16、Redis、RabbitMQ、Qdrant、Meilisearch
- **AI**：OpenAI-compatible、DashScope/百炼、LiteLLM、Embedding、Rerank、ASR、TTS
- **Document**：Docling adapter、OCR adapter、PyPDF、python-docx、openpyxl、jieba
- **Security**：encrypted credentials、JWT、MFA、RBAC、tenant guard、ClamAV

## 项目结构

```text
AI_interview/
├── ai-interview-frontend/          # Vue 3 候选人端与 Playwright 测试
├── ai-interview-admin/             # 独立 Vue 3 员工管理端
├── ai_interview_backend/
│   ├── careers/                    # 职业事实、岗位、投递和学习任务
│   ├── resumes/                    # 简历版本、导入、建议和分析
│   ├── interviews/                 # Composite Agent、评估、语音和 Trace
│   ├── knowledge/                  # 审批、修订、切块、索引和混合检索
│   ├── system/                     # AI 设置、模型网关和 readiness
│   ├── community/                  # 内容 Feed、搜索和 Discourse 集成
│   ├── chat/                       # 私信、附件和 WebSocket
│   ├── reports/                    # 证据化报告和分析快照
│   └── users/                      # 身份、角色、引导和隐私
├── docker/                         # LiteLLM 等服务配置
├── docs/                           # 部署说明与当前产品截图
├── scripts/
│   ├── ifaceoff-infra.ps1          # 只管理基础设施容器
│   ├── ifaceoff-dev.ps1            # 管理本地应用进程
│   └── ifaceoff-docker.ps1         # 完整容器化部署
├── docker-compose.infra.yml        # PostgreSQL/Redis/MQ/Qdrant/LiteLLM 等
├── docker-compose.observability.yml # 可选 Langfuse/ClickHouse/MinIO
└── docker-compose.yml              # 完整应用栈
```

## 本地启动

### 环境要求

- Windows PowerShell 7 或兼容终端
- Python 3.12
- Node.js 20+
- Docker Desktop / Docker Compose v2

### 1. 获取代码并启动基础设施

基础设施和应用进程刻意分离。日常开发将统一 PostgreSQL、Redis、RabbitMQ、Qdrant、LiteLLM、Meilisearch 和 ClamAV 放进 Docker。PostgreSQL 内按独立数据库和角色隔离 `ifaceoff_app`、`ifaceoff_agent`、`litellm`、`langfuse`。

```powershell
git clone https://github.com/6Asmile/AI_interview.git
cd AI_interview
Copy-Item .env.infra.example .env.infra
.\scripts\ifaceoff-infra.ps1 up
```

| 服务 | 默认地址 |
| --- | --- |
| Redis | `127.0.0.1:6379` |
| RabbitMQ / 管理页 | `127.0.0.1:5672` / `http://127.0.0.1:15672` |
| Qdrant | `http://127.0.0.1:6333/dashboard` |
| LiteLLM | `http://127.0.0.1:4000` |
| PostgreSQL（统一实例） | `127.0.0.1:5433` |
| Meilisearch | `http://127.0.0.1:7700` |
| ClamAV | `127.0.0.1:3310` |

### 2. 安装应用依赖并迁移

```powershell
cd ai_interview_backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py setup_agent_checkpoint

cd ..\ai-interview-frontend
npm ci
cd ..
```

请根据 `.env.infra` 修改后端 `.env` 中的数据库、消息队列和服务地址。不要提交真实 API Key、JWT Secret 或数据库密码。

### 3. 一键启动本地应用

```powershell
.\scripts\ifaceoff-dev.ps1 up
.\scripts\ifaceoff-dev.ps1 status
```

该脚本启动 Django、Celery Worker、Celery Beat、候选人 Vite 和员工管理端 Vite，并将 PID 与日志保存在本地忽略目录。停止或重启：

```powershell
.\scripts\ifaceoff-dev.ps1 down
.\scripts\ifaceoff-dev.ps1 restart
```

### 4. 检查运行状态

- Web：`http://127.0.0.1:5173`
- 员工管理端：`http://127.0.0.1:5174`
- API：`http://127.0.0.1:8000/api/v1/`
- 员工管理 API：`http://127.0.0.1:8000/api/admin/v1/`
- Readiness：`http://127.0.0.1:8000/api/v1/system/readiness/`
- Swagger：`http://127.0.0.1:8000/api/v1/schema/swagger-ui/`
- 紧急 Django Admin：`http://127.0.0.1:8000/internal/django-admin/`

首次启用员工端时先迁移并同步角色。员工邀请不会复制候选人密码，激活后必须绑定 MFA：

```powershell
cd ai_interview_backend
python manage.py migrate
python manage.py bootstrap_staff_admin
python manage.py sync_public_site
python manage.py bootstrap_staff_admin --email your-staff@example.com --password "temporary-password"
```

超级管理员登录 `http://127.0.0.1:5174` 后，在“员工与邀请”创建邀请码。系统会通过事务 Outbox 尝试发邮件，并仅在创建或重发响应中显示一次备用激活链接。受邀员工需要依次完成密码设置、TOTP 绑定和恢复码保存确认，之后才会签发独立员工 Session。后台不提供公开注册，候选人账号不能登录员工端。

GitHub 登录由 Django 发起并处理回调，候选人前端不再保存 OAuth state 或拼接授权地址。GitHub OAuth App 的 Authorization callback URL 必须与配置完全一致：

```dotenv
PUBLIC_BACKEND_URL=http://127.0.0.1:8000
PUBLIC_FRONTEND_URL=http://127.0.0.1:5173
PUBLIC_ADMIN_URL=http://127.0.0.1:5174
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_OAUTH_CALLBACK_URL=http://127.0.0.1:8000/api/v1/auth/oauth/github/callback/
```

本地开发统一使用 `127.0.0.1`，不要与 `localhost` 混用。首次授权使用 GitHub 已验证邮箱创建候选人；若邮箱已存在，必须验证原账号密码后才会绑定，系统不会静默合并身份。生产环境应替换为已在 GitHub 登记的 HTTPS 域名。

Readiness 会分别报告 Database、Redis、RabbitMQ、Celery Worker、Qdrant、Meilisearch 和 LiteLLM 状态。异步服务不可用时，上传页面会展示队列不可用，而不是让任务无限停留在 `pending`。

完整容器化部署仍可使用：

```powershell
.\scripts\ifaceoff-docker.ps1 up
```

两种启动方式不要混用同一组端口。更多说明见 [基础设施部署](docs/docker-ifaceoff-infra.md)、[完整容器部署](docs/docker-ifaceoff.md) 与 [Agent 持久化、双 Redis 和容量验收](docs/agent-resilience.md)。

## 关键配置

```dotenv
INTERVIEW_AGENT_ENGINE=composite_v4
IFACEOFF_DATABASE_URL=postgresql://ifaceoff_app:...@127.0.0.1:5433/ifaceoff_app
AGENT_DATABASE_URL=postgresql://ifaceoff_agent:...@127.0.0.1:5433/ifaceoff_agent
AGENT_CONTEXT_TOKEN_BUDGET=12000
AGENT_MAX_GENERATION_RETRIES=2

MODEL_CREDENTIAL_ENCRYPTION_KEY=
LITELLM_PROXY_URL=http://127.0.0.1:4000/v1
QDRANT_URL=http://127.0.0.1:6333
MEILISEARCH_URL=http://127.0.0.1:7700
MEILISEARCH_API_KEY=

DOCUMENT_PARSER=docling
DOCLING_ENABLE_OCR=true
OCR_ENGINE=paddleocr
HYBRID_SEARCH_TOPN=30
HYBRID_SEARCH_TOPK=4

DISCOURSE_BASE_URL=
DISCOURSE_CONNECT_SECRET=
DISCOURSE_WEBHOOK_SECRET=
```

生产环境必须显式配置凭据加密密钥、Django/JWT Secret 和基础设施密码。模型 API Key 仅以密文保存，接口只返回掩码；Prompt、Trace、日志和前端状态不得出现明文密钥。

Langfuse 是可选观测组件，不阻塞基础启动。按 `.env.observability.example` 配置强随机密钥后运行：

```powershell
Copy-Item .env.observability.example .env.observability
docker compose --env-file .env.observability -f docker-compose.observability.yml --profile observability up -d
```

该 profile 使用统一 PostgreSQL 中独立的 `langfuse` 数据库，并按 Langfuse v3 的要求保留 ClickHouse 与 MinIO；这些分析和对象存储不会被错误合并进业务 PostgreSQL。

## API 入口

- `/api/v2/career-facts/`, `/job-targets/`, `/applications/`, `/learning-tasks/`
- `/api/v2/resumes/`, `/resume-imports/`, `/resume-suggestions/`
- `/api/v1/analyze-resume/`
- `/api/v1/interviews/`, `/api/v1/interviews/{id}/abandon/`
- `/api/v1/knowledge/documents/`, `/revisions/`, `/chunk-drafts/`, `/publish/`
- `/api/v1/community/feed/`, `/community/search/`
- `/api/v1/gateway/credentials/`, `/deployments/`, `/aliases/`, `/requests/`
- `/api/v1/system/readiness/`
- `/api/v1/auth/csrf/`, `/auth/session/`, `/auth/token/refresh/`, `/auth/logout-all/`
- `/api/v1/auth/oauth/github/start/`, `/auth/oauth/github/callback/`, `/auth/oauth/github/link/confirm/`
- `/api/v1/ws-tickets/`, `/tasks/`, `/tasks/{id}/retry/`, `/tasks/{id}/cancel/`
- `/api/admin/v1/auth/invitations/{token}/`, `/auth/register/`, `/staff-invitations/`
- `/api/admin/v1/candidates/`, `/interviews/`, `/agent-runs/`, `/interview-config/`
- `/api/admin/v1/knowledge-reviews/`, `/model-gateway/`, `/tasks/`, `/moderation/`, `/audit-logs/`
- `/api/admin/v1/analytics/`, `/feature-flags/`, `/maintenance-notices/`, `/notifications/operations/`

旧简历和 AI 设置 API 保留兼容层，新增流程优先使用版本化 `/api/v2` 资源。

## 数据一致性与运维

- 面试会话状态以 PostgreSQL 为事实来源，Redis 只做缓存；检查未完成面试时会修复失效缓存。
- 放弃面试必须携带明确的 `session_id`；旧兼容接口在存在多个运行会话时返回 `409`。
- 陈旧会话对账默认 dry-run：

```powershell
python manage.py reconcile_interview_sessions
python manage.py reconcile_interview_sessions --apply
```

- 知识库草稿、待审核、拒绝、归档和旧修订不会进入 RAG。
- 社区公开索引只包含已发布文章、公共知识和外部公开主题，不索引简历、私信或私有知识库。

## 质量验证

```powershell
cd ai_interview_backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test interviews.tests knowledge.tests system.tests resumes.tests community.tests careers.tests --noinput

cd ..\ai-interview-frontend
npm run build
$env:IFACEOFF_E2E_EMAIL='your-test-account@example.com'
$env:IFACEOFF_E2E_PASSWORD='your-test-password'
npm run test:e2e
```

当前发布前实测结果：

- Django 全量回归：**149 tests passed**
- Agent / Checkpoint / Memory 定向回归：**50 tests passed**
- Django system check：**0 issues**
- Migration drift：**No changes detected**
- 候选人端与独立管理端 production build：**passed**
- Playwright 登录、核心页面、管理端跳转和移动端边界：**3 suites passed**
- Readiness：业务 PostgreSQL、Agent Checkpoint PostgreSQL、Redis、RabbitMQ、Celery、Qdrant、Meilisearch、LiteLLM **all healthy**

测试业务数据来自本地真实或匿名化样例；provider boundary fake 仅用于超时、异常和降级故障注入，不作为简历、知识库、评分或社区内容。

## License

[Apache License 2.0](LICENSE)
