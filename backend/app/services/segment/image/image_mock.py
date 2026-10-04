from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.config import get_settings
from app.services.render.text_render import load_cjk_font
from app.services.segment.image.image_mgr import ImageProvider


def _parse_mock_size(size_str: str, *, fallback: str = "720*1280") -> tuple[int, int]:
    """把尺寸字符串解析成像素宽高。

    真实 provider（如 agnes）用 ``1K`` / ``2K`` 这类档位字符串，Mock 出图
    只需要一个合理的占位分辨率，故对无法直接解析的档位统一回退到 ``fallback``。
    """
    normalized = (size_str or "").strip().lower().replace("x", "*")
    if "*" in normalized:
        w_str, h_str = normalized.split("*", 1)
        try:
            return int(w_str.strip()), int(h_str.strip())
        except ValueError:
            pass
    fb = (fallback or "720*1280").strip().lower().replace("x", "*")
    if "*" in fb:
        w_str, h_str = fb.split("*", 1)
        try:
            return int(w_str.strip()), int(h_str.strip())
        except ValueError:
            pass
    return 720, 1280


class MockImageProvider(ImageProvider):
    def describe_params(self, *, size: str | None = None) -> str:
        settings = get_settings()
        size = size or settings.wan_image_size
        return f"provider=mock, size={size}"

    def generate(self, prompt: str, output_path: Path, *, size: str | None = None, ref_images: list[Path] | None = None, expected_speakers: list[str] | None = None, content_style: str | None = None) -> Path:
        settings = get_settings()
        size_str = size or settings.wan_image_size
        width, height = _parse_mock_size(size_str, fallback=settings.wan_image_size)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (width, height), color=(32, 48, 72))
        draw = ImageDraw.Draw(img)
        font = load_cjk_font(48)
        snippet = prompt[:80] + ("..." if len(prompt) > 80 else "")
        draw.text((60, height // 2 - 40), snippet, fill=(230, 230, 230), font=font)
        img.save(output_path)
        return output_path
