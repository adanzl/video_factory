"""从 job_log 和 segments_wan 归档恢复被误清的数据。
用法: conda run -n flask_env python scripts/restore_job.py <job_id>
"""
import argparse, json, sqlite3, sys, urllib.request
from pathlib import Path

DB = Path("/mnt/data/project/video_factory/data/data.db")
MEDIA_ROOT = Path("/mnt/data/project/video_factory/data/media")


def get_job_log_script(conn, job_id: int) -> str | None:
    """从 job_log 表提取最近的完整 script_json。"""
    row = conn.execute(
        "SELECT message FROM job_log WHERE job_id=? AND message LIKE 'script_json=%' ORDER BY id DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    if not row:
        return None
    raw = row[0]
    if raw.startswith("script_json="):
        raw = raw[len("script_json=") :]
    return raw


def restore(job_id: int) -> None:
    conn = sqlite3.connect(str(DB))
    media = MEDIA_ROOT / str(job_id)

    # 1. 恢复 script_json
    raw = get_job_log_script(conn, job_id)
    if not raw:
        print(f"ERROR: job {job_id}: no script_json found in job_log")
        sys.exit(1)
    script = json.loads(raw)
    conn.execute(
        "UPDATE video_job SET script_json=?, status='idle', stage='segment', error_message=NULL WHERE id=?",
        (json.dumps(script, ensure_ascii=False), job_id),
    )
    print(f"[1/6] script_json restored ({len(raw)} bytes, {len(script.get('segments',[]))} segments)")

    # 2. 恢复 video_segment 表
    conn.execute("DELETE FROM video_segment WHERE job_id=?", (job_id,))
    segments = script.get("segments", [])
    for seg in segments:
        idx = seg["segment_index"]
        conn.execute(
            "INSERT INTO video_segment (job_id, segment_index, text, image_prompt, motion_prompt, "
            "visual_mode, duration_sec, sd15_prompt_en, image_path, clip_path, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, idx, seg.get("text"), seg.get("image_prompt"), seg.get("motion_prompt"),
             seg.get("visual_mode"), seg.get("duration_sec"), seg.get("sd15_prompt_en"),
             None, None, "pending"),
        )
    print(f"[2/6] video_segment restored ({len(segments)} rows)")

    # 3. 恢复图片（从 .agnes_source_url 侧边文件）
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
            except Exception as e:
                print(f"  WARN: {idx}.png download failed: {e}")
        print(f"[3/6] images restored ({ok}/{len(files)})")
    else:
        print("[3/6] images dir not found, skipping")

    # 4. 恢复 segments 视频（从 segments_wan 归档）
    wan_dir = media / "segments_wan"
    seg_dir = media / "segments"
    restored_seg = 0
    if wan_dir.exists():
        seg_dir.mkdir(parents=True, exist_ok=True)
        for v in sorted(wan_dir.glob("*.mp4")):
            t = seg_dir / v.name
            if not t.exists():
                import shutil
                shutil.copy2(v, t)
            restored_seg += 1
        print(f"[4/6] segment videos restored ({restored_seg} from segments_wan)")

        # 马上更新 clip_path
        rows = conn.execute("SELECT segment_index FROM video_segment WHERE job_id=?", (job_id,)).fetchall()
        c = 0
        for r in rows:
            idx = r[0]
            p = str(seg_dir / f"{idx}.mp4")
            if Path(p).exists():
                conn.execute("UPDATE video_segment SET clip_path=? WHERE job_id=? AND segment_index=?",
                             (p, job_id, idx))
                c += 1
        print(f"     clip_path restored ({c}/{len(rows)})")
    else:
        print("[4/6] segments_wan not found, skipping")

    # 5. 恢复数据库路径
    s = str(media)
    conn.execute("UPDATE video_job SET audio_path=?, subtitle_path=?, intro_path=?, final_path=? WHERE id=?",
                 (f"{s}/audio/narration.mp3", f"{s}/audio/subtitles.srt",
                  f"{s}/intro.mp4", f"{s}/final_wan.mp4", job_id))
    rows = conn.execute("SELECT segment_index FROM video_segment WHERE job_id=?", (job_id,)).fetchall()
    img_cnt = 0
    for r in rows:
        idx = r[0]
        ip = f"{s}/images/{idx}.png"
        if Path(ip).exists():
            conn.execute("UPDATE video_segment SET image_path=? WHERE job_id=? AND segment_index=?",
                         (ip, job_id, idx))
            img_cnt += 1
    print(f"[5/6] database paths restored (images={img_cnt}/{len(rows)}, final=final_wan.mp4)")

    conn.commit()
    conn.close()
    print("\n[6/6] DONE. 提示：TTS 配音需手动调用 /v_factory/api/jobs/tts 重新生成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 job_log 恢复被清空的 job 数据")
    parser.add_argument("job_id", type=int, help="要恢复的 job ID")
    args = parser.parse_args()
    restore(args.job_id)
