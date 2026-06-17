from __future__ import annotations

import json
from typing import Any

from app.config import get_settings
from app.services.llm.llm_mgr import LLMClient

# 中文口播约 7.5 字/秒（12s ≈ 90 字）
_CHARS_PER_SEC = 7.5
_MIN_IMAGE_PROMPT_CHARS = 200

_VISUAL_BRIEF_RULE = (
    "各段含segment_index,text,visual_brief,visual_mode=static_motion；"
    "各段text按顺序拼接须与narration全文一致。"
    "visual_brief为该镜画面描述（60-120字）：写清视觉主旨、关键动作或对比关系、"
    "场景类型与情绪，帮助后续扩写文生图提示词；不写镜头焦距、光线方向、材质参数等细节。"
    "另须输出visual_style：全片画风定调一句话（画风+主色调+跨镜统一元素如道具造型）。"
)

_IMAGE_PROMPT_RULE = (
    "根据每段口播text与visual_brief，扩写为文生图用的image_prompt"
    "和video用的motion_prompt。"
    "全片统一画风：电影级写实科普视觉，布光考究、景深自然、材质细节真实可辨，"
    "色彩明快有层次，适配9:16竖屏构图。所有分镜严格遵守此风格。"
    "每段image_prompt须300-500字，围绕一个视觉焦点展开（如主体特写、关键对比、核心原理可视化），"
    "避免要素平铺罗列。若口播涉及对比（A/B、前后变化），画面须并排展示两种状态，"
    "用箭头、流向线、对勾/叉号等视觉编码辅助说明，禁用可读文字/数字/化学式/水印。"
    "色调忌整体发灰，须有暖色点缀。"
    "须严格对应该段text与visual_brief，禁止提前画后续段落内容。"
    "每段motion_prompt须30-80字，描述画面如何运动，如镜头运动（推近/环绕/平移）、"
    "主体运动（旋转/流动/吸附/弹开）、指示动画（箭头延伸/对勾出现/光晕脉动）、"
    "原理可视化（电流流动/板块挤压/细胞分裂），要求自然流畅不突兀。"
    "若无明显运动，写'静态画面，轻微镜头呼吸感'。"
)


def _format_segment_target_sec(target: float) -> str | float:
    return int(target) if target == int(target) else target


def _storyboard_segment_rule(target: float) -> str:
    common = f"segments为分镜数组；{_VISUAL_BRIEF_RULE}"
    if target <= 0:
        return common + "不约束单镜时长，按口播内容逻辑切分，段数由内容决定。"
    sec = _format_segment_target_sec(target)
    lo = max(15, int(target * _CHARS_PER_SEC * 0.65))
    hi = max(20, int(target * _CHARS_PER_SEC))
    return (
        common
        + f"单镜口播上限{sec}秒；每段text约{lo}-{hi}字，单段禁止超过{hi}字；"
        "段数由口播总长与该上限动态决定，按自然断句切分。"
    )


