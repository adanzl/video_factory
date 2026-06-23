"""分镜 stage 业务编排：出图（ImageProvider）→ 片段（ClipProvider）。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.services.media.media_mgr import SegmentClipsResult, media_mgr
from app.services.visual.visual_mgr import visual_mgr

logger = logging.getLogger(__name__)

__all__ = ["SegmentMgr", "SegmentProduceResult", "segment_mgr"]


@dataclass
class SegmentProduceResult:
    image_paths: list[tuple[int, Path]]
    clips: SegmentClipsResult


class SegmentMgr:
    """分镜生产管理器。"""

    @staticmethod
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
        self,
        *,
        segments: list[dict],
        media_dir: Path,
        audio_path: Path | None = None,
        only_segment_indices: set[int] | None = None,
        scope: str = "all",
    ) -> SegmentProduceResult:
        if scope not in {"all", "images", "clips"}:
            raise ValueError(f"invalid segment scope: {scope}")

        t0 = time.time()
        images_dir = media_dir / "images"
        path_by_id: dict[int, Path] = {}
        image_targets: list[dict] = []

        if scope == "clips":
            for seg in segments:
                index = seg["segment_index"]
                if only_segment_indices is not None and index not in only_segment_indices:
                    existing = self._existing_image_path(seg, images_dir)
                    if existing is None:
                        raise FileNotFoundError(
                            f"segment {index} 缺少 image_path，请先执行 segment/images"
                        )
                    path_by_id[seg["id"]] = existing
                    continue
                existing = self._existing_image_path(seg, images_dir)
                if existing is None:
                    raise FileNotFoundError(
                        f"segment {index} 缺少 image_path，请先执行 segment/images"
                    )
                path_by_id[seg["id"]] = existing
        else:
            for seg in segments:
                index = seg["segment_index"]
                if only_segment_indices is not None and index not in only_segment_indices:
                    existing = self._existing_image_path(seg, images_dir)
                    if existing is None:
                        # 部分重跑静图时，未选中但尚未出图的段落自动补全，避免阻断首次出图
                        image_targets.append(seg)
                        continue
                    path_by_id[seg["id"]] = existing
                    continue

                if only_segment_indices is None and scope == "all":
                    existing = self._existing_image_path(seg, images_dir)
                    if existing is not None:
                        path_by_id[seg["id"]] = existing
                        continue

                image_targets.append(seg)

        logger.info(
            "produce_segments: scope=%s, %s images to generate, %s cached",
            scope,
            len(image_targets),
            len(path_by_id),
        )
        generated = (
            visual_mgr.generate_segment_images(image_targets, images_dir)
            if image_targets
            else []
        )
        for seg_id, path in generated:
            path_by_id[seg_id] = path

        segments_with_images = [
            {**seg, "image_path": str(path_by_id[seg["id"]])} for seg in segments
        ]
        if scope == "images" or audio_path is None:
            if scope != "images" and audio_path is None:
                logger.info("produce_segments: no audio, skipping clips")
            else:
                logger.info("produce_segments: images only, skipping clips")
            clips = SegmentClipsResult(segment_clip_paths=[])
        else:
            clip_targets = (
                len(only_segment_indices)
                if only_segment_indices is not None
                else len(segments)
            )
            logger.info(
                "produce_segments: building clips (audio available, targets=%s)...",
                clip_targets,
            )
            clips = media_mgr.build_segment_clips(
                media_dir=media_dir,
                segments=segments_with_images,
                audio_path=audio_path,
                only_segment_indices=only_segment_indices,
            )
        elapsed = time.time() - t0
        logger.info(
            "produce_segments: done in %.1fs (images=%s, clips=%s)",
            elapsed,
            len(generated),
            len(clips.segment_clip_paths),
        )
        return SegmentProduceResult(image_paths=generated, clips=clips)


segment_mgr = SegmentMgr()
