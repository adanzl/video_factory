"""分镜图 → 视频 clip：Ken Burns 动效 + 字幕 overlay 合成。"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.services.media.ffmpeg_utils import (
    cpu_pix_fmt_suffix,
    escape_ffmpeg_filter_path,
    ffmpeg_cmd_start,
    finalize_filter_complex,
    libx264_encode_args,
    probe_duration,
    run_ffmpeg,
    vf_for_encode,
)

CLIP_FPS = 25
_MOTION_FINISH_RATIO = 0.85
_PIX_FMT = "yuv420p"


def _pix_fmt_filter_suffix() -> str:
    return cpu_pix_fmt_suffix()


__all__ = [
    "fit_video_duration",
    "fit_video_with_ass_subtitles",
    "image_to_clip",
    "image_to_clip_timed_overlays",
    "image_to_clip_with_overlay",
    "video_to_clip_timed_overlays",
]


def _prep_filter(*, headroom: float, width: int, height: int) -> str:
    pw = int(width * headroom)
    ph = int(height * headroom)
    return f"scale={pw}:{ph}:force_original_aspect_ratio=increase:flags=lanczos"


def _motion_zoom_max(preset: str) -> float:
    if preset == "ken_burns_slow":
        return 1.08
    return 1.12


def _motion_vf(
    duration_sec: float,
    *,
    preset: str,
    segment_index: int,
    width: int,
    height: int,
) -> str:
    """Ken Burns：zoom 用 scale:eval=frame（lanczos），pan 用 zoompan。"""
    frames = max(int(duration_sec * CLIP_FPS), 1)
    zoom_max = _motion_zoom_max(preset)
    delta = zoom_max - 1.0
    mf = max(int(frames * _MOTION_FINISH_RATIO), 1)
    prog_z = f"min(1,0.5-0.5*cos(PI*n/{mf}))"
    prog_p = f"min(1,0.5-0.5*cos(PI*on/{mf}))"

    mode = (segment_index * 7 + 3) % 10
    if mode < 5:
        # 放大 50%
        headroom = zoom_max + 0.04
        prep = _prep_filter(headroom=headroom, width=width, height=height)
        z = f"1+{delta:.4f}*({prog_z})"
        return f"{prep},scale='iw*({z})':'ih*({z})':flags=bilinear:eval=frame,crop={width}:{height}:(iw-{width})/2:(ih-{height})/2{_pix_fmt_filter_suffix()}"
    elif mode < 7:
        # 右移 20%
        pan_zoom = max(zoom_max, 1.06)
        headroom = max(pan_zoom + 0.10, 1.22)
        prep = _prep_filter(headroom=headroom, width=width, height=height)
        return f"{prep},zoompan=z='{pan_zoom:.4f}':x='(iw-iw/zoom)*({prog_p})':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={CLIP_FPS}{_pix_fmt_filter_suffix()}"
    elif mode < 9:
        # 左移 20%
        pan_zoom = max(zoom_max, 1.06)
        headroom = max(pan_zoom + 0.10, 1.22)
        prep = _prep_filter(headroom=headroom, width=width, height=height)
        return f"{prep},zoompan=z='{pan_zoom:.4f}':x='(iw-iw/zoom)*(1-{prog_p})':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={CLIP_FPS}{_pix_fmt_filter_suffix()}"
    else:
        # 缩小 10%
        headroom = zoom_max + 0.04
        prep = _prep_filter(headroom=headroom, width=width, height=height)
        z = f"{zoom_max:.4f}-{delta:.4f}*({prog_z})"
        return f"{prep},scale='iw*({z})':'ih*({z})':flags=bilinear:eval=frame,crop={width}:{height}:(iw-{width})/2:(ih-{height})/2{_pix_fmt_filter_suffix()}"


def _resolve_clip_canvas(
    width: int | None,
    height: int | None,
) -> tuple[int, int]:
    settings = get_settings()
    return (
        width if width is not None else settings.video_width,
        height if height is not None else settings.video_height,
    )


def image_to_clip_with_overlay(
    image_path: Path,
    overlay_path: Path,
    output_path: Path,
    duration_sec: float,
    *,
    preset: str = "ken_burns_slow",
    segment_index: int = 0,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    """Ken Burns 动效 + 单张字幕 overlay，单次编码。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas_w, canvas_h = _resolve_clip_canvas(width, height)
    motion = _motion_vf(
        duration_sec,
        preset=preset,
        segment_index=segment_index,
        width=canvas_w,
        height=canvas_h,
    ).removesuffix(
        _pix_fmt_filter_suffix()
    )
    filter_parts = [
        f"[0:v]{motion}{_pix_fmt_filter_suffix()}[bg]",
        f"[1:v]format=rgba,scale={canvas_w}:{canvas_h}[fg]",
        f"[bg][fg]overlay=0:0:format=auto{_pix_fmt_filter_suffix()}[out]",
    ]
    filter_complex = ";".join(finalize_filter_complex(filter_parts, force_cpu=True))

    run_ffmpeg(
        [
            *ffmpeg_cmd_start(hwaccel=False),
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
            *libx264_encode_args(subtitle=True, force_cpu=True),
            "-sws_flags",
            "lanczos+accurate_rnd+full_chroma_int",
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
    width: int | None = None,
    height: int | None = None,
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
            width=width,
            height=height,
        )

    canvas_w, canvas_h = _resolve_clip_canvas(width, height)
    motion = _motion_vf(
        duration_sec,
        preset=preset,
        segment_index=segment_index,
        width=canvas_w,
        height=canvas_h,
    ).removesuffix(
        _pix_fmt_filter_suffix()
    )
    parts = [f"[0:v]{motion}{_pix_fmt_filter_suffix()}[bg]"]
    for idx, (overlay_path, _, _) in enumerate(overlay_windows):
        _ = overlay_path
        parts.append(f"[{idx + 1}:v]format=rgba,scale={canvas_w}:{canvas_h}[s{idx}]")

    current = "bg"
    for idx, (_, start, end) in enumerate(overlay_windows):
        nxt = "out" if idx == len(overlay_windows) - 1 else f"v{idx}"
        parts.append(
            f"[{current}][s{idx}]overlay=0:0:format=auto:enable='between(t,{start:.3f},{end:.3f})'[{nxt}]"
        )
        current = nxt

    parts = finalize_filter_complex(parts, force_cpu=True)
    cmd = [
        *ffmpeg_cmd_start(hwaccel=False),
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
            *libx264_encode_args(subtitle=True, force_cpu=True),
            "-sws_flags",
            "lanczos+accurate_rnd+full_chroma_int",
            str(output_path),
        ]
    )
    run_ffmpeg(cmd)
    return output_path


