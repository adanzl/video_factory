"""片尾视频生成：使用 end.png 作为背景图片，end_daily.mp3 作为声音，合成 MP4。"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.config import get_settings
from app.services.media.ffmpeg_utils import (
    image_to_video,
    mux_video_audio,
    OUTPUT_AUDIO_SAMPLE_RATE,
    probe_duration,
)


def generate_end_card(
    output_path: Path,
    *,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    """生成带背景音乐（end_daily.mp3）的片尾 MP4。

    Args:
        output_path: 输出 MP4 路径
        width: 视频宽度（缺省使用全局 VIDEO 配置）
        height: 视频高度（缺省使用全局 VIDEO 配置）
    """
    settings = get_settings()
    video_w = width if width is not None else settings.video_width
    video_h = height if height is not None else settings.video_height

    bg_path = settings.end_card_bg_path
    if not bg_path.exists():
        raise FileNotFoundError(f"片尾背景图片不存在: {bg_path}")
    audio_path = settings.end_card_audio_path
    if not audio_path.exists():
        raise FileNotFoundError(f"片尾音频不存在: {audio_path}")

    audio_dur = probe_duration(audio_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = output_path.parent / "end_work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # 将背景图片复制到工作目录，避免重复缩放
    bg_copy = work_dir / "bg.png"
    shutil.copy2(bg_path, bg_copy)

    # 静态图转视频（无音轨）
    silent_video = work_dir / "video.mp4"
    image_to_video(
        bg_copy,
        silent_video,
        duration=audio_dur,
        width=video_w,
        height=video_h,
    )

    # 合并音频
    mux_video_audio(
        silent_video,
        audio_path,
        output_path,
        sample_rate=OUTPUT_AUDIO_SAMPLE_RATE,
        channels=1,
    )

    # 清理临时文件
    shutil.rmtree(work_dir, ignore_errors=True)
    return output_path
