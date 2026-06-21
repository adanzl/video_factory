"""分镜图 → 视频 clip：Ken Burns 动效 + 字幕 overlay 合成。"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.services.media.ffmpeg_utils import (
    build_ass_from_phrase_cues,
    cpu_pix_fmt_suffix,
    escape_ffmpeg_filter_path,
    ffmpeg_cmd_start,
    finalize_filter_complex,
    libx264_encode_args,
    probe_duration,
    probe_video_size,
    run_ffmpeg,
    vf_for_encode,
)

CLIP_FPS = 25
_MOTION_FINISH_RATIO = 0.42  # 动效在前 42% 时长内完成，之后保持
_PIX_FMT = "yuv420p"  # 浏览器兼容；避免 yuv444p (High 4:4:4)


def _pix_fmt_filter_suffix() -> str:
    return cpu_pix_fmt_suffix()

__all__ = [
    "fit_video_duration",
    "image_to_clip",
    "image_to_clip_timed_overlays",
    "image_to_clip_with_overlay",
    "video_to_clip_timed_overlays",
]


def _motion_progress(frames: int) -> str:
    motion_frames = max(int(frames * _MOTION_FINISH_RATIO), 1)
    eased = f"0.5-0.5*cos(PI*on/{motion_frames})"
    return f"min(1,{eased})"


def _prep_filter(*, headroom: float) -> str:
    """放大画布，给平移/缩放留出余量（避免先裁死再 zoompan）。"""
    s = get_settings()
    w, h = s.video_width, s.video_height
    pw = int(w * headroom)
    ph = int(h * headroom)
    return f"scale={pw}:{ph}:force_original_aspect_ratio=increase"


def _motion_zoom_max(preset: str) -> float:
    if preset == "ken_burns_slow":
        return 1.10
    return 1.16


def _motion_vf(duration_sec: float, *, preset: str, segment_index: int) -> str:
    """连续 Ken Burns：ease-in-out，按分镜序号轮换推/拉/平移。"""
    settings = get_settings()
    w, h = settings.video_width, settings.video_height
    frames = max(int(duration_sec * CLIP_FPS), 1)
    zoom_max = _motion_zoom_max(preset)
    delta = zoom_max - 1.0
    progress = _motion_progress(frames)

    mode = segment_index % 3
    if mode == 1:
        pan_zoom = max(zoom_max, 1.22)
        headroom = max(pan_zoom + 0.10, 1.30)
        z_expr = f"{pan_zoom:.4f}"
        x_expr = f"(iw-iw/zoom)*({progress})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif mode == 2:
        headroom = zoom_max + 0.04
        z_expr = f"{zoom_max:.4f}-{delta:.4f}*({progress})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        headroom = zoom_max + 0.04
        z_expr = f"1+{delta:.4f}*({progress})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    prep = _prep_filter(headroom=headroom)
    return (
        f"{prep},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={frames}:s={w}x{h}:fps={CLIP_FPS}{_pix_fmt_filter_suffix()}"
    )


def image_to_clip(
    image_path: Path,
    output_path: Path,
    duration_sec: float,
    *,
    preset: str = "ken_burns_slow",
    segment_index: int = 0,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    vf = _motion_vf(duration_sec, preset=preset, segment_index=segment_index)
    run_ffmpeg(
        [
            *ffmpeg_cmd_start(),
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-vf",
            vf_for_encode(vf),
            "-t",
            str(duration_sec),
            *libx264_encode_args(),
            str(output_path),
        ]
    )
    return output_path


def image_to_clip_with_overlay(
    image_path: Path,
    overlay_path: Path,
    output_path: Path,
    duration_sec: float,
    *,
    preset: str = "ken_burns_slow",
    segment_index: int = 0,
) -> Path:
    """Ken Burns 动效 + 单张字幕 overlay，单次编码。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    motion = _motion_vf(duration_sec, preset=preset, segment_index=segment_index).removesuffix(
        _pix_fmt_filter_suffix()
    )
    filter_parts = [
        f"[0:v]{motion}{_pix_fmt_filter_suffix()}[bg]",
        "[1:v]format=rgba[fg]",
        f"[bg][fg]overlay=0:0:format=auto{_pix_fmt_filter_suffix()}[out]",
    ]
    filter_complex = ";".join(finalize_filter_complex(filter_parts))

    run_ffmpeg(
        [
            *ffmpeg_cmd_start(),
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(overlay_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-t",
            str(duration_sec),
            *libx264_encode_args(subtitle=True),
            "-sws_flags",
            "lanczos+accurate_rnd+full_chroma_int",  # cSpell: disable-line
            str(output_path),
        ]
    )
    return output_path


def image_to_clip_timed_overlays(
    image_path: Path,
    overlay_windows: list[tuple[Path, float, float]],
    output_path: Path,
    duration_sec: float,
    *,
    preset: str = "ken_burns_slow",
    segment_index: int = 0,
) -> Path:
    """连续 Ken Burns + 多段字幕按时间轴切换，单次编码。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not overlay_windows:
        return image_to_clip(
            image_path,
            output_path,
            duration_sec,
            preset=preset,
            segment_index=segment_index,
        )

    motion = _motion_vf(duration_sec, preset=preset, segment_index=segment_index).removesuffix(
        _pix_fmt_filter_suffix()
    )
    parts = [f"[0:v]{motion}{_pix_fmt_filter_suffix()}[bg]"]
    for idx, (overlay_path, _, _) in enumerate(overlay_windows):
        parts.append(f"[{idx + 1}:v]format=rgba[s{idx}]")

    current = "bg"
    for idx, (_, start, end) in enumerate(overlay_windows):
        nxt = "out" if idx == len(overlay_windows) - 1 else f"v{idx}"
        parts.append(
            f"[{current}][s{idx}]overlay=0:0:format=auto:enable='between(t,{start:.3f},{end:.3f})'[{nxt}]"
        )
        current = nxt

    parts = finalize_filter_complex(parts)
    cmd = [
        *ffmpeg_cmd_start(),
        "-loop",
        "1",
        "-i",
        str(image_path),
    ]
    for overlay_path, _, _ in overlay_windows:
        cmd.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(CLIP_FPS),
                "-i",
                str(overlay_path),
            ]
        )
    cmd.extend(
        [
            "-filter_complex",
            ";".join(parts),
            "-map",
            "[out]",
            "-t",
            str(duration_sec),
            *libx264_encode_args(subtitle=True),
            "-sws_flags",
            "lanczos+accurate_rnd+full_chroma_int",  # cSpell: disable-line
            str(output_path),
        ]
    )
    run_ffmpeg(cmd)
    return output_path


def _scale_pad_vf(*, width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )


def _fit_vf_chain(
    video_dur: float,
    duration_sec: float,
    *,
    width: int,
    height: int,
) -> str:
    scale = _scale_pad_vf(width=width, height=height)
    drift = video_dur - duration_sec
    if abs(drift) <= 0.08:
        return scale
    if drift > 0:
        return f"{scale},trim=0:{duration_sec:.3f},setpts=PTS-STARTPTS"
    pad = duration_sec - video_dur
    return f"{scale},tpad=stop_mode=clone:stop_duration={pad:.3f}"


def fit_video_with_ass_subtitles(
    video_path: Path,
    ass_path: Path,
    output_path: Path,
    duration_sec: float,
    *,
    width: int | None = None,
    height: int | None = None,
    fonts_dir: Path | None = None,
) -> Path:
    """缩放/对齐时长 + ASS 烧字幕，单次编码（素材 merge 用）。"""
    settings = get_settings()
    width = width if width is not None else settings.video_width
    height = height if height is not None else settings.video_height
    fonts_dir = fonts_dir if fonts_dir is not None else settings.font_path.parent
    output_path.parent.mkdir(parents=True, exist_ok=True)

    video_dur = probe_duration(video_path)
    base_vf = _fit_vf_chain(video_dur, duration_sec, width=width, height=height)
    ass_esc = escape_ffmpeg_filter_path(ass_path)
    fonts_esc = escape_ffmpeg_filter_path(fonts_dir)
    vf = f"{base_vf},subtitles={ass_esc}:fontsdir={fonts_esc}"

    run_ffmpeg(
        [
            *ffmpeg_cmd_start(),
            "-i",
            str(video_path),
            "-vf",
            vf_for_encode(vf),
            "-t",
            f"{duration_sec:.3f}",
            *libx264_encode_args(subtitle=True),
            str(output_path),
        ]
    )
    return output_path


def fit_video_duration(
    video_path: Path,
    output_path: Path,
    duration_sec: float,
    *,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    """缩放至成片尺寸，并按目标时长裁切或末帧定格。"""
    settings = get_settings()
    width = width if width is not None else settings.video_width
    height = height if height is not None else settings.video_height
    output_path.parent.mkdir(parents=True, exist_ok=True)

    video_dur = probe_duration(video_path)
    vf = _fit_vf_chain(video_dur, duration_sec, width=width, height=height)

    run_ffmpeg(
        [
            *ffmpeg_cmd_start(),
            "-i",
            str(video_path),
            "-vf",
            vf_for_encode(vf),
            "-t",
            f"{duration_sec:.3f}",
            *libx264_encode_args(),
            str(output_path),
        ]
    )
    return output_path


def video_to_clip_timed_overlays(
    video_path: Path,
    overlay_windows: list[tuple[Path, float, float]],
    output_path: Path,
    duration_sec: float,
) -> Path:
    """已有视频 + 多段字幕按时间轴切换，单次编码。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not overlay_windows:
        fit_video_duration(video_path, output_path, duration_sec)
        return output_path

    video_w, video_h = probe_video_size(video_path)
    parts = [f"[0:v]format={_PIX_FMT}[bg]"]
    for idx, (overlay_path, _, _) in enumerate(overlay_windows):
        _ = overlay_path
        parts.append(f"[{idx + 1}:v]format=rgba,scale={video_w}:{video_h}[s{idx}]")

    current = "bg"
    for idx, (_, start, end) in enumerate(overlay_windows):
        nxt = "out" if idx == len(overlay_windows) - 1 else f"v{idx}"
        parts.append(
            f"[{current}][s{idx}]overlay=0:0:format=auto:enable='between(t,{start:.3f},{end:.3f})'[{nxt}]"
        )
        current = nxt

    parts = finalize_filter_complex(parts)
    cmd = [
        *ffmpeg_cmd_start(),
        "-i",
        str(video_path),
    ]
    for overlay_path, _, _ in overlay_windows:
        cmd.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(CLIP_FPS),
                "-i",
                str(overlay_path),
            ]
        )
    cmd.extend(
        [
            "-filter_complex",
            ";".join(parts),
            "-map",
            "[out]",
            "-t",
            str(duration_sec),
            *libx264_encode_args(subtitle=True),
            "-sws_flags",
            "lanczos+accurate_rnd+full_chroma_int",  # cSpell: disable-line
            str(output_path),
        ]
    )
    run_ffmpeg(cmd)
    return output_path
