from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings


@dataclass
class JobContext:
    job: dict
    settings: Settings
    media_dir: Path
    rerun_segment_indices: tuple[int, ...] | None = None

    @classmethod
    def from_job(
        cls,
        job: dict,
        *,
        rerun_segment_indices: tuple[int, ...] | None = None,
    ) -> "JobContext":
        settings = get_settings()
        media_dir = settings.video_data_dir / str(job["id"])
        media_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            job=job,
            settings=settings,
            media_dir=media_dir,
            rerun_segment_indices=rerun_segment_indices,
        )

    def rel(self, name: str) -> Path:
        return self.media_dir / name

    def segment_indices_set(self) -> set[int] | None:
        if not self.rerun_segment_indices:
            return None
        return set(self.rerun_segment_indices)
