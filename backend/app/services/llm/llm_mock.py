from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.services.llm.llm_mgr import LLMClient


class MockLLMClient(LLMClient):
    def generate_script(self, title: str, *, feedback: str | None = None) -> dict[str, Any]:
        _ = feedback
        settings = get_settings()
        display_title = re.sub(r"\s+", "", title.strip())
        max_len = settings.max_title_length
        if len(display_title) > max_len:
            display_title = display_title[:max_len]
        if settings.segment_target_sec > 0:
            templates = [
                f"你有没有想过，{display_title}？很多人第一反应是凭直觉，但真相往往更复杂。",
                "今天我们从最基础的概念讲起，用生活里的例子帮你建立正确认知。",
                "首先，科学上会把现象拆成可测量的部分，而不是用一句口号盖棺定论。",
                "其次，常见误区来自以偏概全：个别案例被放大，忽略了统计规律与边界条件。",
                "第三，微生物和环境因素往往才是关键，不能只看表面现象。",
                "第四，包装、储存方式会改变保质期，不同场景结论完全不同。",
                "第五，消毒残留和密封性各有利弊，没有绝对的好坏。",
                "第六，开封之后的暴露时间，比出厂保质期更影响能不能喝。",
                "第七，实验室指标和日常体感的差距，需要分开理解。",
                "第八，厂家标注和实际保存条件，也决定了能放多久。",
                "第九，对比实验时要看变量是否一致，否则结论会跑偏。",
                "第十，日常做法里最简单稳妥的方法，往往被忽视。",
                "最后，遇到类似问题查权威来源，比听传言更可靠。",
            ]
        else:
            templates = [
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
        for idx, text in enumerate(templates):
            narration_parts.append(text)
            segments.append(
                {
                    "segment_index": idx,
                    "text": text,
                    "image_prompt": (
                        f"竖屏9:16卡通插画，扁平信息图风格，主题：{display_title}，"
                        f"场景{idx + 1}，无文字无水印"
                    ),
                    "visual_mode": "static_motion",
                }
            )
        narration = "\n".join(narration_parts)
        return {
            "title": display_title,
            "narration": narration,
            "word_count": len(re.sub(r"\s+", "", narration)),
            "segments": segments,
        }
