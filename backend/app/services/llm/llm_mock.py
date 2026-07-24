from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.services.llm.llm_mgr import LLMClient
from app.quality.image_prompt import MIN_IMAGE_PROMPT_CHARS
from app.utils.media import (
    DEFAULT_SPEECH_CHARS_PER_SEC,
    segment_text_char_cap,
    split_narration_to_segments,
)


def _mock_image_prompt(visual_style: str, display_title: str, idx: int) -> str:
    return (
        f"采用中景竖屏构图的3D卡通渲染科普插画，严格遵循画风：{visual_style}。"
        f"本镜对应口播主题，场景序号{idx}，主体居中略偏上，留出下方字幕安全区，"
        f"单一视觉焦点落在核心道具或对比物上，明亮温馨不压抑。"
        f"前景浅木色台面有轻微景深虚化，中景主体道具造型统一、边缘高光清晰，"
        f"背景为虚化家居轮廓与暖色墙面，左上方暖黄窗光为主光，右侧冷白补光勾边，"
        f"材质区分木质纹理、金属反光与塑料哑光，主色银白暖木辅以少量红色点缀，"
        f"若本镜含对比则左右并排两状态并用箭头连接，辅色点缀提升层次，"
        f"整体氛围清晰易懂、适合竖屏短视频科普表达，画面无文字无水印，"
        f"仅表达当前分镜内容，不提前展示后续情节。"
        f"主题围绕「{display_title}」展开。"
    )


def _mock_motion_prompt() -> str:
    return "镜头缓慢推近主体，指示箭头轻微延伸，整体保持轻微呼吸感。"


