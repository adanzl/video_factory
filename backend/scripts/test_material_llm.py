"""调 LLM 测试 material script：有时间表 vs 无时间表。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

from app.services.script.board import build_material_script_prompts
from app.services.script.board_timeline import _max_chars_for_duration, slot_min_chars
from app.services.llm.llm_deepseek import DeepSeekClient


_TIMELINE = {
    "title": "测试",
    "duration_sec": 189.0,
    "scenes": [
        {"index": 1, "scene": "序幕 — 星条旗永不落", "description": "无人机编队升空，形成大型星条旗图案",
         "start_sec": 0.0, "end_sec": 40.0, "duration_sec": 40.0},
        {"index": 2, "scene": "致敬国父与山姆大叔", "description": "乔治·华盛顿肖像无人机编队",
         "start_sec": 40.0, "end_sec": 60.0, "duration_sec": 20.0},
        {"index": 3, "scene": "二战荣光", "description": "P-40战斧战斗机鲨鱼嘴涂装",
         "start_sec": 60.0, "end_sec": 85.0, "duration_sec": 25.0},
        {"index": 4, "scene": "太空辉煌", "description": "土星5号火箭升空",
         "start_sec": 85.0, "end_sec": 120.0, "duration_sec": 35.0},
        {"index": 5, "scene": "阿波罗与阿尔忒弥斯", "description": "阿波罗飞船月球轨道",
         "start_sec": 120.0, "end_sec": 150.0, "duration_sec": 30.0},
        {"index": 6, "scene": "自由之鹰", "description": "白头海雕展翅翱翔",
         "start_sec": 150.0, "end_sec": 170.0, "duration_sec": 20.0},
        {"index": 7, "scene": "致敬与终章", "description": "THANK YOU 3000字样",
         "start_sec": 170.0, "end_sec": 189.0, "duration_sec": 19.0},
    ],
}
_TIMELINE_JSON = json.dumps(_TIMELINE, ensure_ascii=False)


def budget_table(timeline_str: str, cps: float):
    data = json.loads(timeline_str)
    for item in data.get("scenes") or data.get("segments") or []:
        dur = item.get("duration_sec", 0)
        mc = _max_chars_for_duration(dur, cps)
        mn = slot_min_chars(mc)
        print(f"  seg[{item['index']}] {item['scene']}: {dur}s → {mn}-{mc}")


def check(data: dict, label: str, cps: float | None = None, timeline: str | None = None):
    segs = data.get("segments") or []
    print(f"\n=== {label} ===")
    print(f"  title: {data.get('title')}")
    print(f"  narration chars: {len((data.get('narration') or '') or '')}, segments: {len(segs)}")
    if cps and timeline:
        budget_table(timeline, cps)
    for s in segs:
        idx = s.get("segment_index", "?")
        t = s.get("text", "") or ""
        print(f"    seg[{idx}] chars={len(t)} text={t[:100]}")
    print()


def main():
    client = DeepSeekClient()
    title = "磁铁吸不锈钢是次品吗？"
    cps = 4.1

    print(">>> 有时间表预算 (4.1 字/秒):")
    budget_table(_TIMELINE_JSON, cps)
    print()

    prompts1 = build_material_script_prompts(
        title, video_timeline=_TIMELINE_JSON, max_title_length=16,
        narration_target_words=800, chars_per_sec=cps,
    )
    data1, _ = client._chat_json(prompts1["system"], prompts1["user"])
    check(data1, "有时间表（7段）", cps=cps, timeline=_TIMELINE_JSON)

    prompts2 = build_material_script_prompts(
        title, max_title_length=16, narration_target_words=800,
    )
    data2, _ = client._chat_json(prompts2["system"], prompts2["user"])
    check(data2, "无时间表")


if __name__ == "__main__":
    main()
