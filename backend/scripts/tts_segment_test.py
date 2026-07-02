#!/usr/bin/env python3
"""本地试听：整段流式 PlainText + 字级时间戳断句。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.media.ffmpeg_utils import build_srt_from_cues
from app.services.tts.breath_cue import build_phrase_breath_cues
from app.services.tts.phrase_timing import (
    build_segment_tts_text,
    normalize_word_timestamps,
)
from app.services.tts.segment_trim import apply_tts_segment_trim
from app.services.tts.tts_ali import _run_tts_task
from app.services.tts.tts_mgr import SubtitleCue, tts_mgr
from app.services.render.text_render import split_phrase_chunks

TEXT = (
    "哇，你知道吗？欧洲好多房子都没空调，夏天热得像烤炉！"
    "就像我们躲在冰箱里一样难受。阳光直射着窄窄的街道，"
    "街边的石头房子墙壁晒得发烫，行人纷纷躲进路边咖啡馆的遮阳伞下。"
)

API_RATE = 1.20
AUDIO_EXT = ".mp3"


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
    out_dir = BACKEND_DIR / "tmp" / "tts_segment_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    phrases = split_phrase_chunks(TEXT)
    segment_text = build_segment_tts_text(phrases)

    print(f"voice={settings.tts_voice}")
    print(f"api_rate={API_RATE} format=mp3 transport=websocket")
    print(f"phrases={len(phrases)} chars={len(segment_text)}")
    print(f"output_dir={out_dir}")
    print("-" * 72)

    with patch("app.services.tts.tts_ali.resolve_instruction", return_value=None):
        result = _run_tts_task(
            segment_text,
            rate=API_RATE,
            timeout=180,
            word_timestamps=True,
            audio_format="mp3",
        )

    path = out_dir / f"01_segment{AUDIO_EXT}"
    path.write_bytes(result.audio)
    words = normalize_word_timestamps(result.words)
    if settings.tts_trim_edges and words:
        words = apply_tts_segment_trim(path, words)

    duration = _probe(path)
    breath_cues = build_phrase_breath_cues(
        phrases,
        words,
        segment_duration_sec=duration,
    )

    timeline = []
    for index, cue in enumerate(breath_cues, start=1):
        _, display = phrases[index - 1]
        timeline.append({
            "index": index,
            "display_text": display,
            "duration_sec": round(cue.duration_sec, 3),
            "pause_after_ms": cue.pause_after_ms,
        })

    (out_dir / "words.json").write_text(
        json.dumps(result.words, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "phrase_timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    subtitle_cues = [
        SubtitleCue(segment_index=1, text=display, duration_sec=cue.duration_sec)
        for (_, display), cue in zip(phrases, breath_cues, strict=False)
    ]
    srt_path = out_dir / "subtitles.srt"
    srt_path.write_text(build_srt_from_cues(subtitle_cues), encoding="utf-8")
    cues_path = tts_mgr.subtitle_cues_path_for(out_dir)
    tts_mgr.save_subtitle_cues(cues_path, subtitle_cues)

    print(f"01_segment: {path.name} duration={duration:.2f}s words={len(words)}")
    print(f"usage={json.dumps(result.usage, ensure_ascii=False)}")
    for row in timeline:
        pause = row["pause_after_ms"]
        extra = f" pause_after={pause}ms" if pause is not None else ""
        print(f"  [{row['index']:02d}] {row['duration_sec']:.2f}s {row['display_text']!r}{extra}")
    cue_sum = sum(cue.duration_sec for cue in subtitle_cues)
    print(f"subtitles: {srt_path.name} cues={len(subtitle_cues)} sum={cue_sum:.2f}s drift={abs(cue_sum - duration):.3f}s")
    print()
    print(srt_path.read_text(encoding="utf-8"))
    print(f"播放: open {out_dir}")


if __name__ == "__main__":
    main()
