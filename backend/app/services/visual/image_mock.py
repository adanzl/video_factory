from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.config import get_settings
from app.services.visual.text_render import load_cjk_font
from app.services.visual.visual_mgr import ImageProvider


class MockImageProvider(ImageProvider):
    def generate(self, prompt: str, output_path: Path, *, size: str | None = None) -> Path:
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
