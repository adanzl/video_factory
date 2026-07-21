"""预览横屏片头 MP4 + PNG。

用法（在 backend 目录）:
  python scripts/preview_intro_landscape.py
  python scripts/preview_intro_landscape.py --title "你的标题" --width 1920 --height 1080
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.intro.generator import (  # noqa: E402
    _FPS,
    _HOLD_TAIL_SEC,
    _brand_audio_path,
    _build_layers,
    _compose_frame,
    _layout_for,
    _load_host_sprite,
    _render_frames,
)
from app.services.intro.themes import get_intro_theme


def _run(cmd: list[str], *, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd))
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _probe_duration(path: Path) -> float:
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=30,
    )
    return float(out.stdout.strip())


def _sequence_to_video(frames_dir: Path, output_path: Path, *, fps: int, frame_count: int) -> None:
    pattern = str(frames_dir / "frame_%04d.png")
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-framerate",
            str(fps),
            "-i",
            pattern,
            "-frames:v",
            str(frame_count),
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        timeout=300,
    )


def _mux_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        timeout=120,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug 横屏片头生成")
    parser.add_argument("--title", default="别眨眼，万箭齐发？一分钟看懂冰雹成因")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--hold-tail", type=float, default=_HOLD_TAIL_SEC)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BACKEND_DIR.parent / "data" / "debug",
    )
    args = parser.parse_args()

    settings = get_settings()
    theme = get_intro_theme(None)
    layout = _layout_for(args.width, args.height)
    print(f"layout={'landscape' if layout.landscape else 'portrait'} size={args.width}x{args.height}")

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "intro_landscape.mp4"
    work = out_dir / "intro_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    host = _load_host_sprite(settings, width=args.width, height=args.height, layout=layout)
    moon_tint_yellow = settings.intro_moon_tint in {"yellow", "tint", "gold", "1", "true"}
    layers = _build_layers(
        args.title,
        settings.brand_name,
        theme,
        args.width,
        args.height,
        host,
        layout,
        moon_path=settings.intro_moon_path,
        moon_tint_yellow=moon_tint_yellow,
    )

    audio_path = _brand_audio_path(work)
    audio_dur = _probe_duration(audio_path)
    duration = audio_dur + max(0.0, args.hold_tail)
    print(f"audio={audio_dur:.2f}s total={duration:.2f}s frames≈{int(duration * _FPS)}")

    t0 = time.perf_counter()
    frames_dir = work / "frames"
    frame_count = _render_frames(layers, frames_dir, duration=duration, fps=_FPS)
    print(f"frames rendered: {frame_count} in {time.perf_counter() - t0:.1f}s")

    silent_video = work / "video.mp4"
    _sequence_to_video(frames_dir, silent_video, fps=_FPS, frame_count=frame_count)
    _mux_video_audio(silent_video, audio_path, output_path)

    preview = output_path.with_suffix(".png")
    _compose_frame(layers, duration * 0.45).convert("RGB").save(preview, compress_level=1)

    shutil.rmtree(work, ignore_errors=True)
    print(f"mp4:  {output_path.resolve()}")
    print(f"png:  {preview.resolve()}")
    print(f"size: {output_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
