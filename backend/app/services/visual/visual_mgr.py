"""画面模块总入口：出图、封面。"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)

__all__ = ["ImageProvider", "VideoProvider", "VisualMgr", "visual_mgr"]


class ImageProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, output_path: Path, *, size: str | None = None) -> Path:
        ...


class VideoProvider(Protocol):
    def generate(self, prompt: str, output_path: Path, *, duration: int = 5) -> Path: ...


class VisualMgr:
    """画面生产管理器。"""

    def _get_image_provider(self) -> ImageProvider:
        from app.services.visual.image_mock import MockImageProvider
        from app.services.visual.image_wan import WanImageProvider
        from app.services.visual.image_zimage import ZImageProvider

        if get_settings().mock_mode:
            return MockImageProvider()
        provider = get_settings().image_provider
        if provider == "z_image_t2i":
            return ZImageProvider()
        if provider == "wan_t2i":
            return WanImageProvider()
        raise ValueError(f"unknown IMAGE_PROVIDER: {provider}")

    def generate_segment_images(
        self,
        segments: list[dict],
        images_dir: Path,
    ) -> list[tuple[int, Path]]:
        images_dir.mkdir(parents=True, exist_ok=True)
        provider = self._get_image_provider()
        settings = get_settings()
        max_workers = 1 if settings.mock_mode else max(1, settings.image_max_workers)
        total = len(segments)
        done = 0
        start = time.time()

        def render(seg: dict) -> tuple[int, Path]:
            nonlocal done
            index = seg["segment_index"]
            t0 = time.time()
            logger.info("image %s/%s generating (segment %s)...", done + 1, total, index)
            out = images_dir / f"{index}.png"
            prompt = seg.get("image_prompt") or seg["text"]
            provider.generate(prompt, out)
            elapsed = time.time() - t0
            logger.info("image %s/%s done (segment %s, %.1fs)", done + 1, total, index, elapsed)
            return seg["id"], out

        results: list[tuple[int, Path]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(render, seg): seg for seg in segments}
            for fut in as_completed(futures):
                results.append(fut.result())
                done += 1
        elapsed = time.time() - start
        logger.info("image total: %s/%s done in %.1fs", done, total, elapsed)
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
