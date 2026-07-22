# LLM 调用配置

> 审查日期：2026-07-21。  
> 相关：`docs/提示词构建.md`（提示词链路）。

## DeepSeek 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 模型名称 |
| `DEEPSEEK_MAX_TOKENS` | `32768` | 单次最大 token |
| `DEEPSEEK_THINKING` | `true` | 全局深度思考开关 |

## Agnes 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AGNES_LLM_MAX_TOKENS` | `32768` | Agnes 文本/多模态上限 |

Agnes 校验清单（出图 VL）固定 `max_tokens=256`。

## max_tokens 约定

DeepSeek `_chat` / `_chat_json` 不传 `max_tokens`，统一走
`DEEPSEEK_MAX_TOKENS`。Agnes 文本/帧分析走
`AGNES_LLM_MAX_TOKENS`。

## Thinking 判定原则

本项目偏创意。创意类**硬关** thinking，并设 temperature；需硬约束
的链路**走配置**（默认 `DEEPSEEK_THINKING=true` 即开）。

开 thinking 时模型会**忽略 temperature**，故走配置链路不传
temperature。

| 走配置（默认开） | 硬关 |
| --- | --- |
| 硬约束：字数、静帧禁动作、切镜完整性、SD15 格式 | 创意文案、画面想象、选题钩子 |
| 不开会明显挂（太短/违规/结构塌） | 要花样、要温度采样 |

- **走配置**：不传 `thinking_enabled`，跟 `DEEPSEEK_THINKING`
- **硬关**：`thinking_enabled=False`，不受环境变量影响

## Thinking 全表

| 链路 | thinking | temperature | 理由 |
| --- | --- | --- | --- |
| A1 口播 | ✅ 走配置 | — | 长度硬约束（例外） |
| A2 画面概述 | ❌ 硬关 | 0.8 | 视觉创意 |
| A3 文生图 | ✅ 走配置 | — | 静帧禁动作等硬约束 |
| A4 扩写 | ✅ 走配置 | — | 字数限制 |
| A5 缩句 | ✅ 走配置 | — | 字数限制 |
| B1 素材口播 | ✅ 走配置 | — | 同 A1 |
| C1/C2 选题 | ❌ 硬关 | 0.8 | 钩子创意 |
| D1 主题 | ❌ 硬关 | 0.95 | 高创意 |
| D2 故事 | ❌ 首稿硬关；重试走配置 | 0.95 / — | 首稿创意；重试修字数等硬约束 |
| D2b 发现开场 | ✅ 走配置 | — | 短约束：JSON/锚点/只发现不讲理 |
| D3 分镜 | ✅ 走配置 | — | 台词完整/切镜结构 |
| D4 对话标题 | ❌ 硬关 | 0.8 | 标题创意 |
| E1 标题优化 | ❌ 硬关 | 0.8 | 标题创意 |
| E2 简介 | ❌ 硬关 | 0.5 | 工具型短文案 |
| E3 标签 | ❌ 硬关 | 0.5 | 工具型 |
| E4 Pixabay | ❌ 硬关 | 0.5 | 工具型 |
| 封面辅调 LLM | ❌ 硬关 | 0.5 | 工具型 |
| F1 SD15 英文化 | ✅ 走配置 | — | 格式/结构硬约束 |
| B2/E5主/F2–F4 | — | — | 非 DeepSeek 聊天 |

## temperature（越大越野）

仅硬关 thinking 时生效。代码常量：

- `_TEMP_CREATIVE_HIGH = 0.95`（D1/D2 首稿）
- `_TEMP_CREATIVE_MID = 0.8`（A2/C/D4/E1）
- `_TEMP_UTILITY = 0.5`（E2/E3/E4/封面）
