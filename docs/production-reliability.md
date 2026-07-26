# iFaceOff 生产可靠性基线

本文件是 R0 的部署契约。PostgreSQL 是唯一业务事实源；Redis、RabbitMQ、Qdrant 和 Meilisearch 的数据都必须能从 PostgreSQL 与对象存储重建。

## 托管资源

- PostgreSQL 16：多可用区，启用 PITR，持续归档周期不高于 5 分钟；API 通过 PgBouncer 连接。
- Redis：Cache、Coordination、Realtime 三个独立故障域。生产必须使用 TLS、ACL 和独立服务账号。
  - Cache：`allkeys-lfu`，允许淘汰。
  - Coordination：`noeviction`，验证码、限流、幂等 Claim、模型舱壁和租约必须设置 TTL。
  - Realtime：`noeviction`，Stream 设置 `MAXLEN` 与 TTL，并保留 PostgreSQL 快照。
- RabbitMQ：4.3.4，生产镜像变量 `RABBITMQ_IMAGE` 必须填写经过安全扫描的 `repo@sha256:digest`，不得依赖浮动 Tag。
- 对象存储：版本化、服务端加密、跨账号备份。

## 发布顺序

1. 独立 Migration Job 执行 `python manage.py migrate --noinput`，API 与 Worker 容器设置 `IFACEOFF_RUN_MIGRATIONS=0`。
2. 先部署兼容旧 Schema 的 API，再部署 Worker，最后按内部账号、5%、25%、100%放量 Feature Flag。
3. RabbitMQ 从 3.13 到 4.3 使用蓝绿迁移：新集群声明拓扑、双环境影子验证、停止旧写入、排空、切换 DNS/Secret；旧集群保留一个回滚窗口。
4. 数据库迁移只扩展和回填，不在同一发布删除旧表、旧列、旧队列或旧索引。

## 故障契约

| 依赖 | 固定行为 |
|---|---|
| Cache Redis | 绕过缓存，读取 PostgreSQL |
| Coordination Redis | 安全流程与高成本任务 Fail Closed；普通读取继续 |
| Realtime Redis | SSE/WebSocket 降级为任务快照与轮询 |
| RabbitMQ | IntegrationOutbox 保留，接口返回已受理 |
| Qdrant/Rerank | 降级 Meilisearch/关键词检索并记录质量影响 |
| Meilisearch | 降级受限 SQL 搜索 |
| 模型供应商 | 仅对 429、超时和临时 5xx 重试或切换；共享总 Deadline |
| PostgreSQL | 停止业务写入，禁止由缓存或消息伪造成功 |

## 发布门禁

- 500 在线并发，其中至少 100 个并发 Agent/岗位分析任务。
- 普通 API p95 不高于 500 ms，异步受理 p95 不高于 300 ms，5xx 小于 1%。
- 完成 PostgreSQL PITR、RabbitMQ 节点、Redis 故障转移和完整环境重建演练。
- 预发布环境连续稳定运行 7 天；RPO 不高于 5 分钟，RTO 不高于 30 分钟。
- 发布前检查 Outbox 最老消息年龄、DLQ、模型错误率、成本、数据库连接池和 Redis 淘汰/拒写指标。
