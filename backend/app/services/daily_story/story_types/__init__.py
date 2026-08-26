"""日常故事矛盾类型（A–H）线路注册与解析。"""

from __future__ import annotations

import random
import re

from app.services.daily_story.story_types.model import (
    STORY_TYPE_KEYWORDS,
    STORY_TYPE_LABELS,
    TYPE_CATALOG_LINE,
    StoryTypeLine,
    chat_type_info_message,
    format_story_type_brief,
)
from app.services.daily_story.story_types.a.line import LINE_A
from app.services.daily_story.story_types.b.line import LINE_B
from app.services.daily_story.story_types.c.line import LINE_C
from app.services.daily_story.story_types.d.line import LINE_D
from app.services.daily_story.story_types.e.line import LINE_E
from app.services.daily_story.story_types.f.line import LINE_F
from app.services.daily_story.story_types.g.line import LINE_G
from app.services.daily_story.story_types.h.line import LINE_H
from app.services.daily_story.story_types.i.line import LINE_I
from app.services.daily_story.story_types.l.line import LINE_L

__all__ = [
    "QUALITY_FALLBACK_CODE",
    "STORY_TYPE_KEYWORDS",
    "STORY_TYPE_LABELS",
    "STORY_TYPE_LINES",
    "StoryTypeLine",
    "append_type_body_validation_errors",
    "chat_type_info_message",
    "format_block_for_code",
    "format_story_type_brief",
    "job_chat_type_info",
    "layer_patterns_for_story",
    "infer_story_type_code",
    "normalize_punchline_explain",
    "extract_story_type_code_from_punchline",
    "parse_story_type_code",
    "quality_ready_codes",
    "resolve_story_type_code",
    "patch_type_body",
    "revision_hints_for_type",
    "select_story_type_tag",
    "story_line_for_code",
    "story_type_punchline_conflict",
    "story_type_tag",
    "type_body_validation_enabled",
    "type_catalog_system_block",
    "validate_type_opening",
]

STORY_TYPE_LINES: dict[str, StoryTypeLine] = {
    r.code: r
    for r in (
        LINE_A, LINE_B, LINE_C, LINE_D, LINE_E, LINE_F, LINE_G, LINE_H, LINE_I, LINE_L,
    )
}

_VALID_STORY_TYPES = frozenset(STORY_TYPE_LABELS.keys())
_STORY_TYPE_CODE_CLASS = "[" + "".join(sorted(_VALID_STORY_TYPES)) + "]"

# 解析不到类型标签时的默认质检配置（与 C 公平执念一致）
QUALITY_FALLBACK_CODE = "C"


def story_line_for_code(code: str) -> StoryTypeLine:
    return STORY_TYPE_LINES.get(code.upper(), LINE_C)


def type_body_validation_enabled(code: str) -> bool:
    """quality_ready=False 的类型不进 H5 生成硬卡（仅 gold 侧观测）。"""
    line = STORY_TYPE_LINES.get(code.upper())
    return bool(line and line.quality_ready)


def story_type_punchline_conflict(story: dict) -> str | None:
    """DB story_type 与 punchline 类型标记不一致时返回告警文案。"""
    if not isinstance(story, dict):
        return None
    st_raw = str(story.get("story_type") or "").strip()
    if not st_raw:
        return None
    st = parse_story_type_code(story_type=st_raw)
    punch = str(story.get("punchline_explain") or "").strip()
    if not punch:
        return None
    punch_code = extract_story_type_code_from_punchline(punch)
    if not punch_code:
        punch_code = _parse_weak_punchline_type_code(punch)
    if punch_code and punch_code != st:
        return f"类型标签冲突：story_type={st}，punchline={punch_code}类"
    return None


def repair_punchline_explain_for_story_type(story: dict) -> bool:
    """story_type 与 punchline 类型冲突时，按 story_type 重写前缀。"""
    if not isinstance(story, dict):
        return False
    conflict = story_type_punchline_conflict(story)
    if not conflict:
        return False
    st = parse_story_type_code(story_type=str(story.get("story_type") or ""))
    raw = str(story.get("punchline_explain") or "").strip()
    punch_code = extract_story_type_code_from_punchline(raw) or _parse_weak_punchline_type_code(raw)
    if not punch_code or punch_code == st:
        return False
    rest = raw
    rest = re.sub(rf"^矛盾类型\s*{punch_code}[（(][^)）]+[)）]?\s*[：:]?\s*", "", rest, flags=re.IGNORECASE)
    rest = re.sub(rf"^{punch_code}\s*类?\s*[：:]\s*", "", rest)
    rest = rest.strip()
    tag = story_type_tag(st)
    story["punchline_explain"] = f"{tag}，{rest}" if rest else tag
    return True


