"""调 LLM 测试 material script：有时间表 vs 无时间表。"""

from __future__ import annotations

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

from app.services.script.board import build_material_script_prompts
from app.services.llm.llm_deepseek import DeepSeekClient


def check(data: dict, label: str):
    n = (data.get("narration") or "") or ""
    segs = data.get("segments") or []
    joined = "".join(s.get("text", "") or "" for s in sorted(segs, key=lambda x: x.get("segment_index", 0)))
    ok = joined == n
    print(f"\n=== {label} ===")
    print(f"  title: {data.get('title')}")
    print(f"  narration chars: {len(n)}, segments: {len(segs)}")
    print(f"  joined == narration: {'✅' if ok else '❌'}")
    for s in segs:
        idx = s.get("segment_index", "?")
        t = s.get("text", "") or ""
        print(f"    seg[{idx}] chars={len(t)} text={t[:100]}")
    print()


_TIMELINE_7SCENES = r"""{
  "title": "美国建国250周年无人机庆典",
  "duration_sec": 189.0,
  "scenes": [
    {"index": 1, "scene": "序幕 — 星条旗永不落", "start_sec": 0.0, "end_sec": 40.0, "duration_sec": 40.0},
    {"index": 2, "scene": "致敬国父与山姆大叔", "start_sec": 40.0, "end_sec": 60.0, "duration_sec": 20.0},
    {"index": 3, "scene": "二战荣光 — 飞虎队与珍珠港", "start_sec": 60.0, "end_sec": 85.0, "duration_sec": 25.0},
    {"index": 4, "scene": "太空辉煌 — 从土星5号到SLS", "start_sec": 85.0, "end_sec": 120.0, "duration_sec": 35.0},
    {"index": 5, "scene": "阿波罗与阿尔忒弥斯 — 人类登月之路", "start_sec": 120.0, "end_sec": 150.0, "duration_sec": 30.0},
    {"index": 6, "scene": "自由之鹰 — 白头海雕", "start_sec": 150.0, "end_sec": 170.0, "duration_sec": 20.0},
    {"index": 7, "scene": "致敬与终章 — 三千次致敬", "start_sec": 170.0, "end_sec": 189.0, "duration_sec": 19.0}
  ]
}"""


def main():
    client = DeepSeekClient()
    title = "磁铁吸不锈钢是次品吗？"

    # 场景1：有时间表
    prompts1 = build_material_script_prompts(
        title, video_timeline=_TIMELINE_7SCENES, max_title_length=16, narration_target_words=800,
    )
    data1, _ = client._chat_json(prompts1["system"], prompts1["user"])
    check(data1, "有时间表（7段）")

    # 场景2：无时间表
    prompts2 = build_material_script_prompts(
        title, max_title_length=16, narration_target_words=800,
    )
    data2, _ = client._chat_json(prompts2["system"], prompts2["user"])
    check(data2, "无时间表")


if __name__ == "__main__":
    main()
