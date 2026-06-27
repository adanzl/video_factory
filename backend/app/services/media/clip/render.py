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
_MOTION_FINISH_RATIO = 0.85  # 动效在前 85% 时长内完成，之后保持
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


def _even_dim(value: int) -> int:
    """yuv420p / zoompan 要求宽高为偶数。"""
    return value if value % 2 == 0 else value + 1


def _prep_filter(*, headroom: float, width: int, height: int) -> str:
    """放大画布，给平移/缩放留出余量。lanczos 插值减少 zoompan 亚像素抖动。"""
    pw = _even_dim(int(width * headroom))
    ph = _even_dim(int(height * headroom))
    return (
        f"scale={pw}:{ph}:force_original_aspect_ratio=increase:flags=lanczos,"
        "setsar=1"
    )


def _motion_zoom_max(preset: str) -> float:
    if preset == "ken_burns_slow":
        return 1.08
    return 1.12


def _center_xy() -> tuple[str, str]:
    """zoompan 取整坐标，避免亚像素平移抖动。"""
    return "floor(iw/2-(iw/zoom/2))", "floor(ih/2-(ih/zoom/2))"


def _motion_vf(
    duration_sec: float,
    *,
    preset: str,
    segment_index: int,
    width: int,
    height: int,
) -> str:
    """连续 Ken Burns：4 种动效轮换，放大权重最高。"""
    frames = max(int(duration_sec * CLIP_FPS), 1)
    zoom_max = _motion_zoom_max(preset)
    delta = zoom_max - 1.0
    progress = _motion_progress(frames)
    x_center, y_center = _center_xy()

    mode = segment_index % 4
    if mode == 0:
        # 居中放大
        headroom = zoom_max + 0.04
        z_expr = f"1+{delta:.4f}*({progress})"
        x_expr, y_expr = x_center, y_center
    elif mode == 1:
        # 居中缩小
        headroom = zoom_max + 0.04
        z_expr = f"{zoom_max:.4f}-{delta:.4f}*({progress})"
        x_expr, y_expr = x_center, y_center
    elif mode == 2:
        # 缓慢右移（幅度减小）
        pan_zoom = max(zoom_max, 1.06)
        headroom = max(pan_zoom + 0.06, 1.16)
        z_expr = f"{pan_zoom:.4f}"
        x_expr = f"floor((iw-iw/zoom)*({progress}))"
        y_expr = y_center
    else:
        # 缓慢左移
        pan_zoom = max(zoom_max, 1.06)
        headroom = max(pan_zoom + 0.06, 1.16)
        z_expr = f"{pan_zoom:.4f}"
        x_expr = f"floor((iw-iw/zoom)*(1-{progress}))"
        y_expr = y_center

    prep = _prep_filter(headroom=headroom, width=width, height=height)
    return (
        f"{prep},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={frames}:s={width}x{height}:fps={CLIP_FPS}{_pix_fmt_filter_suffix()}"
    )


def _resolve_clip_canvas(
    width: int | None,
    height: int | None,
) -> tuple[int, int]:
    settings = get_settings()
    canvas_w = width if width is not None else settings.video_width
    canvas_h = height if height is not None else settings.video_height
    return _even_dim(canvas_w), _even_dim(canvas_h)


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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas_w, canvas_h = _resolve_clip_canvas(width, height)
    vf = _motion_vf(
        duration_sec,
        preset=preset,
        segment_index=segment_index,
        width=canvas_w,
        height=canvas_h,
    )
    run_ffmpeg(
        [
            *ffmpeg_cmd_start(hwaccel=False),
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-vf",
            vf_for_encode(vf, force_cpu=True),
            "-t",
            str(duration_sec),
            *libx264_encode_args(force_cpu=True),
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
            "lanczos+accurate_rnd+full_chroma_int",  # cSpell: disable-line
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


def _temporal_smooth_vf() -> str:
    """轻量时域混合，减轻 I2V 帧间闪烁。"""
    return f"fps={CLIP_FPS},format={_PIX_FMT},tmix=frames=3:weights='1 2 1'"


def _fit_vf_chain(
    video_dur: float,
    duration_sec: float,
    *,
    width: int,
    height: int,
    temporal_smooth: bool = False,
) -> str:
    scale = _scale_pad_vf(width=width, height=height)
    if temporal_smooth:
        scale = f"{scale},{_temporal_smooth_vf()}"
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
    vf = f"{base_vf},subtitles={ass_esc}:fontsdir={fonts_esc},format={_PIX_FMT}"
    # libass 仅 CPU；长片经 hwupload→VAAPI 在 AMD 上易触发 context lost，此处强制软编。
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
    video_path: Path,
    output_path: Path,
    duration_sec: float,
    *,
    width: int | None = None,
    height: int | None = None,
    temporal_smooth: bool = False,
    stream_loop: int = 0,
) -> Path:
    """缩放至成片尺寸，并按目标时长裁切或末帧定格。"""
    settings = get_settings()
    canvas_w, canvas_h = _resolve_clip_canvas(width, height)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    video_dur = probe_duration(video_path)
    looped_dur = video_dur * (stream_loop + 1) if stream_loop > 0 else video_dur
    vf = _fit_vf_chain(
        looped_dur,
        duration_sec,
        width=canvas_w,
        height=canvas_h,
        temporal_smooth=temporal_smooth,
    )

    cmd = [
        *ffmpeg_cmd_start(hwaccel=False if temporal_smooth else None),
        *(
            ["-stream_loop", str(stream_loop)]
            if stream_loop > 0
            else []
        ),
        "-i",
        str(video_path),
        "-vf",
        vf_for_encode(vf, force_cpu=temporal_smooth),
        "-t",
        f"{duration_sec:.3f}",
        *libx264_encode_args(force_cpu=temporal_smooth),
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
    force_cpu: bool = False,
) -> Path:
    """已有视频 + 多段字幕按时间轴切换，单次编码。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas_w, canvas_h = _resolve_clip_canvas(width, height)
    if not overlay_windows:
        fit_video_duration(
            video_path,
            output_path,
            duration_sec,
            width=canvas_w,
            height=canvas_h,
        )
        return output_path

    video_w, video_h = canvas_w, canvas_h
    parts = [
        f"[0:v]{_scale_pad_vf(width=canvas_w, height=canvas_h)},format={_PIX_FMT}[bg]"
    ]
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

    parts = finalize_filter_complex(parts, force_cpu=force_cpu)
    cmd = [
        *ffmpeg_cmd_start(hwaccel=False if force_cpu else None),
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
            *libx264_encode_args(subtitle=True, force_cpu=force_cpu),
            "-sws_flags",
            "lanczos+accurate_rnd+full_chroma_int",  # cSpell: disable-line
            str(output_path),
        ]
    )
    run_ffmpeg(cmd)
    return output_path
