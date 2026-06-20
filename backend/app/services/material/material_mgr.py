"""视频素材库业务逻辑。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from werkzeug.datastructures import FileStorage

from app.config import get_settings
from app.core.pipelines import PIPELINE_MATERIAL
from app.repositories import job_log_repo, job_repo, material_repo
from app.repositories.connection import connection
from app.services.media.ffmpeg_utils import extract_first_frame, probe_duration, probe_video_size

_ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024
_PLACEHOLDER_PATH = "pending"


class MaterialMgr:
    def list_materials(self, *, limit: int = 50, offset: int = 0) -> list[dict]:
        with connection() as conn:
            return material_repo.list_materials(conn, limit=limit, offset=offset)

    def get_material(self, material_id: int) -> dict:
        with connection() as conn:
            material = material_repo.get_material(conn, material_id)
            material["job_count"] = material_repo.count_jobs_for_material(conn, material_id)
            return material

    def update_material(self, material_id: int, **fields: object) -> dict:
        updates = {k: v for k, v in fields.items() if k in {"name", "note"}}
        if not updates:
            raise ValueError("no updatable fields provided")
        if "name" in updates:
            name = updates["name"]
            if not isinstance(name, str) or not name.strip():
                raise ValueError("name is empty")
            updates["name"] = name.strip()
        with connection() as conn:
            return material_repo.update_material(conn, material_id, **updates)

    def delete_material(self, material_id: int) -> None:
        settings = get_settings()
        with connection() as conn:
            material_repo.get_material(conn, material_id)
            material_repo.soft_delete_material(conn, material_id)
        material_dir = settings.material_data_dir / str(material_id)
        if material_dir.exists():
            shutil.rmtree(material_dir, ignore_errors=True)

    def _rollback_upload(self, material_id: int | None, material_dir: Path | None) -> None:
        if material_dir is not None and material_dir.exists():
            shutil.rmtree(material_dir, ignore_errors=True)
        if material_id is None:
            return
        with connection() as conn:
            try:
                material_repo.soft_delete_material(conn, material_id)
            except KeyError:
                pass

    def upload_material(
        self,
        file: FileStorage,
        *,
        name: str | None = None,
        note: str | None = None,
    ) -> dict:
        if not file or not file.filename:
            raise ValueError("file is required")

        original = Path(file.filename).name
        ext = Path(original).suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise ValueError(f"unsupported file type: {ext or '(none)'}")

        settings = get_settings()
        materials_root = settings.material_data_dir
        materials_root.mkdir(parents=True, exist_ok=True)

        display_name = (name or Path(original).stem).strip() or "未命名素材"
        note_text = note.strip() if note else None

        material_id: int | None = None
        material_dir: Path | None = None
        try:
            with connection() as conn:
                material = material_repo.create_material(
                    conn,
                    name=display_name,
                    file_path=_PLACEHOLDER_PATH,
                    note=note_text,
                )
                material_id = material["id"]

            material_dir = materials_root / str(material_id)
            material_dir.mkdir(parents=True, exist_ok=True)
            dest = material_dir / f"source{ext}"

            file.stream.seek(0, 2)
            size = file.stream.tell()
            file.stream.seek(0)
            if size > _MAX_UPLOAD_BYTES:
                raise ValueError(f"file too large: {size} bytes (max {_MAX_UPLOAD_BYTES})")

            file.save(dest)

            duration = probe_duration(dest)
            width, height = probe_video_size(dest)
            thumb = material_dir / "thumb.jpg"
            extract_first_frame(dest, thumb)

            with connection() as conn:
                return material_repo.update_material(
                    conn,
                    material_id,
                    name=display_name,
                    file_path=str(dest),
                    duration_sec=duration,
                    width=width,
                    height=height,
                    size_bytes=dest.stat().st_size,
                    thumbnail_path=str(thumb),
                    note=note_text,
                )
        except Exception:
            self._rollback_upload(material_id, material_dir)
            raise

    def create_job_from_material(
        self,
        material_id: int,
        title: str,
        *,
        narration: str | None = None,
        script_mode: str = "ai",
        skip_publish: bool = True,
    ) -> dict:
        cleaned_title = re.sub(r"\s+", "", title.strip())
        if not cleaned_title:
            raise ValueError("title is empty")
        mode = script_mode.strip().lower()
        if mode not in {"ai", "manual"}:
            raise ValueError("script_mode must be ai or manual")
        if mode == "manual":
            if not narration or not narration.strip():
                raise ValueError("narration is required for manual script_mode")
            if len(re.sub(r"\s+", "", narration)) < 200:
                raise ValueError("narration too short (need >= 200 chars)")

        with connection() as conn:
            material_repo.get_material(conn, material_id)
            script_json = (
                {"pending_narration": narration.strip(), "script_mode": "manual"}
                if mode == "manual"
                else None
            )
            job = job_repo.create_job(
                conn,
                cleaned_title,
                skip_publish=skip_publish,
                stage="prepare",
                status="pending",
                pipeline=PIPELINE_MATERIAL,
                material_id=material_id,
                script_json=script_json,
            )
            job_log_repo.append_log(
                conn,
                job["id"],
                "prepare",
                f"created material job from material #{material_id}, script_mode={mode}",
            )
            return job


material_mgr = MaterialMgr()

__all__ = ["MaterialMgr", "material_mgr"]
