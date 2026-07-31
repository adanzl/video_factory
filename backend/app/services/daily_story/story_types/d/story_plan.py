"""D 类笑点骨架：字段、校验、展开提纲。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types.d.humor import RE_TWIST_VISUAL

# True = 走 D1.5；A/B/C/E 空实现为 False
ENABLED = True

# 共享壳 + D 扩展
D_BLUEPRINT_KEYS = (
    "setup",
    "rule",
    "key_line",
    "twist",
    "beats",
    "persona",
    "fix",
    "boom",
)

_FIELD_MAX = {
    "setup": 16,
    "rule": 8,
    "key_line": 12,
    "twist": 20,
    "persona": 16,
    "fix": 12,
    "boom": 16,
}
_BEAT_MAX = 10
_BEAT_N_MIN = 3
_BEAT_N_MAX = 4

_RE_DIALOGUE_LEAK = re.compile(
    r"[：:]|昭昭说|灿灿说|妈妈说|你自己说.{0,12}怎么",
)
_RE_TWIST_ARROW = re.compile(r"→|->|读成|歪读")


SYSTEM_APPEND = """\
【D·笑点骨架】你是喜剧结构师，只设计「字面执行」骨架，禁止写对白。
输出 JSON 对象，字段仅：
setup, rule, key_line, twist, beats, persona, fix, boom。
- setup≤16字：情境一帧
- rule≤8字：规矩核（如系紧）
- key_line≤12字：可被回旋镖引用的叮嘱子串
- twist≤20字：规矩词的第二种读法（须含→或「读成」）
- beats：3～4条，各≤10字，同一歪读可拍递进（禁第一块第二块）
- persona≤16字：中段性格意图（非对白原文，如「惨状当正确证明」）
- fix≤12字：叮嘱方破规动作
- boom≤16字：扣法说明（key_line×上手破规），禁止完整对白句
整卡宜短；不要 dialogue / 分镜。
"""

USER_FEW_SHOT = """\
【正例·鞋带】
{"setup":"玄关系鞋带出门","rule":"系紧","key_line":"鞋带要系紧","twist":"越紧越好→打死结","beats":["拉到底","花生米结","抽紧试走","脚麻焊死"],"persona":"惨状当正确证明","fix":"上手抠开死结","boom":"扣key_line×现在又解"}

【正例·收玩具】
{"setup":"客厅收玩具进箱","rule":"轻轻放","key_line":"轻轻放进箱子","twist":"先地上轻轻码塔再进箱","beats":["轻轻码第一层","再码高一层","塔开始晃","哗一下倒地"],"persona":"码齐才算轻轻","fix":"一把扫进箱","boom":"扣key_line×动手扫乱"}
"""


def expansion_outline(bp: dict) -> str:
    """D2 Flash 用的展开提纲（非对白范文）。"""
    beats = [str(b) for b in (bp.get("beats") or [])]
    beat_txt = " → ".join(beats) if beats else "（按 twist 递进 3 拍）"
    return (
        "【D·按骨架展开·逐拍硬性】\n"
        f"1. 点到 setup，勿展开互怼。\n"
        f"2. 灿灿立规，只说一次 key_line「{bp.get('key_line') or bp.get('rule') or ''}」。\n"
        f"3. 昭昭按 beats 顺序逐拍演：{beat_txt}。\n"
        "   每一拍都要有昭昭第一人称报出自己正在做的动作，一拍都不许跳；\n"
        f"   歪读关键拍（twist「{bp.get('twist') or ''}」落地那一拍）必须由昭昭\n"
        "   亲口亲手演出来，禁止跳过后靠灿灿一句惊呼补认。\n"
        "   每拍惨状须换新形态（东西/姿势/位置变了才算一拍），\n"
        "   禁止同一件事只换形容词原地加码；\n"
        f"   中段兑现 persona「{bp.get('persona') or ''}」（意图，勿整句照抄）。\n"
        f"4. 灿灿破规：{bp.get('fix') or '上手补救'}。破规动作要先在对白里演出来\n"
        "   （工具从哪来、手上在干什么），完成在昭昭点破之前，\n"
        "   禁止只在昭昭台词里被追认。\n"
        f"5. 昭昭回旋镖：引用 key_line，并点破上手破规"
        f"（按 boom「{bp.get('boom') or ''}」现场组织口语，禁止照抄 boom 原文当台词）。\n"
        "6. 灿灿哼/算了收束，勿再发指令。\n"
        "全程只用本骨架里的物件与动词，禁止套用其他主题的旧梗字眼"
        "（骨架没有「焊」就不许出现「焊」）。"
    )


def validate(bp: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(bp, dict):
        return ["骨架须为 JSON 对象"]
    for key in D_BLUEPRINT_KEYS:
        if key not in bp:
            errors.append(f"缺字段 {key}")
    if errors:
        return errors

    for key, lim in _FIELD_MAX.items():
        val = str(bp.get(key) or "").strip()
        if not val:
            errors.append(f"{key} 为空")
        elif len(val) > lim:
            errors.append(f"{key} 超过{lim}字（当前{len(val)}）")

    beats = bp.get("beats")
    if not isinstance(beats, list):
        errors.append("beats 须为数组")
    else:
        if not (_BEAT_N_MIN <= len(beats) <= _BEAT_N_MAX):
            errors.append(f"beats 须{_BEAT_N_MIN}～{_BEAT_N_MAX}条")
        for i, b in enumerate(beats):
            s = str(b or "").strip()
            if not s:
                errors.append(f"beats[{i}] 为空")
            elif len(s) > _BEAT_MAX:
                errors.append(f"beats[{i}] 超过{_BEAT_MAX}字")
            if re.search(r"第[一二三四1234]块", s):
                errors.append(f"beats[{i}] 禁止流程块序号")

    twist = str(bp.get("twist") or "")
    if twist and not _RE_TWIST_ARROW.search(twist):
        errors.append("twist 须含→或读成/歪读")
    beats_text = "".join(str(b) for b in (bp.get("beats") or []))
    if twist and not (
        RE_TWIST_VISUAL.search(twist) or RE_TWIST_VISUAL.search(beats_text)
    ):
        # 软提醒仍当硬卡：无可见歪读画面则骨架不合格
        if not re.search(r"死结|塔|倒|溢|焊|花生|扫|码", twist + beats_text):
            errors.append("twist/beats 缺可拍歪读画面")

    boom = str(bp.get("boom") or "")
    if _RE_DIALOGUE_LEAK.search(boom):
        errors.append("boom 禁止写成完整对白")
    key_line = str(bp.get("key_line") or "")
    if key_line and key_line not in boom and str(bp.get("rule") or "") not in boom:
        if "key_line" not in boom and "扣" not in boom:
            errors.append("boom 须扣 key_line/rule")

    return errors


def project_meta(bp: dict) -> tuple[str, str]:
    """投影 conflict_core / punchline_explain。"""
    rule = str(bp.get("rule") or "").strip()
    twist = str(bp.get("twist") or "").strip()
    key = str(bp.get("key_line") or rule).strip()
    fix = str(bp.get("fix") or "").strip()
    boom = str(bp.get("boom") or "").strip()
    core = f"{rule}被读成{twist}" if rule and twist else (twist or rule or "字面执行")
    punch = (
        f"D类字面执行：规矩「{key}」，歪读「{twist}」，"
        f"破规「{fix}」，回旋镖「{boom}」。"
    )
    return core[:40], punch[:120]
