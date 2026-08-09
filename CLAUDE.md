# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

B 站 AI 全自动科普视频量产系统。输入一个标题，自动完成脚本、配音、配图、动效、合成、投稿的全链路流水线。

**技术栈：** Python Flask 后端 + Vue 3 / Vite / TypeScript 前端 + SQLite

## 开发环境

- **Python 环境：** Conda `flask_env` (`conda activate flask_env`)
- **前端：** `cd frontend && npm run dev` → `http://localhost:5175/video_factory/web/`
- **前端构建：** `npm run build`，产物在 `frontend/dist/`
- **初始化数据库：** `cd backend && python -m scripts.db_init`
- **Mock 模式跑样片（无需 API Key）：** `cd backend && python -m worker run --title "标题" --skip-publish`
- **选题工具：** `cd backend && python -m topic --theme "主题"`

## 核心架构

### 三流水线 (`backend/app/core/pipelines.py`)

| Pipeline | 用途 | Stage 链 |
| --- | --- | --- |
| `standard` | AI 分镜视频（主流程） | script → tts → segment → intro → merge → publish |
| `material` | 素材基底合成 | prepare → script → tts → intro → merge → publish |
| `chat` (daily_story) | 日常故事对话 | script → tts → segment → intro → merge → publish |

每条流水线是一串 `StageExecutor` 子类（`backend/worker/stages/`），每个 stage 有 `name` 和 `run(ctx: JobContext)` 方法。流水线执行逻辑在 `backend/worker/loop.py`，CLI 入口在 `backend/worker/cli.py`。daily_story 使用 `worker/stages/daily_story/{script,tts}.py`，下游复用共享的 Segment / Intro / Merge / Publish。

### 日常故事（`chat` 流水线，近期开发主线）

业务在 `backend/app/services/daily_story/`：`daily_story_mgr.py` 组织「生成剧本 → 建 job」；LLM 故事生成在落 `daily_story` 表时完成，建任务只落 `pending`，需在任务页手动跑阶段（无独立 cron）。代码地图与五类叙事契约见 `docs/日常故事.md`、`docs/日常故事-类型.md`、`docs/提示词构建.md` §D。

- **五类矛盾 A–E**：`story_types/{a,b,c,d,e}/`，每类含 `line.py`（提示词线路）、`validate.py`（硬卡）、`patch.py`（本地修稿）、`facts.py`、`opening.py`、`humor.py`、`quality.py`。类型选择用抽象不变量，**禁止**在 validate.py 按单篇剧情/词表写 regex（见 `.cursor/rules/daily-story-validate.mdc`）。
- **三层分工**：叙事与措辞放 `line.py`/`prompts.py`；机读不变量放 `validate.py`（字数、speaker、末段结构槽位）；观感放 `quality.py`。「写得不好」走观感降分或改提示词，不做生成硬拦。
- **选题门控**：`select_story_type_tag` 按主题关键词选类型，无匹配时在 `quality_ready=True` 的类型中随机（现 A/B/C）。
- **D1.5 笑点骨架**：各类型 `story_plan.py` 的 `ENABLED` 决定是否走（现仅 D），统一入口 `story_design.py`，落库 `story.punchline_blueprint`。
- **回归**：`backend/scripts/preview_daily_story_batch.py` 批量预览生成稿；文档不贴长对白正例，回归用脚本或线上稿。

### 关键服务目录 (`backend/app/services/`)

