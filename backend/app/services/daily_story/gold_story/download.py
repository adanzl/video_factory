"""H0b 媒体下载：按 source 分支，v0 仅 bili，预留 douyin。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Config

_BV_PATTERN = re.compile(r"(BV[0-9A-Za-z]{10})")
# 抖音 aweme_id（19 位数字）；后续 H0 接入时复用
_DOUYIN_ID_PATTERN = re.compile(r"(?:video/|modal/id=|/)(\d{15,22})")
_SUPPORTED_SOURCES = frozenset({"bili", "douyin"})


@dataclass(frozen=True, slots=True)
class MediaRef:
    source: str
    source_id: str
    url: str
    display_name: str


@dataclass(frozen=True, slots=True)
class DownloadResult:
    ref: MediaRef
    video_path: Path
    metadata: dict[str, Any]


def normalize_bv(source: str) -> str:
    return parse_media_ref(source, platform="bili").source_id


def parse_media_ref(raw: str, *, platform: str = "bili") -> MediaRef:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("empty source")
    platform = platform.strip().lower()
    if platform not in _SUPPORTED_SOURCES:
        raise ValueError(f"unsupported platform: {platform}")

    if platform == "bili":
        match = _BV_PATTERN.search(value)
        if not match:
            raise ValueError(f"not a BV id or URL: {value}")
        bv = match.group(1)
        url = value if _looks_like_url(value) else f"https://www.bilibili.com/video/{bv}"
        return MediaRef(source="bili", source_id=bv, url=url, display_name=bv)

    match = _DOUYIN_ID_PATTERN.search(value)
    if not match:
        raise ValueError(f"not a douyin id or URL: {value}")
    aweme_id = match.group(1)
    url = value if _looks_like_url(value) else f"https://www.douyin.com/video/{aweme_id}"
    return MediaRef(
        source="douyin",
        source_id=aweme_id,
        url=url,
        display_name=aweme_id,
    )


def download_media(ref: MediaRef, config: Config) -> DownloadResult:
    if ref.source == "bili":
        return _download_with_ytdlp(ref, config, cookie_path=config.bili_cookie_path)
    if ref.source == "douyin":
        cookie_path = config.douyin_cookie_path
        if cookie_path is None or not cookie_path.exists():
            raise RuntimeError(
                "douyin download requires DOUYIN_COOKIE_PATH; not configured yet"
            )
        return _download_with_ytdlp(ref, config, cookie_path=cookie_path)
    raise ValueError(f"unsupported source: {ref.source}")


def extract_audio_wav(video_path: Path, *, audio_dir: Path, stem: str) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required but was not found on PATH")

    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{stem}.wav"
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(audio_path),
        ],
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "unknown ffmpeg error"
        raise RuntimeError(f"ffmpeg failed to extract audio: {stderr}")
    return audio_path


def write_metadata(
    *,
    ref: MediaRef,
    metadata_dir: Path,
    payload: dict[str, Any],
) -> Path:
    metadata_dir.mkdir(parents=True, exist_ok=True)
    path = metadata_dir / f"{ref.source_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _playwright_cookies_to_netscape(cookie_path: Path, workspace: Path) -> Path:
    """Playwright storage_state JSON → yt-dlp Netscape cookie 文件。"""
    payload = json.loads(cookie_path.read_text(encoding="utf-8"))
    cookies = payload.get("cookies") if isinstance(payload, dict) else payload
    if not isinstance(cookies, list):
        raise ValueError(f"unsupported cookie format: {cookie_path}")
    out_dir = workspace / "cookies"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "bili_ytdlp_cookies.txt"
    lines = ["# Netscape HTTP Cookie File", "# generated from Playwright storage_state"]
    for item in cookies:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "")
        if "bilibili" not in domain:
            continue
        name = str(item.get("name") or "")
        value = str(item.get("value") or "")
        if not name:
            continue
        path = str(item.get("path") or "/")
        secure = "TRUE" if item.get("secure") else "FALSE"
        include_sub = "TRUE" if domain.startswith(".") else "FALSE"
        expires = int(float(item.get("expires") or 0))
        if expires <= 0:
            expires = int(datetime.now(timezone.utc).timestamp()) + 86400 * 30
        lines.append(
            "\t".join([domain, include_sub, path, secure, str(expires), name, value])
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _ytdlp_cookie_path(cookie_path: Path | None, workspace: Path) -> str | None:
    if cookie_path is None or not cookie_path.exists():
        return None
    head = cookie_path.read_text(encoding="utf-8").lstrip()[:1]
    if head in "{[":
        return str(_playwright_cookies_to_netscape(cookie_path, workspace))
    return str(cookie_path)


def _download_with_ytdlp(
    ref: MediaRef,
    config: Config,
    *,
    cookie_path: Path | None,
) -> DownloadResult:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed") from exc

    workspace = config.gold_story_media_workspace
    downloads_dir = workspace / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts: dict[str, Any] = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "outtmpl": str(downloads_dir / f"{ref.source_id}.%(ext)s"),
        "noprogress": True,
        "quiet": True,
        "no_warnings": True,
    }
    if cookie_path and cookie_path.exists():
        resolved = _ytdlp_cookie_path(cookie_path, workspace)
        if resolved:
            ydl_opts["cookiefile"] = resolved
    if not config.gold_story_use_proxy:
        ydl_opts["proxy"] = ""

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(ref.url, download=True)
        if info and "entries" in info and info["entries"]:
            info = info["entries"][0]
        info = ydl.sanitize_info(info or {})
        video_path = _resolve_video_path(ydl, info, ref.source_id, downloads_dir)
        if not video_path.exists():
            raise RuntimeError(f"download finished but file missing: {video_path}")

    metadata = {
        "source": ref.source,
        "source_id": ref.source_id,
        "url": ref.url,
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "webpage_url": info.get("webpage_url") or ref.url,
        "downloaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return DownloadResult(ref=ref, video_path=video_path, metadata=metadata)


def _resolve_video_path(
    ydl: Any,
    info: dict[str, Any],
    source_id: str,
    downloads_dir: Path,
) -> Path:
    requested = info.get("requested_downloads") or []
    for item in requested:
        filepath = item.get("filepath")
        if filepath:
            return Path(filepath)

    prepared = Path(ydl.prepare_filename(info))
    if prepared.exists():
        return prepared

    merged = prepared.with_suffix(".mp4")
    if merged.exists():
        return merged

    fallback = downloads_dir / f"{source_id}.mp4"
    if fallback.exists():
        return fallback
    return prepared


def _looks_like_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")
