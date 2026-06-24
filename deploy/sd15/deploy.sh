#!/bin/bash
set -e

SD_HOME="${SD_HOME:-$HOME/stable-diffusion-webui}"
SD_PORT="${SD_PORT:-7860}"
LOG_FILE="${LOG_FILE:-$HOME/sd-webui.log}"
PID_FILE="${PID_FILE:-$HOME/sd-webui.pid}"

echo "=== SD1.5 WebUI API Deployment ==="
echo "SD_HOME=$SD_HOME  PORT=$SD_PORT"

if [ ! -d "$SD_HOME" ]; then
    echo "[1/4] Cloning stable-diffusion-webui..."
    git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git "$SD_HOME"
else
    echo "[1/4] WebUI already cloned"
fi

echo "[2/4] Writing webui-user.sh..."
cat > "$SD_HOME/webui-user.sh" << 'EOF'
#!/bin/bash
export HF_ENDPOINT=https://hf-mirror.com
# gfx1103 核显：MIOpen 卷积库不全，关闭部分 solver 并禁用 MIOpen（见 scripts/gfx1103_disable_miopen.py）
export MIOPEN_FIND_MODE=1
export MIOPEN_DEBUG_DISABLE_FIND_DB=1
export MIOPEN_DEBUG_CONV_DIRECT=0
export MIOPEN_DEBUG_CONV_IMPLICIT_GEMM=0
mkdir -p "$HOME/.cache/miopen"
export COMMANDLINE_ARGS="--skip-torch-cuda-test --medvram --lowvram --nowebui --api --listen --port 7860 --opt-split-attention --disable-safe-unpickle"
EOF
chmod +x "$SD_HOME/webui-user.sh"
# gfx1103：禁用 MIOpen 的启动脚本（可选，与上面环境变量配合）
mkdir -p "$SD_HOME/scripts"
cp -f "$(dirname "$0")/scripts/gfx1103_disable_miopen.py" "$SD_HOME/scripts/" 2>/dev/null || true

if [ ! -f "$SD_HOME/venv/bin/python" ]; then
    echo "[3/4] Installing dependencies (first run, may take a while)..."
    cd "$SD_HOME"
    bash webui.sh --exit --skip-torch-cuda-test
else
    echo "[3/4] Dependencies already installed"
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "[4/4] Server already running (PID $(cat "$PID_FILE"))"
    exit 0
fi

echo "[4/4] Starting API server on port $SD_PORT..."
cd "$SD_HOME"
nohup bash webui.sh > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
sleep 10

if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Server started! PID: $(cat "$PID_FILE")"
    echo "Logs: tail -f $LOG_FILE"
    echo "API:  http://127.0.0.1:$SD_PORT/sdapi/v1/"
else
    echo "Server failed to start. Last 30 lines:"
    tail -30 "$LOG_FILE"
    exit 1
fi
