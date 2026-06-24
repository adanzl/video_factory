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
# 国内服务器：CLIP 等依赖走 hf-mirror，避免 huggingface.co 连不上
export HF_ENDPOINT=https://hf-mirror.com
export COMMANDLINE_ARGS="--skip-torch-cuda-test --medvram --lowvram --nowebui --api --listen --port 7860 --opt-split-attention --disable-safe-unpickle"
EOF
chmod +x "$SD_HOME/webui-user.sh"

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
