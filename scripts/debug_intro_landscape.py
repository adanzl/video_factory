"""从项目根目录运行横屏片头 debug（转发到 backend/scripts）。"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

BACKEND_SCRIPT = Path(__file__).resolve().parents[1] / "backend" / "scripts" / "debug_intro_landscape.py"

if not BACKEND_SCRIPT.is_file():
    raise SystemExit(f"找不到脚本: {BACKEND_SCRIPT}")

sys.path.insert(0, str(BACKEND_SCRIPT.parent.parent))
runpy.run_path(str(BACKEND_SCRIPT), run_name="__main__")
