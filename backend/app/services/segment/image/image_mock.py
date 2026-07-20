from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.config import get_settings
from app.services.render.text_render import load_cjk_font
from app.services.segment.image.image_mgr import ImageProvider


class MockImageProvider(ImageProvider):
    def describe_params(self, *, size: str | None = None) -> str:
        settings = get_settings()
        size = size or settings.wan_image_size
        return f"provider=mock, size={size}"

    def generate(self, prompt: str, output_path: Path, *, size: str | None = None, ref_images: list[Path] | None = None, expected_speakers: list[str] | None = None, content_style: str | None = None) -> Path:
        settings = get_settings()
        size_str = size or settings.wan_image_size
        w, h = size_str.split("*", 1)
        width, height = int(w), int(h)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (width, height), color=(32, 48, 72))
        draw = ImageDraw.Draw(img)
        font = load_cjk_font(48)
        snippet = prompt[:80] + ("..." if len(prompt) > 80 else "")
        draw.text((60, height // 2 - 40), snippet, fill=(230, 230, 230), font=font)
        img.save(output_path)
        return output_path
