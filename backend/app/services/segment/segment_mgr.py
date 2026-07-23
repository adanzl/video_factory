"""分镜 stage 业务编排：出图（ImageProvider）→ 片段（ClipProvider）。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.utils.job_cancel import job_cancel
from app.services.media.media_mgr import SegmentClipsResult, media_mgr
from app.services.tts.tts_mgr import tts_mgr
from app.services.segment.image.image_mgr import image_mgr
from app.utils.job_info import resolve_segment_image_size

logger = logging.getLogger(__name__)

__all__ = ["SegmentMgr", "SegmentProduceResult", "segment_mgr"]


@dataclass
class SegmentProduceResult:
    image_paths: list[tuple[int, Path]]
    clips: SegmentClipsResult


def _resolve_chat_ref_images() -> list[Path]:
    """解析 chat 流水线角色参考图路径。

    昭昭与灿灿参考图已合并为一张并排图（combined.png），
    避免分别发送多张参考图时模型混淆角色。
    """
    settings = get_settings()
    combined = settings.res_dir / "host" / "crayon" / "hosts.png"
    if combined.exists():
        return [combined]
    return [
        settings.res_dir / "host" / "crayon" / "zhao.png",
        settings.res_dir / "host" / "crayon" / "can.png",
    ]


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

    @staticmethod
    def _has_clip_timing(media_dir: Path) -> bool:
        cues_path = tts_mgr.subtitle_cues_path_for(media_dir / "audio")
        return cues_path.exists()

    @staticmethod
    def _existing_clip_path(seg: dict, clips_dir: Path) -> Path | None:
        """仅当 DB 仍有 clip_path 时才复用磁盘文件。

        TTS 重跑会清空 clip_path 但保留 mp4；此时不得因磁盘残留而 skip。
        """
        recorded = seg.get("clip_path")
        if not recorded:
            return None
        path = Path(recorded)
        if path.exists():
            return path
        fallback = clips_dir / f"{seg['segment_index']}.mp4"
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
        job: dict | None = None,
        on_image_done: Callable[[int, Path, float], None] | None = None,
        on_clip_done: Callable[[int, Path, float], None] | None = None,
    ) -> SegmentProduceResult:
        if scope not in {"all", "images", "clips"}:
            raise ValueError(f"invalid segment scope: {scope}")

        job_id = job.get("id") if job else None

        def _check_cancelled() -> None:
            if job_id is not None:
                job_cancel.raise_if_cancelled(job_id)

        _check_cancelled()

        t0 = time.time()
        images_dir = media_dir / "images"
        path_by_id: dict[int, Path] = {}
        image_targets: list[dict] = []

        if scope == "clips":
            for seg in segments:
                index = seg["segment_index"]
                if only_segment_indices is not None and index not in only_segment_indices:
                    existing = self._existing_image_path(seg, images_dir)
                    if existing is not None:
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
                    if existing is not None:
                        path_by_id[seg["id"]] = existing
                    continue

                if only_segment_indices is None and scope == "all":
                    existing = self._existing_image_path(seg, images_dir)
                    if existing is not None:
                        path_by_id[seg["id"]] = existing
                        continue

                image_targets.append(seg)

        if scope == "clips":
            clip_target_indices = (
                sorted(only_segment_indices)
                if only_segment_indices is not None
                else [seg["segment_index"] for seg in segments]
            )
            logger.info(
                "produce_segments: scope=clips, %s clips to generate, segments=%s",
                len(clip_target_indices),
                clip_target_indices,
            )
        elif image_targets:
            image_size = resolve_segment_image_size(job)
            logger.info(
                "produce_segments: scope=%s, %s images to generate, %s cached, size=%s",
                scope,
                len(image_targets),
                len(path_by_id),
                image_size,
            )
        generated = []
        if scope != "clips" and image_targets:
            _check_cancelled()
            from app.utils.job_info import content_style_from_job, resolve_image_provider

            image_size = resolve_segment_image_size(job)
            image_provider = resolve_image_provider(job)
            style = content_style_from_job(job) if job else None

            # chat 流水线传入角色参考图
            ref_images: list[Path] | None = None
            if job and job.get("pipeline") == "chat":
                ref_images = _resolve_chat_ref_images()
                logger.info(
                    "produce_segments: chat pipeline, ref_images=%s",
                    [p.name for p in ref_images],
                )

            generated = image_mgr.generate_segment_images(
                image_targets,
                images_dir,
                size=image_size,
                image_provider=image_provider,
                on_image_done=on_image_done,
                job_id=job_id,
                job=job,
                ref_images=ref_images,
                content_style=style,
            )
        for seg_id, path in generated:
            path_by_id[seg_id] = path

        segments_with_images = [
            {
                **seg,
                "image_path": str(path)
                if (path := path_by_id.get(seg["id"]))
                else seg.get("image_path"),
            }
            for seg in segments
        ]
        if scope == "images":
            logger.info("produce_segments: images only, skipping clips")
            clips = SegmentClipsResult(segment_clip_paths=[])
        elif scope == "all" and audio_path is None and not self._has_clip_timing(media_dir):
            logger.info(
                "produce_segments: no tts timing, skipping clips (run tts first or use segment/clips)"
            )
            clips = SegmentClipsResult(segment_clip_paths=[])
        else:
            _check_cancelled()

            # 收集已有 clip 的分镜（服务重启恢复时避免重新生成）
            clips_dir = media_dir / "segments"
            existing_clip_paths: list[tuple[int, Path]] = []
            if only_segment_indices is None and clips_dir.exists():
                remaining_segments: list[dict] = []
                for seg in segments_with_images:
                    existing = self._existing_clip_path(seg, clips_dir)
                    if existing is not None:
                        existing_clip_paths.append((seg["id"], existing))
                        logger.info(
                            "produce_segments: segment %s clip already exists, skipping",
                            seg["segment_index"],
                        )
                    else:
                        remaining_segments.append(seg)
                if existing_clip_paths:
                    logger.info(
                        "produce_segments: %s/%s clips already exist, "
                        "only %s need regeneration",
                        len(existing_clip_paths),
                        len(segments_with_images),
                        len(remaining_segments),
                    )
                segments_with_images = remaining_segments

            if not segments_with_images:
                logger.info("produce_segments: all clips already exist, skipping clip generation")
                clips = SegmentClipsResult(segment_clip_paths=existing_clip_paths)
            else:
                logger.info(
                    "produce_segments: building clips (targets=%s)...",
                    sorted(only_segment_indices) if only_segment_indices is not None else "all",
                )
                new_clips = media_mgr.build_segment_clips(
                    media_dir=media_dir,
                    segments=segments_with_images,
                    audio_path=audio_path,
                    only_segment_indices=only_segment_indices,
                    job=job,
                    on_clip_done=on_clip_done,
                )
                # 合并已有 clip（跳过生成的不在 new_clips 里）
                all_paths = list(new_clips.segment_clip_paths) + existing_clip_paths
                clips = SegmentClipsResult(segment_clip_paths=all_paths)
        elapsed = time.time() - t0
        logger.info(
            "produce_segments: done in %.1fs (images=%s, clips=%s)",
            elapsed,
            len(generated),
            len(clips.segment_clip_paths),
        )
        return SegmentProduceResult(image_paths=generated, clips=clips)


segment_mgr = SegmentMgr()
