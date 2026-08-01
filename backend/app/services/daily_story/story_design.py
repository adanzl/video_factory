"""日常故事 D1.5 笑点骨架（story_design）：统一入口、按类型分发。

A–E 均有 `story_types/{code}/story_plan.py`：
实装类型设 `ENABLED = True`；未调通的类型用空实现
`ENABLED = False`，生成时自动跳过，不走环境变量开关。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.daily_story.story_types import (
    STORY_TYPE_LABELS,
    parse_story_type_code,
    story_type_tag,
)

TypeBlueprintMod = Any


def _load_type_mod(code: str) -> TypeBlueprintMod | None:
    code = (code or "").upper()
    if code == "A":
        from app.services.daily_story.story_types.a import story_plan as mod

        return mod
    if code == "B":
        from app.services.daily_story.story_types.b import story_plan as mod

        return mod
    if code == "C":
        from app.services.daily_story.story_types.c import story_plan as mod

        return mod
    if code == "D":
        from app.services.daily_story.story_types.d import story_plan as mod

        return mod
    if code == "E":
        from app.services.daily_story.story_types.e import story_plan as mod

        return mod
    return None


def story_plan_enabled(*, story_type: str | None = None) -> bool:
    """该类型 story_plan 已实装（ENABLED）则走 D1.5。"""
    code = parse_story_type_code(story_type=story_type) if story_type else ""
    if not code:
        return False
    mod = _load_type_mod(code)
    return bool(mod is not None and getattr(mod, "ENABLED", False))


# 兼容旧名
punchline_blueprint_enabled = story_plan_enabled


def blueprint_implemented(code: str) -> bool:
    mod = _load_type_mod(code)
    return bool(mod is not None and getattr(mod, "ENABLED", False))


def validate_punchline_blueprint(
    bp: dict,
    *,
    story_type: str | None = None,
) -> list[str]:
    code = parse_story_type_code(story_type=story_type) if story_type else "D"
    mod = _load_type_mod(code)
    if mod is None or not getattr(mod, "ENABLED", False):
        return [f"{code}类笑点骨架为空实现"]
    return list(mod.validate(bp))


# 流程块序号前缀：「第X块/第X步/第X招」及 ①②③ 、X. 等，均可安全剥掉
_RE_BEAT_ORDINAL_PREFIX = re.compile(
    r"^(?:第[一二三四五六123456]+\s*[块步招个拍条]"
    r"|[①②③④⑤⑥⑦⑧]|[1-6]\s*[.、）\)])"
    r"?\s*",
)


def clean_blueprint(
    bp: dict,
    *,
    story_type: str | None = None,
) -> tuple[dict, list[str]]:
    """本地清洗确定性格式错误：剥 beats 序号前缀、丢空条。

    校验失败后先试这个再重烧 Pro；返回 (清洗后骨架, 改动说明)。
    """
    if not isinstance(bp, dict):
        return bp, []
    beats = bp.get("beats")
    if not isinstance(beats, list):
        return bp, []
    notes: list[str] = []
    cleaned: list[Any] = []
    changed = False
    for b in beats:
        s = str(b or "").strip()
        new = _RE_BEAT_ORDINAL_PREFIX.sub("", s).strip()
        if not new:
            changed = True
            notes.append(f"beats 丢空条 {s!r}")
            continue
        if new != s:
            changed = True
            notes.append(f"beats 剥序号 {s!r}→{new!r}")
        cleaned.append(new)
    if changed:
        bp = dict(bp)
        bp["beats"] = cleaned
    return bp, notes


def format_blueprint_block(bp: dict) -> str:
    """注入 D2 user 的可读骨架块。"""
    lines = ["【笑点骨架·只许表演不许换歪读】"]
    order = (
        "setup",
        "rule",
        "key_line",
        "twist",
        "beats",
        "persona",
        "fix",
        "boom",
    )
    labels = {
        "setup": "铺垫",
        "rule": "规矩",
        "key_line": "关键台词",
        "twist": "歪读",
        "beats": "递进",
        "persona": "性格意图",
        "fix": "破规",
        "boom": "回旋镖扣法",
    }
    for key in order:
        if key not in bp:
            continue
        val = bp[key]
        if key == "beats" and isinstance(val, list):
            val = " → ".join(str(x) for x in val)
        lines.append(f"- {labels.get(key, key)}：{val}")
    return "\n".join(lines)


def expansion_outline_for(
    bp: dict,
    *,
    story_type: str | None = None,
) -> str:
    code = parse_story_type_code(story_type=story_type) if story_type else "D"
    mod = _load_type_mod(code)
    if mod is None or not getattr(mod, "ENABLED", False):
        return ""
    return str(mod.expansion_outline(bp))


def apply_blueprint_to_story(
    story: dict,
    bp: dict,
    *,
    story_type: str | None = None,
) -> None:
    """写入 punchline_blueprint，并投影 conflict_core / punchline_explain。"""
    if not isinstance(story, dict) or not isinstance(bp, dict):
        return
    story["punchline_blueprint"] = bp
    code = parse_story_type_code(story_type=story_type) if story_type else "D"
    mod = _load_type_mod(code)
    if mod is None or not getattr(mod, "ENABLED", False):
        return
    core, punch = mod.project_meta(bp)
    if core and not str(story.get("conflict_core") or "").strip():
        story["conflict_core"] = core
    elif core:
        story["conflict_core"] = core
    if punch:
        story["punchline_explain"] = punch


def build_punchline_blueprint_prompts(
    theme: str,
    *,
    story_type: str | None = None,
) -> tuple[str, str]:
    """构造 D1.5 Pro 用 system + user。"""
    code = parse_story_type_code(story_type=story_type) if story_type else "D"
    label = STORY_TYPE_LABELS.get(code, code)
    tag = story_type_tag(code)
    mod = _load_type_mod(code)
    if mod is None or not getattr(mod, "ENABLED", False):
        raise ValueError(f"{code}类笑点骨架为空实现")

    system = (
        "你是一位喜剧结构师。给定主题与矛盾类型，只输出一个极简 JSON 笑点骨架，"
        "禁止写完整对白、禁止分镜、禁止解释性长文。\n"
        f"{mod.SYSTEM_APPEND}"
    )
    user = (
        f"主题：{theme}\n"
        f"类型：{tag}（{label}）\n"
        f"{mod.USER_FEW_SHOT}\n"
        "请只输出一个 JSON 对象（不要 markdown 围栏）。"
    )
    return system, user


def parse_blueprint_response(raw: Any) -> dict:
    """从 LLM JSON 结果抽出骨架对象。"""
    if isinstance(raw, dict):
        if "punchline_blueprint" in raw and isinstance(
            raw["punchline_blueprint"], dict,
        ):
            return raw["punchline_blueprint"]
        if "blueprint" in raw and isinstance(raw["blueprint"], dict):
            return raw["blueprint"]
        if "story_plan" in raw and isinstance(raw["story_plan"], dict):
            return raw["story_plan"]
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        data = json.loads(text)
        return parse_blueprint_response(data)
    raise ValueError("笑点骨架响应无法解析为对象")
