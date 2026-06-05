"""单分镜字幕预览：只重建 segments/{N}.mp4，便于调样式。"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.repositories import segment_repo
from app.repositories.connection import connection
from app.services.media.subtitle_overlay import build_segment_clip, burn_subtitled_clip
from app.services.tts.tts_mgr import (
    cues_for_segment,
    load_subtitle_cues,
    subtitle_cues_path_for,
)


def rebuild_segment_subtitles(
    job_id: int,
    segment_index: int,
    *,
    sentence: int | None = None,
) -> Path:
    settings = get_settings()
    media_dir = settings.video_data_dir / str(job_id)
    clips_dir = media_dir / "segments"
    clips_dir.mkdir(parents=True, exist_ok=True)

    with connection() as conn:
        segments = segment_repo.list_segments(conn, job_id)

    seg = next((s for s in segments if s["segment_index"] == segment_index), None)
    if seg is None:
        raise ValueError(f"job {job_id} 无 segment {segment_index}")

    cues_path = subtitle_cues_path_for(media_dir / "audio")
    seg_cues = cues_for_segment(load_subtitle_cues(cues_path), segment_index)
    if not seg_cues:
        raise ValueError(f"segment {segment_index} 无字幕时间轴")

    if sentence is not None:
        if sentence < 0 or sentence >= len(seg_cues):
            raise ValueError(f"sentence 需在 0..{len(seg_cues) - 1}")
        text, duration = seg_cues[sentence]
        out_path = clips_dir / f"{segment_index}_test.mp4"
        burn_subtitled_clip(
            image_path=Path(seg["image_path"]),
            text=text,
            output_path=out_path,
            duration_sec=duration,
            motion_preset=settings.motion_preset,
        )
        return out_path

    out_path = clips_dir / f"{segment_index}.mp4"
    build_segment_clip(
        image_path=Path(seg["image_path"]),
        subtitle_cues=seg_cues,
        output_path=out_path,
        motion_preset=settings.motion_preset,
        work_dir=clips_dir,
        segment_index=segment_index,
    )
    return out_path
