#!/usr/bin/env bash
# Cloud Agent 环境安装脚本（幂等）。
# 在仓库检出后运行：装系统依赖、建 Python venv、装前后端依赖、初始化 SQLite。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[install] system packages (ffmpeg / python venv / build tools)"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y -qq --no-install-recommends \
  ffmpeg python3-venv python3-dev build-essential

echo "[install] python venv + backend requirements"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install -r requirements.txt
python -m pip install pytest   # 测试用（未在 requirements.txt 中固定）

echo "[install] .env (从 .env.example 生成，已存在则保留)"
[ -f .env ] || cp .env.example .env

echo "[install] init sqlite schema (幂等，CREATE TABLE IF NOT EXISTS)"
( cd backend && python -m scripts.db_init )

echo "[install] frontend npm deps"
( cd frontend && npm install )

echo "[install] done"