def extract_story_type_code_from_punchline(punchline: str | None) -> str | None:
    """仅从笑点解析文本提取 A–H；解析不到则返回 None（不做默认兜底）。"""
    from app.repositories.schema import extract_story_type_from_punchline

    return extract_story_type_from_punchline(punchline)


def parse_story_type_code(
    *,
    story_type: str | None = None,
    punchline: str | None = None,
) -> str:
    if story_type:
        m = re.match(rf"^({_STORY_TYPE_CODE_CLASS})", story_type.strip())
        if m:
            return m.group(1).upper()
    text = punchline or ""
    weak = _parse_weak_punchline_type_code(text)
    if weak:
        return weak
    for k in sorted(STORY_TYPE_LABELS.keys()):
        if f"{k}类" in text or f"{k}：" in text:
            return k
    return QUALITY_FALLBACK_CODE


_RE_PUNCHLINE_STD_TAG = re.compile(rf"^({_STORY_TYPE_CODE_CLASS})类")
_RE_A_TAIL = re.compile(r"哪里不一样|都是听|大人也要听小孩")
_RE_A_CITE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)",
)


def _parse_weak_punchline_type_code(text: str) -> str | None:
    """旧稿：矛盾类型C / A 权威翻车 等非「X类」写法。"""
    t = (text or "").strip()
    if not t:
        return None
    m = re.search(rf"矛盾类型\s*({_STORY_TYPE_CODE_CLASS})", t, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.match(rf"^({_STORY_TYPE_CODE_CLASS})\s*类?\s*([^，,。：:]+)", t)
    if m:
        return m.group(1).upper()
    m = re.match(rf"^({_STORY_TYPE_CODE_CLASS})\s+", t)
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
            rf"^矛盾类型\s*{_STORY_TYPE_CODE_CLASS}[（(][^)）]+[)）]?\s*[：:]?\s*",
            "",
            rest,
            flags=re.IGNORECASE,
        )
        rest = re.sub(rf"^[{_STORY_TYPE_CODE_CLASS[1:-1]}]\s*类?\s*[^，,。：:]+[：:]\s*", "", rest)
        rest = re.sub(rf"^[{_STORY_TYPE_CODE_CLASS[1:-1]}]\s+\S+\s*[：:]\s*", "", rest)
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
    if isinstance(story, dict):
        locked = str(story.get("_story_type") or "").strip()
        if locked:
            parsed = parse_story_type_code(story_type=locked)
            if parsed in STORY_TYPE_LABELS:
                return parsed
    punch = str(story.get("punchline_explain") or "") if isinstance(story, dict) else ""
    if punchline_has_standard_type_tag(punch):
        return parse_story_type_code(punchline=punch)
    th = theme or (
        str(story.get("_theme") or "") if isinstance(story, dict) else ""
    )
    return infer_story_type_code(story, theme=th)


def story_type_tag(code: str) -> str:
    c = code.upper()
    return f"{c}类{STORY_TYPE_LABELS[c]}"


def job_chat_type_info(job: dict, *, success: bool = False) -> str | None:
    """chat 任务信息栏文案；非 chat 或没有类型时返回 None。"""
    if (job.get("pipeline") or "") != "chat":
        return None
    from app.repositories import repo_daily_story

    info = job.get("info") if isinstance(job.get("info"), dict) else {}
    raw_id = info.get("daily_story_id") or job.get("material_id")
    if not raw_id:
        return None
    try:
        story = repo_daily_story.get_story(int(raw_id))
    except (KeyError, TypeError, ValueError):
        return None
    return chat_type_info_message(story.get("story_type"), success=success)


def quality_ready_codes() -> list[str]:
    """已校准、可进入默认可选池的类型码。"""
    return [k for k, line in STORY_TYPE_LINES.items() if line.quality_ready]