- **llm/** — LLM 调用（DeepSeek / Agnes），包括脚本生成、分镜拆分、提示词生成
- **script/** — 脚本与分镜管理 (`script_mgr`)，也包括 image_prompt 构建
- **tts/** — CosyVoice TTS（DashScope WebSocket 字级时间戳）
- **segment/** — 分镜执行：出图 (`image/`) + 片段合成 (`clip/`)，含字幕叠加
- **daily_story/** — 日常故事业务逻辑（A/B/C/D/E 类型），核心：`daily_story_mgr.py` + 各类型子目录 `story_types/{a,b,c,d,e}/`
- **end_card/** — 片尾生成
- **job/** — job 生命周期、锁、submit_action
- **intro/** — 片头生成（多种 intro 策略：science / history_mystery）
- **media/** — 媒体文件处理（motion_prompt 注入、片头叠加）
- **publish/** — B 站投稿
- **clip_search/** — 外部素材片段搜索（Pexels / Pixabay / NASA）
- **render/** — 渲染引擎
- **topic/** — 选题生成

### 质检系统 (`backend/app/quality/`)

各步骤内嵌质检：`script` → `image_prompt` → `tts_audio` → `segment`(images + clips) → `final_video`。每项返回 `QualityReport`（`pass` / `minor` / `major`），最终汇总为 `quality_report` 字段。相关 env：`SKIP_SCRIPT_QUALITY_CHECK`。

### 数据库

SQLite，路径配置在 `SQLITE_PATH`（默认 `data/data.db`）。Repository 层（`backend/app/repositories/`）使用裸 SQL + SQLAlchemy。`JobContext` 是 stage 间传递的上下文对象。

### 配置

所有配置通过 `.env` 和 `app/config.py` 的 `Config` 类管理。.env.example 有完整注释。重要的 provider 切换：`LLM_PROVIDER`、`IMAGE_PROVIDER`、`CLIP_PROVIDER`、`MOCK_MODE`。

### 前端路由

`/home`、`/jobs`（任务列表+详情）、`/materials/video`、`/materials/audio`、`/clips`（素材搜索）、`/topic`（选题）、`/daily-story`（日常故事管理）、`/config`

### 「专家」

DeepSeek 网页模拟 API，不是 Claude 子代理。涉及提示词方案评审时用户说「和专家商量/达成一致再落地」，指用它的专家模式评审。接口 `POST http://127.0.0.1:8765/api/deepseek/chat`，body `{"question":..., "mode":"expert", "deep_thinking":true}`；新对话不带 `conversation_id`，续聊带返回 id；

#### 状态查
 `GET /api/deepseek/status`

#### 地址
- 优先级从上到下
<!-- - 127.0.0.1  -->
- http://192.168.50.172:8848/mock_agent
- https://leo-zhao.natapp4.cc/mock_agent

#### 专家模式 + 深度思考：

```json
{
  "question": "证明根号2是无理数",
  "mode": "expert",
  "deep_thinking": true
}
```

#### 成功响应

```json
{
  "ok": true,
  "question": "...",
  "answer": "...",
  "conversation_id": "uuid",
  "mode": "instant",
  "deep_thinking": true,
  "search": false,
  "url": "https://chat.deepseek.com/a/chat/s/uuid"
}
```

#### 续聊并保持选项：

```json
{
  "conversation_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "question": "把证明写得更短一些",
  "mode": "expert",
  "deep_thinking": true
}

## 常用操作

```bash
# 重跑指定 stage（清空下游产物，从该 stage 连续跑完）
python -m worker run --job-id 2 --from-stage merge --skip-publish

# 只重跑一个 stage（只执行该步，不继续）
python -m worker run --job-id 2 --only-stage tts --skip-publish

# 只重跑指定分镜
python -m worker run --job-id 2 --only-stage segment --segments 1,3 --skip-publish

# 消耗所有 pending job
python -m worker drain

# 查进度
sqlite3 data/data.db "SELECT id, title, stage, status FROM video_job ORDER BY id DESC;"

# 日志
tail -f logs/worker.log              # 主日志（按天切割，默认保留 3 天）
tail -f data/media/{job_id}/run.log  # 单 job 日志

# 测试
cd backend && python -m pytest tests/                     # 全量
cd backend && python -m pytest tests/test_script_validation.py  # 单个文件
```

## 文档

`docs/` 是子系统权威文档，改动对应模块前先读：`需求.md`、`日常故事.md`、`日常故事-类型.md`、`提示词构建.md`（LLM 提示词阶段索引）、`LLM.md`、`成本.md`、`数据恢复.md`、`平台激励.md`。**日常故事 A–E 类型的校准进度先读 `docs/日常故事-校准.md`**（换机器/换会话继续协同的存档）。编辑 `.md` 文件遵守 `.cursor/rules/markdown-docs.mdc`（markdownlint），自检：`npx markdownlint-cli2 "docs/**/*.md"`。

## 远程服务器

- **主机名优先级：** `mini`（局域网）> `vip.sy.frp.one:57904` > `57c42474b0ea.ofalias.net:58186`
- **用户：** `leo`，密码见 `.env` 的 `SSH_PASSWORD`
- **项目目录：** `/mnt/data/project/video_factory`
- **服务名：** `video-factory`
- **SD WebUI 目录：** `/mnt/data/stable-diffusion/webui`，服务 `sd.service`
- **查询数据/日志先去远程服务器查**，不要查本地

## 注意事项

- 重跑任务、重启服务、新建独立文件需要用户确认
- 测试先本地测通过再推送；`push` = git commit + push
- 不要用 PowerShell 执行远程查询（会拆坏远程 Python）
- `ssh` 命令查远程数据
- Always reply in Chinese.
- 每次查库可以通过 scripts/download_db.py 把数据库和日志同步到本地再查
