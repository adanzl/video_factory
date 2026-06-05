from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import get_settings


def _scale_crop_filter() -> str:
    s = get_settings()
    w, h = s.video_width, s.video_height
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",  # cSpell: disable-line
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(out.stdout.strip())


def concat_clips(clips: list[Path], output_path: Path) -> Path:
    """ffmpeg concat demuxer，适用于同编码的音频/视频片段。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.with_suffix(".txt")
    list_file.write_text(
        "\n".join(f"file '{clip.resolve()}'" for clip in clips),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    list_file.unlink(missing_ok=True)
    return output_path


def concat_videos(clips: list[Path], output_path: Path) -> Path:
    return concat_clips(clips, output_path)


def generate_silent_mp3(output_path: Path, duration_sec: float) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=22050:cl=mono",
            "-t",
            str(duration_sec),
            "-c:a",
            "libmp3lame",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path


def image_to_clip(
    image_path: Path,
    output_path: Path,
    duration_sec: float,
    *,
    preset: str = "ken_burns_slow",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fps = 25
    frames = max(int(duration_sec * fps), 1)
    settings = get_settings()
    w, h = settings.video_width, settings.video_height
    zoom = "1.08" if preset == "ken_burns_slow" else "1.15"
    vf = (
        f"{_scale_crop_filter()},"
        f"zoompan=z='min(zoom+0.0008,{zoom})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"  # cSpell: disable-line
        f"d={frames}:s={w}x{h}:fps={fps},format=yuv444p")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-vf",
            vf,
            "-t",
            str(duration_sec),
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv444p",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path


def image_to_clip_with_overlay(
    image_path: Path,
    overlay_path: Path,
    output_path: Path,
    duration_sec: float,
    *,
    preset: str = "ken_burns_slow",
    crf: int = 14,
) -> Path:
    """Ken Burns 动效 + 字幕 overlay，单次编码（减少字缘压缩损失）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fps = 25
    frames = max(int(duration_sec * fps), 1)
    settings = get_settings()
    w, h = settings.video_width, settings.video_height
    zoom = "1.08" if preset == "ken_burns_slow" else "1.15"
    motion = (
        f"{_scale_crop_filter()},"
        f"zoompan=z='min(zoom+0.0008,{zoom})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"  # cSpell: disable-line
        f"d={frames}:s={w}x{h}:fps={fps}"
    )
    filter_complex = (
        f"[0:v]{motion},format=yuv444p[bg];"
        f"[1:v]format=rgba[fg];"
        f"[bg][fg]overlay=0:0:format=auto,format=yuv444p"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(overlay_path),
            "-filter_complex",
            filter_complex,
            "-t",
            str(duration_sec),
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv444p",
            "-sws_flags",
            "lanczos+accurate_rnd+full_chroma_int",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path


def image_to_video(
    image_path: Path,
    output_path: Path,
    *,
    duration: float,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    settings = get_settings()
    width = width if width is not None else settings.video_width
    height = height if height is not None else settings.video_height
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from PIL import Image

    with Image.open(image_path) as img:
        need_scale = img.size != (width, height)
    vf = (
        f"scale={width}:{height}:flags=lanczos,format=yuv420p"
        if need_scale
        else "format=yuv420p"
    )

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(duration),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path


def merge_audio_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    *,
    subtitle_path: Path | None = None,
) -> Path:
    """合并画面与配音。字幕已在分镜阶段烧录；subtitle_path 仅保留供质检/外挂使用。"""
    _ = subtitle_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path


def _probe_audio_sample_rate(path: Path) -> int | None:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",  # cSpell: disable-line
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    rate = out.stdout.strip()
    if not rate:
        return None
    return int(rate)


def prepend_intro(intro_path: Path, body_path: Path, output_path: Path) -> Path:
    """片头（通常无音轨）接正文，保留正文配音。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = _probe_audio_sample_rate(body_path)
    if sample_rate is None:
        return concat_clips([intro_path, body_path], output_path)

    intro_dur = probe_duration(intro_path)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(intro_path),
            "-i",
            str(body_path),
            "-filter_complex",
            (
                "[0:v]setpts=PTS-STARTPTS[v0];"
                "[1:v]setpts=PTS-STARTPTS[v1];"
                "[v0][v1]concat=n=2:v=1:a=0[vout];"
                f"anullsrc=r={sample_rate}:cl=mono,atrim=0:{intro_dur},asetpts=PTS-STARTPTS[asilent];"
                "[1:a]asetpts=PTS-STARTPTS[a1];"
                "[asilent][a1]concat=n=2:v=0:a=1[aout]"
            ),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path


def _fmt_srt(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt_from_cues(cues: list) -> str:
    """按 TTS 逐句合成的真实时长生成 SRT。"""
    lines: list[str] = []
    cursor = 0.0
    for idx, cue in enumerate(cues, start=1):
        text = cue.text if hasattr(cue, "text") else cue["text"]
        duration = cue.duration_sec if hasattr(cue, "duration_sec") else cue["duration_sec"]
        start = cursor
        end = cursor + duration
        cursor = end
        lines.extend([str(idx), f"{_fmt_srt(start)} --> {_fmt_srt(end)}", text, ""])
    return "\n".join(lines)
