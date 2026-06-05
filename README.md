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

## 架构

```text
backend/
├── worker/          # CLI + 流水线 stage 执行器
├── app/
│   ├── core/        # pipeline、job_service
│   ├── repositories/# SQLite 裸 SQL
│   ├── services/    # LLM / TTS / 出图 / FFmpeg
│   └── quality/     # 质检编排
└── scripts/init_db.py
```

流水线：`script → image → cover → intro → tts → quality → ffmpeg → publish → done`

讲解人卡通 IP（`HOST_ENABLED`）暂未接入，片头为纯文字模板。

## 文档

- [需求规格](docs/需求.md)
- [选题](docs/选题.md)
