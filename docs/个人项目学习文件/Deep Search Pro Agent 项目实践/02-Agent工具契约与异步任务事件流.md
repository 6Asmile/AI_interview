---
title: Agent 工具契约与异步任务事件流
project: deep-search-pro-lab
status: 已验证
updated: 2026-08-11
tags:
  - FastAPI
  - WebSocket
  - LangChain
  - LangGraph
---

# Agent 工具契约与异步任务事件流

## 建设内容

- 主 Agent 负责路由和汇总；
- 数据库子 Agent 负责查看表结构和执行只读 SQL；
- `POST /api/tasks` 创建后台执行；
- WebSocket 按 `task_id` 推送事件；
- PostgreSQL Checkpointer 按 `thread_id` 保存会话；
- 同一 `thread_id` 同时只允许一个运行任务；
- 支持完成、失败、取消和超时终态。

## 问题一：工具函数没有 docstring

### 现象

```text
ValueError: Function must have a docstring if description not provided.
```

### 根因与解决

普通 Python 函数转换成 StructuredTool 时，框架需要工具描述供模型理解。没有显式 `description` 时会读取 docstring，两者都没有就无法完成工具契约。

这让我认识到：工具描述不是普通代码注释，而是模型可见的能力说明、参数边界和路由依据。

## 问题二：误导入 uvicorn.workers

### 现象

本地启动 FastAPI 时提示缺少 Gunicorn。

### 根因

任务管理器误导入 `uvicorn.workers`，该模块面向 Gunicorn 部署，因此触发额外依赖。本地任务管理器并不需要它。

### 解决与收获

删除无关导入，而不是为了消除报错盲目安装 Gunicorn。处理依赖错误时，应先追踪“为什么会加载这个模块”，再判断应该加依赖还是删错误耦合。

## 问题三：task_id 与 thread_id 混淆

### 正确语义

- `task_id`：一次后台执行的标识，用于 WebSocket 订阅和取消；
- `thread_id`：一段 Agent 会话的标识，用于读取和写入 Checkpoint。

一次会话可以有多次顺序执行，因此两者不能复用成同一个概念。继续对话时传旧 `thread_id`；做独立性能测试时不传 `thread_id`，避免旧上下文污染结果。

## 问题四：WebSocket 输出后关闭

单次任务订阅在产生终态后关闭连接是合理的，不等于聊天能力中断。正确协议是：

1. 推送唯一终态事件；
2. 服务端发送 WebSocket close frame；
3. 使用正常关闭码 `1000`；
4. 终态成功交付后再释放任务队列。

## 问题五：Task not found

任务注册表当前位于进程内存。服务热重载、进程切换或订阅旧 `task_id` 时会出现 `Task not found`。

Checkpoint 只保存 Agent 会话状态，不保存 HTTP 后台任务注册表。生产化时可以将任务层迁移到：

- Redis；
- 数据库任务表；
- Celery、RQ 等任务队列；
- 独立工作进程与消息代理。

## 面试表达

> 我把一次 Agent 执行与可恢复会话拆成 task_id 和 thread_id：前者负责后台任务、取消和 WebSocket 订阅，后者负责 LangGraph Checkpoint。这样既能继续历史对话，也不会把一次执行状态和长期会话状态混为一谈。同时为 WebSocket 定义唯一终态和正常关闭协议，保证前端能区分完成、失败、取消和服务重载。
