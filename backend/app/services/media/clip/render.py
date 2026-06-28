"""分镜图 → 视频 clip：Ken Burns 动效 + 字幕 overlay 合成。"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

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
    """居中缩放坐标。"""
    return "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"


def _motion_vf(
    duration_sec: float,
    *,
    preset: str,
    segment_index: int,
    width: int,
    height: int,
) -> str:
    """已废弃——改为 PIL 逐帧渲染。返回 scale+pad（无动效）用于字幕 overlay 基底。"""
    return _scale_pad_vf(width=width, height=height)


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
    """Ken Burns + 单张字幕 overlay，numpy 管道编码。"""
    canvas_w, canvas_h = _resolve_clip_canvas(width, height)
    overlay_img = np.array(Image.open(overlay_path).convert("RGBA"))
    fps = CLIP_FPS
    total_frames = max(int(duration_sec * fps), 1)
    base_gen = _render_ken_burns_frames_np(
        image_path, total_sec=duration_sec,
        preset=preset, segment_index=segment_index,
        width=canvas_w, height=canvas_h,
    )

    def composite_gen():
        for frame_data in base_gen:
            frame = np.frombuffer(frame_data, dtype=np.uint8).reshape((canvas_h, canvas_w, 3))
            rgba = np.dstack([frame, np.full((canvas_h, canvas_w), 255, dtype=np.uint8)])
            alpha = overlay_img[:, :, 3:4] / 255.0
            blended = (rgba * (1 - alpha) + overlay_img * alpha).astype(np.uint8)[:, :, :3]
            yield blended.tobytes()

    return _encode_frames(
        composite_gen(), output_path,
        total_frames=total_frames, fps=fps,
        width=canvas_w, height=canvas_h,
    )


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
    """连续 Ken Burns + 多段字幕按时间轴切换，numpy 管道编码。"""
    canvas_w, canvas_h = _resolve_clip_canvas(width, height)
    fps = CLIP_FPS
    total_frames = max(int(duration_sec * fps), 1)
    base_gen = _render_ken_burns_frames_np(
        image_path, total_sec=duration_sec,
        preset=preset, segment_index=segment_index,
        width=canvas_w, height=canvas_h,
    )

    if not overlay_windows:
        return _encode_frames(
            base_gen, output_path,
            total_frames=total_frames, fps=fps,
            width=canvas_w, height=canvas_h,
        )

    overlays = [(np.array(Image.open(p).convert("RGBA")), s, e) for p, s, e in overlay_windows]

    def composite_gen():
        for fn, frame_data in enumerate(base_gen):
            t = fn / fps
            frame = np.frombuffer(frame_data, dtype=np.uint8).reshape((canvas_h, canvas_w, 3))
            rgba = np.dstack([frame, np.full((canvas_h, canvas_w), 255, dtype=np.uint8)])
            for ov_img, start, end in overlays:
                if start <= t < end:
                    alpha = ov_img[:, :, 3:4] / 255.0
                    blended = (rgba * (1 - alpha) + ov_img * alpha).astype(np.uint8)[:, :, :3]
                    yield blended.tobytes()
                    break
            else:
                yield frame_data

    return _encode_frames(
        composite_gen(), output_path,
        total_frames=total_frames, fps=fps,
        width=canvas_w, height=canvas_h,
    )


def _image_to_clip_fallback(
    image_path: Path,
    output_path: Path,
    duration_sec: float,
    *,
    preset: str = "ken_burns_slow",
    segment_index: int = 0,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    canvas_w, canvas_h = _resolve_clip_canvas(width, height)
    fps = CLIP_FPS
    total_frames = max(int(duration_sec * fps), 1)
    return _encode_frames(
        _render_ken_burns_frames_np(
            image_path, total_sec=duration_sec,
            preset=preset, segment_index=segment_index,
            width=canvas_w, height=canvas_h,
        ),
        output_path,
        total_frames=total_frames, fps=fps,
        width=canvas_w, height=canvas_h,
    )


def _encode_frames(
    frame_gen,
    output_path: Path,
    *,
    total_frames: int,
    fps: int,
    width: int,
    height: int,
) -> Path:
    """将帧生成器的 RGB bytes 管道传给 FFmpeg 编码。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-f", "rawvideo",
        "-pixel_format", "rgb24",
        "-video_size", f"{width}x{height}",
        "-framerate", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-crf", str(get_settings().ffmpeg_crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    total_bytes = 0
    for i, frame_data in enumerate(frame_gen):
        if frame_data is None:
            break
        proc.stdin.write(frame_data)
        total_bytes += len(frame_data)
    proc.stdin.close()
    _, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg encode failed: {stderr[-500:]}")
    return output_path


def _render_ken_burns_frames_np(
    image_path: Path,
    *,
    total_sec: float,
    preset: str,
    segment_index: int,
    width: int,
    height: int,
):
    """Ken Burns 帧生成器（numpy array），逐帧 yield RGB bytes。"""
    fps = CLIP_FPS
    total_frames = max(int(total_sec * fps), 1)
    zoom_max = _motion_zoom_max(preset)
    delta = zoom_max - 1.0
    motion_frames = max(int(total_frames * _MOTION_FINISH_RATIO), 1)
    pw = int(width * 1.20)
    ph = int(height * 1.20)

    src = Image.open(image_path).convert("RGB")
    prepped = np.array(src.resize((pw, ph), Image.LANCZOS))

    mode = segment_index % 4
    for fn in range(total_frames):
        progress = min(1.0, 0.5 - 0.5 * math.cos(math.pi * fn / motion_frames)) if motion_frames > 0 else 1.0
        if mode == 0:
            zoom = 1.0 + delta * progress
            crop_w = int(width / zoom)
            crop_h = int(height / zoom)
            cx = (pw - crop_w) // 2
            cy = (ph - crop_h) // 2
            chunk = prepped[cy:cy + crop_h, cx:cx + crop_w]
            frame = Image.fromarray(chunk).resize((width, height), Image.LANCZOS)
            yield np.array(frame).tobytes()
        elif mode == 1:
            zoom = zoom_max - delta * progress
            crop_w = max(1, int(width / zoom))
            crop_h = max(1, int(height / zoom))
            cx = (pw - crop_w) // 2
            cy = (ph - crop_h) // 2
            chunk = prepped[cy:cy + crop_h, cx:cx + crop_w]
            frame = Image.fromarray(chunk).resize((width, height), Image.LANCZOS)
            yield np.array(frame).tobytes()
        elif mode == 2:
            pan_x = int((pw - width) * progress)
            cy = (ph - height) // 2
            raw = prepped[cy:cy + height, pan_x:pan_x + width]
            yield raw.tobytes()
        else:
            pan_x = int((pw - width) * (1.0 - progress))
            cy = (ph - height) // 2
            raw = prepped[cy:cy + height, pan_x:pan_x + width]
            yield raw.tobytes()
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
