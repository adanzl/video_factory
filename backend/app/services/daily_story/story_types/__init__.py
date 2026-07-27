"""日常故事矛盾类型（A–E）线路注册与解析。"""

from __future__ import annotations

import random
import re

from app.services.daily_story.story_types.model import (
    STORY_TYPE_KEYWORDS,
    STORY_TYPE_LABELS,
    TYPE_CATALOG_LINE,
    StoryTypeLine,
)
from app.services.daily_story.story_types.a.line import LINE_A
from app.services.daily_story.story_types.b.line import LINE_B
from app.services.daily_story.story_types.c.line import LINE_C
from app.services.daily_story.story_types.d.line import LINE_D
from app.services.daily_story.story_types.e.line import LINE_E

__all__ = [
    "QUALITY_FALLBACK_CODE",
    "STORY_TYPE_KEYWORDS",
    "STORY_TYPE_LABELS",
    "STORY_TYPE_LINES",
    "StoryTypeLine",
    "append_type_body_validation_errors",
    "format_block_for_code",
    "layer_patterns_for_story",
    "infer_story_type_code",
    "normalize_punchline_explain",
    "extract_story_type_code_from_punchline",
    "parse_story_type_code",
    "resolve_story_type_code",
    "patch_type_body",
    "revision_hints_for_type",
    "select_story_type_tag",
    "story_line_for_code",
    "story_type_tag",
    "type_catalog_system_block",
    "validate_type_opening",
]

STORY_TYPE_LINES: dict[str, StoryTypeLine] = {
    r.code: r
    for r in (LINE_A, LINE_B, LINE_C, LINE_D, LINE_E)
}

# 解析不到类型标签时的默认质检配置（与 C 公平执念一致）
QUALITY_FALLBACK_CODE = "C"


def story_line_for_code(code: str) -> StoryTypeLine:
    return STORY_TYPE_LINES.get(code.upper(), LINE_C)


def extract_story_type_code_from_punchline(punchline: str | None) -> str | None:
    """仅从笑点解析文本提取 A–E；解析不到则返回 None（不做默认兜底）。"""
    from app.repositories.schema import extract_story_type_from_punchline

    return extract_story_type_from_punchline(punchline)


def parse_story_type_code(
    *,
    story_type: str | None = None,
    punchline: str | None = None,
) -> str:
    if story_type:
        m = re.match(r"^([ABCDE])", story_type.strip())
        if m:
            return m.group(1).upper()
    text = punchline or ""
    weak = _parse_weak_punchline_type_code(text)
    if weak:
        return weak
    for k in ("A", "B", "C", "D", "E"):
        if f"{k}类" in text or f"{k}：" in text:
            return k
    return QUALITY_FALLBACK_CODE


_RE_PUNCHLINE_STD_TAG = re.compile(r"^([ABCDE])类")
_RE_A_TAIL = re.compile(r"哪里不一样|都是听|大人也要听小孩")
_RE_A_CITE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)",
)


