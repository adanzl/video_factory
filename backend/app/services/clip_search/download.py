"""下载素材库视频并写入任务分镜。"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import requests

from app.config import get_settings
from app.services.clip_search.preview_proxy import validate_preview_url
from app.services.intro.size import resolve_intro_size
from app.services.segment.clip.clip_render import fit_video_duration
from app.services.media.ffmpeg_utils import probe_duration
from app.utils.job_info import orientation_for_resolve

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = 120.0


def download_stock_clip_to_segment(
    *,
    job: dict,
    media_dir: Path,
    segment: dict,
    video_url: str,
) -> Path:
    validated = validate_preview_url(video_url)
    segment_index = int(segment["segment_index"])
    clips_dir = media_dir / "segments"
    clips_dir.mkdir(parents=True, exist_ok=True)
    output_path = clips_dir / f"{segment_index}.mp4"

    settings = get_settings()
    width, height = resolve_intro_size(
        settings=settings,
        orientation=orientation_for_resolve(job),
        job=job,
        media_dir=media_dir,
    )

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=clips_dir) as tmp:
        tmp_path = Path(tmp.name)

    try:
        logger.info(
            "downloading stock clip for job=%s segment=%s",
            job.get("id"),
            segment_index,
        )
        resp = requests.get(validated, timeout=_DOWNLOAD_TIMEOUT, stream=True)
        resp.raise_for_status()
        with tmp_path.open("wb") as fp:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    fp.write(chunk)

        duration_sec = segment.get("duration_sec")
        if not isinstance(duration_sec, (int, float)) or duration_sec <= 0:
            duration_sec = probe_duration(tmp_path)

        fit_video_duration(
            tmp_path,
            output_path,
            float(duration_sec),
            width=width,
            height=height,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return output_path
