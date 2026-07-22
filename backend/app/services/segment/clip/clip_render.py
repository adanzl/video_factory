"""分镜图 → 视频 clip：Ken Burns 动效（字幕在 merge 阶段 ASS 烧录）。"""

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
_MOTION_FINISH_RATIO = 0.95
_PIX_FMT = "yuv420p"

# 相邻尽量不同类；按 segment_index 均匀轮换（无静止）
_MOTION_MODES = (
    "zoom_in",
    "pan_right",
    "zoom_out",
    "pan_left",
    "pan_up",
    "pan_diag_dr",
    "pan_down",
    "pan_diag_ul",
)


def _pix_fmt_filter_suffix() -> str:
    return cpu_pix_fmt_suffix()


def _even(value: int) -> int:
    return value if value % 2 == 0 else value + 1


def _still_image_input_args(image_path: Path) -> list[str]:
    """静图必须带 framerate，否则 loop 时间基不稳，动效会顿/掉帧。"""
    return [
        "-loop",
        "1",
        "-framerate",
        str(CLIP_FPS),
        "-i",
        str(image_path),
    ]


__all__ = [
    "burn_ass_subtitles",
    "fit_video_duration",
    "fit_video_with_ass_subtitles",
    "image_to_clip",
    "image_to_clip_timed_overlays",
    "image_to_clip_with_overlay",
    "video_to_clip_timed_overlays",
]


def _prep_filter(*, headroom: float, width: int, height: int) -> str:
    pw = _even(int(width * headroom))
    ph = _even(int(height * headroom))
    return f"scale={pw}:{ph}:force_original_aspect_ratio=increase:flags=lanczos"


def _motion_zoom_max(preset: str) -> float:
    if preset == "ken_burns_slow":
        return 1.16
    return 1.20


def _pick_motion_mode(segment_index: int) -> str:
    idx = segment_index if segment_index > 0 else 1
    return _MOTION_MODES[(idx - 1) % len(_MOTION_MODES)]


def _ease_prog(motion_frames: int) -> str:
    mf = max(motion_frames, 1)
    return f"min(1,0.5-0.5*cos(PI*n/{mf}))"


def _motion_tail() -> str:
    return f",fps={CLIP_FPS}{_pix_fmt_filter_suffix()}"


def _zoom_motion_vf(
    *,
    zoom_expr: str,
    width: int,
    height: int,
    headroom: float,
) -> str:
    prep = _prep_filter(headroom=headroom, width=width, height=height)
    # crop 取整，避免亚像素裁切抖动
    return (
        f"{prep},"
        f"scale='iw*({zoom_expr})':'ih*({zoom_expr})':flags=bilinear:eval=frame,"
        f"crop={width}:{height}:floor((iw-{width})/2):floor((ih-{height})/2)"
        f"{_motion_tail()}"
    )


def _pan_motion_vf(
    *,
    pan_zoom: float,
    x_expr: str,
    y_expr: str,
    width: int,
    height: int,
) -> str:
    headroom = max(pan_zoom + 0.12, 1.24)
    prep = _prep_filter(headroom=headroom, width=width, height=height)
    z = f"{pan_zoom:.4f}"
    return (
        f"{prep},"
        f"scale=iw*{z}:ih*{z}:flags=lanczos,"
        f"crop={width}:{height}:'floor(({x_expr}))':'floor(({y_expr}))'"
        f"{_motion_tail()}"
    )


