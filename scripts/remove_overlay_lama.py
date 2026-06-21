"""Remove fixed overlays via LaMa inpainting (frame-by-frame)."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from remove_overlay import DEFAULT_IN, REGIONS_852x480, Region, encode_args, probe_video, run

DEFAULT_OUT = DEFAULT_IN / "clean_lama"
WORK_ROOT = DEFAULT_IN / "_lama_work"


def build_mask(width: int, height: int, regions: tuple[Region, ...]) -> Image.Image:
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for region in regions:
        r = region.scaled(width, height)
        draw.rectangle([r.x, r.y, r.x + r.w - 1, r.y + r.h - 1], fill=255)
    return mask


def extract_frames(src: Path, frames_dir: Path, fps: float, limit_sec: float | None) -> int:
    frames_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
    ]
    if limit_sec is not None:
        cmd.extend(["-t", f"{limit_sec:.3f}"])
    cmd.extend(["-vsync", "0", str(frames_dir / "frame_%06d.png")])
    run(cmd)
    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise RuntimeError(f"no frames extracted to {frames_dir}")
    return len(frames)


def get_fps(src: Path) -> float:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(src),
        ]
    )
    num, den = result.stdout.strip().split("/")
    return float(num) / float(den)


def inpaint_frames(
    frames_dir: Path,
    out_dir: Path,
    mask: Image.Image,
) -> None:
    from simple_lama_inpainting import SimpleLama

    out_dir.mkdir(parents=True, exist_ok=True)
    frames = sorted(frames_dir.glob("frame_*.png"))
    lama = SimpleLama()

    t0 = time.time()
    for i, frame_path in enumerate(frames, 1):
        image = Image.open(frame_path).convert("RGB")
        orig_size = image.size
        result = lama(image, mask)
        if result.size != orig_size:
            result = result.crop((0, 0, orig_size[0], orig_size[1]))
        result.save(out_dir / frame_path.name)
        if i == 1 or i % 50 == 0 or i == len(frames):
            elapsed = time.time() - t0
            fps = i / elapsed if elapsed > 0 else 0.0
            print(f"  inpaint {i}/{len(frames)} ({fps:.1f} fps)")


def mux_video(
    src: Path,
    frames_dir: Path,
    dst: Path,
    fps: float,
    *,
    use_nvenc: bool = True,
) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    video_only = dst.with_suffix(".video.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        f"{fps:.6f}",
        "-i",
        str(frames_dir / "frame_%06d.png"),
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        *encode_args(use_nvenc),
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        "-movflags",
        "+faststart",
        str(video_only),
    ]
    try:
        run(cmd)
    except RuntimeError:
        if not use_nvenc:
            raise
        print("NVENC mux failed, retrying with libx264...", file=sys.stderr)
        mux_video(src, frames_dir, dst, fps, use_nvenc=False)
        return

    if video_only == dst:
        return
    if dst.exists():
        dst.unlink()
    video_only.rename(dst)


def process_one(
    src: Path,
    dst: Path,
    *,
    limit_sec: float | None = None,
    keep_work: bool = False,
    use_nvenc: bool = True,
    regions: tuple[Region, ...] = REGIONS_852x480,
) -> dict:
    width, height, duration = probe_video(src)
    fps = get_fps(src)
    work = WORK_ROOT / src.stem
    frames_in = work / "in"
    frames_out = work / "out"

    if work.exists():
        shutil.rmtree(work)
    frames_in.mkdir(parents=True)

    print(f"extract frames ({limit_sec or duration:.1f}s max)...")
    n_frames = extract_frames(src, frames_in, fps, limit_sec)
    mask = build_mask(width, height, regions)
    mask.save(work / "mask.png")

    print(f"inpaint {n_frames} frames with LaMa...")
    inpaint_frames(frames_in, frames_out, mask)

    print("mux video + audio...")
    mux_video(src, frames_out, dst, fps, use_nvenc=use_nvenc)

    if not keep_work:
        shutil.rmtree(work, ignore_errors=True)

    out_duration = min(duration, limit_sec) if limit_sec else duration
    return {
        "src": str(src),
        "dst": str(dst),
        "method": "lama",
        "frames": n_frames,
        "duration": out_duration,
        "encoder": "h264_nvenc" if use_nvenc else "libx264",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove overlays with LaMa inpainting.")
    parser.add_argument("inputs", nargs="*", help="Input mp4; default: none (require input)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit-sec", type=float, default=None, help="Only process first N seconds")
    parser.add_argument("--keep-work", action="store_true", help="Keep intermediate frames")
    parser.add_argument("--cpu", action="store_true", help="Force libx264 on mux")
    args = parser.parse_args()

    if not args.inputs:
        parser.error("provide at least one input mp4")

    manifest: list[dict] = []
    for raw in args.inputs:
        src = Path(raw).resolve()
        dst = args.out_dir / src.name
        print(f"\n[{src.name}]")
        entry = process_one(
            src,
            dst,
            limit_sec=args.limit_sec,
            keep_work=args.keep_work,
            use_nvenc=not args.cpu,
        )
        manifest.append(entry)

    if len(manifest) > 1:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = args.out_dir / "clean_lama_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote {manifest_path}")


if __name__ == "__main__":
    main()
