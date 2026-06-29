"""按磁盘文件恢复分镜 image_path / clip_path（CLI 工具）。"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings


def restore_job_media_paths(job_id: int, *, dry_run: bool = False) -> dict:
    settings = get_settings()
    media_dir = settings.video_data_dir / str(job_id)
    images_dir = media_dir / "images"
    clips_dir = media_dir / "segments"

    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, segment_index, image_path, clip_path, status
        FROM video_segment
        WHERE job_id = ?
        ORDER BY segment_index
        """,
        (job_id,),
    ).fetchall()
    if not rows:
        raise SystemExit(f"job {job_id}: no segments in database")

    updated_images = 0
    updated_clips = 0
    missing_images: list[int] = []

    for row in rows:
        seg_id = int(row["id"])
        index = int(row["segment_index"])
        fields: dict[str, object] = {}

        image_file = images_dir / f"{index}.png"
        if image_file.exists():
            image_path = str(image_file.resolve())
            if row["image_path"] != image_path:
                fields["image_path"] = image_path
                updated_images += 1
        elif not row["image_path"]:
            missing_images.append(index)

        clip_file = clips_dir / f"{index}.mp4"
        if clip_file.exists():
            clip_path = str(clip_file.resolve())
            if row["clip_path"] != clip_path:
                fields["clip_path"] = clip_path
                updated_clips += 1

        if fields:
            if row["status"] == "pending" and fields.get("image_path"):
                fields["status"] = "done"
            if dry_run:
                print(f"#{index} would update: {fields}")
                continue
            parts = [f"{key} = ?" for key in fields]
            values = list(fields.values()) + [seg_id]
            conn.execute(
                f"UPDATE video_segment SET {', '.join(parts)} WHERE id = ?",
                values,
            )

    if not dry_run:
        conn.commit()
    conn.close()

    return {
        "job_id": job_id,
        "segments": len(rows),
        "updated_images": updated_images,
        "updated_clips": updated_clips,
        "missing_images": missing_images,
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore segment media paths from disk")
    parser.add_argument("job_id", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = restore_job_media_paths(args.job_id, dry_run=args.dry_run)
    print(result)


if __name__ == "__main__":
    main()