class MockLLMClient(LLMClient):
    def generate_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        existing_script: dict | None = None,
        retry_scope: str | None = None,
        generate_image_prompts: bool = True,
    ) -> dict[str, Any]:
        _ = feedback, supplementary_info, job, narration_target_words
        if retry_scope == "image_prompts" and existing_script is not None:
            if generate_image_prompts:
                return self.fill_image_prompts(existing_script)
            return existing_script
        if retry_scope == "visual_brief" and existing_script is not None:
            for idx, seg in enumerate(existing_script.get("segments") or [], start=1):
                display_title = re.sub(
                    r"\s+",
                    "",
                    str(existing_script.get("title") or "科普").strip(),
                ) or "科普"
                seg["visual_brief"] = (
                    f"第{idx}镜：围绕「{display_title}」展示一个生活化科普场景与关键对比。（写实场景）"
                )
            return existing_script
        data = self.generate_storyboard(
            title,
            segment_target_sec=segment_target_sec,
            max_title_length=max_title_length,
        )
        if generate_image_prompts:
            return self.fill_image_prompts(data)
        for seg in data.get("segments") or []:
            seg.pop("image_prompt", None)
            seg.pop("motion_prompt", None)
        return data

    def generate_storyboard(
        self,
        title: str,
        *,
        feedback: str | None = None,
        segment_target_sec: float | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        _ = feedback, supplementary_info, job, narration_target_words
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
        narration = "".join(templates)
        segments = split_narration_to_segments(narration, seg_target)
        for idx, seg in enumerate(segments, start=1):
            seg["segment_index"] = idx
            seg["visual_brief"] = (
                f"第{idx}镜：围绕「{display_title}」展示一个生活化科普场景与关键对比。（写实场景）"
            )
            seg["image_prompt"] = _mock_image_prompt(visual_style, display_title, idx)
            seg["motion_prompt"] = _mock_motion_prompt()
        return {
            "title": display_title,
            "narration": narration,
            "word_count": len(re.sub(r"\s+", "", narration)),
            "visual_style": visual_style,
            "segments": segments,
        }

    def fill_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        _ = feedback, supplementary_info, job
        visual_style = script.get("visual_style") or (
            "3D卡通渲染科普插画，暖黄侧光，浅木色场景，银红条形磁铁统一造型"
        )
        display_title = re.sub(r"\s+", "", str(script.get("title") or "科普").strip()) or "科普"
        allowed = {int(i) for i in segment_indices} if segment_indices else None
        for seg in script.get("segments") or []:
            idx = int(seg["segment_index"])
            if allowed is not None and idx not in allowed:
                continue
            if len(str(seg.get("image_prompt") or "")) >= MIN_IMAGE_PROMPT_CHARS:
                continue
            seg.setdefault(
                "visual_brief",
                f"第{idx}镜：围绕「{display_title}」展示一个生活化科普场景与关键对比。",
            )
            seg["image_prompt"] = _mock_image_prompt(visual_style, display_title, idx)
            seg.setdefault("motion_prompt", _mock_motion_prompt())
        return script

    def fill_visual_briefs(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
        supplementary_info: str | None = None,
        job: dict | None = None,
        segment_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        _ = feedback, supplementary_info, job
        display_title = (
            re.sub(r"\s+", "", str(script.get("title") or "科普").strip()) or "科普"
        )
        allowed = {int(i) for i in segment_indices} if segment_indices else None
        for seg in script.get("segments") or []:
            idx = int(seg["segment_index"])
            if allowed is not None and idx not in allowed:
                continue
            seg["visual_brief"] = (
                f"第{idx}镜：围绕「{display_title}」展示一个生活化科普场景与关键对比。（写实场景）"
            )
            seg.setdefault("visual_mode", "static_motion")
        return script

    def shrink_segment_texts(
        self,
        script: dict[str, Any],
        *,
        segment_indices: list[int],
        segment_target_sec: float,
        job: dict | None = None,
        chars_per_sec: float | None = None,
    ) -> dict[str, Any]:
        _ = job
        cps = chars_per_sec if chars_per_sec is not None else DEFAULT_SPEECH_CHARS_PER_SEC
        cap = segment_text_char_cap(segment_target_sec, chars_per_sec=cps)
        allowed = {int(i) for i in segment_indices}
        for seg in script.get("segments") or []:
            idx = int(seg["segment_index"])
            if idx not in allowed:
                continue
            text = str(seg.get("text") or "")
            compact = re.sub(r"\s+", "", text)
            if len(compact) <= cap:
                continue
            seg["text"] = compact[:cap]
        ordered = sorted(
            script.get("segments") or [],
            key=lambda s: int(s.get("segment_index") or 0),
        )
        narration = "".join(str(seg.get("text") or "") for seg in ordered)
        script["narration"] = narration
        script["word_count"] = len(re.sub(r"\s+", "", narration))
        return script

    def generate_material_script(
        self,
        title: str,
        *,
        feedback: str | None = None,
        max_title_length: int | None = None,
        narration_target_words: int | None = None,
        supplementary_info: str | None = None,
        video_timeline: str | None = None,
        job: dict | None = None,
    ) -> dict[str, Any]:
        _ = feedback, narration_target_words, supplementary_info, video_timeline, job
        base = self.generate_script(
            title,
            segment_target_sec=0,
            max_title_length=max_title_length,
        )
        segments = []
        for seg in base["segments"]:
            segments.append(
                {
                    "segment_index": seg["segment_index"],
                    "text": seg["text"],
                    "visual_mode": "material",
                }
            )
        return {
            "title": base["title"],
            "narration": base["narration"],
            "word_count": base["word_count"],
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
        from app.services.topic.text import normalize_title

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

    def generate_video_description(
        self,
        title: str,
        narration: str,
        *,
        content_style: str | None = None,
    ) -> str:
        _ = narration
        cleaned = re.sub(r"\s+", "", title.strip()) or "日常"
        if content_style == "daily_story":
            return (
                f"家里又吵起来了：{cleaned}。\n"
                f"姐弟抬杠笑点一触即发。\n"
                f"#亲子日常 #{cleaned}"
            )
        return (
            f"你以为自己懂{cleaned}？很多人第一反应都错了。\n"
            f"一分钟讲清核心原理，帮你看懂常见误区。\n"
            f"#科普 #{cleaned}"
        )

    def generate_tags(
        self,
        title: str,
        narration: str,
        *,
        content_style: str | None = None,
    ) -> list[str]:
        _ = narration
        cleaned = re.sub(r"\s+", "", title.strip()) or "日常"
        if content_style == "daily_story":
            return [
                "#亲子日常",
                "#儿童对话",
                "#姐弟",
                "#家庭搞笑",
                "#育儿",
                "#生活日常",
                "#昭墨日常",
                f"#{cleaned}",
            ]
        return [
            "#科普",
            "#冷知识",
            "#涨知识",
            f"#{cleaned}",
            "#科学",
            "#实验",
            "#原理",
            "#知识分享",
        ]

    def rewrite_pixabay_query(
        self,
        query: str,
        *,
        language: str | None = None,
    ) -> str:
        _ = language
        cleaned = query.strip()
        if re.search(r"[\u3400-\u9fff]", cleaned):
            if "磁" in cleaned:
                return "magnet experiment"
            if "水" in cleaned or "海" in cleaned:
                return "water ocean"
            return "science experiment"
        return cleaned.lower()

    def prepare_sd15_image_prompt(
        self,
        prompt: str,
        *,
        size_hint: str | None = None,
        business_override: str | None = None,
    ) -> dict[str, str]:
        from app.services.segment.image.image_sd15 import (
            fallback_split_panel_prompts,
            normalize_sd15_prompt_en,
            parse_image_size,
            pick_business_by_keywords,
            pick_lora_by_keywords,
            resolve_split_layout,
        )

        _ = size_hint
        cleaned = prompt.strip()
        lora = pick_lora_by_keywords(cleaned)
        if business_override in {"life", "science"}:
            business = business_override
        else:
            business = pick_business_by_keywords(cleaned)
        prompt_en = normalize_sd15_prompt_en(
            self.rewrite_pixabay_query(cleaned),
            business=business,
            lora=lora,
        )

        width, height = parse_image_size(size_hint) if size_hint else (0, 0)
        layout, split_axis = resolve_split_layout(
            result=None,
            prompt=cleaned,
            business=business,
            width=width,
            height=height,
        )
        if layout == "split":
            left_en, right_en = fallback_split_panel_prompts(cleaned)
            return {
                "layout": "split",
                "split_axis": split_axis,
                "left_en": left_en,
                "right_en": right_en,
                "business": business,
                "lora": lora,
            }
        return {"layout": "single", "prompt_en": prompt_en, "business": business, "lora": lora}

    def generate_topics(
        self,
        theme: str,
        *,
        count: int = 10,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        category: str | None = None,
        keywords: str | list[str] | None = None,
    ) -> list[dict[str, str]]:
        _ = (system_prompt, keywords)
        from app.services.topic.catalog import (
            CATEGORY_HISTORY,
            CATEGORY_SCIENCE,
            get_category_spec,
            resolve_category,
        )

        settings = get_settings()
        count = max(1, min(count, 20))
        theme = re.sub(r"\s+", "", theme.strip()) or "科普"
        if user_prompt:
            theme = re.sub(r"\s+", "", user_prompt.strip()) or theme
        max_len = settings.max_title_length
        resolved = resolve_category(category)
        spec = get_category_spec(resolved)

        if resolved == CATEGORY_HISTORY:
            patterns = [
                ("悬念钩子式", CATEGORY_HISTORY, "烛影斧声：宋太祖半夜暴毙"),
                ("未解之谜式", CATEGORY_HISTORY, "建文帝下落：紫禁城大火后消失"),
                ("误区反问式", CATEGORY_HISTORY, "和珅贪亿两白银？嘉庆抄家才懂"),
                ("反差好奇式", CATEGORY_HISTORY, "雍正勤政猝死：圆明园咯血无人敢近"),
            ]
            hooks = {CATEGORY_HISTORY: "知名历史人物悬案最容易引发点击"}
        else:
            patterns = [
                ("误区反问式", CATEGORY_SCIENCE, f"{theme}里最常见的误区，你中招了吗？"),
                ("误区反问式", CATEGORY_SCIENCE, f"关于{theme}，多数人第一步就错了？"),
                ("反差好奇式", CATEGORY_SCIENCE, f"同样是{theme}，为什么结果差这么多？"),
                ("实操避坑式", CATEGORY_SCIENCE, f"{theme}暗藏陷阱？三招快速辨别"),
                ("误区反问式", CATEGORY_SCIENCE, f"看起来一样的{theme}，原理完全不同？"),
            ]
            hooks = {CATEGORY_SCIENCE: "反常识原理最容易引发好奇点击"}

        out: list[dict[str, str]] = []
        for tpl, cat, title in patterns[:count]:
            display = title[:max_len]
            out.append(
                {
                    "title": display,
                    "category": cat,
                    "template": tpl,
                    "hook": hooks.get(cat, spec.default_theme),
                }
            )
        return out

    def generate_daily_script(
        self,
        dialogue_script: dict,
        *,
        job: dict | None = None,
        chars_per_sec: float | None = None,
    ) -> dict[str, Any]:
        _ = job, chars_per_sec
        dialogue = dialogue_script.get("dialogue", [])
        # 按 8-10 个镜头模拟
        scene_count = min(10, max(8, (len(dialogue) + 2) // 3))
        per_scene = max(2, (len(dialogue) + scene_count - 1) // scene_count)
        scenes = []
        for i in range(scene_count):
            start = i * per_scene
            end = min(start + per_scene, len(dialogue))
            if start >= len(dialogue):
                break
            lines = dialogue[start:end]
            dialogue_data = [
                {"speaker": d["speaker"], "text": d["line"]}
                for d in lines
            ]
            shot_types = ["全景", "中景", "特写"]
            shot = shot_types[i % 3]
            if shot == "特写" and len(lines) > 2:
                shot = "中景"
            scenes.append({
                "scene_id": i + 1,
                "shot_type": shot,
                "dialogue": dialogue_data,
                "img2img_prompt": (
                    "剪贴画风格，扁平插画，纸张纹理，明亮色彩，无阴影，几何图形简洁，"
                    f"{shot}，家庭场景，"
                    "昭昭男孩气黑色超短发（发长在耳垂以上，清晰露出双耳及整个后颈，齐耳学生头），蓝色短袖T恤，比姐姐矮一点；灿灿单侧高马尾（仅一根），粉色卫衣。"
                ),
            })
        return {
            "scenes": scenes,
        }

    def generate_daily_story(
        self,
        theme: str,
        *,
        story_type: str | None = None,
    ) -> dict[str, Any]:
        from app.services.daily_story.prompts import (
            DAILY_STORY_BODY_CHARS_MIN,
            DAILY_STORY_LINE_CHARS_MAX,
            dialogue_total_chars,
            stitch_daily_story_opening,
            validate_daily_story_json,
        )

        pad = "一二三四五六七八九十一二三四五六七八"[:DAILY_STORY_LINE_CHARS_MAX]
        speakers = ("昭昭", "灿灿")
        # 正文从互怼起，不含发现开场；凑满正文下限
        body_lines: list[dict[str, str]] = [
            {"speaker": "昭昭", "line": "这橡皮明明是我先拿到的呀"},
            {"speaker": "灿灿", "line": "规则是谁看见谁就能拿"},
            {"speaker": "昭昭", "line": "那你刚才明明没看见"},
            {"speaker": "灿灿", "line": "我说看见了就算看见了"},
            {"speaker": "昭昭", "line": "那你规则自己说了不算"},
            {"speaker": "灿灿", "line": "姐姐说的规则当然算数"},
            {"speaker": "昭昭", "line": "那我也可以说新规则"},
            {"speaker": "灿灿", "line": "你还小你说了不算"},
            {"speaker": "昭昭", "line": "你刚才也说谁看见谁拿"},
            {"speaker": "灿灿", "line": "那是对你说的规矩"},
            {"speaker": "昭昭", "line": "规矩怎么能两套标准"},
            {"speaker": "灿灿", "line": "因为我是姐姐"},
            {"speaker": "昭昭", "line": "姐姐也不能自己改规则"},
            {"speaker": "灿灿", "line": "好好好算你说得有点道理"},
            {"speaker": "昭昭", "line": "那橡皮先放中间谁都别抢"},
            {"speaker": "灿灿", "line": "行吧今天听你这一回"},
        ]
        i = 0
        while dialogue_total_chars({"dialogue": body_lines}) < DAILY_STORY_BODY_CHARS_MIN:
            body_lines.insert(
                -2,
                {"speaker": speakers[i % 2], "line": pad},
            )
            i += 1
        body = {
            "scene_title": "测试场景",
            "setting": f"家里客厅，姐弟俩围绕{theme}争新橡皮",
            "conflict_core": f"姐弟争{theme}"[:24] if theme else "姐弟抢新橡皮",
            "dialogue": body_lines,
            "punchline_explain": "C类公平执念，弟弟戳穿双标规则",
        }
        # 保证 conflict 锚点可进 setting
        if "橡皮" not in body["conflict_core"]:
            body["conflict_core"] = "姐弟抢新橡皮"
            body["setting"] = f"家里客厅，围绕{theme}抢新橡皮"
        opening = [
            {"speaker": "昭昭", "line": "咦这个新橡皮你怎么攥着"},
        ]
        story = stitch_daily_story_opening(body, opening)
        validate_daily_story_json(story, phase="full")
        return story

    def generate_daily_story_themes(self, count: int = 15) -> list[str]:
        themes = ["争最后一瓶酸奶", "谁先洗澡", "检查作业时发现错题", "抢着开门接快递"]
        return themes[:count]