def _motion_vf(
    duration_sec: float,
    *,
    preset: str,
    segment_index: int,
    width: int,
    height: int,
) -> str:
    """Ken Burns：全部走 scale+crop（不用 zoompan），末尾强制 CFR。"""
    frames = max(1, round(duration_sec * CLIP_FPS))
    zoom_max = _motion_zoom_max(preset)
    delta = zoom_max - 1.0
    prog = _ease_prog(max(int(frames * _MOTION_FINISH_RATIO), 1))
    mode = _pick_motion_mode(segment_index)
    pan_zoom = max(zoom_max, 1.08)
    # 平移可用行程（相对放大后画布）
    max_x = f"iw-{width}"
    max_y = f"ih-{height}"
    mid_x = f"({max_x})/2"
    mid_y = f"({max_y})/2"

    if mode == "zoom_in":
        z = f"1+{delta:.4f}*({prog})"
        return _zoom_motion_vf(zoom_expr=z, width=width, height=height, headroom=zoom_max + 0.06)
    if mode == "zoom_out":
        z = f"{zoom_max:.4f}-{delta:.4f}*({prog})"
        return _zoom_motion_vf(zoom_expr=z, width=width, height=height, headroom=zoom_max + 0.06)
    if mode == "pan_right":
        return _pan_motion_vf(
            pan_zoom=pan_zoom,
            x_expr=f"({max_x})*({prog})",
            y_expr=mid_y,
            width=width,
            height=height,
        )
    if mode == "pan_left":
        return _pan_motion_vf(
            pan_zoom=pan_zoom,
            x_expr=f"({max_x})*(1-({prog}))",
            y_expr=mid_y,
            width=width,
            height=height,
        )
    if mode == "pan_down":
        return _pan_motion_vf(
            pan_zoom=pan_zoom,
            x_expr=mid_x,
            y_expr=f"({max_y})*({prog})",
            width=width,
            height=height,
        )
    if mode == "pan_up":
        return _pan_motion_vf(
            pan_zoom=pan_zoom,
            x_expr=mid_x,
            y_expr=f"({max_y})*(1-({prog}))",
            width=width,
            height=height,
        )
    if mode == "pan_diag_dr":
        return _pan_motion_vf(
            pan_zoom=pan_zoom,
            x_expr=f"({max_x})*({prog})",
            y_expr=f"({max_y})*({prog})",
            width=width,
            height=height,
        )
    # pan_diag_ul
    return _pan_motion_vf(
        pan_zoom=pan_zoom,
        x_expr=f"({max_x})*(1-({prog}))",
        y_expr=f"({max_y})*(1-({prog}))",
        width=width,
        height=height,
    )


def _resolve_clip_canvas(
    width: int | None,
    height: int | None,
) -> tuple[int, int]:
    settings = get_settings()
    w = width if width is not None else settings.video_width
    h = height if height is not None else settings.video_height
    return _even(w), _even(h)


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
            *_still_image_input_args(image_path),
            *_still_image_input_args(overlay_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-t",
            str(duration_sec),
            "-r",
            str(CLIP_FPS),
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
        *_still_image_input_args(image_path),
    ]
    for overlay_path, _, _ in overlay_windows:
        cmd.extend(_still_image_input_args(overlay_path))
    cmd.extend(
        [
            "-filter_complex",
            ";".join(parts),
            "-map",
            "[out]",
            "-t",
            str(duration_sec),
            "-r",
            str(CLIP_FPS),
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


def burn_ass_subtitles(
    video_path: Path,
    ass_path: Path,
    output_path: Path,
    *,
    fonts_dir: Path | None = None,
) -> Path:
    """对已有音视频烧 ASS 字幕：视频重编码，音频 copy。"""
    settings = get_settings()
    fonts_dir = fonts_dir if fonts_dir is not None else settings.font_path.parent
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ass_esc = escape_ffmpeg_filter_path(ass_path)
    fonts_esc = escape_ffmpeg_filter_path(fonts_dir)
    vf = f"subtitles={ass_esc}:fontsdir={fonts_esc},format={_PIX_FMT}"
    run_ffmpeg(
        [
            *ffmpeg_cmd_start(hwaccel=False),
            "-i",
            str(video_path),
            "-vf",
            vf,
            *libx264_encode_args(subtitle=True, force_cpu=True),
            "-c:a",
            "copy",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            str(output_path),
        ]
    )
    return output_path


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
        *_still_image_input_args(image_path),
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
        "-r",
        str(CLIP_FPS),
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
