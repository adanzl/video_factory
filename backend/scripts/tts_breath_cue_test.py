#!/usr/bin/env python3
"""本地试听：PlainText vs 气口 SSML。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.tts.breath_cue import prepare_ssml_text, request_parsed
from app.services.tts.ssml_build import build_ssml_from_breath_cue
from app.services.tts.tts_ali import _run_tts_task

TEXT = (
    "哇，你知道吗？欧洲好多房子都没空调，夏天热得像烤炉！"
    "就像我们躲在冰箱里一样难受。阳光直射着窄窄的街道，"
    "街边的石头房子墙壁晒得发烫，行人纷纷躲进路边咖啡馆的遮阳伞下。"
)

API_RATE = 1.20


def _probe(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        text=True,
    )
    return float(out.strip())


def main() -> None:
    settings = get_settings()
    out_dir = BACKEND_DIR / "tmp" / "tts_breath_cue_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"voice={settings.tts_voice}")
    print(f"api_rate={API_RATE}")
    print(f"text_chars={len(TEXT)}")
    print(f"output_dir={out_dir}")
    print("-" * 72)

    parsed = request_parsed(TEXT)
    if parsed:
        print(f"气口 segmented={parsed.segmented!r}")
        print(f"pause_ms={parsed.pause_ms}")
        ssml = build_ssml_from_breath_cue(parsed)
        if ssml:
            (out_dir / "breath_ssml.txt").write_text(ssml, encoding="utf-8")
    else:
        print("气口 LLM 未产出可用结果（可能走规则兜底）")

    cases: list[tuple[str, str, bool]] = []
    with patch("app.services.tts.tts_ali.resolve_instruction", return_value=None):
        cases.append(("01_plain", TEXT, False))
        tts_text, use_ssml = prepare_ssml_text(TEXT)
        if use_ssml:
            cases.append(("02_breath_ssml", tts_text, True))
            (out_dir / "02_breath_ssml.txt").write_text(tts_text, encoding="utf-8")

    print()
    for label, tts_text, enable_ssml in cases:
        with patch("app.services.tts.tts_ali.resolve_instruction", return_value=None):
            audio = _run_tts_task(
                tts_text, rate=API_RATE, timeout=180, enable_ssml=enable_ssml,
            )
        path = out_dir / f"{label}.mp3"
        path.write_bytes(audio.audio)
        dur = _probe(path)
        mode = "SSML气口" if enable_ssml else "PlainText"
        print(f"{path.name}: {mode}  {dur:.2f}s  字/秒={len(TEXT)/dur:.2f}")

    print()
    print(f"播放: open {out_dir}")


if __name__ == "__main__":
    main()
