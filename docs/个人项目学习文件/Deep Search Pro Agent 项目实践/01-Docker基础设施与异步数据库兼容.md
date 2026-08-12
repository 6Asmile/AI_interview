---
title: Docker 基础设施与异步数据库兼容
project: deep-search-pro-lab
status: 已验证
updated: 2026-08-11
tags:
  - Docker
  - MySQL
  - PostgreSQL
  - AsyncIO
---

# Docker 基础设施与异步数据库兼容

## 背景与取舍

学习阶段采用“本地运行 FastAPI，Docker 承载数据库”的方式。这样既能练习 Compose、容器、网络、端口和数据卷，又保留 PyCharm 本地调试的便利。应用生产镜像、全容器化部署留到后续阶段。

## 问题一：MySQL 重启后认证缺少 cryptography

### 现象

MySQL 容器可以启动，但应用查询时报错：

```text
RuntimeError: 'cryptography' package is required for
sha256_password or caching_sha2_password auth methods
```

### 根因

MySQL 8 常用 `caching_sha2_password`。异步 MySQL 驱动完成认证流程时需要 `cryptography`。TCP 端口可连接只说明网络可达，不表示认证依赖完整。

### 解决

在 Python 项目依赖中显式加入 `cryptography`，重新安装依赖后，用真实 SQL 查询而不是只用容器健康状态完成验收。

### 收获

- 基础设施健康检查、网络连接和应用层认证是不同层次；
- “容器 Up”不能代替应用验收；
- 依赖问题应根据认证链路定位，而不是反复重建容器。

## 问题二：复用 postgres:16-alpine 镜像

### 结论

已有镜像可以复用。镜像是只读模板，多个项目共享镜像不会共享业务数据。需要隔离的是：

- 容器名称；
- 宿主机端口；
- Docker 网络；
- 数据库名称和账号；
- 数据卷。

本项目为 PostgreSQL Checkpointer 使用独立容器、数据库和数据卷，并使用宿主机 `5433` 端口避免与其他项目冲突。

## 问题三：Windows ProactorEventLoop 与异步 Psycopg

### 现象

验证 `AsyncPostgresSaver` 时出现：

```text
Psycopg cannot use the 'ProactorEventLoop' to run in async mode
```

### 根因

这是 Windows 默认异步事件循环与 Psycopg 异步实现的兼容问题，不是 PostgreSQL 账号、端口或建表 SQL 错误。

### 解决与验证

验证脚本使用兼容的 Selector Event Loop，随后：

- `checkpointer.setup()` 执行成功；
- 创建 `checkpoint_blobs`；
- 创建 `checkpoint_migrations`；
- 创建 `checkpoint_writes`；
- 创建 `checkpoints`。

## 方案比较

| 方案 | 优点 | 局限 |
|---|---|---|
| InMemorySaver | 简单、无需数据库 | 进程重启后丢失，不能验证真实恢复 |
| SQLite | 本地启动方便 | 并发、生产一致性和连接池能力有限 |
| PostgreSQL Checkpointer | 可持久化、可恢复、适合并发服务 | 配置和异步兼容复杂度更高 |
| 应用与数据库全部容器化 | 环境一致性强 | 学习早期调试成本更高 |

## 面试表达

> 我没有一开始就把应用全部容器化，而是让 Docker 承载 MySQL 和 PostgreSQL，本地 PyCharm 运行 FastAPI。这样既练习了 Compose、端口、网络和数据卷，又保持了调试效率。过程中分别解决了 MySQL 8 认证依赖和 Windows 异步 Psycopg 事件循环兼容问题，并以真实查询和 Checkpointer 建表结果完成验收，而不是只看容器是否处于 Up 状态。
