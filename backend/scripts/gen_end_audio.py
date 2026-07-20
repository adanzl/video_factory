"""生成片尾配音：开头叮 + 昭昭/灿灿对白，并写出时间轴 JSON。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 确保能找到 backend 包
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.tts.tts_mgr import tts_mgr
from app.services.media.ffmpeg_utils import (
    concat_clips,
    loudnorm_replace,
    probe_duration,
    run_ffmpeg,
)

VOICE_ZHAO = "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9"
VOICE_CAN = "cosyvoice-v3.5-flash-leo-40c4359c732f4b459a40f3408e1186ed"

OUTPUT_DIR = BACKEND_DIR / "res" / "audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "end_daily.mp3"
TIMELINE_PATH = OUTPUT_DIR / "end_daily_timeline.json"
DING_SRC = OUTPUT_DIR / "ding.mp3"
DING_PATH = OUTPUT_DIR / "end_ding.mp3"

# 叮后留一点空再开口，避免贴脸
_DING_GAP_SEC = 0.22
# ding.mp3 原片约 2s：多留完整衰减，再加速压短（避免听感「没发完」）
_DING_SKIP_SEC = 0.05
_DING_KEEP_SEC = 0.90  # 约到原片主音结束
_DING_ATEMPO = 1.7
_DING_FADE_SEC = 0.08


def _fmt_duration(sec: float) -> str:
    if sec < 60:
        return f"{sec:.2f}秒"
    m, s = divmod(sec, 60)
    return f"{int(m)}分{s:.2f}秒"


def _prepare_ding(src: Path, dest: Path) -> float:
    """从 ding.mp3 取完整叮声，atempo 加速后输出 48k mono。"""
    if not src.exists():
        raise FileNotFoundError(f"叮声源文件不存在: {src}")
    # 淡出点按加速后的时长估算
    out_dur = _DING_KEEP_SEC / _DING_ATEMPO
    fade_start = max(0.0, out_dur - _DING_FADE_SEC)
    print(
        f"裁切叮声: {src.name} → {dest.name} "
        f"(skip={_DING_SKIP_SEC:.2f}s keep={_DING_KEEP_SEC:.2f}s "
        f"atempo={_DING_ATEMPO})"
    )
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{_DING_SKIP_SEC:.3f}",
            "-t",
            f"{_DING_KEEP_SEC:.3f}",
            "-i",
            str(src),
            "-af",
            (
                f"atempo={_DING_ATEMPO},"
                f"afade=t=out:st={fade_start:.3f}:d={_DING_FADE_SEC:.3f},"
                "aformat=sample_rates=48000:channel_layouts=mono"
            ),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(dest),
        ]
    )
    return probe_duration(dest)


def _make_silence(path: Path, duration_sec: float) -> Path:
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            f"{duration_sec:.3f}",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(path),
        ]
    )
    return path


def main() -> int:
    settings = get_settings()
    if not (settings.dashscope_api_key or settings.tts_api_key):
        print("ERROR: DASHSCOPE_API_KEY 未配置，无法使用 TTS")
        return 1

    ding_dur = _prepare_ding(DING_SRC, DING_PATH)
    print(f"叮声：{_fmt_duration(ding_dur)}")

    segments = [
        ("昭昭", VOICE_ZHAO, "他们为什么不关注啊？", 1.1),
        ("灿灿", VOICE_CAN, "没准是忘了……", 1.1),
    ]

    clips: list[Path] = []
    timeline_seg_lst: list[dict] = []
    # 对白时间轴从叮+间隙之后起算
    speech_offset = ding_dur + _DING_GAP_SEC
    cursor = speech_offset

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
        timeline_seg_lst.append(
            {
                "speaker": name,
                "text": text,
                "start": round(cursor, 3),
                "end": round(cursor + duration, 3),
            }
        )
        cursor += duration
        print(f"  {name}「{text}」→ {_fmt_duration(duration)}")
        clips.append(clip)

    dialogue_dur = cursor - speech_offset
    print(f"\n对白合计：{_fmt_duration(dialogue_dur)}")

    dialogue_path = OUTPUT_DIR / "clip_dialogue.mp3"
    silence_path = OUTPUT_DIR / "clip_ding_gap.mp3"
    print("正在合并对白并归一音量...")
    concat_clips(clips, dialogue_path)
    loudnorm_replace(dialogue_path)
    _make_silence(silence_path, _DING_GAP_SEC)

    print("正在拼接：叮 + 间隙 + 对白...")
    concat_clips([DING_PATH, silence_path, dialogue_path], OUTPUT_PATH)

    merged_duration = probe_duration(OUTPUT_PATH)
    # concat 后若总长漂移，只校准对白段（叮/间隙保持）
    expected = speech_offset + probe_duration(dialogue_path)
    if expected > 0 and abs(merged_duration - expected) > 0.05:
        # 整段线性缩放（含叮），避免末尾裁切
        scale = merged_duration / expected
        speech_offset_scaled = speech_offset * scale
        for seg in timeline_seg_lst:
            # 相对对白起点缩放后再加回叮偏移
            rel_start = (seg["start"] - speech_offset) * scale
            rel_end = (seg["end"] - speech_offset) * scale
            seg["start"] = round(speech_offset_scaled + rel_start, 3)
            seg["end"] = round(speech_offset_scaled + rel_end, 3)
        speech_offset = speech_offset_scaled

    timeline = {
        "duration": round(merged_duration, 3),
        "ding_end": round(ding_dur, 3),
        "speech_start": round(speech_offset, 3),
        "segments": timeline_seg_lst,
    }
    TIMELINE_PATH.write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for clip in [*clips, dialogue_path, silence_path]:
        clip.unlink(missing_ok=True)

    print(f"合并总时长：{_fmt_duration(merged_duration)}")
    print(f"时间轴：{TIMELINE_PATH}")
    print(f"  叮 0.00-{ding_dur:.2f}s")
    for seg in timeline_seg_lst:
        print(
            f"  {seg['speaker']} {seg['start']:.2f}-{seg['end']:.2f}s 「{seg['text']}」"
        )
    print(f"\n✅ 完成！音频文件: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
