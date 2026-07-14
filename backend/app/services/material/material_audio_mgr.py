"""音频素材库业务逻辑。"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from werkzeug.datastructures import FileStorage

from app.config import get_settings
from app.repositories import repo_material_audio
from app.repositories.connection import connection
from app.services.media.ffmpeg_utils import probe_duration

logger = logging.getLogger(__name__)

_AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"}
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024
_PLACEHOLDER_PATH = "pending"


class MaterialAudioMgr:
    def list_materials(self, *, limit: int = 50, offset: int = 0) -> dict:
        """返回 {items: [...], total: N}。"""
        with connection() as conn:
            items = repo_material_audio.list_material_audios(conn, limit=limit, offset=offset)
            total = repo_material_audio.count_material_audios(conn)
            return {"items": items, "total": total}

    def get_material(self, material_id: int) -> dict:
        with connection() as conn:
            return repo_material_audio.get_material_audio(conn, material_id)

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
            return repo_material_audio.update_material_audio(conn, material_id, **updates)

    def delete_material(self, material_id: int) -> None:
        settings = get_settings()
        with connection() as conn:
            repo_material_audio.get_material_audio(conn, material_id)
            repo_material_audio.soft_delete_material_audio(conn, material_id)
        material_dir = settings.audio_data_dir / str(material_id)
        if material_dir.exists():
            shutil.rmtree(material_dir, ignore_errors=True)

    def _rollback_upload(self, material_id: int | None, material_dir: Path | None) -> None:
        if material_dir is not None and material_dir.exists():
            shutil.rmtree(material_dir, ignore_errors=True)
        if material_id is None:
            return
        with connection() as conn:
            try:
                repo_material_audio.soft_delete_material_audio(conn, material_id)
            except KeyError:
                pass

    def _validate_upload_file(self, file: FileStorage) -> tuple[str, str]:
        if not file or not file.filename:
            raise ValueError("file is required")
        original = Path(file.filename).name
        ext = Path(original).suffix.lower()
        if ext not in _AUDIO_EXTENSIONS:
            raise ValueError(f"unsupported audio file type: {ext or '(none)'}")
        file.stream.seek(0, 2)
        size = file.stream.tell()
        file.stream.seek(0)
        if size > _MAX_UPLOAD_BYTES:
            raise ValueError(f"file too large: {size} bytes (max {_MAX_UPLOAD_BYTES})")
        return original, ext

    def _write_audio_file(self, material_dir: Path, file: FileStorage, ext: str) -> Path:
        material_dir.mkdir(parents=True, exist_ok=True)
        for old in material_dir.glob("source.*"):
            old.unlink(missing_ok=True)
        dest = material_dir / f"source{ext}"
        file.save(dest)
        return dest

    def _finalize_audio_file(self, material_dir: Path, dest: Path) -> dict[str, object]:
        duration = probe_duration(dest)
        return {
            "file_path": str(dest),
            "duration_sec": duration if isinstance(duration, (int, float)) else None,
            "size_bytes": dest.stat().st_size,
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
        audio_root = settings.audio_data_dir
        audio_root.mkdir(parents=True, exist_ok=True)

        display_name = (name or Path(original).stem).strip() or "未命名音频"
        note_text = note.strip() if note else None

        material_id: int | None = None
        material_dir: Path | None = None
        try:
            with connection() as conn:
                material = repo_material_audio.create_material_audio(
                    conn,
                    name=display_name,
                    file_path=_PLACEHOLDER_PATH,
                    note=note_text,
                )
                material_id = material["id"]

            material_dir = audio_root / str(material_id)
            dest = self._write_audio_file(material_dir, file, ext)
            meta = self._finalize_audio_file(material_dir, dest)

            with connection() as conn:
                return repo_material_audio.update_material_audio(
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
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("name is empty")
        note_text = note.strip() if note else None

        settings = get_settings()
        with connection() as conn:
            repo_material_audio.get_material_audio(conn, material_id)

        meta: dict[str, object] = {}
        if file and file.filename:
            _, ext = self._validate_upload_file(file)
            material_dir = settings.audio_data_dir / str(material_id)
            dest = self._write_audio_file(material_dir, file, ext)
            meta = self._finalize_audio_file(material_dir, dest)

        with connection() as conn:
            return repo_material_audio.update_material_audio(
                conn,
                material_id,
                name=cleaned_name,
                note=note_text,
                **meta,
            )


material_audio_mgr = MaterialAudioMgr()

__all__ = ["MaterialAudioMgr", "material_audio_mgr"]
