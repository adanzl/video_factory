"""预览动态片尾（默认写到 res/host/crayon/end.mp4）。

用法:
  conda activate flask_env
  python backend/scripts/preview_end_card.py
  python backend/scripts/preview_end_card.py --width 1920 --height 1080
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from app.services.end_card import generate_end_card  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="生成动态片尾预览")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument(
        "--out",
        type=Path,
        default=_root / "res" / "host" / "crayon" / "end.mp4",
    )
    args = parser.parse_args()

    out = generate_end_card(args.out, width=args.width, height=args.height)
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
