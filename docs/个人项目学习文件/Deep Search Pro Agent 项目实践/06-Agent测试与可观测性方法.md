---
title: Agent 测试与可观测性方法
project: deep-search-pro-lab
status: 进行中
updated: 2026-08-11
tags:
  - Testing
  - Observability
  - WebSocket
  - Evaluation
---

# Agent 测试与可观测性方法

## 为什么普通单元测试不够

Agent 系统的最终文字看起来正确，不代表执行过程合理。可能出现：

- 用错工具但碰巧答对；
- 简单问题委派了复杂子 Agent；
- 搜索次数失控但最终答案正常；
- 引用 URL 并非工具真实返回；
- 使用旧会话历史导致测试结果失真；
- 完成事件之后后台仍继续运行。

因此至少要同时验证三层：

1. **最终结果**：是否回答问题、是否包含真实来源；
2. **单步决策**：工具和参数是否正确；
3. **完整轨迹**：节点顺序、调用次数、终态和总耗时是否合理。

## 离线测试与在线测试分工

### 离线测试

适合验证确定性契约：

- Pydantic 参数 Schema；
- 额外参数禁止；
- 预算边界；
- 并发预算竞态；
- URL 规范化；
- 结果字符截断；
- 熔断状态机；
- 根超时与锁释放；
- Agent 图能否编译。

优点是快速、稳定、不消耗 LLM 和 Tavily 额度。

### 在线测试

适合验证真实协作：

- 模型是否选择正确路由；
- 供应商 API 是否兼容；
- Search 与 Extract 是否真实可用；
- 最终答案是否引用工具返回的 URL；
- 总体延迟是否可接受；
- WebSocket 是否产生唯一终态。

## Fresh Thread 原则

性能或路由基准测试必须创建新会话，即请求中不传 `thread_id`。

复用旧 `thread_id` 会加载 PostgreSQL Checkpoint 历史，影响：

- 输入 Token；
- 模型延迟；
- 路由判断；
- 已知事实；
- 工具调用次数；
- 最终回答。

只有测试“继续对话”和“记忆恢复”时才应该复用 thread。

## task_id 与 thread_id 在测试中的使用

```text
POST /api/tasks
→ 返回 task_id + thread_id
→ WebSocket 使用 task_id
→ 后续继续会话时 POST 使用 thread_id
```

不要把第一轮的 `task_id` 当作第二轮 `thread_id`。

## 关键事件

当前事件流包括：

- `started`；
- `step`；
- `delegation_started`；
- `tool_requested`；
- `tool_completed`；
- `message`；
- `delegation_finished`；
- `completed`；
- `failed`；
- `cancelled`。

终态附带：

- 总耗时；
- 模型轮数；
- 工具调用数；
- 最终答案字符数；
- ResearchBudget 快照；
- 失败错误码和最后可观测位置。

## 一次真实定位方法

旧复杂任务的可见 Tavily 调用只花了约几秒，但终态在几十秒后超时。通过事件时间线可以判断：

```text
外部工具已完成
→ 长时间没有 tool_completed
→ 最终模型阶段失败
```

因此根因是最终上下文与模型综合，而不是 Tavily 网络。没有事件轨迹时，很容易错误地更换供应商或不断增加工具超时。

## Uvicorn 热重载的 1012

代码变更后，开发服务器 `--reload` 会重启进程，正在连接的 WebSocket 可能收到：

```text
1012 service restart
```

这不应计入 Agent 业务失败。在线验收时应：

1. 等待新进程健康；
2. 丢弃被 reload 中断的任务；
3. 创建新的 `task_id` 和 `thread_id`；
4. 用稳定进程中的完整终态作为证据。

生产环境不应使用开发 reload 模式。

## 当前性能基线

| 测试 | 轨迹 | 结果 | 单次实测 |
|---|---|---:|---:|
| 简单 Tavily 用途查询 | 1 次 quick search，无委派 | completed | 8.07 秒 |
| Search/Extract 对比研究 | plan + 2 search + 1 extract | completed | 32.04 秒 |

这些数字只用于当前阶段回归。后续应多次采样并记录 P50、P95、错误率和供应商耗时，才能形成真正的性能指标。

## 后续质量评估重点

- 路由准确率：quick、deep、database、mixed；
- 工具选择准确率；
- 搜索和提取调用次数；
- 来源是否真实且与论断匹配；
- 官方来源占比；
- 答案覆盖率与证据充分性；
- 任务 P50/P95 延迟；
- 超时率和供应商错误率；
- 同一测试集的回归稳定性。

## 面试表达

> 我没有只检查 Agent 最终能不能答出一段文字，而是同时验证最终答案、单步工具决策和完整执行轨迹。离线测试覆盖 Schema、并发预算、URL 去重、熔断和超时，在线测试用全新 thread 验证真实模型路由、Tavily 调用、WebSocket 终态和延迟。通过时间线我定位到一次超时发生在工具完成后的最终模型综合阶段，避免把问题错误归因于搜索供应商。
