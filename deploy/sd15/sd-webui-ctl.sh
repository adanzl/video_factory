#!/bin/bash
# WebUI 启停：start | stop | restart | status | logs
set -euo pipefail

SD_HOME="${SD_HOME:-/mnt/data/stable-diffusion/webui}"
SD_PORT="${SD_PORT:-7860}"
LOG_FILE="${LOG_FILE:-$HOME/sd-webui.log}"
PID_FILE="${PID_FILE:-$HOME/sd-webui.pid}"

stop_webui() {
  local pid=""
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping PID $pid ..."
      kill "$pid" 2>/dev/null || true
      sleep 2
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
  # webui.sh 会拉起 launch.py，一并清理
  pkill -f "$SD_HOME/launch.py" 2>/dev/null || true
  pkill -f "$SD_HOME/webui.sh" 2>/dev/null || true
  sleep 1
  if ss -tlnp 2>/dev/null | grep -q ":${SD_PORT} "; then
    echo "Port $SD_PORT still in use, force kill ..."
    fuser -k "${SD_PORT}/tcp" 2>/dev/null || true
    sleep 1
  fi
  echo "Stopped."
}

start_webui() {
  if [[ ! -d "$SD_HOME" ]]; then
    echo "SD_HOME not found: $SD_HOME" >&2
    exit 1
  fi
  if ss -tlnp 2>/dev/null | grep -q ":${SD_PORT} "; then
    echo "Port $SD_PORT already in use. Run: $0 stop" >&2
    exit 1
  fi
  echo "Starting WebUI (SD_HOME=$SD_HOME, port=$SD_PORT) ..."
  cd "$SD_HOME"
  nohup bash webui.sh >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  sleep 5
  if kill -0 "$(cat "$PID_FILE")" 2>/dev/null || ss -tlnp 2>/dev/null | grep -q ":${SD_PORT} "; then
    echo "Started. PID=$(cat "$PID_FILE" 2>/dev/null || echo '?')"
    echo "API:  http://127.0.0.1:${SD_PORT}/sdapi/v1/"
    echo "Logs: tail -f $LOG_FILE"
  else
    echo "Start failed. Last 20 lines:" >&2
    tail -20 "$LOG_FILE" >&2
    exit 1
  fi
}

status_webui() {
  echo "SD_HOME=$SD_HOME  PORT=$SD_PORT"
  if [[ -f "$PID_FILE" ]]; then
    echo -n "PID file: $(cat "$PID_FILE") "
    kill -0 "$(cat "$PID_FILE")" 2>/dev/null && echo "(running)" || echo "(stale)"
  else
    echo "PID file: none"
  fi
  if ss -tlnp 2>/dev/null | grep ":${SD_PORT} "; then
    echo "Port $SD_PORT: listening"
  else
    echo "Port $SD_PORT: not listening"
  fi
  curl -sf "http://127.0.0.1:${SD_PORT}/sdapi/v1/sd-models" >/dev/null 2>&1 \
    && echo "API: OK" || echo "API: not ready"
}

usage() {
  echo "Usage: $0 {start|stop|restart|status|logs}"
  echo "Env: SD_HOME SD_PORT LOG_FILE PID_FILE"
}

cmd="${1:-}"
case "$cmd" in
  start) start_webui ;;
  stop) stop_webui ;;
  restart) stop_webui; start_webui ;;
  status) status_webui ;;
  logs) tail -f "$LOG_FILE" ;;
  *) usage; exit 1 ;;
esac
