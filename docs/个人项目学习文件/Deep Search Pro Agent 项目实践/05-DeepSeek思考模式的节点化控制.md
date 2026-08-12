---
title: DeepSeek 思考模式的节点化控制
project: deep-search-pro-lab
status: 已验证
updated: 2026-08-11
tags:
  - DeepSeek
  - Thinking
  - Tool-Calling
  - Performance
---

# DeepSeek 思考模式的节点化控制

## 问题现象

固定 Deep Research 图第一次在线运行时，规划节点返回：

```text
Thinking mode does not support this tool_choice
```

去掉强制工具选择后，最终综合节点开启 thinking 又在单次 30 秒模型超时内未完成：

```text
Request timed out.
```

## DeepSeek V4 的关键协议

DeepSeek V4 Flash 默认开启 thinking。OpenAI 兼容接口通过 `extra_body` 控制：

```python
extra_body={
    "thinking": {
        "type": "enabled"  # 或 disabled
    }
}
```

思考强度使用：

```python
reasoning_effort="high"  # 或 max
```

thinking 模式工具调用还要求后续请求完整回传相应 `reasoning_content`。如果 Agent 框架没有正确保存和重放，可能产生 400 错误。官方兼容说明还指出 thinking 模式不应依赖强制具体工具的 `tool_choice`。

参考：

- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)
- [DeepSeek Chat Completion API](https://api-docs.deepseek.com/api/create-chat-completion)

## 错误做法

为所有节点默认开启 thinking，表面上像是在提高智能，实际上会带来：

- 路由延迟增加；
- 简单 JSON 规划成本增加；
- 工具调用协议更复杂；
- 需要保存 reasoning_content；
- 更容易触发单回合超时；
- 对已经筛选好的证据做无必要长推理。

## 当前节点策略

模型工厂提供显式参数：

```python
get_llm(thinking=False)
get_llm(thinking=True)
```

当前选择：

| 节点 | Thinking | 原因 |
|---|---:|---|
| 主 Agent 路由 | 关闭 | 分类和工具选择，强调延迟与协议稳定 |
| 快速联网回答 | 关闭 | 单一问题的受控总结 |
| 数据库 Agent | 关闭 | 主要工作是调用受控数据库工具 |
| 研究规划 | 关闭 | 只生成 1～2 个小型 JSON 问题 |
| Tavily Search/Extract | 不涉及 | 纯外部工具节点 |
| 当前研究综合 | 关闭 | 证据已筛选，主要是写作；thinking 实测超时 |
| 未来来源冲突判断 | 按需开启 | 只有真正需要复杂判断时单独增加 reasoning 节点 |

## 规划节点的兼容降级

规划节点不再强制 `tool_choice`，而是要求模型输出严格 JSON，再使用 Pydantic 验证。如果模型未返回合法结构，则本地降级成一个不扩大用户范围的搜索问题。

这体现了一个原则：模型负责提出候选结构，后端负责验证和安全降级。

## 为什么最终综合也关闭 thinking

一次受控研究中：

- 规划已限定范围；
- 搜索次数固定；
- 来源已经筛选；
- 正文已经裁剪；
- 最终节点只需按证据写答案。

这时 thinking 的边际收益有限，却实际导致 30 秒模型超时。关闭后，同一复杂研究在约 32 秒内完成整条根任务。

未来如果增加“来源冲突检测”节点，可以只让这个节点开启 thinking，并把输出变成小型结构，例如：

```json
{
  "has_conflict": true,
  "conflicting_claims": [],
  "preferred_source": "",
  "reason": ""
}
```

最终写作节点仍保持非 thinking。

## 收获

- thinking 是资源，不是模型的永久开关；
- 应按节点的任务复杂度选择，而不是按“这是 Agent 项目”选择；
- 工具调用节点更重视协议兼容与低延迟；
- 复杂推理最好隔离成输入、输出都很小的独立节点；
- 任何模型模式选择都应通过真实延迟和错误轨迹验证。

## 面试表达

> DeepSeek V4 默认开启 thinking，但我在 Agent 工具链中遇到了 tool_choice 兼容错误和最终综合超时。我没有简单增加总超时，而是按节点重新分配模型模式：路由、工具调用、JSON 规划和受控写作关闭 thinking，只把真正的来源冲突推理预留为独立 reasoning 节点。这样减少了 reasoning_content 回放等协议负担，也把复杂研究从超时改为约 32 秒完成。
