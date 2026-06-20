"""媒体文件路径校验与 URL 互转（仅接受绝对路径）。"""

from __future__ import annotations

import os
import re
import stat
from urllib.parse import unquote

_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[/\\]")
_JOB_RELATIVE_RE = re.compile(r"^\d+/")


def decode_url_path(path: str) -> str:
    """解码 URL 编码路径（支持多次编码）。"""
    for _ in range(32):
        if "%" not in path:
            break
        try:
            decoded = unquote(path)
            if decoded == path:
                break
            path = decoded
        except Exception:
            break
    return path.replace("\\", "/")


def to_media_url_path(local_path: str) -> str:
    """本地绝对路径 → 媒体 URL 路径段（去掉开头的 `/`）。"""
    cleaned = (local_path or "").strip().replace("\\", "/")
    if not cleaned:
        return ""
    if cleaned.startswith("/"):
        return cleaned[1:]
    return cleaned


def path_under_allowed_roots(file_path: str, roots: list[str]) -> bool:
    norm = os.path.normpath(file_path)
    for root in roots:
        root_norm = os.path.normpath(root)
        if norm == root_norm or norm.startswith(root_norm + os.sep):
            return True
    return False


def allowed_media_roots() -> list[str]:
    from app.config import get_settings

    settings = get_settings()
    roots = [
        str(settings.video_data_dir.resolve()),
        str(settings.material_data_dir.resolve()),
        str((settings.root_dir / "data").resolve()),
    ]
    allowed_dir = (settings.allowed_dir or "").strip()
    if allowed_dir:
        roots.append(os.path.normpath(allowed_dir))

    unique: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if root and root not in seen:
            seen.add(root)
            unique.append(root)
    return unique


def _absolute_path_from_segment(segment: str) -> str:
    """URL 路径段或 API 参数 → 磁盘绝对路径（不接受相对路径）。"""
    cleaned = (segment or "").strip().replace("\\", "/")
    if not cleaned:
        raise ValueError("path is required")
    if ".." in cleaned.split("/") or cleaned.startswith("~"):
        raise ValueError("path traversal not allowed")

    if _WINDOWS_ABS_RE.match(cleaned):
        return os.path.normpath(cleaned)
    if os.path.isabs(cleaned):
        return os.path.normpath(cleaned)
    if _JOB_RELATIVE_RE.match(cleaned):
        raise ValueError("path must be absolute")
    if "/" not in cleaned:
        raise ValueError("path must be absolute")

    # getMediaFileUrl 会去掉 Linux 绝对路径开头的 /（如 mnt/data/...）
    return os.path.normpath("/" + cleaned.lstrip("/"))


def normalize_media_path(
    file_path: str,
    *,
    allowed_roots: list[str] | None = None,
    must_be_file: bool = True,
) -> str:
    """验证并返回磁盘绝对路径。"""
    cleaned = _absolute_path_from_segment(decode_url_path(file_path.strip()))

    roots = allowed_roots or allowed_media_roots()
    if not roots:
        raise ValueError("no allowed media roots configured")

    if not path_under_allowed_roots(cleaned, roots):
        raise ValueError("path not in allowed directory")

    try:
        st = os.lstat(cleaned)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"file not found: {cleaned}") from exc
    except RecursionError as exc:
        raise ValueError("Invalid path: 路径解析失败") from exc
    except OSError as exc:
        raise ValueError(f"Invalid path: {exc}") from exc

    if must_be_file and not stat.S_ISREG(st.st_mode):
        raise FileNotFoundError(f"file not found: {cleaned}")

    return cleaned


def resolve_media_serve_path(
    url_path: str,
    *,
    allowed_roots: list[str] | None = None,
) -> str:
    """解析 HTTP 媒体 URL 路径段 → 磁盘绝对路径。"""
    roots = allowed_roots or allowed_media_roots()
    filepath = decode_url_path((url_path or "").strip()).replace("../", "").replace("..\\", "")

    try:
        cleaned = _absolute_path_from_segment(filepath)
    except ValueError as exc:
        raise FileNotFoundError(str(exc)) from exc

    if not path_under_allowed_roots(cleaned, roots):
        raise ValueError("path not in allowed directory")

    if not os.path.isfile(cleaned):
        raise FileNotFoundError(f"file not found: {cleaned}")

    return cleaned
