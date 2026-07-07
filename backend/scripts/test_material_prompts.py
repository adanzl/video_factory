"""测试 material script prompt 结构：有时间表 vs 无时间表。"""

from __future__ import annotations

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

from app.services.script.board import build_material_script_prompts


_TIMELINE_7SCENES = r"""{
  "title": "美国建国250周年无人机庆典",
  "duration_sec": 189.0,
  "scenes": [
    {
      "index": 1, "scene": "序幕 — 星条旗永不落",
      "start_sec": 0.0, "end_sec": 40.0, "duration_sec": 40.0
    },
    {
      "index": 2, "scene": "致敬国父与山姆大叔",
      "start_sec": 40.0, "end_sec": 60.0, "duration_sec": 20.0
    },
    {
      "index": 3, "scene": "二战荣光 — 飞虎队与珍珠港",
      "start_sec": 60.0, "end_sec": 85.0, "duration_sec": 25.0
    },
    {
      "index": 4, "scene": "太空辉煌 — 从土星5号到SLS",
      "start_sec": 85.0, "end_sec": 120.0, "duration_sec": 35.0
    },
    {
      "index": 5, "scene": "阿波罗与阿尔忒弥斯 — 人类登月之路",
      "start_sec": 120.0, "end_sec": 150.0, "duration_sec": 30.0
    },
    {
      "index": 6, "scene": "自由之鹰 — 白头海雕",
      "start_sec": 150.0, "end_sec": 170.0, "duration_sec": 20.0
    },
    {
      "index": 7, "scene": "致敬与终章 — 三千次致敬",
      "start_sec": 170.0, "end_sec": 189.0, "duration_sec": 19.0
    }
  ]
}"""


def main():
    title = "磁铁吸不锈钢是次品吗？"

    # ── 场景1：有时间表 ──
    print("=" * 70)
    print("场景1: 有时间表（7段）")
    print("=" * 70)
    prompts1 = build_material_script_prompts(
        title,
        video_timeline=_TIMELINE_7SCENES,
        max_title_length=16,
        narration_target_words=800,
    )
    print("--- SYSTEM ---")
    print(prompts1["system"])
    print("\n--- USER ---")
    print(prompts1["user"])
    print()

    # ── 场景2：无时间表 ──
    print("=" * 70)
    print("场景2: 无时间表")
    print("=" * 70)
    prompts2 = build_material_script_prompts(
        title,
        max_title_length=16,
        narration_target_words=800,
    )
    print("--- SYSTEM ---")
    print(prompts2["system"])
    print("\n--- USER ---")
    print(prompts2["user"])


if __name__ == "__main__":
    main()
