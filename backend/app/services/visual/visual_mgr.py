"""画面模块总入口：出图、封面。"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from app.config import get_settings
from app.services.job.job_cancel import job_cancel

logger = logging.getLogger(__name__)

__all__ = ["ImageProvider", "VideoProvider", "VisualMgr", "visual_mgr"]


class ImageProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, output_path: Path, *, size: str | None = None) -> Path:
        ...

    def describe_params(self, *, size: str | None = None) -> str:
        return "provider=unknown"


class VideoProvider(Protocol):
    def generate(self, prompt: str, output_path: Path, *, duration: int = 5) -> Path: ...


class VisualMgr:
    """画面生产管理器。"""

    def _get_image_provider(self, provider_name: str | None = None) -> ImageProvider:
        from app.services.visual.image_agnes import AgnesImageProvider
        from app.services.visual.image_mock import MockImageProvider
        from app.services.visual.image_sd15 import Sd15ImageProvider
        from app.services.visual.image_wan import WanImageProvider
        from app.services.visual.image_zimage import ZImageProvider

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

    def generate_segment_images(
        self,
        segments: list[dict],
        images_dir: Path,
        *,
        size: str | None = None,
        image_provider: str | None = None,
        on_image_done: Callable[[int, Path], None] | None = None,
        job_id: int | None = None,
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

        def render(seg: dict) -> tuple[int, Path]:
            nonlocal done
            index = seg["segment_index"]
            t0 = time.time()
            out = images_dir / f"{index}.png"
            # SD15 provider 优先使用预生成的短英文 prompt（sd15_prompt_en），
            # 避免出图时再次 LLM 翻译导致语义二次漂移；
            # 其他 provider（ZImage/WAN）继续使用完整中文 image_prompt
            if type(provider).__name__ == "Sd15ImageProvider":
                prompt = seg.get("sd15_prompt_en") or seg.get("image_prompt") or seg["text"]
            else:
                prompt = seg.get("image_prompt") or seg["text"]
            logger.info(
                "image %s/%s generating segment %s | %s | prompt_chars=%s",
                done + 1,
                total,
                index,
                params_desc,
                len(prompt),
            )
            provider.generate(prompt, out, size=size)
            elapsed = time.time() - t0
            logger.info(
                "image %s/%s done segment %s in %.1fs | %s",
                done + 1,
                total,
                index,
                elapsed,
                params_desc,
            )
            return seg["id"], out

        results: list[tuple[int, Path]] = []
        if on_image_done is not None:
            for seg in segments:
                if job_id is not None:
                    job_cancel.raise_if_cancelled(job_id)
                seg_id, path = render(seg)
                results.append((seg_id, path))
                on_image_done(seg_id, path)
                done += 1
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(render, seg): seg for seg in segments}
                for fut in as_completed(futures):
                    if job_id is not None:
                        job_cancel.raise_if_cancelled(job_id)
                    results.append(fut.result())
                    done += 1
        elapsed = time.time() - start
        logger.info("image batch done: %s/%s in %.1fs | %s", done, total, elapsed, params_desc)
        return results

    def generate_cover(
        self,
        title: str,
        output_path: Path,
        *,
        base_prompt: str | None = None,
    ) -> Path:
        prompt = base_prompt or (
            f"B站科普视频封面，16:9，信息图风格，标题文字区域留白，主题：{title}"
        )
        return self._get_image_provider().generate(
            prompt,
            output_path,
            size=get_settings().wan_cover_size,
        )


visual_mgr = VisualMgr()
