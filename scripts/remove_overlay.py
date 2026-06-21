"""Remove fixed Bilibili overlay regions (top-right logo + bottom subtitles) via FFmpeg delogo."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "data" / "tmp" / "material"
DEFAULT_OUT = DEFAULT_IN / "clean"


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    w: int
    h: int

    def scaled(self, src_w: int, src_h: int, ref_w: int = 852, ref_h: int = 480) -> Region:
        sx = src_w / ref_w
        sy = src_h / ref_h
        return Region(
            x=max(0, round(self.x * sx)),
            y=max(0, round(self.y * sy)),
            w=max(1, round(self.w * sx)),
            h=max(1, round(self.h * sy)),
        )

    def delogo(self) -> str:
        return f"delogo=x={self.x}:y={self.y}:w={self.w}:h={self.h}"


# 852x480 B站合集素材默认遮罩（可用 --probe 抽帧核对后微调）
REGIONS_852x480: tuple[Region, ...] = (
    Region(648, 12, 200, 42),   # 右上「不可思议的时刻」+ bilibili
    Region(120, 418, 610, 58),  # 底部中文字幕带
)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(f'"{p}"' if " " in p else p for p in cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"command failed ({result.returncode}): {detail[-2000:]}")
    return result


def probe_video(path: Path) -> tuple[int, int, float]:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    duration = float(data["format"]["duration"])
    return int(stream["width"]), int(stream["height"]), duration


def build_filter(width: int, height: int, regions: tuple[Region, ...]) -> str:
    scaled = [r.scaled(width, height) for r in regions]
    for r in scaled:
        if r.x + r.w > width or r.y + r.h > height:
            raise ValueError(f"region out of bounds for {width}x{height}: {r}")
    return ",".join(r.delogo() for r in scaled)


def probe(path: Path, out_dir: Path | None = None) -> None:
    width, height, duration = probe_video(path)
    out_dir = out_dir or path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stamps = [max(0.5, duration * 0.05), duration * 0.25, duration * 0.5]
    for i, sec in enumerate(stamps, 1):
        out = out_dir / f"{path.stem}_probe{i}.jpg"
        run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{sec:.2f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                str(out),
            ]
        )
        print(f"  {out}")

    print(f"\n{path.name}: {width}x{height}, {duration:.1f}s")
    print("Suggested filter (-vf):")
    print(f"  {build_filter(width, height, REGIONS_852x480)}")
    print("\nRegions (852x480 preset, scaled to actual size):")
    for name, region in zip(("top-right", "bottom-sub"), REGIONS_852x480):
        r = region.scaled(width, height)
        print(f"  {name}: x={r.x} y={r.y} w={r.w} h={r.h}")


def encode_args(use_nvenc: bool) -> list[str]:
    if use_nvenc:
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def process_one(
    src: Path,
    dst: Path,
    *,
    use_nvenc: bool = True,
    regions: tuple[Region, ...] = REGIONS_852x480,
) -> dict:
    width, height, duration = probe_video(src)
    vf = build_filter(width, height, regions)
    dst.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-vf",
        vf,
        *encode_args(use_nvenc),
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    try:
        run(cmd)
    except RuntimeError:
        if not use_nvenc:
            raise
        print("NVENC failed, retrying with libx264...", file=sys.stderr)
        process_one(src, dst, use_nvenc=False, regions=regions)
        return {"src": str(src), "dst": str(dst), "encoder": "libx264", "duration": duration}

    return {"src": str(src), "dst": str(dst), "encoder": "h264_nvenc" if use_nvenc else "libx264", "duration": duration}


def batch(
    in_dir: Path,
    out_dir: Path,
    *,
    dry_run: bool = False,
    use_nvenc: bool = True,
) -> list[dict]:
    files = sorted(p for p in in_dir.glob("*.mp4") if p.is_file())
    if not files:
        print(f"No mp4 files in {in_dir}")
        return []

    manifest: list[dict] = []
    for src in files:
        dst = out_dir / src.name
        if dry_run:
            print(f"  {src.name} -> {dst}")
            continue
        print(f"\n[{src.name}]")
        entry = process_one(src, dst, use_nvenc=use_nvenc)
        manifest.append(entry)

    if not dry_run and manifest:
        manifest_path = out_dir / "clean_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote {manifest_path} ({len(manifest)} files)")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove fixed Bilibili overlays with FFmpeg delogo.")
    parser.add_argument("inputs", nargs="*", help="Input mp4 file(s); default: batch all in --in-dir")
    parser.add_argument("--in-dir", type=Path, default=DEFAULT_IN, help=f"Input directory (default: {DEFAULT_IN})")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT, help=f"Output directory (default: {DEFAULT_OUT})")
    parser.add_argument("--probe", action="store_true", help="Extract probe frames and print delogo params")
    parser.add_argument("--dry-run", action="store_true", help="List files only, do not encode")
    parser.add_argument("--cpu", action="store_true", help="Force libx264 instead of NVENC")
    args = parser.parse_args()

    use_nvenc = not args.cpu

    if args.probe:
        targets = [Path(p) for p in args.inputs] if args.inputs else sorted(args.in_dir.glob("*.mp4"))[:1]
        if not targets:
            parser.error("no input for --probe")
        for path in targets:
            probe(path.resolve())
        return

    if args.inputs:
        for raw in args.inputs:
            src = Path(raw).resolve()
            dst = args.out_dir / src.name
            if args.dry_run:
                print(f"  {src.name} -> {dst}")
                continue
            print(f"\n[{src.name}]")
            process_one(src, dst, use_nvenc=use_nvenc)
        return

    batch(args.in_dir, args.out_dir, dry_run=args.dry_run, use_nvenc=use_nvenc)


if __name__ == "__main__":
    main()
