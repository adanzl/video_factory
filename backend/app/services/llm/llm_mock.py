from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.services.llm.llm_mgr import LLMClient


class MockLLMClient(LLMClient):
    def generate_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
    ) -> dict[str, Any]:
        _ = feedback
        settings = get_settings()
        display_title = re.sub(r"\s+", "", title.strip())
        max_len = settings.max_title_length if max_title_length is None else max_title_length
        seg_target = (
            settings.segment_target_sec if segment_target_sec is None else segment_target_sec
        )
        if len(display_title) > max_len:
            display_title = display_title[:max_len]
        if seg_target > 0:
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
        visual_style = "3D卡通渲染科普插画，暖黄侧光，浅木色场景，银红条形磁铁统一造型"
        segments = []
        narration_parts: list[str] = []
        for idx, text in enumerate(templates, start=1):
            narration_parts.append(text)
            brief = f"第{idx}镜：围绕「{display_title}」展示一个生活化科普场景与关键对比。"
            image_prompt = (
                f"采用中景竖屏构图的3D卡通渲染科普插画，严格遵循画风：{visual_style}。"
                f"本镜对应口播主题，场景序号{idx}，主体居中略偏上，留出下方字幕安全区，"
                f"单一视觉焦点落在核心道具或对比物上，明亮温馨不压抑。"
                f"前景浅木色台面有轻微景深虚化，中景主体道具造型统一、边缘高光清晰，"
                f"背景为虚化家居轮廓与暖色墙面，左上方暖黄窗光为主光，右侧冷白补光勾边，"
                f"材质区分木质纹理、金属反光与塑料哑光，主色银白暖木辅以少量红色点缀，"
                f"若本镜含对比则左右并排两状态并用箭头连接，辅色点缀提升层次，"
                f"整体氛围清晰易懂、适合竖屏短视频科普表达，画面无文字无水印，"
                f"仅表达当前分镜内容，不提前展示后续情节。"
            )
            segments.append(
                {
                    "segment_index": idx,
                    "text": text,
                    "visual_brief": brief,
                    "image_prompt": image_prompt,
                    "motion_prompt": "镜头缓慢推近主体，指示箭头轻微延伸，整体保持轻微呼吸感。",
                    "visual_mode": "static_motion",
                }
            )
        narration = "\n".join(narration_parts)
        return {
            "title": display_title,
            "narration": narration,
            "word_count": len(re.sub(r"\s+", "", narration)),
            "visual_style": visual_style,
            "segments": segments,
        }

    def optimize_script_title(
        self,
        draft_title: str,
        narration: str,
        *,
        max_title_length: int | None = None,
    ) -> str:
        _ = narration
        from app.services.llm.llm_topics import normalize_title

        settings = get_settings()
        max_len = settings.max_title_length if max_title_length is None else max_title_length
        cleaned = re.sub(r"\s+", "", draft_title.strip())
        if "？" in cleaned or "?" in cleaned:
            optimized = cleaned
        elif cleaned.endswith("吗"):
            optimized = f"{cleaned}？"
        else:
            optimized = f"{cleaned}，多数人不知道？"
        return normalize_title(optimized, max_len=max_len)

    def generate_topics(
        self,
        theme: str,
        *,
        count: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        _ = system_prompt
        settings = get_settings()
        count = max(1, min(count, 20))
        theme = re.sub(r"\s+", "", theme.strip()) or "科普"
        if user_prompt:
            theme = re.sub(r"\s+", "", user_prompt.strip()) or theme
        max_len = settings.max_title_length
        patterns = [
            ("误区反问式", "日常科学原理", f"{theme}里最常见的误区，你中招了吗？"),
            ("误区反问式", "生活避坑实用常识", f"关于{theme}，多数人第一步就错了？"),
            ("反差好奇式", "日常科学原理", f"同样是{theme}，为什么结果差这么多？"),
            ("误区反问式", "数码小白避坑", f"{theme}越贵越好？真相可能相反"),
            ("实操避坑式", "生活避坑实用常识", f"{theme}暗藏陷阱？三招快速辨别"),
            ("误区反问式", "古代冷门生活史", f"古人没有现代工具，怎么解决{theme}？"),
            ("反差好奇式", "日常科学原理", f"看起来一样的{theme}，原理完全不同？"),
            ("误区反问式", "生活避坑实用常识", f"{theme}这样做，反而更危险？"),
            ("误区反问式", "数码小白避坑", f"买{theme}只看参数？最容易踩的坑"),
            ("实操避坑式", "日常科学原理", f"一文搞懂{theme}：别被直觉骗了"),
        ]
        tracks_hooks = {
            "日常科学原理": "反常识原理最容易引发好奇点击",
            "生活避坑实用常识": "生活误区是稳定长尾搜索流量",
            "数码小白避坑": "参数误区对小白用户转化高",
            "古代冷门生活史": "古今对比制造新鲜感和完播",
        }
        out: list[dict[str, str]] = []
        for template, track, title in patterns[:count]:
            display = title[:max_len]
            out.append(
                {
                    "title": display,
                    "track": track,
                    "template": template,
                    "hook": tracks_hooks[track],
                }
            )
        return out
