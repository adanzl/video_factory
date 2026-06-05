#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

resolve_python() {
  if [[ -n "${PYTHON:-}" && -x "$PYTHON" ]]; then
    echo "$PYTHON"
    return
  fi
  local conda_python="/opt/homebrew/Caskroom/miniconda/base/envs/flask_env/bin/python"
  if [[ -x "$conda_python" ]]; then
    echo "$conda_python"
    return
  fi
  command -v python3
}

PYTHON="$(resolve_python)"
DEFAULT_TITLE="不锈钢能被磁铁吸住，就代表买到次品了？"

if [[ $# -eq 0 ]]; then
  exec "$PYTHON" -m worker run --title "$DEFAULT_TITLE" --skip-publish
else
  exec "$PYTHON" -m worker run "$@"
fi
