"""分镜出图总入口：ImageProvider 工厂与批量出图。"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.utils.job_cancel import job_cancel

logger = logging.getLogger(__name__)

__all__ = ["ImageMgr", "ImageProvider", "image_mgr"]

_VERIFY_PROMPT_REGEN_FEEDBACK = (
    "出图质检连续未通过（发型/人数/肢体/场景/妈妈是否成年等），请改写本段 image_prompt："
    "换姿势与构图、冲突道具更醒目；仍须保持角色外貌与身高约束"
    "（灿灿单侧高马尾禁双马尾；昭昭男孩超短发禁波波头；"
    "妈妈须为成年女性黑长发米色上衣牛仔裤，禁止画成小孩）。"
)


class ImageProvider(ABC):
    @abstractmethod
    def generate(
        self,
        prompt: str,
        output_path: Path,
        *,
        size: str | None = None,
        ref_images: list[Path] | None = None,
        expected_speakers: list[str] | None = None,
        content_style: str | None = None,
    ) -> Path:
        ...

    def describe_params(self, *, size: str | None = None) -> str:
        return "provider=unknown"


class ImageMgr:
    """分镜出图管理器。"""

    def _get_image_provider(self, provider_name: str | None = None) -> ImageProvider:
        from app.services.segment.image.image_agnes import AgnesImageProvider
        from app.services.segment.image.image_mock import MockImageProvider
        from app.services.segment.image.image_sd15 import Sd15ImageProvider
        from app.services.segment.image.image_wan import WanImageProvider
        from app.services.segment.image.image_zimage import ZImageProvider

        if get_settings().mock_mode:
            return MockImageProvider()
        provider = provider_name or get_settings().image_provider
        if provider == "z_image_t2i":
            return ZImageProvider()
        if provider == "wan_t2i":
            return WanImageProvider()
        if provider == "sd15_t2i":
            return Sd15ImageProvider()
        if provider == "agnes_t2i":
            return AgnesImageProvider()
        raise ValueError(f"unknown IMAGE_PROVIDER: {provider}")

    @staticmethod
    def _regen_segment_image_prompt(
        seg: dict,
        *,
        job: dict[str, Any] | None,
        content_style: str | None,
    ) -> str:
        """质检耗尽后，按单段重写 image_prompt（含 daily wrap）。"""
        from app.services.llm.llm_mgr import llm_mgr
        from app.services.script.image_prompt import wrap_image_prompts
        from app.utils.job_info import resolve_include_sd15_prompt

        if not job:
            raise RuntimeError("missing job for image_prompt regen")
        script = job.get("script_json")
        if not isinstance(script, dict):
            raise RuntimeError("job.script_json missing for image_prompt regen")

        index = int(seg["segment_index"])
        script_segments = list(script.get("segments") or [])
        by_index = {
            int(s.get("segment_index") or 0): s for s in script_segments if s
        }
        # 用 DB 分镜补齐 script 中可能缺失的字段
        target = dict(by_index.get(index) or {})
        for key in (
            "segment_index",
            "text",
            "visual_brief",
            "dialogue",
            "shot_type",
            "info",
            "motion_prompt",
            "visual_mode",
        ):
            if seg.get(key) is not None:
                target[key] = seg[key]
        target["segment_index"] = index
        by_index[index] = target
        script["segments"] = sorted(
            by_index.values(),
            key=lambda s: int(s.get("segment_index") or 0),
        )

        llm_mgr.fill_image_prompts(
            script,
            feedback=_VERIFY_PROMPT_REGEN_FEEDBACK,
            job=job,
            segment_indices=[index],
            include_sd15_prompt=resolve_include_sd15_prompt(job),
        )
        refreshed = next(
            (
                s
                for s in (script.get("segments") or [])
                if int(s.get("segment_index") or 0) == index
            ),
            None,
        )
        if refreshed is None:
            raise RuntimeError(f"image_prompt regen missing segment {index}")
        wrap_image_prompts([refreshed], content_style=content_style)
        new_prompt = str(refreshed.get("image_prompt") or "").strip()
        if not new_prompt:
            raise RuntimeError(f"image_prompt regen empty for segment {index}")
        if refreshed.get("motion_prompt") is not None:
            seg["motion_prompt"] = refreshed.get("motion_prompt")
        if refreshed.get("sd15_prompt_en") is not None:
            seg["sd15_prompt_en"] = refreshed.get("sd15_prompt_en")
        seg["image_prompt"] = new_prompt
        return new_prompt

    @staticmethod
    def _persist_segment_prompt(seg: dict) -> None:
        seg_id = seg.get("id")
        if seg_id is None:
            return
        from app.repositories import repo_segment
        from app.repositories.connection import connection

        payload: dict[str, Any] = {"image_prompt": seg.get("image_prompt")}
        if seg.get("motion_prompt") is not None:
            payload["motion_prompt"] = seg.get("motion_prompt")
        if seg.get("sd15_prompt_en") is not None:
            payload["sd15_prompt_en"] = seg.get("sd15_prompt_en")
        with connection() as conn:
            repo_segment.update_segment(conn, int(seg_id), **payload)

    def generate_segment_images(
        self,
        segments: list[dict],
        images_dir: Path,
        *,
        size: str | None = None,
        image_provider: str | None = None,
        on_image_done: Callable[[int, Path, float], None] | None = None,
        job_id: int | None = None,
        job: dict[str, Any] | None = None,
        ref_images: list[Path] | None = None,
        content_style: str | None = None,
    ) -> list[tuple[int, Path]]:
        images_dir.mkdir(parents=True, exist_ok=True)
        provider = self._get_image_provider(image_provider)
        settings = get_settings()
        max_workers = 1 if settings.mock_mode else max(1, settings.image_max_workers)
        total = len(segments)
        done = 0
        start = time.time()
        params_desc = provider.describe_params(size=size)
        logger.info(
            "image batch start: count=%s, workers=%s, %s",
            total,
            max_workers,
            params_desc,
        )

        def _build_prompt(seg: dict) -> str:
            if type(provider).__name__ == "Sd15ImageProvider":
                prompt = seg.get("sd15_prompt_en") or seg.get("image_prompt") or seg["text"]
            else:
                prompt = seg.get("image_prompt") or seg["text"]
            from app.services.intro.cover_layout import _subject_has_map_keyword

            if _subject_has_map_keyword(prompt):
                prompt = (
                    f"若包含世界地图，不得显示中国部分。"
                    f"任何地图不得出现中国领土、藏南地区、阿克赛钦地区。"
                    f"{prompt}"
                )
            return prompt

        def _speakers(seg: dict) -> list[str] | None:
            dialogue = seg.get("dialogue") or []
            speakers = sorted(
                set(d.get("speaker", "") for d in dialogue if d.get("speaker"))
            )
            return speakers if speakers else None

        def render(seg: dict) -> tuple[int, Path] | None:
            from app.services.segment.image.image_agnes import AgnesImageVerifyFailed

            nonlocal done
            index = seg["segment_index"]
            t0 = time.time()
            out = images_dir / f"{index}.png"
            prompt = _build_prompt(seg)
            expected_speakers = _speakers(seg)
            logger.info(
                "image %s/%s generating segment %s | %s | prompt_chars=%s"
                " | speakers=%s | out=%s",
                done + 1,
                total,
                index,
                params_desc,
                len(prompt),
                expected_speakers,
                out.name,
            )
            try:
                try:
                    provider.generate(
                        prompt,
                        out,
                        size=size,
                        ref_images=ref_images,
                        expected_speakers=expected_speakers,
                        content_style=content_style,
                    )
                except AgnesImageVerifyFailed as first_fail:
                    logger.warning(
                        "image segment %s verify exhausted on current prompt; "
                        "regenerating image_prompt then retry",
                        index,
                    )
                    try:
                        new_prompt = self._regen_segment_image_prompt(
                            seg,
                            job=job,
                            content_style=content_style,
                        )
                        self._persist_segment_prompt(seg)
                        prompt = _build_prompt(seg)
                        logger.info(
                            "image segment %s prompt regenerated chars=%s; "
                            "retry generate",
                            index,
                            len(new_prompt),
                        )
                    except Exception as regen_exc:
                        logger.error(
                            "image segment %s prompt regen failed: %s",
                            index,
                            regen_exc,
                        )
                        raise first_fail from regen_exc
                    provider.generate(
                        prompt,
                        out,
                        size=size,
                        ref_images=ref_images,
                        expected_speakers=expected_speakers,
                        content_style=content_style,
                    )
            except AgnesImageVerifyFailed as exc:
                logger.error(
                    "image %s/%s SKIP segment %s after verify fail (%.1fs) | %s | %s",
                    done + 1,
                    total,
                    index,
                    time.time() - t0,
                    params_desc,
                    exc,
                )
                if out.exists():
                    try:
                        out.unlink()
                    except OSError:
                        pass
                return None
            except Exception as exc:
                logger.error(
                    "image %s/%s FAILED segment %s after %.1fs | %s | err=%s",
                    done + 1,
                    total,
                    index,
                    time.time() - t0,
                    params_desc,
                    exc,
                )
                raise
            elapsed = time.time() - t0
            logger.info(
                "image %s/%s done segment %s in %.1fs | %s | bytes=%s",
                done + 1,
                total,
                index,
                elapsed,
                params_desc,
                out.stat().st_size if out.exists() else 0,
            )
            return seg["id"], out, elapsed

        results: list[tuple[int, Path]] = []
        skipped = 0
        if on_image_done is not None:
            for seg in segments:
                if job_id is not None:
                    job_cancel.raise_if_cancelled(job_id)
                item = render(seg)
                done += 1
                if item is None:
                    skipped += 1
                    continue
                seg_id, path, gen_sec = item
                results.append((seg_id, path))
                on_image_done(seg_id, path, gen_sec)
        else:
            from gevent.pool import Pool

            pool = Pool(size=max_workers)
            green_lets = [pool.spawn(render, seg) for seg in segments]
            for g in green_lets:
                if job_id is not None:
                    job_cancel.raise_if_cancelled(job_id)
                item = g.get()
                done += 1
                if item is None:
                    skipped += 1
                    continue
                seg_id, path, _ = item
                results.append((seg_id, path))
        elapsed = time.time() - start
        logger.info(
            "image batch done: %s/%s ok, skipped=%s in %.1fs | %s",
            len(results),
            total,
            skipped,
            elapsed,
            params_desc,
        )
        return results

    def generate_cover(
        self,
        title: str,
        output_path: Path,
        *,
        base_prompt: str | None = None,
    ) -> Path:
        from app.services.intro.cover_layout import _resolve_cover_subject, _subject_has_map_keyword

        resolved_title = _resolve_cover_subject(title)
        if base_prompt:
            prompt = base_prompt
        else:
            prompt = f"B站科普视频封面，16:9，信息图风格，标题文字区域留白，"
            if _subject_has_map_keyword(title):
                prompt += "若包含世界地图，不得显示中国部分。任何地图不得出现中国领土、藏南地区、阿克赛钦地区，"
            prompt += f"主题：{resolved_title}"
        return self._get_image_provider().generate(
            prompt,
            output_path,
            size=get_settings().wan_cover_size,
        )


image_mgr = ImageMgr()
