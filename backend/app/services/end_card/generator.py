"""动态片尾：按配音时间轴驱动头像轻动 + 三连弹出 + 淡入。"""

from __future__ import annotations

import json
import logging
import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from app.config import get_settings
from app.services.media.ffmpeg_utils import (
    OUTPUT_AUDIO_SAMPLE_RATE,
    mux_video_audio,
    probe_duration,
    sequence_to_video,
)
from app.services.render.text_render import load_cjk_font

logger = logging.getLogger(__name__)

_FPS = 25
_FADE_IN_SEC = 0.40
_CHAR_ENTER_SEC = 0.45
_ICON_STAGGER_SEC = 0.16
_ICON_ENTER_SEC = 0.28
# 每人开口后脉冲次数（放大缩小一轮算 1 次），满次停住
_SPEAK_PULSE_CYCLES = 3
_SPEAK_PULSE_PERIOD = 0.38
_SPEAK_PULSE_AMP = 0.05
_BG = (8, 8, 12, 255)
_LABEL_FILL = (210, 190, 200, 255)

_ICON_FILES = {"like": "icon_4.png", "coin": "icon_3.png", "save": "icon_1.png"}
_ICON_LABELS = {"like": "点赞", "coin": "投币", "save": "收藏"}
_ICON_ORDER = ("like", "coin", "save")


@dataclass(frozen=True)
class _SpeechSeg:
    speaker: str
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class _Timeline:
    duration: float
    segments: tuple[_SpeechSeg, ...]

    def active_speaker(self, t: float) -> str | None:
        for seg in self.segments:
            if seg.start <= t < seg.end:
                return seg.speaker
        return None

    def segment_for(self, speaker: str) -> _SpeechSeg | None:
        for seg in self.segments:
            if seg.speaker == speaker:
                return seg
        return None


@dataclass(frozen=True)
class _EndLayout:
    char_zone_ratio: float
    can_top_ratio: float
    char_gap_px: int
    ico_h_ratio: float
    ico_gap_ratio: float
    label_font_ratio: float
    ico_y_nudge_ratio: float


_LANDSCAPE = _EndLayout(
    char_zone_ratio=0.65,
    can_top_ratio=0.15,
    char_gap_px=4,
    ico_h_ratio=0.122,
    ico_gap_ratio=0.053,
    label_font_ratio=0.033,
    ico_y_nudge_ratio=0.04,
)

_PORTRAIT = _EndLayout(
    char_zone_ratio=0.58,
    can_top_ratio=0.12,
    char_gap_px=4,
    ico_h_ratio=0.09,
    ico_gap_ratio=0.045,
    label_font_ratio=0.028,
    ico_y_nudge_ratio=0.02,
)


def _layout_for(width: int, height: int) -> _EndLayout:
    return _LANDSCAPE if width >= height else _PORTRAIT


