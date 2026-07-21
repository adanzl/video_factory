"""恢复 job 数据。

用法:
  # 从 job_log / segments_wan 归档做完整恢复（服务器路径）
  python scripts/restore_job.py full <job_id>

  # 按磁盘文件回填分镜 image_path / clip_path
  python scripts/restore_job.py media-paths <job_id>
  python scripts/restore_job.py media-paths <job_id> --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings

# full 模式默认走服务器路径（与线上一致）
SERVER_DB = Path("/mnt/data/project/video_factory/data/data.db")
SERVER_MEDIA_ROOT = Path("/mnt/data/project/video_factory/data/media")


def get_job_log_script(conn: sqlite3.Connection, job_id: int) -> str | None:
    """从 job_log 表提取最近的完整 script_json。"""
    row = conn.execute(
        "SELECT message FROM job_log WHERE job_id=? AND message LIKE 'script_json=%' "
        "ORDER BY id DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    if not row:
        return None
    raw = row[0]
    if raw.startswith("script_json="):
        raw = raw[len("script_json=") :]
    return raw


def restore_full(job_id: int) -> None:
    """从 job_log 和 segments_wan 归档恢复被误清的数据。"""
    conn = sqlite3.connect(str(SERVER_DB))
    media = SERVER_MEDIA_ROOT / str(job_id)

    raw = get_job_log_script(conn, job_id)
    if not raw:
        print(f"ERROR: job {job_id}: no script_json found in job_log")
        sys.exit(1)
    script = json.loads(raw)
    conn.execute(
        "UPDATE video_job SET script_json=?, status='pending', stage='segment', "
        "error_message=NULL WHERE id=?",
        (json.dumps(script, ensure_ascii=False), job_id),
    )
    print(
        f"[1/6] script_json restored "
        f"({len(raw)} bytes, {len(script.get('segments', []))} segments)"
    )

    conn.execute("DELETE FROM video_segment WHERE job_id=?", (job_id,))
    segments = script.get("segments", [])
    for seg in segments:
        idx = seg["segment_index"]
        conn.execute(
            "INSERT INTO video_segment (job_id, segment_index, text, image_prompt, "
            "motion_prompt, visual_mode, duration_sec, sd15_prompt_en, image_path, "
            "clip_path, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                idx,
                seg.get("text"),
                seg.get("image_prompt"),
                seg.get("motion_prompt"),
                seg.get("visual_mode"),
                seg.get("duration_sec"),
                seg.get("sd15_prompt_en"),
                None,
                None,
                "pending",
            ),
        )
    print(f"[2/6] video_segment restored ({len(segments)} rows)")

    images_dir = media / "images"
    ok = 0
    if images_dir.exists():
        files = sorted(images_dir.glob("*.agnes_source_url"))
        for sf in files:
            idx = sf.name.split(".png.")[0]
            url = sf.read_text().strip()
            target = images_dir / f"{idx}.png"
            if target.exists():
                ok += 1
                continue
            try:
                urllib.request.urlretrieve(url, str(target))
                ok += 1
            except Exception as exc:
                print(f"  WARN: {idx}.png download failed: {exc}")
        print(f"[3/6] images restored ({ok}/{len(files)})")
    else:
        print("[3/6] images dir not found, skipping")

    wan_dir = media / "segments_wan"
    seg_dir = media / "segments"
    restored_seg = 0
    if wan_dir.exists():
        seg_dir.mkdir(parents=True, exist_ok=True)
        for v in sorted(wan_dir.glob("*.mp4")):
            t = seg_dir / v.name
            if not t.exists():
                shutil.copy2(v, t)
            restored_seg += 1
        print(f"[4/6] segment videos restored ({restored_seg} from segments_wan)")

        rows = conn.execute(
            "SELECT segment_index FROM video_segment WHERE job_id=?",
            (job_id,),
        ).fetchall()
        c = 0
        for r in rows:
            idx = r[0]
            p = str(seg_dir / f"{idx}.mp4")
            if Path(p).exists():
                conn.execute(
                    "UPDATE video_segment SET clip_path=? "
                    "WHERE job_id=? AND segment_index=?",
                    (p, job_id, idx),
                )
                c += 1
        print(f"     clip_path restored ({c}/{len(rows)})")
    else:
        print("[4/6] segments_wan not found, skipping")

    s = str(media)
    conn.execute(
        "UPDATE video_job SET audio_path=?, subtitle_path=?, intro_path=?, "
        "final_path=? WHERE id=?",
        (
            f"{s}/audio/narration.mp3",
            f"{s}/audio/subtitles.srt",
            f"{s}/intro.mp4",
            f"{s}/final_wan.mp4",
            job_id,
        ),
    )
    rows = conn.execute(
        "SELECT segment_index FROM video_segment WHERE job_id=?",
        (job_id,),
    ).fetchall()
    img_cnt = 0
    for r in rows:
        idx = r[0]
        ip = f"{s}/images/{idx}.png"
        if Path(ip).exists():
            conn.execute(
                "UPDATE video_segment SET image_path=? "
                "WHERE job_id=? AND segment_index=?",
                (ip, job_id, idx),
            )
            img_cnt += 1
    print(
        f"[5/6] database paths restored "
        f"(images={img_cnt}/{len(rows)}, final=final_wan.mp4)"
    )

    conn.commit()
    conn.close()
    print("\n[6/6] DONE. 提示：TTS 配音需手动调用 /v_factory/api/jobs/tts 重新生成。")


def restore_media_paths(job_id: int, *, dry_run: bool = False) -> dict:
    """按磁盘文件恢复分镜 image_path / clip_path。"""
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


def cmd_full(args: argparse.Namespace) -> int:
    restore_full(args.job_id)
    return 0


def cmd_media_paths(args: argparse.Namespace) -> int:
    result = restore_media_paths(args.job_id, dry_run=args.dry_run)
    print(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="恢复 job 数据")
    sub = parser.add_subparsers(dest="command", required=True)

    p_full = sub.add_parser("full", help="从 job_log / 归档完整恢复")
    p_full.add_argument("job_id", type=int)
    p_full.set_defaults(func=cmd_full)

    p_media = sub.add_parser("media-paths", help="按磁盘回填 image/clip 路径")
    p_media.add_argument("job_id", type=int)
    p_media.add_argument("--dry-run", action="store_true")
    p_media.set_defaults(func=cmd_media_paths)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
