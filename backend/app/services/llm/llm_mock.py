from __future__ import annotations

import re
from typing import Any

from app.services.llm.llm_mgr import LLMClient


class MockLLMClient(LLMClient):
    def generate_script(self, title: str) -> dict[str, Any]:
        paragraphs = [
            f"你有没有想过，{title}？很多人第一反应是凭直觉判断，但真相往往更复杂。",
            "今天我们从最基础的概念讲起，用几个生活里的例子帮你建立正确认知。",
            "首先，科学上会把现象拆成可测量的部分，而不是用一句口号盖棺定论。",
            "其次，常见误区来自以偏概全：个别案例被放大，忽略了统计规律与边界条件。",
            "第三，判断时要区分相关和因果，别把同时出现当成谁导致了谁。",
            "最后，遇到争议话题，查权威来源、看实验设计，比听传言更可靠。",
            "记住：科普不是站队，而是把复杂问题讲清楚，让你下次能自己判断。",
        ]
        segments = []
        narration_parts: list[str] = []
        for idx, text in enumerate(paragraphs):
            narration_parts.append(text)
            segments.append(
                {
                    "segment_index": idx,
                    "text": text,
                    "image_prompt": (
                        f"科普插画，竖屏9:16，扁平信息图风格，主题：{title}，"
                        f"场景{idx + 1}：{text[:30]}"
                    ),
                    "visual_mode": "static_motion",
                }
            )
        narration = "\n".join(narration_parts)
        return {
            "title": title,
            "narration": narration,
            "word_count": len(re.sub(r"\s+", "", narration)),
            "segments": segments,
        }