# A 类反向过滤：纯知识争议/口头辩论（无犯规行为）不适合权威翻车
# 恐龙化石是鸟的祖先 → 知识争议，没有灿灿立规矩→犯规→被抓的链条
_RE_A_REQUIRES_RULE = re.compile(
    r"不能|不许|不准|不让|不可以|只能|必须|应该|要换|得换|要脱|得脱|"
    r"别玩|别吃|别进|别碰|少玩|少吃|写完|做完|练完|刷满|刷够|"
    r"系[好对紧]|叠[好齐整]|收拾|整理|关掉|放下|别[看玩碰拿]",
)
# 知识争议特征：学术话题 + 对错争论，没有行为规矩
_RE_A_KNOWLEDGE_DISPUTE = re.compile(
    r"恐龙|化石|祖先|进化|起源|科学|宇宙|星球|历史|古代|"
    r"百科|书上[说写]|图鉴|真的[是嘛]|假的|不对|你错|"
    r"说.{0,4}(?:是|不是|对|错)|争论|辩论|证明|证据",
)


def select_story_type_tag(theme: str) -> str:
    """按主题关键词选类型；无匹配时在 `quality_ready` 类型中随机。"""
    scores = {
        k: sum(1 for kw in line.keywords if kw in theme)
        for k, line in STORY_TYPE_LINES.items()
    }
    max_score = max(scores.values())
    ready = quality_ready_codes() or ["A", "C"]
    if max_score <= 0:
        candidates = list(ready)
    else:
        candidates = [k for k, v in scores.items() if v >= max_score]
    # A 类排除纯知识争议（无行为犯规链条）
    if "A" in candidates and _RE_A_KNOWLEDGE_DISPUTE.search(theme) and not _RE_A_REQUIRES_RULE.search(theme):
        candidates = [c for c in candidates if c != "A"]
    if not candidates:
        candidates = list(ready)
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
    lines_hard = ""
    if line.body_lines_min and line.body_lines_max and line.body_lines_max > line.body_lines_min:
        # D 等硬句数类型：把数组长度写进 JSON 模板（Flash 对可校验格式更听话）
        vals = list(range(line.body_lines_min, line.body_lines_max + 1))
        num_text = "、".join(str(v) for v in vals[:-1]) + " 或 " + str(vals[-1])
        lines_hard = f'    // 数组长度必须等于 {num_text}，不得少，不得多。\n'
    alternation_hard = (
        '    // 【硬约束】speaker 必须与上一句严格交替'
        '（昭昭→灿灿→昭昭→…），连续相同则整组作废\n'
    )
    code_u = (code or "").upper()
    if code_u == "D":
        rows = (
            f'    {{"speaker": "昭昭", "line": "台词（{line.line_format_hint}）"}},\n'
            '    {"speaker": "灿灿", "line": "台词"}  // 本场仅昭昭/灿灿，禁止妈妈\n'
        )
        footer = "本场仅昭昭/灿灿出场；禁止妈妈。"
    elif code_u == "E":
        rows = (
            f'    {{"speaker": "妈妈", "line": "台词（{line.line_format_hint}）"}},\n'
            f'    {{"speaker": "昭昭", "line": "台词（{line.line_format_hint}）"}},\n'
            f'    {{"speaker": "灿灿", "line": "台词（{line.line_format_hint}）"}}\n'
        )
        footer = (
            "妈妈三拍：开场立规+中段恰好1句短反应+末句破功并当场做回去；"
            "假开脱由灿灿扛，昭昭只戳穿追问；大人例外最多2次。"
        )
    else:
        rows = (
            f'    {{"speaker": "昭昭", "line": "台词（{line.line_format_hint}）"}},\n'
            '    {"speaker": "灿灿", "line": "台词"},\n'
            '    {"speaker": "妈妈", "line": "台词（宜少）"}\n'
        )
        footer = "妈妈可有台词，但宜少（建议≤3句）；主回合仍是姐弟。"
    return f"""\
【格式要求】
严格输出以下JSON结构：
{{
  "scene_title": "不超过10字，口语钩子（孩子台词/反差疑问/带口吻动作），禁纯事件名如「藏玩具」「分蛋糕」；好例：「老鼠会开柜子门吗」「就一块，别告状」",
  "setting": "一句话说明地点和初始冲突动作",
  "key": "2–8字内容标签，如饭前偷吃、偷看电视（防重复；勿写成谁vs谁）",
  "conflict_core": "≤24字，谁vs谁争什么",
  "dialogue": [
{alternation_hard}{lines_hard}{rows}  ],
  "punchline_explain": "{line.punchline_example}"
}}

【轮换硬锁·全域最高优先级】
每一句的 speaker 必须与上一句严格交替（昭昭→灿灿→昭昭→…）。
生成任何一句前，先检查上句 speaker；若相同，禁止输出，重写本句。
无论语义衔接多顺、无论当前说话人是否「还没说完」，禁止连说。
宁可把同一人的完整内容拆成两轮说（中间隔一句），也绝不允许连说 2 句。
{footer}
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
    elif code == "G":
        from app.services.daily_story.story_types.g.validate import append_g_body_errors

        append_g_body_errors(story, errors)
    elif code == "F":
        from app.services.daily_story.story_types.f.validate import append_f_body_errors

        append_f_body_errors(story, errors)
    elif code == "H" and type_body_validation_enabled("H"):
        from app.services.daily_story.story_types.h.validate import append_h_body_errors

        append_h_body_errors(story, errors)
    elif code == "I" and type_body_validation_enabled("I"):
        from app.services.daily_story.story_types.i.validate import append_i_body_errors

        append_i_body_errors(story, errors)
    elif code == "L" and type_body_validation_enabled("L"):
        from app.services.daily_story.story_types.l.validate import append_l_body_errors

        append_l_body_errors(story, errors)


def patch_type_body(story: dict) -> list[str]:
    code = resolve_story_type_code(story)
    if code == "A":
        from app.services.daily_story.story_types.a.patch import patch_a_body

        return patch_a_body(story)
    if code == "C":
        from app.services.daily_story.story_types.c.patch import patch_c_body

        return patch_c_body(story)
    if code == "B":
        from app.services.daily_story.story_types.b.patch import patch_b_body

        return patch_b_body(story)
    if code == "D":
        from app.services.daily_story.story_types.d.patch import patch_d_body

        return patch_d_body(story)
    if code == "E":
        from app.services.daily_story.story_types.e.patch import patch_e_body

        return patch_e_body(story)
    if code == "G":
        from app.services.daily_story.story_types.g.patch import patch_g_body

        return patch_g_body(story)
    if code == "F":
        from app.services.daily_story.story_types.f.patch import patch_f_body

        return patch_f_body(story)
    if code == "H":
        from app.services.daily_story.story_types.h.patch import patch_h_body

        return patch_h_body(story)
    if code == "I":
        from app.services.daily_story.story_types.i.patch import patch_i_body

        return patch_i_body(story)
    if code == "L":
        from app.services.daily_story.story_types.l.patch import patch_l_body

        return patch_l_body(story)
    return []


def validate_type_opening(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    from app.services.daily_story.story_types.a.opening import append_a_opening_errors
    from app.services.daily_story.story_types.b.opening import append_b_opening_errors

    append_a_opening_errors(
        normalized,
        type_code=type_code,
        errors=errors,
        setting=setting,
    )
    append_b_opening_errors(normalized, type_code=type_code, errors=errors)
    from app.services.daily_story.story_types.c.opening import append_c_opening_errors

    append_c_opening_errors(
        normalized,
        type_code=type_code,
        errors=errors,
        setting=setting,
        conflict_core=conflict_core,
    )
    from app.services.daily_story.story_types.d.opening import append_d_opening_errors
    from app.services.daily_story.story_types.e.opening import append_e_opening_errors

    append_d_opening_errors(
        normalized,
        type_code=type_code,
        errors=errors,
        conflict_core=conflict_core,
    )
    append_e_opening_errors(
        normalized,
        type_code=type_code,
        errors=errors,
        conflict_core=conflict_core,
        setting=setting,
    )
    from app.services.daily_story.story_types.g.opening import append_g_opening_errors

    append_g_opening_errors(
        normalized,
        type_code=type_code,
        errors=errors,
        conflict_core=conflict_core,
        setting=setting,
    )
    from app.services.daily_story.story_types.f.opening import append_f_opening_errors

    append_f_opening_errors(
        normalized,
        type_code=type_code,
        errors=errors,
        conflict_core=conflict_core,
        setting=setting,
    )
    from app.services.daily_story.story_types.h.opening import append_h_opening_errors

    if type_body_validation_enabled("H"):
        append_h_opening_errors(
            normalized,
            type_code=type_code,
            errors=errors,
            conflict_core=conflict_core,
            setting=setting,
        )
    if type_body_validation_enabled("I"):
        from app.services.daily_story.story_types.i.opening import append_i_opening_errors

        append_i_opening_errors(
            normalized,
            type_code=type_code,
            errors=errors,
            conflict_core=conflict_core,
            setting=setting,
        )
    if type_body_validation_enabled("L"):
        from app.services.daily_story.story_types.l.opening import append_l_opening_errors

        append_l_opening_errors(
            normalized,
            type_code=type_code,
            errors=errors,
            conflict_core=conflict_core,
            setting=setting,
        )
