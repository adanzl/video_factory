"""预生成片头品牌喊声 MP3，写入 backend/res/audio/intro_shout.mp3。

用法（项目根目录）:
  python backend/scripts/gen_intro_audio.py

有 TTS API Key 时用 CosyVoice 合成；否则生成等时长静音占位（请后续替换为真人录音）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.services.media.ffmpeg_utils import generate_silent_mp3, probe_duration
from app.services.tts.tts_mgr import tts_mgr


def main() -> None:
    settings = get_settings()
    out = settings.intro_shout_path
    out.parent.mkdir(parents=True, exist_ok=True)
    text = f"{settings.brand_name}～～～"
    has_tts = bool(settings.tts_api_key or settings.dashscope_api_key)

    if not has_tts:
        generate_silent_mp3(out, 1.6)
        print(f"无 TTS Key: 已写入静音占位 {out} ({probe_duration(out):.2f}s)")
        return

    tts_mgr.synthesize_utterance(
        text,
        out,
        rate=settings.intro_tts_rate,
        pitch=settings.intro_tts_pitch,
    )
    print(
        f"TTS: {out} ({probe_duration(out):.2f}s, "
        f"voice={settings.tts_voice}, preset={settings.tts_instruct_preset})"
    )


if __name__ == "__main__":
    main()