def _parse_weak_punchline_type_code(text: str) -> str | None:
    """旧稿：矛盾类型C / A 权威翻车 等非「X类」写法。"""
    t = (text or "").strip()
    if not t:
        return None
    m = re.search(r"矛盾类型\s*([ABCDE])", t, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.match(r"^([ABCDE])\s*类?\s*([^，,。：:]+)", t)
    if m:
        return m.group(1).upper()
    m = re.match(r"^([ABCDE])\s+", t)
    if m and m.group(1).upper() in STORY_TYPE_LABELS:
        return m.group(1).upper()
    return None


def punchline_has_standard_type_tag(text: str) -> bool:
    """是否已有规范前缀「X类…」。"""
    return bool(_RE_PUNCHLINE_STD_TAG.match((text or "").strip()))


def normalize_punchline_explain(explain: str, code: str) -> str:
    """在现有笑点解析前补上「X类标签」，已有规范前缀则尽量归一化。"""
    raw = (explain or "").strip()
    c = code.upper()
    tag = story_type_tag(c)
    line = story_line_for_code(c)
    if not raw:
        return line.punchline_example

    if punchline_has_standard_type_tag(raw):
        return raw

    weak = _parse_weak_punchline_type_code(raw)
    if weak:
        rest = raw
        rest = re.sub(
            r"^矛盾类型\s*[ABCDE][（(][^)）]+[)）]?\s*[：:]?\s*",
            "",
            rest,
            flags=re.IGNORECASE,
        )
        rest = re.sub(r"^[ABCDE]\s*类?\s*[^，,。：:]+[：:]\s*", "", rest)
        rest = re.sub(r"^[ABCDE]\s+\S+\s*[：:]\s*", "", rest)
        rest = rest.strip()
        if rest and not punchline_has_standard_type_tag(rest):
            return f"{tag}，{rest}"
        if rest:
            return rest
        return line.punchline_example

    return f"{tag}，{raw}"


def _story_dialogue_tail(story: dict) -> tuple[str, str]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return "", ""
    lines = [
        str(d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict) and str(d.get("line") or "").strip()
    ]
    if not lines:
        return "", ""
    tail4 = "".join(lines[-4:])
    blob = "".join(lines)
    return tail4, blob


def _keyword_scores(blob: str) -> dict[str, int]:
    return {
        k: sum(1 for kw in STORY_TYPE_KEYWORDS[k] if kw in blob)
        for k in STORY_TYPE_LINES
    }


def infer_story_type_code(
    story: dict,
    *,
    theme: str = "",
) -> str:
    """无规范「X类」标签时，从主题/笑点/对白推断矛盾类型。"""
    if not isinstance(story, dict):
        return QUALITY_FALLBACK_CODE

    punch = str(story.get("punchline_explain") or "")
    if punchline_has_standard_type_tag(punch):
        return parse_story_type_code(punchline=punch)

    weak = _parse_weak_punchline_type_code(punch)
    if weak:
        return weak

    tail4, dlg_blob = _story_dialogue_tail(story)
    core = str(story.get("conflict_core") or "")
    setting = str(story.get("setting") or "")
    blob = f"{theme}{core}{setting}{punch}{dlg_blob}"

    if _RE_A_CITE.search(tail4) and _RE_A_TAIL.search(tail4) and "那不一样" in tail4:
        return "A"

    from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE

    scores = _keyword_scores(blob)
    if RE_BOOMERANG_RULE.search(tail4):
        scores["C"] = scores.get("C", 0) + 2
    if _RE_A_TAIL.search(tail4):
        scores["A"] = scores.get("A", 0) + 2
    if re.search(r"教.*作业|写作业|写错|刷牙|管.*手机", blob):
        scores["A"] = scores.get("A", 0) + 2
    if re.search(r"鞋带|叮嘱|照做|字面", blob):
        scores["D"] = scores.get("D", 0) + 2

    max_score = max(scores.values())
    if max_score <= 0:
        return QUALITY_FALLBACK_CODE
    top = [k for k, v in scores.items() if v == max_score]
    if len(top) == 1:
        return top[0]
    if "A" in top and "C" in top:
        return "A" if _RE_A_TAIL.search(tail4) else "C"
    return random.choice(top)


def resolve_story_type_code(
    story: dict,
    *,
    theme: str = "",
) -> str:
    """解析或推断类型（DB 旧稿、生成选题均可用）。"""
    punch = str(story.get("punchline_explain") or "") if isinstance(story, dict) else ""
    if punchline_has_standard_type_tag(punch):
        return parse_story_type_code(punchline=punch)
    return infer_story_type_code(story, theme=theme)


def story_type_tag(code: str) -> str:
    c = code.upper()
    return f"{c}类{STORY_TYPE_LABELS[c]}"


def select_story_type_tag(theme: str) -> str:
    """按主题关键词选类型；无匹配时在已校准类型 A/C 中随机。"""
    scores = {
        k: sum(1 for kw in line.keywords if kw in theme)
        for k, line in STORY_TYPE_LINES.items()
    }
    max_score = max(scores.values())
    if max_score <= 0:
        candidates = ["A", "C"]
    else:
        candidates = [k for k, v in scores.items() if v >= max_score]
    if not candidates:
        candidates = ["A", "C"]
    selected = random.choice(candidates)
    return story_type_tag(selected)


def layer_patterns_for_story(story: dict | None) -> tuple[tuple[str, re.Pattern[str]], ...]:
    if not isinstance(story, dict):
        return LINE_C.layer_patterns
    code = parse_story_type_code(punchline=str(story.get("punchline_explain") or ""))
    return story_line_for_code(code).layer_patterns


def revision_hints_for_type(code: str) -> tuple[str, str]:
    line = story_line_for_code(code)
    return line.escalation_revision_hint, line.closing_revision_hint


def type_catalog_system_block() -> str:
    return TYPE_CATALOG_LINE


def format_block_for_code(code: str) -> str:
    line = story_line_for_code(code)
    return f"""\
【格式要求】
严格输出以下JSON结构：
{{
  "scene_title": "不超过10字，场记或口语钩子均可",
  "setting": "一句话说明地点和初始冲突动作",
  "conflict_core": "≤24字，谁vs谁争什么",
  "dialogue": [
    {{"speaker": "昭昭", "line": "台词（≤18字）"}},
    {{"speaker": "灿灿", "line": "台词"}},
    {{"speaker": "妈妈", "line": "台词（宜少）"}}
  ],
  "punchline_explain": "{line.punchline_example}"
}}
妈妈可有台词，但宜少（建议≤3句）；主回合仍是姐弟。
"""


def append_type_body_validation_errors(story: dict, errors: list[str]) -> None:
    from app.services.daily_story.story_types.a.facts import (
        append_brush_timer_fact_errors,
        append_homework_fact_errors,
    )
    from app.services.daily_story.story_types.a.validate import append_a_body_errors
    from app.services.daily_story.story_types.b.facts import append_b_fact_errors

    append_homework_fact_errors(story, errors)
    append_brush_timer_fact_errors(story, errors)
    code = resolve_story_type_code(story)
    append_b_fact_errors(story, errors)
    if code == "A":
        append_a_body_errors(story, errors)
    elif code == "B":
        from app.services.daily_story.story_types.b.validate import append_b_body_errors

        append_b_body_errors(story, errors)
    elif code == "C":
        from app.services.daily_story.story_types.c.validate import append_c_body_errors

        append_c_body_errors(story, errors)
    elif code == "D":
        from app.services.daily_story.story_types.d.validate import append_d_body_errors

        append_d_body_errors(story, errors)
    elif code == "E":
        from app.services.daily_story.story_types.e.validate import append_e_body_errors

        append_e_body_errors(story, errors)


def patch_type_body(story: dict) -> list[str]:
    code = resolve_story_type_code(story)
    if code == "A":
        from app.services.daily_story.story_types.a.patch import patch_a_body

        return patch_a_body(story)
    if code == "C":
        from app.services.daily_story.story_types.c.patch import patch_c_body

        return patch_c_body(story)
    if code == "D":
        from app.services.daily_story.story_types.d.patch import patch_d_body

        return patch_d_body(story)
    if code == "E":
        from app.services.daily_story.story_types.e.patch import patch_e_body

        return patch_e_body(story)
    return []


def validate_type_opening(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
) -> None:
    from app.services.daily_story.story_types.a.opening import append_a_opening_errors
    from app.services.daily_story.story_types.b.opening import append_b_opening_errors

    append_a_opening_errors(normalized, type_code=type_code, errors=errors)
    append_b_opening_errors(normalized, type_code=type_code, errors=errors)
    from app.services.daily_story.story_types.c.opening import append_c_opening_errors

    append_c_opening_errors(normalized, type_code=type_code, errors=errors)
    from app.services.daily_story.story_types.d.opening import append_d_opening_errors
    from app.services.daily_story.story_types.e.opening import append_e_opening_errors

    append_d_opening_errors(normalized, type_code=type_code, errors=errors)
    append_e_opening_errors(normalized, type_code=type_code, errors=errors)
