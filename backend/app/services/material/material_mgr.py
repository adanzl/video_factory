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
from app.services.job.job_mgr import job_mgr
from app.services.media.ffmpeg_utils import extract_first_frame, probe_duration, probe_video_size

_ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
_RUN_MODES = frozenset({"none", "prepare", "full"})
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024
_PLACEHOLDER_PATH = "pending"


class MaterialMgr:
    def list_materials(self, *, limit: int = 50, offset: int = 0) -> list[dict]:
        with connection() as conn:
            return material_repo.list_materials(conn, limit=limit, offset=offset)

    def get_material(self, material_id: int) -> dict:
        with connection() as conn:
            return material_repo.get_material(conn, material_id)

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

    def _validate_upload_file(self, file: FileStorage) -> tuple[str, str]:
        if not file or not file.filename:
            raise ValueError("file is required")
        original = Path(file.filename).name
        ext = Path(original).suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise ValueError(f"unsupported file type: {ext or '(none)'}")
        file.stream.seek(0, 2)
        size = file.stream.tell()
        file.stream.seek(0)
        if size > _MAX_UPLOAD_BYTES:
            raise ValueError(f"file too large: {size} bytes (max {_MAX_UPLOAD_BYTES})")
        return original, ext

    def _write_material_video(self, material_dir: Path, file: FileStorage, ext: str) -> Path:
        material_dir.mkdir(parents=True, exist_ok=True)
        for old in material_dir.glob("source.*"):
            old.unlink(missing_ok=True)
        dest = material_dir / f"source{ext}"
        file.save(dest)
        return dest

    def _finalize_material_video(self, material_dir: Path, dest: Path) -> dict[str, object]:
        duration = probe_duration(dest)
        width, height = probe_video_size(dest)
        thumb = material_dir / "thumb.jpg"
        extract_first_frame(dest, thumb)
        return {
            "file_path": str(dest),
            "duration_sec": duration,
            "width": width,
            "height": height,
            "size_bytes": dest.stat().st_size,
            "thumbnail_path": str(thumb),
        }

    def upload_material(
        self,
        file: FileStorage,
        *,
        name: str | None = None,
        note: str | None = None,
    ) -> dict:
        original, ext = self._validate_upload_file(file)

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
            dest = self._write_material_video(material_dir, file, ext)
            meta = self._finalize_material_video(material_dir, dest)

            with connection() as conn:
                return material_repo.update_material(
                    conn,
                    material_id,
                    name=display_name,
                    note=note_text,
                    **meta,
                )
        except Exception:
            self._rollback_upload(material_id, material_dir)
            raise

    def edit_material(
        self,
        material_id: int,
        *,
        name: str,
        note: str | None = None,
        file: FileStorage | None = None,
    ) -> dict:
        """编辑素材：名称、备注；可选更换视频文件。"""
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("name is empty")
        note_text = note.strip() if note else None

        settings = get_settings()
        with connection() as conn:
            material_repo.get_material(conn, material_id)

        meta: dict[str, object] = {}
        if file and file.filename:
            _, ext = self._validate_upload_file(file)
            material_dir = settings.material_data_dir / str(material_id)
            dest = self._write_material_video(material_dir, file, ext)
            meta = self._finalize_material_video(material_dir, dest)

        with connection() as conn:
            return material_repo.update_material(
                conn,
                material_id,
                name=cleaned_name,
                note=note_text,
                **meta,
            )

    def create_job_from_material(
        self,
        material_id: int,
        title: str,
        *,
        narration: str | None = None,
        script_mode: str = "ai",
        skip_publish: bool = True,
        run_mode: str = "prepare",
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
        run = run_mode.strip().lower()
        if run not in _RUN_MODES:
            raise ValueError(f"run_mode must be one of {sorted(_RUN_MODES)}")

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
                status="idle",
                pipeline=PIPELINE_MATERIAL,
                material_id=material_id,
                script_json=script_json,
            )
            job_log_repo.append_log(
                conn,
                job["id"],
                "prepare",
                f"created material job from material #{material_id}, "
                f"script_mode={mode}, run_mode={run}",
            )
            material_repo.update_material(conn, material_id, job_id=job["id"])

        if run == "prepare":
            job_mgr.run_prepare(job["id"], to_end=False)
        elif run == "full":
            job_mgr.run_prepare(job["id"], to_end=True)

        return job


material_mgr = MaterialMgr()

__all__ = ["MaterialMgr", "material_mgr"]
