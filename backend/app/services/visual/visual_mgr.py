"""画面模块总入口：出图、封面、片头。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Protocol

from app.config import get_settings
from app.services.visual.intro import generate_intro as _generate_intro

__all__ = ["ImageProvider", "VideoProvider", "generate_cover", "generate_intro", "generate_segment_images"]


class ImageProvider(Protocol):
    def generate(self, prompt: str, output_path: Path, *, size: str | None = None) -> Path: ...


class VideoProvider(Protocol):
    def generate(self, prompt: str, output_path: Path, *, duration: int = 5) -> Path: ...


def _get_image_provider() -> ImageProvider:
    from app.services.visual.image_mock import MockImageProvider
    from app.services.visual.image_wan import WanImageProvider

    if get_settings().mock_mode:
        return MockImageProvider()
    return WanImageProvider()


def generate_segment_images(
    segments: list[dict],
    images_dir: Path,
) -> list[tuple[int, Path]]:
    images_dir.mkdir(parents=True, exist_ok=True)
    provider = _get_image_provider()
    settings = get_settings()
    max_workers = 1 if settings.mock_mode else max(1, settings.image_max_workers)

    def render(seg: dict) -> tuple[int, Path]:
        out = images_dir / f"{seg['segment_index']}.png"
        prompt = seg.get("image_prompt") or seg["text"]
        provider.generate(prompt, out)
        return seg["id"], out

    results: list[tuple[int, Path]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(render, seg) for seg in segments]
        for fut in as_completed(futures):
            results.append(fut.result())
    return results


def generate_cover(title: str, output_path: Path, *, base_prompt: str | None = None) -> Path:
    prompt = base_prompt or (
        f"B站科普视频封面，16:9，信息图风格，标题文字区域留白，主题：{title}"
    )
    return _get_image_provider().generate(prompt, output_path, size=get_settings().wan_cover_size)


def generate_intro(title: str, output_path: Path) -> Path:
    return _generate_intro(title, output_path)
