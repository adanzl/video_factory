"""媒体文件路径校验与 URL 互转（对齐 MyTodo utils.validate_and_normalize_path / get_media_url）。"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from urllib.parse import unquote

_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[/\\]")


def decode_url_path(path: str) -> str:
    """解码 URL 编码路径（支持多次编码，对齐 MyTodo）。"""
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
    """路径须在允许的根目录之下（对齐 MyTodo _path_under_allowed_roots）。"""
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


def normalize_media_path(
    file_path: str,
    *,
    allowed_roots: list[str] | None = None,
    must_be_file: bool = True,
) -> str:
    """验证并规范化媒体路径（对齐 MyTodo validate_and_normalize_path）。"""
    if not file_path:
        raise ValueError("path is required")

    cleaned = decode_url_path(file_path.strip())
    if ".." in cleaned.split("/") or cleaned.startswith("~"):
        raise ValueError("path traversal not allowed")

    roots = allowed_roots or allowed_media_roots()
    if not roots:
        raise ValueError("no allowed media roots configured")

    base_dir = roots[0]
    if not os.path.isabs(cleaned):
        cleaned = os.path.normpath(os.path.join(base_dir, cleaned.lstrip("/")))
    else:
        cleaned = os.path.normpath(cleaned)

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
    """解析媒体文件 URL 路径（对齐 MyTodo media_mgr.prepare_serve_file）。"""
    roots = allowed_roots or allowed_media_roots()
    filepath = decode_url_path((url_path or "").strip())
    filepath = filepath.replace("../", "").replace("..\\", "")

    if not filepath.startswith("/") and not _WINDOWS_ABS_RE.match(filepath):
        filepath = "/" + filepath

    filepath = os.path.normpath(filepath)

    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"file not found: {filepath}")

    if not path_under_allowed_roots(filepath, roots):
        raise ValueError("path not in allowed directory")

    return filepath
