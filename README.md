# video_factory

B 站 AI 全自动科普视频量产系统（MVP 后端）。

## 快速开始

### 依赖

- Python 3.10+（**Conda 环境 `flask_env`**）
- FFmpeg（`ffmpeg` 在 PATH 中）

```bash
# 已有 flask_env 时
conda activate flask_env
pip install -r requirements.txt   # 首次或依赖变更时

# 新建环境（二选一）
conda env create -f environment.yml
# 或：conda create -n flask_env python=3.10 && conda activate flask_env && pip install -r requirements.txt

cp .env.example .env
```

### 初始化数据库

```bash
cd backend
python -m scripts.init_db
```

### 跑一条样片（Mock 模式，无需 API Key）

```bash
cd backend
python -m worker run \
  --title "不锈钢能被磁铁吸住，就代表买到次品了？" \
  --skip-publish
```

成片：`data/media/{job_id}/final.mp4`

### 接入真实 API

在 `.env` 中配置 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`、`TTS_API_KEY`，并设置 `MOCK_MODE=false`。

### 查进度

```bash
sqlite3 data/data.db "SELECT id, title, stage, status FROM video_job ORDER BY id DESC;"
```

日志写入 `data/logs/worker.log`（**按天切割，默认保留 3 天**）；每次跑 job 另写 `data/media/{job_id}/run.log`：

```bash
tail -f data/logs/worker.log
tail -f data/media/4/run.log
ls data/logs/worker.log*    # worker.log.2026-06-17 等归档
```

## 架构

```text
backend/
├── worker/          # CLI + 流水线 stage 执行器
├── topic/           # 选题 CLI（python -m topic）
├── app/
│   ├── core/        # pipeline、job_service
│   ├── repositories/# SQLite 裸 SQL
│   ├── services/    # LLM / TTS / 出图 / FFmpeg
│   └── quality/     # 各步骤内置质检（checkers + gate）
└── scripts/init_db.py
```

流水线：`script → intro → cover → tts → segment → host → merge → publish → done`

- 封面由 `intro.png` 导出，不用 AI
- `segment`：分镜（ImageProvider 出图 → ClipProvider 片段；可灵为可选 ClipProvider）
- 质检嵌入各步骤：`copy` / `storyboard` / `tts` / `visual` / `clip` / `final` → `quality_report`
- TTS 后 loudnorm 归一；`tts` / `final` 检测响度与静音
- `host`：讲解人叠图占位（儿童 IP，`HOST_ENABLED` 未开时自动跳过）
- **儿童科普线**：`longhuhu_v3` + `TTS_INSTRUCT_PRESET=science_child`（片头喊声与正文 TTS 一致）
- FFmpeg 仅为 media 层工具，不是 stage 名

### 重跑模式

| 参数 | 行为 |
| --- | --- |
| `--from-stage X` | 清空 X 及下游产物，从 X **连续跑到结束** |
| `--only-stage X` | 清空 X 及下游产物，**只执行 X 一步**，完成后 `stage` 指向下游、`status=pending` |

```bash
# 从 merge 跑到成片（含 host）
python -m worker run --job-id 2 --from-stage merge --skip-publish

# 只重跑 TTS（保留分镜静图，清 clip + 成片）
python -m worker run --job-id 2 --only-stage tts --skip-publish

# 只重跑指定分镜
python -m worker run --job-id 2 --only-stage segment --segments 1,3 --skip-publish
```

### 选题（LLM 生成标题候选）

```bash
cd backend
python -m topic --theme "高考志愿填报"
python -m topic -t "磁铁与不锈钢" -n 10 -v   # 显示赛道与钩子
python -m topic -t "日常用电安全" --json      # JSON 输出
```

## 文档

- [需求规格](docs/需求.md)
- [选题](docs/选题.md)