def _ease_out_back(t: float, s: float = 1.4) -> float:
    t = max(0.0, min(1.0, t))
    t -= 1.0
    return t * t * ((s + 1.0) * t + s) + 1.0


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _with_opacity(img: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return img
    if opacity <= 0.001:
        out = img.copy()
        out.putalpha(0)
        return out
    out = img.copy()
    alpha = out.split()[3].point(lambda a: int(a * opacity))
    out.putalpha(alpha)
    return out


def _crop_content(img: Image.Image) -> Image.Image:
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox is None:
        return img
    return img.crop(bbox)


def _scale_around(
    img: Image.Image,
    scale: float,
) -> tuple[Image.Image, int, int]:
    """缩放并返回 (图, 居中缩放相对原尺寸的 dx, dy)。"""
    if abs(scale - 1.0) < 0.001:
        return img, 0, 0
    w, h = img.size
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    scaled = img.resize((nw, nh), Image.Resampling.LANCZOS)
    return scaled, (w - nw) // 2, (h - nh) // 2


def _timeline_path_for(audio_path: Path) -> Path:
    return audio_path.with_name(f"{audio_path.stem}_timeline.json")


def _parse_timeline(data: dict, *, audio_dur: float) -> _Timeline:
    segs_raw = data.get("segments") or []
    segs: list[_SpeechSeg] = []
    for item in segs_raw:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip()
        if not speaker:
            continue
        start = float(item.get("start", 0.0))
        end = float(item.get("end", start))
        if end <= start:
            continue
        segs.append(
            _SpeechSeg(
                speaker=speaker,
                text=str(item.get("text") or ""),
                start=start,
                end=end,
            )
        )
    duration = float(data.get("duration") or audio_dur)
    if not segs:
        raise ValueError("timeline segments empty")
    # 音频与 JSON 总长轻微偏差时按比例对齐
    if duration > 0 and audio_dur > 0 and abs(duration - audio_dur) > 0.05:
        scale = audio_dur / duration
        segs = [
            _SpeechSeg(
                speaker=s.speaker,
                text=s.text,
                start=s.start * scale,
                end=s.end * scale,
            )
            for s in segs
        ]
        duration = audio_dur
    return _Timeline(duration=duration, segments=tuple(segs))


def _infer_timeline_from_silence(audio_path: Path, audio_dur: float) -> _Timeline:
    """无 JSON 时：用句间静音把两段对白切开，默认 昭昭→灿灿。"""
    from app.services.tts.audio_analysis import analyze_silence

    stats = analyze_silence(audio_path, noise_db=-40.0, min_duration_sec=0.12)
    # 取中间的静音缝（排除首尾静音）作为换人点
    split = audio_dur * 0.48
    for start, dur in stats.gaps:
        mid = start + dur / 2.0
        if 0.4 < mid < audio_dur - 0.4:
            split = mid
            break

    speakers = ("昭昭", "灿灿")
    texts = ("他们为什么不关注啊？", "没准是忘了……")
    segs = (
        _SpeechSeg(speakers[0], texts[0], 0.0, split),
        _SpeechSeg(speakers[1], texts[1], split, audio_dur),
    )
    logger.info(
        "end_card timeline inferred from silence: split=%.3fs gaps=%s",
        split,
        stats.gaps,
    )
    return _Timeline(duration=audio_dur, segments=segs)


def load_end_timeline(audio_path: Path, audio_dur: float) -> _Timeline:
    """优先读旁路 JSON；缺失则静音推断。"""
    path = _timeline_path_for(audio_path)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            try:
                timeline = _parse_timeline(data, audio_dur=audio_dur)
                logger.info(
                    "end_card timeline loaded: %s (%d segs)",
                    path.name,
                    len(timeline.segments),
                )
                return timeline
            except (TypeError, ValueError, KeyError) as exc:
                logger.warning("end_card timeline invalid %s: %s", path, exc)
    return _infer_timeline_from_silence(audio_path, audio_dur)


def _build_layers(width: int, height: int) -> dict:
    settings = get_settings()
    layout = _layout_for(width, height)
    crayon = settings.res_dir / "host" / "crayon"
    ico_dir = settings.res_dir / "ico"

    zhao_path = crayon / "zhao_circle.png"
    can_path = crayon / "can_circle.png"
    if not zhao_path.exists():
        raise FileNotFoundError(f"片尾昭昭素材不存在: {zhao_path}")
    if not can_path.exists():
        raise FileNotFoundError(f"片尾灿灿素材不存在: {can_path}")

    zhao = _crop_content(Image.open(zhao_path).convert("RGBA"))
    can = _crop_content(Image.open(can_path).convert("RGBA"))

    char_zone = int(height * layout.char_zone_ratio)
    can_top = int(height * layout.can_top_ratio)
    can_h = max(1, char_zone - can_top)
    can_s = can.resize((can_h, can_h), Image.Resampling.LANCZOS)
    zhao_h = max(1, int(can_h * 0.9))
    zhao_s = zhao.resize((zhao_h, zhao_h), Image.Resampling.LANCZOS)

    total_w = zhao_s.width + can_s.width + layout.char_gap_px
    start_x = (width - total_w) // 2
    zhao_pos = (start_x, can_top + (can_h - zhao_h))
    can_pos = (start_x + zhao_s.width + layout.char_gap_px, can_top)

    ico_h_target = max(48, int(height * layout.ico_h_ratio))
    icons: dict[str, Image.Image] = {}
    for name in _ICON_ORDER:
        path = ico_dir / _ICON_FILES[name]
        if not path.exists():
            raise FileNotFoundError(f"片尾图标不存在: {path}")
        ico = Image.open(path).convert("RGBA")
        tw = max(1, int(ico_h_target * ico.width / ico.height))
        icons[name] = ico.resize((tw, ico_h_target), Image.Resampling.LANCZOS)

    font_size = max(18, int(height * layout.label_font_ratio))
    font = load_cjk_font(font_size)

    ico_gap = max(24, int(width * layout.ico_gap_ratio))
    total_iw = sum(icons[n].width for n in _ICON_ORDER) + ico_gap * (
        len(_ICON_ORDER) - 1
    )
    ico_start_x = (width - total_iw) // 2
    btn_zone = height - char_zone
    ico_y = (
        char_zone
        + (btn_zone - ico_h_target) // 2
        - int(height * layout.ico_y_nudge_ratio)
    )

    label_gap = max(6, int(height * 0.011))
    icon_slots: list[dict] = []
    curr_x = ico_start_x
    draw_probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for name in _ICON_ORDER:
        ico = icons[name]
        label = _ICON_LABELS[name]
        bbox = draw_probe.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        label_img = Image.new("RGBA", (max(tw + 4, ico.width), th + 4), (0, 0, 0, 0))
        ImageDraw.Draw(label_img).text(
            ((label_img.width - tw) // 2, 0),
            label,
            font=font,
            fill=_LABEL_FILL,
        )
        icon_slots.append(
            {
                "name": name,
                "icon": ico,
                "label": label_img,
                "x": curr_x,
                "y": ico_y,
                "label_x": curr_x + (ico.width - label_img.width) // 2,
                "label_y": ico_y + ico_h_target + label_gap,
            }
        )
        curr_x += ico.width + ico_gap

    return {
        "width": width,
        "height": height,
        "zhao": zhao_s,
        "can": can_s,
        "zhao_pos": zhao_pos,
        "can_pos": can_pos,
        "icon_slots": icon_slots,
    }


def _speak_pulse(local_t: float, *, talking: bool) -> float:
    """开口后放大缩小若干次再停；未开口或已满次 → 1.0。"""
    if not talking or local_t < 0:
        return 1.0
    total = _SPEAK_PULSE_CYCLES * _SPEAK_PULSE_PERIOD
    if local_t >= total:
        return 1.0
    return 1.0 + _SPEAK_PULSE_AMP * math.sin(
        2.0 * math.pi * local_t / _SPEAK_PULSE_PERIOD
    )


def _compose_frame(layers: dict, t: float, timeline: _Timeline) -> Image.Image:
    width = layers["width"]
    height = layers["height"]
    frame = Image.new("RGBA", (width, height), _BG)

    fade = _ease_out_cubic(t / _FADE_IN_SEC) if t < _FADE_IN_SEC else 1.0
    char_enter = _ease_out_back(min(t / _CHAR_ENTER_SEC, 1.0))

    speaker = timeline.active_speaker(t)
    zhao_seg = timeline.segment_for("昭昭")
    can_seg = timeline.segment_for("灿灿")

    zhao_local = t - (zhao_seg.start if zhao_seg else 0.0)
    can_local = t - (can_seg.start if can_seg else 0.0)

    zhao_pulse = _speak_pulse(zhao_local, talking=speaker == "昭昭")
    can_pulse = _speak_pulse(can_local, talking=speaker == "灿灿")
    # 灿灿脉冲期内轻微上下晃，满次后停
    can_bob = 0
    if speaker == "灿灿" and 0 <= can_local < _SPEAK_PULSE_CYCLES * _SPEAK_PULSE_PERIOD:
        can_bob = int(5 * math.sin(2.0 * math.pi * can_local / _SPEAK_PULSE_PERIOD))

    slide = int((1.0 - char_enter) * (height * 0.12))
    base_scale = 0.82 + 0.18 * char_enter

    zhao_img, zdx, zdy = _scale_around(layers["zhao"], base_scale * zhao_pulse)
    zx, zy = layers["zhao_pos"]
    frame.alpha_composite(
        _with_opacity(zhao_img, fade * char_enter),
        (zx + zdx, zy + zdy + slide),
    )

    can_img, cdx, cdy = _scale_around(layers["can"], base_scale * can_pulse)
    cx, cy = layers["can_pos"]
    frame.alpha_composite(
        _with_opacity(can_img, fade * char_enter),
        (cx + cdx, cy + cdy + slide + can_bob),
    )

    # 三连：灿灿开口时弹出（对白答「忘了关注」→ CTA）
    icon_start = can_seg.start if can_seg else timeline.duration * 0.5
    for i, slot in enumerate(layers["icon_slots"]):
        local_t = t - (icon_start + i * _ICON_STAGGER_SEC)
        if local_t < 0:
            continue
        pop = _ease_out_back(min(local_t / _ICON_ENTER_SEC, 1.0))
        breathe = 1.0 + 0.04 * math.sin(max(0.0, local_t - _ICON_ENTER_SEC) * 5.0)
        scale = (0.55 + 0.45 * pop) * breathe
        opacity = fade * min(1.0, local_t / 0.12)

        ico, idx, idy = _scale_around(slot["icon"], scale)
        iy_slide = int((1.0 - pop) * 28)
        frame.alpha_composite(
            _with_opacity(ico, opacity),
            (slot["x"] + idx, slot["y"] + idy + iy_slide),
        )
        frame.alpha_composite(
            _with_opacity(slot["label"], opacity * pop),
            (slot["label_x"], slot["label_y"] + iy_slide),
        )

    return frame


def _render_frames(
    layers: dict,
    timeline: _Timeline,
    frames_dir: Path,
    *,
    duration: float,
    fps: int = _FPS,
) -> int:
    frames_dir.mkdir(parents=True, exist_ok=True)
    total = max(int(duration * fps), 1)
    for i in range(total):
        t = i / fps
        frame = _compose_frame(layers, t, timeline)
        frame.convert("RGB").save(frames_dir / f"frame_{i:04d}.png", compress_level=1)
        time.sleep(0.001)
    return total


def generate_end_card(
    output_path: Path,
    *,
    width: int | None = None,
    height: int | None = None,
    work_dir: Path | None = None,
) -> Path:
    """生成动态片尾 MP4（配音时间轴驱动动效）。

    只复用已有 ``end_daily.mp3``（及旁路 timeline JSON）mux 进成片，
    **不会**调用 TTS、不会改写/重新生成音频文件。
    音频请用 ``scripts/gen_end_audio.py`` 单独生成。
    """
    settings = get_settings()
    video_w = width if width is not None else settings.video_width
    video_h = height if height is not None else settings.video_height

    audio_path = settings.end_card_audio_path
    if not audio_path.exists():
        raise FileNotFoundError(
            f"片尾音频不存在: {audio_path}，请先运行 scripts/gen_end_audio.py"
        )

    # 只读复用预置配音；时长与时间轴均来自现成文件
    audio_dur = probe_duration(audio_path)
    timeline = load_end_timeline(audio_path, audio_dur)
    layers = _build_layers(video_w, video_h)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    work = work_dir or output_path.parent / "end_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    frames_dir = work / "frames"
    frame_count = _render_frames(
        layers, timeline, frames_dir, duration=audio_dur, fps=_FPS
    )

    silent_video = work / "video.mp4"
    sequence_to_video(
        frames_dir,
        silent_video,
        fps=_FPS,
        frame_count=frame_count,
        force_cpu=True,
    )

    mux_video_audio(
        silent_video,
        audio_path,
        output_path,
        sample_rate=OUTPUT_AUDIO_SAMPLE_RATE,
        channels=1,
    )
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"片尾 MP4 未生成: {output_path}")

    shutil.rmtree(work, ignore_errors=True)
    return output_path
