"""媒体文件路径校验：限制在允许的根目录内。"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote


def decode_url_path(raw: str) -> str:
    return unquote(raw.replace("\\", "/"))


def allowed_media_roots() -> list[Path]:
    from app.config import get_settings

    settings = get_settings()
    roots = [
        settings.video_data_dir.resolve(),
        (settings.root_dir / "data").resolve(),
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def normalize_media_path(
    file_path: str,
    *,
    allowed_roots: list[Path] | None = None,
    must_be_file: bool = True,
) -> Path:
    """校验并规范化媒体路径，禁止目录穿越。"""
    cleaned = decode_url_path((file_path or "").strip())
    if not cleaned:
        raise ValueError("path is required")

    parts = cleaned.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise ValueError("path traversal not allowed")
    if cleaned.startswith("~"):
        raise ValueError("path traversal not allowed")

    roots = allowed_roots or allowed_media_roots()
    if not roots:
        raise ValueError("no allowed media roots configured")

    candidate = Path(cleaned)
    if not candidate.is_absolute():
        candidate = (roots[0] / cleaned.lstrip("/\\")).resolve()
    else:
        candidate = candidate.resolve()

    if not any(_is_under_root(candidate, root) for root in roots):
        raise ValueError("path not in allowed directory")

    if must_be_file and not candidate.is_file():
        raise FileNotFoundError(f"file not found: {candidate}")
    return candidate


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