def _scale_pad_vf(*, width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
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
    canvas_w, canvas_h = _resolve_clip_canvas(width, height)
    fonts_dir = fonts_dir if fonts_dir is not None else settings.font_path.parent
    output_path.parent.mkdir(parents=True, exist_ok=True)

    video_dur = probe_duration(video_path)
    base_vf = _fit_vf_chain(video_dur, duration_sec, width=canvas_w, height=canvas_h)
    ass_esc = escape_ffmpeg_filter_path(ass_path)
    fonts_esc = escape_ffmpeg_filter_path(fonts_dir)
    vf = f"{base_vf},subtitles={ass_esc}:fontsdir={fonts_esc},format={_PIX_FMT}"
    run_ffmpeg(
        [
            *ffmpeg_cmd_start(hwaccel=False),
            "-i",
            str(video_path),
            "-vf",
            vf,
            "-t",
            f"{duration_sec:.3f}",
            *libx264_encode_args(subtitle=True, force_cpu=True),
            str(output_path),
        ]
    )
    return output_path


def fit_video_duration(
    input_path: Path,
    output_path: Path,
    target_sec: float,
    *,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if width and height:
        video_dur = probe_duration(input_path)
        vf = _fit_vf_chain(video_dur, target_sec, width=width, height=height)
    else:
        vf = f"fps={CLIP_FPS},format={_PIX_FMT}"
    run_ffmpeg(
        [
            *ffmpeg_cmd_start(hwaccel=False),
            "-i",
            str(input_path),
            "-vf",
            vf_for_encode(vf, force_cpu=True),
            "-c:v",
            "libx264",
            "-crf",
            str(get_settings().ffmpeg_crf),
            "-pix_fmt",
            _PIX_FMT,
            "-movflags",
            "+faststart",
            "-t",
            str(target_sec),
            str(output_path),
        ]
    )
    return output_path


def image_to_clip(
    image_path: Path,
    output_path: Path,
    duration_sec: float,
    *,
    preset: str = "ken_burns_slow",
    segment_index: int = 0,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    """纯 Ken Burns（无字幕），兼容旧调用。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas_w, canvas_h = _resolve_clip_canvas(width, height)
    cmd = [
        *ffmpeg_cmd_start(hwaccel=False),
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-vf",
        vf_for_encode(
            _motion_vf(duration_sec, preset=preset, segment_index=segment_index, width=canvas_w, height=canvas_h)
        ),
        "-c:v",
        "libx264",
        "-crf",
        str(get_settings().ffmpeg_crf),
        "-pix_fmt",
        _PIX_FMT,
        "-movflags",
        "+faststart",
        "-t",
        str(duration_sec),
        str(output_path),
    ]
    run_ffmpeg(cmd)
    return output_path


def video_to_clip_timed_overlays(
    video_path: Path,
    overlay_windows: list[tuple[Path, float, float]],
    output_path: Path,
    duration_sec: float,
    *,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas_w, canvas_h = _resolve_clip_canvas(width, height)

    streams_parts = [
        f"[0:v]scale={canvas_w}:{canvas_h}:flags=lanczos,format=rgba[v0]",
    ]
    for idx, (ov_path, _, _) in enumerate(overlay_windows):
        _ = ov_path
        streams_parts.append(f"[{idx + 1}:v]format=rgba,scale={canvas_w}:{canvas_h}[o{idx}]")

    current = "v0"
    for idx, (_, seg_start, seg_end) in enumerate(overlay_windows):
        nxt = "vout" if idx == len(overlay_windows) - 1 else f"v{idx + 1}"
        streams_parts.append(
            f"[{current}][o{idx}]overlay=0:0:format=auto:enable='between(t,{seg_start:.3f},{seg_end:.3f})'[{nxt}]"
        )
        current = nxt

    filter_complex = ";".join(streams_parts)
    cmd = [
        *ffmpeg_cmd_start(hwaccel=False),
        "-i",
        str(video_path),
    ]
    for ov_path, _, _ in overlay_windows:
        cmd.extend(["-loop", "1", "-framerate", str(CLIP_FPS), "-i", str(ov_path)])
    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-t",
            str(duration_sec),
            *libx264_encode_args(subtitle=True, force_cpu=True),
            str(output_path),
        ]
    )
    run_ffmpeg(cmd)
    return output_path
