"""日常故事：对白 speaker / 台词在场角色 与画面文案中的角色名对齐。"""

from __future__ import annotations

import re

DAILY_STORY_SPEAKER_NAMES: tuple[str, ...] = ("昭昭", "灿灿", "妈妈")

# 点名但非当场在画：转述旧规矩、询问去向、刻意避开等（不授予入画）
# 口语常写「妈」；妈妈? = 妈|妈妈，避免「别让妈看见」漏判导致粘性硬塞三人
_ABSENT_MOM_RE = re.compile(
    r"妈妈?(?:说过|说的|让我们|叫我们|呢|在哪儿?|去哪儿?)"
    r"|听妈妈?的"
    r"|(?:别|先别|不要).{0,4}(?:告诉|让).{0,3}妈妈?"
    r"|(?:躲|背|瞒)着妈妈?"
    r"|别让妈妈?(?:看见|发现|知道)"
    r"|别被妈妈?(?:看见|发现)"
    r"|不让妈妈?知道"
    r"|趁妈妈?不在"
    r"|(?:听见?|听着?).{0,6}妈妈?(?:脚步声|脚步|声音|动静)"
    # 妈妈是「听见/听到」的主语：她隔着房间听到动静，还没到场（如「妈听见响声了」）
    r"|妈妈?(?:刚)?(?:听见|听到)"
    # 「回」在未来/假设句里不授予入画：妈妈还没到场，只预判她回来会怎样
    r"|(?:不然|否则|等|等到|如果|要是|万一).{0,3}妈妈?回来"
    r"|妈妈?(?:马上|就|快要).{0,3}回来了?"
    r"|妈妈?回来(?:要|就|会)"
)

# 台词写明妈妈当场可见：动作/状态，或当面称呼
_PRESENT_MOM_RE = re.compile(
    r"妈妈?(?:还|正|就)?(?:在)?"
    r"(?:躺|刷|拿|握|坐|站|睡|笑|吃|嗑|看|玩|举|点|回|戴|听|抱)"
    r"|妈妈?(?:手里|手机|屏幕|沙发|被窝|床上)"
    r"|妈妈?还在"
    r"|(?:^|[，,。！？\s])妈[，,]"
    r"|妈妈[，,]"
    r"|妈妈?你"
)

_ABSENT_CHILD_RE = {
    "昭昭": re.compile(r"昭昭(?:说过|呢|在哪|去哪)"),
    "灿灿": re.compile(r"灿灿(?:说过|呢|在哪|去哪)"),
}

_PRESENT_CHILD_RE = {
    "昭昭": re.compile(
        r"昭昭(?:还|正|就)?(?:在)?"
        r"(?:躺|拿|握|坐|站|笑|吃|举|指|抢|夺|藏|摊|耸|叉|瞪|看)"
        r"|昭昭[，,]"
        r"|昭昭你"
    ),
    "灿灿": re.compile(
        r"灿灿(?:还|正|就)?(?:在)?"
        r"(?:躺|拿|握|坐|站|笑|吃|举|指|抢|夺|藏|摊|耸|叉|瞪|看)"
        r"|灿灿[，,]"
        r"|灿灿你"
    ),
}

_ROOM_WORDS = (
    "客厅",
    "厨房",
    "卧室",
    "卫生间",
    "厕所",
    "阳台",
    "餐厅",
    "书房",
    "玄关",
    "门口",
)
_ROOM_RE = re.compile("|".join(_ROOM_WORDS))
_SETTING_OFFSCREEN_MOM_RE = re.compile(
    r"妈妈(?:还|正|就)?(?:在|待在|留在|躲在)?"
    r"(客厅|厨房|卧室|卫生间|厕所|阳台|餐厅|书房|玄关|门口)"
)

