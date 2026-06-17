"""分镜 stage 业务编排：出图（ImageProvider）→ 片段（ClipProvider）。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.services.media.media_mgr import SegmentClipsResult, build_segment_clips
from app.services.visual.visual_mgr import generate_segment_images

logger = logging.getLogger(__name__)

__all__ = ["SegmentProduceResult", "produce_segments"]


@dataclass
class SegmentProduceResult:
    image_paths: list[tuple[int, Path]]
    clips: SegmentClipsResult


def _existing_image_path(seg: dict, images_dir: Path) -> Path | None:
    if seg.get("image_path"):
        path = Path(seg["image_path"])
        if path.exists():
            return path
    fallback = images_dir / f"{seg['segment_index']}.png"
    if fallback.exists():
        return fallback
    return None


def produce_segments(
    *,
    segments: list[dict],
    media_dir: Path,
    audio_path: Path | None = None,
    only_segment_indices: set[int] | None = None,
) -> SegmentProduceResult:
    t0 = time.time()
    images_dir = media_dir / "images"
    path_by_id: dict[int, Path] = {}
    image_targets: list[dict] = []

    for seg in segments:
        index = seg["segment_index"]
        if only_segment_indices is not None and index not in only_segment_indices:
            existing = _existing_image_path(seg, images_dir)
            if existing is None:
                raise FileNotFoundError(
                    f"segment {index} 缺少 image_path，请全量重跑 segment"
                )
            path_by_id[seg["id"]] = existing
            continue

        if only_segment_indices is None:
            existing = _existing_image_path(seg, images_dir)
            if existing is not None:
                path_by_id[seg["id"]] = existing
                continue

        image_targets.append(seg)

    logger.info("produce_segments: %s images to generate, %s cached", len(image_targets), len(path_by_id))
    generated = generate_segment_images(image_targets, images_dir) if image_targets else []
    for seg_id, path in generated:
        path_by_id[seg_id] = path

    segments_with_images = [
        {**seg, "image_path": str(path_by_id[seg["id"]])} for seg in segments
    ]
    if audio_path is not None:
        logger.info("produce_segments: building clips (audio available)...")
        clips = build_segment_clips(
            media_dir=media_dir,
            segments=segments_with_images,
            audio_path=audio_path,
            only_segment_indices=only_segment_indices,
        )
    else:
        logger.info("produce_segments: no audio, skipping clips")
        clips = SegmentClipsResult(segment_clip_paths=[])
    elapsed = time.time() - t0
    logger.info("produce_segments: done in %.1fs (images=%s, clips=%s)", elapsed, len(generated), len(clips.segment_clip_paths))
    return SegmentProduceResult(image_paths=generated, clips=clips)
