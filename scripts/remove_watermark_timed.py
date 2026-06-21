"""LaMa inpainting with optional start time and custom mask regions."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from remove_overlay import Region, encode_args, probe_video, run


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

# 1920x1080 顶部「夏凉数据」可能出现的左/中/右位置
REGIONS_1920_TOP: tuple[Region, ...] = (
    Region(10, 8, 520, 175),
    Region(700, 8, 520, 175),
    Region(1390, 8, 520, 175),
)


def build_mask(width: int, height: int, regions: tuple[Region, ...]) -> Image.Image:
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for region in regions:
        r = region.scaled(width, height, ref_w=1920, ref_h=1080)
        draw.rectangle([r.x, r.y, r.x + r.w - 1, r.y + r.h - 1], fill=255)
    return mask


def extract_frames(src: Path, frames_dir: Path, start_sec: float | None, limit_sec: float | None) -> int:
    frames_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if start_sec:
        cmd.extend(["-ss", f"{start_sec:.3f}"])
    cmd.extend(["-i", str(src)])
    if limit_sec is not None:
        cmd.extend(["-t", f"{limit_sec:.3f}"])
    cmd.extend(["-vsync", "0", str(frames_dir / "frame_%06d.png")])
    run(cmd)
    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise RuntimeError(f"no frames extracted to {frames_dir}")
    return len(frames)


def inpaint_dir(frames_in: Path, frames_out: Path, mask: Image.Image) -> None:
    from simple_lama_inpainting import SimpleLama

    frames_out.mkdir(parents=True, exist_ok=True)
    frames = sorted(frames_in.glob("frame_*.png"))
    lama = SimpleLama()
    t0 = time.time()
    for i, frame_path in enumerate(frames, 1):
        image = Image.open(frame_path).convert("RGB")
        orig_size = image.size
        result = lama(image, mask)
        if result.size != orig_size:
            result = result.crop((0, 0, orig_size[0], orig_size[1]))
        result.save(frames_out / frame_path.name)
        if i == 1 or i % 50 == 0 or i == len(frames):
            elapsed = time.time() - t0
            print(f"  inpaint {i}/{len(frames)} ({i / elapsed:.1f} fps)" if elapsed else f"  inpaint {i}/{len(frames)}")


def mux_part(src: Path, frames_dir: Path, dst: Path, fps: float, *, use_nvenc: bool = True) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
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
        str(dst),
    ]
    run(cmd)


def concat_parts(head: Path, tail: Path, dst: Path) -> None:
    list_file = dst.with_suffix(".concat.txt")
    list_file.write_text(f"file '{head.as_posix()}'\nfile '{tail.as_posix()}'\n", encoding="utf-8")
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(dst),
        ]
    )
    list_file.unlink(missing_ok=True)


def process(
    src: Path,
    dst: Path,
    *,
    start_sec: float = 0.0,
    regions: tuple[Region, ...] = REGIONS_1920_TOP,
    use_nvenc: bool = True,
) -> None:
    width, height, duration = probe_video(src)
    fps = get_fps(src)
    work = src.parent / "_lama_work" / f"{src.stem}_timed"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    if start_sec <= 0:
        frames_in = work / "in"
        extract_frames(src, frames_in, None, None)
        mask = build_mask(width, height, regions)
        mask.save(work / "mask.png")
        inpaint_dir(frames_in, work / "out", mask)
        mux_part(src, work / "out", dst, fps, use_nvenc=use_nvenc)
    else:
        head = work / "head.mp4"
        tail = work / "tail.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(src),
                "-t",
                f"{start_sec:.3f}",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(head),
            ]
        )
        frames_in = work / "in"
        n = extract_frames(src, frames_in, start_sec, None)
        mask = build_mask(width, height, regions)
        mask.save(work / "mask.png")
        print(f"inpaint {n} frames from {start_sec:.1f}s...")
        inpaint_dir(frames_in, work / "out", mask)
        print("mux tail...")
        mux_part(src, work / "out", tail, fps, use_nvenc=use_nvenc)
        print("concat...")
        concat_parts(head, tail, dst)

    shutil.rmtree(work, ignore_errors=True)
    print(f"done -> {dst}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Timed LaMa watermark removal.")
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path, nargs="?", default=None)
    parser.add_argument("--start-sec", type=float, default=0.0, help="Only inpaint from this time (earlier part copied)")
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    src = args.src.resolve()
    dst = (args.dst or src.with_name(f"{src.stem}_clean{src.suffix}")).resolve()
    process(src, dst, start_sec=args.start_sec, use_nvenc=not args.cpu)


if __name__ == "__main__":
    main()
