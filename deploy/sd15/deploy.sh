#!/bin/bash
# SD1.5 WebUI API：首次安装依赖 + 启动
set -euo pipefail

CTL_DIR="$(cd "$(dirname "$0")" && pwd)"
SD_HOME="${SD_HOME:-/mnt/data/stable-diffusion/webui}"
MODELS_DIR="${MODELS_DIR:-/mnt/data/stable-diffusion/models}"

echo "=== SD1.5 deploy ==="
echo "SD_HOME=$SD_HOME  MODELS_DIR=$MODELS_DIR"

if [[ ! -d "$SD_HOME" ]]; then
  echo "[1/4] Clone WebUI..."
  git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git "$SD_HOME"
else
  echo "[1/4] WebUI exists"
fi

echo "[2/4] webui-user.sh + models symlink..."
cp -f "$CTL_DIR/webui-user.example.sh" "$SD_HOME/webui-user.sh"
chmod +x "$SD_HOME/webui-user.sh"
mkdir -p "$MODELS_DIR/Stable-diffusion" "$MODELS_DIR/Lora"
if [[ ! -L "$SD_HOME/models" ]]; then
  rm -rf "$SD_HOME/models"
  ln -s "$MODELS_DIR" "$SD_HOME/models"
fi

if [[ ! -f "$SD_HOME/venv/bin/python" ]]; then
  echo "[3/4] Install Python deps (first run, 10-30 min)..."
  cd "$SD_HOME"
  bash webui.sh --exit --skip-torch-cuda-test
else
  echo "[3/4] venv exists"
fi

echo "[4/4] Start API..."
bash "$CTL_DIR/sd-webui-ctl.sh" start