class DeepSeekClient(LLMClient):
    def __init__(self) -> None:
        import requests

        self._requests = requests
        settings = get_settings()
        self._api_key = settings.deepseek_api_key
        self._base_url = settings.deepseek_base_url.rstrip("/")
        self._model = settings.deepseek_model

    def _chat(self, system: str, user: str) -> str:
        resp = self._requests.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 8192,
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _generate_storyboard(
        self, title: str, *, feedback: str | None = None
    ) -> dict[str, Any]:
        settings = get_settings()
        target = settings.segment_target_sec
        seg_rule = _storyboard_segment_rule(target)
        max_title = settings.max_title_length
        system = (
            "你是科普视频编剧。输出JSON，字段：title, narration, word_count, "
            "visual_style, segments。"
            f"title为精简后的视频标题，保留原标题核心意思，"
            f"不含空格换行，字数不超过{max_title}，适合封面最多三行展示。"
            f"{seg_rule}"
            "narration为完整口播，总字数950-1150（不含空格换行），口语化，结构完整有开头结尾；"
            "选题撑不满时可略短，但须结构完整。"
            "禁止口播开头自我介绍或人设铺垫；第一句直接进入主题或抛出问题。"
            "word_count必须等于narration实际字数，不得虚报。"
            "本步只写口播与画面描述visual_brief，不写image_prompt。"
        )
        if target > 0:
            sec = _format_segment_target_sec(target)
            split_hint = f"并按单镜口播上限{sec}秒动态切分分镜"
        else:
            split_hint = "并按口播内容逻辑动态切分分镜"
        user = (
            f"原标题：{title}\n"
            f"请输出精简 title（≤{max_title}字）、完整口播、visual_style 与分镜，{split_hint}。"
            "每段 visual_brief 写清该镜画面主旨与对比关系，便于下一步扩写文生图提示词。"
        )
        if feedback:
            user += f"\n\n上次不合格：{feedback}。请按要求重写。"
        data = json.loads(self._chat(system, user))
        if "segments" not in data:
            raise ValueError("LLM storyboard response missing segments")
        if not data.get("visual_style"):
            raise ValueError("LLM storyboard response missing visual_style")
        return data

    def _generate_image_prompts(
        self,
        script: dict[str, Any],
        *,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        segments = script["segments"]
        lines = [
            f"segment {seg['segment_index']}: "
            f"text={seg.get('text', '')!r}; visual_brief={seg.get('visual_brief', '')!r}"
            for seg in segments
        ]
        system = (
            "你是科普视频文生图与运动提示词专家。输出JSON，字段：image_prompts。"
            "image_prompts为数组，每项含segment_index、image_prompt与motion_prompt。"
            f"{_IMAGE_PROMPT_RULE}"
            "image_prompts须覆盖输入的每一段，segment_index一一对应，不得遗漏。"
        )
        user = (
            f"视频标题：{script.get('title', '')}\n"
            f"全片画风定调 visual_style：{script.get('visual_style', '')}\n\n"
            "各分镜口播与画面描述：\n"
            + "\n".join(lines)
            + "\n\n请为每段扩写 image_prompt。"
        )
        if feedback:
            user += f"\n\n上次不合格：{feedback}。请按要求重写。"
        data = json.loads(self._chat(system, user))
        prompts = data.get("image_prompts")
        if not prompts:
            raise ValueError("LLM image prompt response missing image_prompts")
        return data

    def _merge_image_prompts(self, script: dict[str, Any], prompts: list[dict]) -> None:
        by_index: dict[int, dict] = {
            int(item["segment_index"]): item
            for item in prompts
            if item.get("image_prompt")
        }
        missing = [
            seg["segment_index"]
            for seg in script["segments"]
            if seg["segment_index"] not in by_index
        ]
        if missing:
            raise ValueError(f"image_prompts missing segments: {missing}")
        for seg in script["segments"]:
            item = by_index[seg["segment_index"]]
            seg["image_prompt"] = item["image_prompt"]
            seg["motion_prompt"] = item.get("motion_prompt", "")

    def generate_script(self, title: str, *, feedback: str | None = None) -> dict[str, Any]:
        data = self._generate_storyboard(title, feedback=feedback)

        prompt_feedback: str | None = None
        for attempt in range(4):
            prompt_data = self._generate_image_prompts(data, feedback=prompt_feedback)
            self._merge_image_prompts(data, prompt_data["image_prompts"])
            short = [
                (seg["segment_index"], len(seg["image_prompt"]))
                for seg in data["segments"]
                if len(seg["image_prompt"]) < _MIN_IMAGE_PROMPT_CHARS
            ]
            if not short:
                break
            prompt_feedback = (
                f"image_prompt too short: {short}; "
                f"need >={_MIN_IMAGE_PROMPT_CHARS} chars each, expand all layers"
            )
        return data
