"""一次性本地跑脚本生成（调试用）。"""

from __future__ import annotations

import sys
import time

from app.services.llm.llm_mgr import llm_mgr
from app.utils.job_info import CONTENT_STYLE_LIFE_EXPERIENCE
from app.utils.media import narration_accept_min_chars, narration_target_for_minutes
from worker.stages.standard.script import _min_narration_chars, _validate_script

TITLE = "瓦斯逃生湿布捂口鼻？致命误区别犯"
SEG_TARGET = 28.0
TARGET = narration_target_for_minutes(6.0)
ACCEPT = narration_accept_min_chars(TARGET)
HARD = _min_narration_chars(TARGET)


def main() -> int:
    job = {
        "id": 0,
        "pipeline": "standard",
        "content_style": CONTENT_STYLE_LIFE_EXPERIENCE,
        "info": {
            "orientation": "landscape",
            "content_style": CONTENT_STYLE_LIFE_EXPERIENCE,
        },
    }

    print(f"title={TITLE}")
    print(f"target={TARGET} accept={ACCEPT} hard_floor={HARD} seg_target={SEG_TARGET}s")
    print("--- generating storyboard (no image_prompts) ---")
    started = time.perf_counter()
    script = llm_mgr.generate_script(
        TITLE,
        segment_target_sec=SEG_TARGET,
        narration_target_words=TARGET,
        job=job,
        generate_image_prompts=False,
    )
    storyboard_sec = time.perf_counter() - started
    words = script.get("word_count") or len(script.get("narration", "").replace(" ", ""))
    segs = len(script.get("segments") or [])
    timing = script.get("_llm_timing") or {}
    print(f"storyboard done: segments={segs} words={words} elapsed={storyboard_sec:.1f}s timing={timing}")

    try:
        warnings = _validate_script(
            script,
            segment_target_sec=SEG_TARGET,
            min_narration_chars=HARD,
            accept_narration_chars=ACCEPT,
            narration_target_words=TARGET,
            require_image_prompt=False,
        )
        print(f"validation: PASS warnings={warnings}")
    except Exception as exc:
        print(f"validation: FAIL {exc}")
        return 1

    print("--- generating image_prompts ---")
    ip_started = time.perf_counter()
    llm_mgr.fill_image_prompts(script, job=job)
    ip_sec = time.perf_counter() - ip_started
    try:
        _validate_script(
            script,
            segment_target_sec=SEG_TARGET,
            min_narration_chars=HARD,
            accept_narration_chars=ACCEPT,
            narration_target_words=TARGET,
            require_image_prompt=True,
            check_narration=False,
        )
        print(f"image_prompts: PASS elapsed={ip_sec:.1f}s")
    except Exception as exc:
        print(f"image_prompts: FAIL {exc}")
        return 1

    total = time.perf_counter() - started
    print(f"--- total={total:.1f}s title={script.get('title')} ---")
    print(f"accept_ratio={words / TARGET:.1%} need>={ACCEPT}")
    narration = script.get("narration") or ""
    if narration:
        print("narration_preview:", narration[:200], "...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
