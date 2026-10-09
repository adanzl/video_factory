# LLM 调用配置

> 审查日期：2026-08-03。  
> 相关：`docs/提示词构建.md`（提示词链路）。

## DeepSeek 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 默认模型 |
| `DEEPSEEK_PRO_MODEL` | `deepseek-v4-pro` | A1 失败重试；D1.5 骨架（若 ENABLED） |
| `DEEPSEEK_MAX_TOKENS` | `32768` | 单次最大 token |
| `DEEPSEEK_THINKING` | `true` | 全局深度思考开关 |

**Pro 路由（以代码为准）**：

- **A1 口播**：首稿 Flash；校验失败后的重试升 Pro。
- **日常故事 D2 正文 / 质量修订 / 开场**：全程 Flash + 关
  thinking（高温）；**不再**升 Pro（Pro+thinking 又慢又短）。
- **D1.5 笑点骨架**：仅当类型 `story_plan.ENABLED=True` 时固定用
  Pro；失败降级纯 D2。D 类实测 ROI 偏低（常 fallback / 终稿不带
  bp），校准不以 D1.5 为前提。

## Agnes 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AGNES_LLM_MAX_TOKENS` | `32768` | Agnes 文本/多模态上限 |
| `AGNES_SUBMIT_INTERVAL_SEC` | `12` | 视频提交间隔（付费池 5 RPM） |
| `AGNES_FREE_SUBMIT_INTERVAL_SEC` | `60` | 视频提交间隔（免费池 1 RPM） |
| `AGNES_IMAGE_SUBMIT_INTERVAL_SEC` | `1` | 图片提交间隔（付费池 1K 100 RPM） |
| `AGNES_FREE_IMAGE_SUBMIT_INTERVAL_SEC` | `6` | 图片提交间隔（免费池 1K 10 RPM） |
| `AGNES_FREE_POOL_SHARED` | `1` | 两把免费 key 是否同池 |
| `AGNES_VIDEO_RATE_LIMIT_COOLDOWN_SEC` | `60` | 429 后该池冷却时长 |
| `AGNES_VIDEO_KEY_WAIT_BUDGET_SEC` | `300` | 全池冷却时单次等待预算 |
| `AGNES_VIDEO_UPSTREAM_WAIT_BUDGET_SEC` | `3600` | 上游 5xx 单段最长等待 |
| `AGNES_VIDEO_UPSTREAM_COOLDOWN_BASE_SEC` | `20` | 上游 5xx 首次冷却 |
| `AGNES_VIDEO_UPSTREAM_COOLDOWN_MAX_SEC` | `300` | 上游 5xx 冷却上限 |

Agnes 校验清单（出图 VL）固定 `max_tokens=256`。

### 图片 RPM 与限制池（t2i）

官方 1K 档实际 RPM：免费/默认 **10**、企业认证 40、TokenPlan **100**
（2K 档免费 5 / TokenPlan 80；3K、4K 各档均 1）。

图片提交同样**按池计时**（付费池 `AGNES_IMAGE_SUBMIT_INTERVAL_SEC`、
免费池 `AGNES_FREE_IMAGE_SUBMIT_INTERVAL_SEC`）：

- 出图与 5xx 重试都过闸门，不在窗口内连打；
- 并发度由 `IMAGE_MAX_WORKERS` 控制，与池间隔互不替代；
- `IMAGE_SUBMIT_INTERVAL_SEC` 现仅供 wan / z_image provider 使用。

### 视频 RPM 与限制池（i2v）

官方数字见 <https://wiki.agnes-ai.com/zh-Hans/docs/tokenplan>：
视频模型免费/默认实际 **1 RPM**、企业认证 2 RPM、TokenPlan **5 RPM**；
TokenPlan 另受**每日 500 秒**视频时长配额约束（RPM 与配额同时生效）。

**限制池按「密钥类型」共享**：同类型多把 key 合起来只有一个池的额度，
故视频提交按池计时（付费池 / 免费池），不是按 key 计时。实现约束：

- 首次提交、503 重试、换域名重试**都过同一个闸门**，任一路径都算次数；
- 429 视为 RPM 窗口：冻结该池一个冷却窗口并**立刻换下一把 key**，
  不在被限的池上原地睡满窗口；
- 全部池冷却时才整批等待最早恢复，等待上限 `AGNES_VIDEO_KEY_WAIT_BUDGET_SEC`；
- 轮询请求不计入提交闸门（另有全局 poll 错峰）。

`AGNES_SUBMIT_INTERVAL_SEC`（秒）= `60 / 该池实际 RPM`；换套餐或
实测限速不同时改这里，勿改代码。

### 上游 5xx（网关抖动）容错

实测 Agnes 网关偶发长时间 503，**只打在 `/v1/videos`**（2026-10-10 事故：
持续 >70 分钟；同期 `images/generations`、轮询、`/v1/models` 全 200）。
此时换 key、换域名都无效（`.com`/`.cn` 同一后端，额度按账号算），
故单独归为 ``AgnesUpstreamUnavailable`` 走**等待-恢复**：

- **不换 key、不烧密钥**：503 不计入 key 故障，密钥链保持可用；
- **全局冷却**：跨 key / 池 / 任务共享，指数退避
  `20s→40s→80s→160s→300s`（±20% 抖动），任一次提交成功即清零；
- **不连打**：提交里两个域名都 5xx 即停手进冷却，请求量从
  每 30 秒 4 次降到每轮 1 次；
- **有界自愈**：单段 clip 最多等 `AGNES_VIDEO_UPSTREAM_WAIT_BUDGET_SEC`
  （默认 60 分钟）；期间任务保持 running、日志每轮一条、可随时中止；
  超预算才失败并提示「稍后重跑 segment 可续跑」。

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
| D1.5 笑点骨架 | ✅ 走配置 | — | 短 JSON；仅 ENABLED 类型；D 可选 |
| D2 故事 | ❌ 硬关 | 0.95/1.0 | 全程 Flash；有骨架时首稿 1.0 |
| D2b 发现开场 | ❌ 硬关 | — | 短约束；快失败快重试 |
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
- `_TEMP_CREATIVE_BLUEPRINT = 1.0`（D1.5 有骨架时的 D2 首稿）
- `_TEMP_CREATIVE_MID = 0.8`（A2/C/D4/E1）
- `_TEMP_UTILITY = 0.5`（E2/E3/E4/封面）
