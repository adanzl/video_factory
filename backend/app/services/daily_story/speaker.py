"""日常故事：对白 speaker 与画面文案中的角色名对齐（未发言不入画）。"""

from __future__ import annotations

import re

DAILY_STORY_SPEAKER_NAMES: tuple[str, ...] = ("昭昭", "灿灿", "妈妈")

__all__ = [
    "DAILY_STORY_SPEAKER_NAMES",
    "collect_speaker_leak_issues",
    "collect_speaker_leak_segments",
    "leaked_speaker_names_in_text",
    "scrub_leaked_speaker_names",
    "speakers_from_dialogue",
]


def speakers_from_dialogue(dialogue: list | None) -> set[str]:
    names: set[str] = set()
    for item in dialogue or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("speaker") or "").strip()
        if name:
            names.add(name)
    return names


def leaked_speaker_names_in_text(text: str, allowed: set[str]) -> list[str]:
    """返回文本中出现、但不在 allowed 里的固定角色名。"""
    body = text or ""
    return [
        name
        for name in DAILY_STORY_SPEAKER_NAMES
        if name not in allowed and name in body
    ]


def scrub_leaked_speaker_names(text: str, allowed: set[str]) -> str:
    """去掉含未授权角色的分句；若删光则退回纯场景占位。"""
    raw = (text or "").strip()
    if not raw or not leaked_speaker_names_in_text(raw, allowed):
        return raw
    parts = re.split(r"(?<=[。！？；;!?])", raw)
    kept = [
        p for p in parts if p and not leaked_speaker_names_in_text(p, allowed)
    ]
    cleaned = "".join(kept).strip()
    if cleaned:
        return cleaned
    return "室内场景，无未发言角色入画。"


def _image_prompt_body_for_speaker_check(text: str) -> str:
    """去掉 daily wrap 硬编码前缀后再做入画校验，避免参考图外貌句误报。"""
    body = text or ""
    marker = "孩子气的构图。"
    if "基于参考图调整人物动作" in body and marker in body:
        idx = body.find(marker)
        if idx >= 0:
            return body[idx + len(marker) :]
    return body


def collect_speaker_leak_segments(
    segments: list[dict],
    *,
    check_image_prompt: bool = True,
    check_visual_brief: bool = True,
) -> list[dict]:
    """返回 [{segment_index, field, leaks, speakers}, ...]。"""
    rows: list[dict] = []
    for seg in segments:
        idx = seg.get("segment_index")
        allowed = speakers_from_dialogue(seg.get("dialogue"))
        if check_visual_brief:
            leaks = leaked_speaker_names_in_text(
                str(seg.get("visual_brief") or ""),
                allowed,
            )
            if leaks:
                rows.append(
                    {
                        "segment_index": idx,
                        "field": "visual_brief",
                        "leaks": leaks,
                        "speakers": sorted(allowed),
                    },
                )
        if check_image_prompt:
            prompt_body = _image_prompt_body_for_speaker_check(
                str(seg.get("image_prompt") or ""),
            )
            leaks = leaked_speaker_names_in_text(prompt_body, allowed)
            if leaks:
                rows.append(
                    {
                        "segment_index": idx,
                        "field": "image_prompt",
                        "leaks": leaks,
                        "speakers": sorted(allowed),
                    },
                )
    return rows


def collect_speaker_leak_issues(
    segments: list[dict],
    *,
    check_image_prompt: bool = True,
    check_visual_brief: bool = True,
) -> list[str]:
    """汇总 daily 分镜未发言角色入画违规文案。"""
    rows = collect_speaker_leak_segments(
        segments,
        check_image_prompt=check_image_prompt,
        check_visual_brief=check_visual_brief,
    )
    return [
        f"segment {r['segment_index']}: {r['field']} 含未发言角色 {r['leaks']} "
        f"(speakers={r['speakers'] or '[]'})"
        for r in rows
    ]
