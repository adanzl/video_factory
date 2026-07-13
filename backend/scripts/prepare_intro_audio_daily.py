"""为 chat 流水线生成片头品牌喊声 MP3: "昭墨日常"（灿灿+昭昭双音色混音）。

流程：rate=1.0 合成 → 切首尾静音 → atempo 对齐 → amix 混音 → 整体倍速。

用法（项目根目录）:
  python backend/scripts/prepare_intro_audio_daily.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

# cSpell: disable
VOICE_CAN = "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d"
VOICE_ZHAO = "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9"
# cSpell: enable

from app.config import get_settings
from app.services.media.ffmpeg_utils import probe_duration, run_ffmpeg
from app.services.tts.tts_mgr import tts_mgr

# ── 可调参数 ──
OVERALL_RATE = 0.7  # 混音后整体倍速，调这个控制最终时长


def _silencedetect(path: Path) -> tuple[float, float]:
    """返回 (首部静音结束秒, 尾部静音开始秒)。"""
    dur = probe_duration(path)
    result = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "silencedetect=noise=-35dB:d=0.05",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=30,
    )
    # 解析 silence_start / silence_end
    starts = re.findall(r"silence_start:\s*([\d.]+)", result.stderr)
    ends = re.findall(r"silence_end:\s*([\d.]+)", result.stderr)

    # 首部静音：第一个 silence_end（从 0 开始的静音）
    head_end = float(ends[0]) if ends and float(ends[0]) < dur * 0.3 else 0.0
    # 尾部静音：最后一个 silence_start（靠近结尾的静音）
    tail_start = float(starts[-1]) if starts and float(starts[-1]) > dur * 0.7 else dur

    return head_end, tail_start


def _trim_silence(src: Path, dst: Path) -> float:
    """切掉首尾静音，输出 WAV，返回裁切后时长。"""
    head_end, tail_start = _silencedetect(src)
    trim_dur = tail_start - head_end
    run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner",
        "-ss", f"{head_end:.3f}",
        "-t", f"{trim_dur:.3f}",
        "-i", str(src),
        "-c:a", "pcm_s16le",
        str(dst),
    ])
    return probe_duration(dst)


def _atempo(src: Path, dst: Path, target_sec: float) -> None:
    """atempo 变速到目标时长，输出 WAV。"""
    src_dur = probe_duration(src)
    tempo = src_dur / target_sec
    filters: list[str] = []
    remaining = tempo
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")
    run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(src),
        "-filter:a", ",".join(filters),
        "-c:a", "pcm_s16le",
        str(dst),
    ])


def main() -> None:
    settings = get_settings()
    out = settings.res_dir / "audio" / "intro_shout_daily.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)

    text = "昭墨日常"
    has_tts = bool(settings.tts_api_key or settings.dashscope_api_key)

    if not has_tts:
        print("无 TTS Key")
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)

        # 1. rate=1.0 合成
        raw_can = p / "can.mp3"
        raw_zhao = p / "zhao.mp3"
        tts_mgr.synthesize_utterance(text, raw_can, rate=1.0, voice=VOICE_CAN)
        tts_mgr.synthesize_utterance(text, raw_zhao, rate=1.0, voice=VOICE_ZHAO)
        print(f"[合成] 灿灿={probe_duration(raw_can):.3f}s  昭昭={probe_duration(raw_zhao):.3f}s")

        # 2. 切首尾静音
        trim_can = p / "can_trim.wav"
        trim_zhao = p / "zhao_trim.wav"
        dur_can = _trim_silence(raw_can, trim_can)
        dur_zhao = _trim_silence(raw_zhao, trim_zhao)
        print(f"[裁剪] 灿灿={dur_can:.3f}s  昭昭={dur_zhao:.3f}s")

        # 3. atempo 对齐：长的缩到短的时长
        target = min(dur_can, dur_zhao)
        aligned_can = p / "can_aligned.wav"
        aligned_zhao = p / "zhao_aligned.wav"
        _atempo(trim_can, aligned_can, target)
        _atempo(trim_zhao, aligned_zhao, target)
        print(f"[对齐] 灿灿={probe_duration(aligned_can):.3f}s  昭昭={probe_duration(aligned_zhao):.3f}s  (target={target:.3f}s)")

        # 4. amix 混音
        mixed = p / "mixed.wav"
        run_ffmpeg([
            "ffmpeg", "-y", "-hide_banner",
            "-i", str(aligned_can),
            "-i", str(aligned_zhao),
            "-filter_complex", "amix=inputs=2:duration=longest:normalize=0",
            "-c:a", "pcm_s16le",
            str(mixed),
        ])
        print(f"[混音] {probe_duration(mixed):.3f}s")

        # 5. 整体倍速
        final_wav = p / "final.wav"
        _atempo(mixed, final_wav, probe_duration(mixed) / OVERALL_RATE)
        run_ffmpeg([
            "ffmpeg", "-y", "-hide_banner",
            "-i", str(final_wav),
            "-c:a", "libmp3lame", "-q:a", "2",
            str(out),
        ])

    final_dur = probe_duration(out)
    print(f"[输出] {out}  {final_dur:.2f}s  (overall_rate={OVERALL_RATE})")


if __name__ == "__main__":
    main()
