"""临时脚本：展示单段 image_prompt 生成的 LLM 提示词"""
import json
import sqlite3
import sys
sys.path.insert(0, ".")

from app.services.script.image_prompt import build_image_prompts

conn = sqlite3.connect("../data/data.db")
conn.row_factory = sqlite3.Row

# 取最近一个有脚本的任务
row = conn.execute(
    "SELECT id, title, script_json FROM jobs WHERE script_json IS NOT NULL ORDER BY id DESC LIMIT 1"
).fetchone()

if not row:
    print("没有可用的任务")
    sys.exit(1)

job_id = row["id"]
script = json.loads(row["script_json"])
segments = script.get("segments") or []

if not segments:
    print(f"job {job_id} 没有分镜")
    sys.exit(1)

# 取第一个分镜的 segment_index
target_idx = int(segments[0]["segment_index"])
print(f"=== job_id={job_id} title={script.get('title', '')} ===")
print(f"=== 目标分镜 segment_index={target_idx} (共 {len(segments)} 段) ===\n")

# 生成单段提示词
prompts = build_image_prompts(
    script,
    job={"id": job_id, **row},
    segment_indices=[target_idx],
)

print("========== SYSTEM ==========")
print(prompts["system"])
print()
print("========== USER ==========")
print(prompts["user"])

conn.close()
