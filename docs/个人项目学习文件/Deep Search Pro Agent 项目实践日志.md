---
title: Deep Search Pro Agent 项目实践日志
project: deep-search-pro-lab
status: 进行中
started: 2026-08-07
updated: 2026-08-11
tags:
  - Python
  - FastAPI
  - Docker
  - Deep-Agents
  - LangGraph
  - Agent
---

# Deep Search Pro Agent 项目实践日志

> 这是 `deep-search-pro-lab` 的项目复盘入口。详细记录按“大问题”拆分，每个问题都尽量形成一段可以独立用于复习、简历完善或面试回答的工程故事。

## 阅读入口

- [[Deep Search Pro Agent 项目实践/00-索引与项目概览|00 - 索引与项目概览]]
- [[Deep Search Pro Agent 项目实践/01-Docker基础设施与异步数据库兼容|01 - Docker 基础设施与异步数据库兼容]]
- [[Deep Search Pro Agent 项目实践/02-Agent工具契约与异步任务事件流|02 - Agent 工具契约与异步任务事件流]]
- [[Deep Search Pro Agent 项目实践/03-网络研究失控与可靠性硬边界|03 - 网络研究失控与可靠性硬边界]]
- [[Deep Search Pro Agent 项目实践/04-简单查询误入DeepResearch与分层重构|04 - 简单查询误入 Deep Research 与分层重构]]
- [[Deep Search Pro Agent 项目实践/05-DeepSeek思考模式的节点化控制|05 - DeepSeek 思考模式的节点化控制]]
- [[Deep Search Pro Agent 项目实践/06-Agent测试与可观测性方法|06 - Agent 测试与可观测性方法]]

## 记录规则

- 普通语法错误和每次点击不单独记录，只保留有复用价值的工程问题；
- 每个问题按照“现象 → 证据 → 根因 → 方案比较 → 实现 → 验证 → 收获”组织；
- “计划完成”与“真实验证通过”严格区分；
- 不写入 API Key、密码、完整数据库连接串或其他敏感信息；
- 性能数据必须说明测试任务与上下文，不能把单次结果包装成普遍保证；
- 一个阶段稳定后再更新日志，避免笔记追着临时代码反复变化。
