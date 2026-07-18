"""生成两段对话音频：昭昭 + 灿灿，合并为单文件。"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保能找到 backend 包
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.tts.tts_mgr import tts_mgr
from app.services.media.ffmpeg_utils import concat_clips, loudnorm_replace, probe_duration

VOICE_ZHAO = "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9"
VOICE_CAN = "cosyvoice-v3.5-flash-leo-40c4359c732f4b459a40f3408e1186ed"

OUTPUT_DIR = BACKEND_DIR.parent / "backend" / "res" / "audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "end_daily.mp3"


def _fmt_duration(sec: float) -> str:
    if sec < 60:
        return f"{sec:.2f}秒"
    m, s = divmod(sec, 60)
    return f"{int(m)}分{s:.2f}秒"


def main() -> int:
    settings = get_settings()
    if not (settings.dashscope_api_key or settings.tts_api_key):
        print("ERROR: DASHSCOPE_API_KEY 未配置，无法使用 TTS")
        return 1

    segments = [
        ("昭昭", VOICE_ZHAO, "他们为什么不关注啊？", 1.1),
        ("灿灿", VOICE_CAN, "没准是忘了……", 1.1),
    ]

    clips = []
    total_duration = 0.0

    for name, voice, text, rate in segments:
        print(f"正在生成{name}音频...")
        clip = OUTPUT_DIR / f"clip_{name}.mp3"
        tts_mgr.synthesize_utterance(
            text,
            clip,
            voice=voice,
            rate=rate,
        )
        duration = probe_duration(clip)
        total_duration += duration
        print(f"  {name}「{text}」→ {_fmt_duration(duration)}")
        clips.append(clip)

    print(f"\n各句时长合计：{_fmt_duration(total_duration)}")

    print("正在合并音频...")
    concat_clips(clips, OUTPUT_PATH)

    print("正在归一音量...")
    loudnorm_replace(OUTPUT_PATH)

    merged_duration = probe_duration(OUTPUT_PATH)

    # 清理临时文件
    for clip in clips:
        clip.unlink(missing_ok=True)

    print(f"合并总时长：{_fmt_duration(merged_duration)}")
    print(f"\n✅ 完成！音频文件: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