__all__ = [
    "DAILY_STORY_SPEAKER_NAMES",
    "allowed_cast_from_dialogue",
    "allowed_cast_from_segment",
    "annotate_sticky_stage_speakers",
    "collect_speaker_leak_issues",
    "collect_speaker_leak_segments",
    "leaked_speaker_names_in_text",
    "mom_should_stay_offscreen",
    "present_cast_from_dialogue",
    "scrub_leaked_speaker_names",
    "scrub_offscreen_doorway_cues",
    "speakers_from_dialogue",
    "stage_cast_from_setting",
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


def _line_texts(dialogue: list | None) -> list[str]:
    texts: list[str] = []
    for item in dialogue or []:
        if not isinstance(item, dict):
            continue
        # daily 分镜用 text；故事原稿用 line
        raw = item.get("text")
        if raw is None:
            raw = item.get("line")
        text = str(raw or "").strip()
        if text:
            texts.append(text)
    return texts


def present_cast_from_dialogue(dialogue: list | None) -> set[str]:
    """台词写明当场在场/动作的角色（可不发言）。

    不含仅转述/询问去向的点名（如「妈妈说过」「妈妈呢」）。
    """
    present: set[str] = set()
    for text in _line_texts(dialogue):
        if _PRESENT_MOM_RE.search(text) and not _ABSENT_MOM_RE.search(text):
            present.add("妈妈")
        for name in ("昭昭", "灿灿"):
            if _PRESENT_CHILD_RE[name].search(text) and not _ABSENT_CHILD_RE[
                name
            ].search(text):
                present.add(name)
    return present


def allowed_cast_from_dialogue(dialogue: list | None) -> set[str]:
    """本段可入画角色 = 发言角色 ∪ 台词写明在场角色。"""
    return speakers_from_dialogue(dialogue) | present_cast_from_dialogue(dialogue)


def mom_should_stay_offscreen(dialogue: list | None) -> bool:
    """台词明确要求避开妈妈视线时，妈妈本段不得入画。"""
    speakers = speakers_from_dialogue(dialogue)
    if "妈妈" in speakers:
        return False
    present = present_cast_from_dialogue(dialogue)
    if "妈妈" in present:
        return False
    return any(_ABSENT_MOM_RE.search(text) for text in _line_texts(dialogue))


def _primary_room_from_setting(setting: str | None) -> str | None:
    text = str(setting or "")
    m = _ROOM_RE.search(text)
    return m.group(0) if m else None


def _mom_should_stay_offscreen_in_setting(setting: str | None) -> bool:
    """setting 只表示妈妈在另一房间/门外时，不授予当前镜头入画。"""
    text = str(setting or "")
    primary_room = _primary_room_from_setting(text)
    mom_room_m = _SETTING_OFFSCREEN_MOM_RE.search(text)
    if not primary_room or not mom_room_m:
        return False
    return mom_room_m.group(1) != primary_room


def stage_cast_from_setting(setting: str | None) -> set[str]:
    """setting 点名的角色视为开场已在场（同场戏粘性起点）。"""
    text = str(setting or "")
    cast = {name for name in DAILY_STORY_SPEAKER_NAMES if name in text}
    if _mom_should_stay_offscreen_in_setting(text):
        cast.discard("妈妈")
    return cast


def annotate_sticky_stage_speakers(
    segments: list | None,
    *,
    setting: str | None = None,
) -> None:
    """同场粘性入画：setting 已点名 + 前面镜已出场的角色，后续镜继续保留。

    写入每段 ``speakers``（有序）。例：餐桌戏妈妈先出场后，
    姐弟互怼镜仍须三人同框，不能把妈妈 scrub 掉。

    若 setting 已同时点到妈妈与另一角色，或开场镜妈妈已发言且
    全文三人都会出场，则开场起全员同框。
    """
    segs = [s for s in (segments or []) if isinstance(s, dict)]
    sticky = stage_cast_from_setting(setting)
    # 无 setting 重跑拼装时，保留已有 speakers，避免把开场三人冲成两人
    if not str(setting or "").strip():
        for seg in segs:
            raw = seg.get("speakers")
            if isinstance(raw, list) and raw:
                sticky |= {str(s).strip() for s in raw if str(s).strip()}
    story_speakers: set[str] = set()
    for seg in segs:
        story_speakers |= speakers_from_dialogue(seg.get("dialogue"))
    ordered = sorted(
        segs,
        key=lambda s: int(s.get("segment_index") or 0),
    )
    opening = speakers_from_dialogue(
        ordered[0].get("dialogue") if ordered else None,
    )
    family_stage = (
        ("妈妈" in sticky and len(sticky) >= 2)
        or (
            "妈妈" in opening
            and len(story_speakers) >= 3
        )
    )
    if family_stage:
        sticky |= story_speakers
    for seg in ordered:
        local = allowed_cast_from_dialogue(seg.get("dialogue"))
        if mom_should_stay_offscreen(seg.get("dialogue")):
            local.discard("妈妈")
            # 当前段明确要求避开妈妈视线时，打断“妈妈持续同框”的粘性；
            # 后续若台词再次明确在场或由妈妈发言，会自然重新入画。
            sticky.discard("妈妈")
        sticky |= local
        seg["speakers"] = [n for n in DAILY_STORY_SPEAKER_NAMES if n in sticky]


def allowed_cast_from_segment(seg: dict | None) -> set[str]:
    """优先用显式 speakers 字段，否则从 dialogue 推导（含在场）。"""
    seg = seg or {}
    raw = seg.get("speakers")
    if isinstance(raw, list) and raw:
        allowed = {str(s).strip() for s in raw if str(s).strip()}
        if mom_should_stay_offscreen(seg.get("dialogue")):
            allowed.discard("妈妈")
        return allowed
    return allowed_cast_from_dialogue(seg.get("dialogue"))


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
    return "室内场景，无未授权角色入画。"


# 妈妈未入画时，「盯/瞟门口」会诱使 T2I 画出陌生人（如「妈出来了」却无妈妈外貌）
_OFFSCREEN_DOOR_GAZE_RE = re.compile(
    r"(?:同时)?"
    r"(?:眼睛|目光|余光|身体)?"
    r"(?:扭头)?"
    r"(?:紧)?"
    r"(?:瞟|瞥|盯|望|看)(?:向|着)?"
    r"(?:厨房|客厅|卧室|卫生间|厕所|阳台|餐厅|玄关)?"
    r"门口"
    r"(?:方向)?"
)


def scrub_offscreen_doorway_cues(text: str, *, allowed: set[str]) -> str:
    """妈妈不在 allowed 时，去掉「盯/瞟门口」，避免暗示第三人入画。"""
    body = (text or "").strip()
    if not body or "妈妈" in allowed:
        return body

    cleaned = _OFFSCREEN_DOOR_GAZE_RE.sub("", body)
    cleaned = re.sub(r"[，,]{2,}", "，", cleaned)
    cleaned = re.sub(r"[；;]{2,}", "；", cleaned)
    return cleaned.strip("，,；; ").strip()


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
        allowed = allowed_cast_from_segment(seg)
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
    """汇总 daily 分镜未授权角色入画违规文案。"""
    rows = collect_speaker_leak_segments(
        segments,
        check_image_prompt=check_image_prompt,
        check_visual_brief=check_visual_brief,
    )
    return [
        f"segment {r['segment_index']}: {r['field']} 含未授权角色 {r['leaks']} "
        f"(cast={r['speakers'] or '[]'})"
        for r in rows
    ]
