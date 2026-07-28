"""日常故事重试/修订：按本轮首要问题生成单点提示，避免堆叠全套规则。"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MAX,
    DAILY_STORY_BODY_CHARS_MIN,
    DAILY_STORY_RETRY_PATCH_DEFICIT_MAX,
)
from app.services.daily_story.story_types import story_line_for_code


def _parse_body_char_deficit(errors: str) -> int | None:
    m = re.search(r"还差\s*(\d+)\s*字", errors or "")
    return int(m.group(1)) if m else None


def _parse_body_char_excess(errors: str) -> int | None:
    m = re.search(r"超出\s*(\d+)\s*字", errors or "")
    return int(m.group(1)) if m else None

# 数字越小越优先（先修硬性格式，再修收束形态）
_VALIDATION_PRIORITY: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"连说"), "consecutive"),
    (re.compile(rf"超过.*{DAILY_STORY_LINE_CHARS_MAX}字"), "line_too_long"),
    (re.compile(r"总字数须≤"), "body_too_long"),
    (re.compile(r"E类正文过长"), "e_body_too_long"),
    (re.compile(r"汤汁太弱|尝菜眼"), "e_weak_taste_eye"),
    (re.compile(r"引话须|无出处|自造后再假装引用|提前引话"), "quote_ground"),
    (re.compile(r"总字数须≥"), "body_too_short"),
    (re.compile(r"角色反了"), "role_swap"),
    (re.compile(r"收束对白须写完整|未说完|引号"), "c_incomplete_line"),
    (re.compile(r"末段须有回旋镖|实物真相反转"), "c_boomerang"),
    (re.compile(r"末句须被戳穿方"), "c_loser_last"),
    (re.compile(r"末句须写完整或嘴硬"), "c_incomplete_last"),
    (re.compile(r"勿写成 A 式末四拍"), "c_not_a_close"),
    (re.compile(r"收束末两句须换人"), "c_close_alternate"),
    (re.compile(r"无破功软收|弱收束|甩给妈妈"), "soft_close"),
    (re.compile(r"多套免责|借口复读|只能一套免责"), "a_excuse"),
    (re.compile(r"提前引话|引话"), "quote_ground"),
    (re.compile(r"注水|三十下|认真数"), "padding"),
    (re.compile(r"不好玩|吐水算停"), "hammer_beat"),
    (re.compile(r"跑题"), "off_topic"),
    (re.compile(r"C类"), "c_generic"),
)


def split_validation_errors(errors: str) -> list[str]:
    err = (errors or "").strip()
    if err.startswith("daily_story 校验失败:"):
        err = err.removeprefix("daily_story 校验失败:").strip()
    return [p.strip() for p in err.split(";") if p.strip()]


def pick_primary_validation_errors(
    errors: str,
    *,
    max_items: int = 1,
) -> list[str]:
    """从本轮校验文案中取出最高优先的 1 条（默认只修一项）。"""
    fragments = split_validation_errors(errors)
    if not fragments:
        return []
    ranked: list[tuple[int, int, str]] = []
    for idx, frag in enumerate(fragments):
        pri = len(_VALIDATION_PRIORITY)
        for i, (pat, _) in enumerate(_VALIDATION_PRIORITY):
            if pat.search(frag):
                pri = i
                break
        ranked.append((pri, idx, frag))
    ranked.sort(key=lambda t: (t[0], t[1]))
    chosen = ranked[0][2]
    # 差几个字时若同时有引话硬伤，先修引话（句内补字可下轮再做）
    if _classify_validation_fragment(chosen) == "body_too_short":
        deficit = _parse_body_char_deficit(chosen)
        if deficit is not None and deficit <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
            for _, _, frag in ranked:
                if _classify_validation_fragment(frag) == "quote_ground":
                    return [frag]
    return [chosen for _, _, chosen in ranked[: max(1, max_items)]]


def _hint_body_too_short(err: str, *, chars: int) -> str:
    deficit = _parse_body_char_deficit(err)
    if deficit is not None and deficit <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
        return (
            f"【补字·句内】只差 {deficit} 字：在中段 2–3 句各加 2–6 字抬杠语气，"
            f"禁止插入新句、禁止动末四拍；写到 ≥{DAILY_STORY_BODY_CHARS_MIN}。"
        )
    return (
        "【补字】在立规后加 1–2 个新证据来回（量化/动作），"
        "禁止用三十下/认真数/计时器注水凑字。"
    )


def _hint_body_too_long(err: str) -> str:
    excess = _parse_body_char_excess(err)
    if excess is not None and excess <= DAILY_STORY_RETRY_PATCH_DEFICIT_MAX:
        return (
            f"【删字·句内】只从中段 1–2 句各删几个虚词/重复，"
            f"禁止删末四拍；压到 ≤{DAILY_STORY_BODY_CHARS_MAX}。"
        )
    return (
        "【删字】只删中段车轱辘重复句 1–2 句，勿动末四拍与已立赛规。"
    )


_VALIDATION_HINT_BUILDERS: dict[str, Callable[..., str]] = {}


def _register_validation_hints() -> None:
    def consecutive(**_kw: Any) -> str:
        chars = _kw.get("chars", 0)
        return (
            "【连说】把连说拆开：交替 speaker 或合并为一人一句；"
            f"保持约 {chars} 字，勿借机大删末四拍。"
        )

    def line_too_long(**_kw: Any) -> str:
        return (
            f"【单句】超长句压到 ≤{DAILY_STORY_LINE_CHARS_MAX} 字；"
            "可拆给两人轮流说，禁止同人连说硬拆。"
        )

    def c_boomerang(**_kw: Any) -> str:
        return (
            "【C·回旋镖·只改末 4 句】"
            "倒数4=按赛规可见动作/加赛；3=对方喊不算；"
            "2=你刚说/你说的+短赛规（完整一句）；"
            "1=被规则反噬方哼/认了。前文 dialogue 其余行勿动。"
        )

    def c_loser_last(**_kw: Any) -> str:
        return (
            "【C·末句说话人】末句须「被戳穿/吃亏」方嘴硬（哼/行吧/给你），"
            "禁止赢家总结或继续立规矩；只改末 1–2 句 speaker/台词。"
        )

    def c_incomplete_line(**_kw: Any) -> str:
        return (
            "【C·完整句】收束前两句须写完整（≤22字）；"
            "回旋镖可拆成两句，禁止停在引号或未说完。"
        )

    def c_incomplete_last(**_kw: Any) -> str:
        return (
            "【C·末句】补全末句或改成哼/行吧/算了/给你等嘴硬软收。"
        )

    def c_not_a_close(**_kw: Any) -> str:
        return (
            "【C·去A化】删掉「那不一样+哪里不一样」末四拍；"
            "改成赛规回旋镖反问，只改末 4 句。"
        )

    def c_close_alternate(**_kw: Any) -> str:
        return "【C·收束】末两句须灿灿/昭昭交替，禁止同人连说。"

    def soft_close(**_kw: Any) -> str:
        type_code = _kw.get("type_code")
        soft = ""
        if type_code:
            soft = story_line_for_code(type_code).retry_soft_close_hint.strip()
        return soft or (
            "【收束】只改末 2–3 句：先字面戳穿，末句破功方嘴硬；"
            "禁止等妈评理/一人一半和解收场。"
        )

    def e_body_too_long(**_kw: Any) -> str:
        type_code = _kw.get("type_code")
        soft = ""
        if type_code:
            soft = story_line_for_code(type_code).retry_soft_close_hint.strip()
        base = (
            "【E·删句】只删中段同型揭穿/狡辩复读；"
            "保留妈妈立论+开脱+闭环+末句破功；禁止新增台词。"
        )
        return f"{base} {soft}" if soft else base

    def e_weak_taste_eye(**_kw: Any) -> str:
        return (
            "【E·尝菜眼】开场/前段须可拍试吃：勺上沾菜、嘴角油渍、"
            "试吃咽下；禁止「偷尝汤汁」当唯一眼，改勺子或嘴角。"
        )

    _VALIDATION_HINT_BUILDERS.update({
        "consecutive": consecutive,
        "line_too_long": line_too_long,
        "body_too_short": lambda frag, *, chars=0, **_kw: _hint_body_too_short(
            frag, chars=chars,
        ),
        "body_too_long": lambda frag, **_kw: _hint_body_too_long(frag),
        "e_body_too_long": e_body_too_long,
        "e_weak_taste_eye": e_weak_taste_eye,
        "c_incomplete_line": c_incomplete_line,
        "c_boomerang": c_boomerang,
        "c_loser_last": c_loser_last,
        "c_incomplete_last": c_incomplete_last,
        "c_not_a_close": c_not_a_close,
        "c_close_alternate": c_close_alternate,
        "soft_close": soft_close,
        "c_generic": c_boomerang,
        "off_topic": lambda **_kw: "【跑题】删掉后半无关句，回到 conflict_core。",
        "role_swap": lambda **_kw: "【角色】昭昭=弟弟、灿灿=姐姐，改正自称与立场。",
        "quote_ground": lambda **_kw: (
            "【引话·只改1–2句】引话须是前文真实子串；"
            "改埋句或改引话，禁止整篇重写。"
        ),
        "padding": lambda **_kw: (
            "【删注水】删三十下/认真数/帮你盯；用抬杠补字，只留一套免责。"
        ),
        "a_excuse": lambda **_kw: (
            "【单线借口】偷吃只留「检查不算吃」；咽下后立刻末四拍。"
        ),
        "hammer_beat": lambda **_kw: (
            "【一锤】下一来回必须示范吐水/偷停，勿只口头争论。"
        ),
    })


_register_validation_hints()


def _classify_validation_fragment(fragment: str) -> str:
    for pat, key in _VALIDATION_PRIORITY:
        if pat.search(fragment):
            return key
    return "unknown"


def build_validation_retry_hints(
    errors: str,
    *,
    chars: int,
    type_code: str | None = None,
    max_issues: int = 1,
) -> str:
    """按首要校验失败项生成 1 条修订指令（字数方向由 length_mode 另管）。"""
    primaries = pick_primary_validation_errors(errors, max_items=max_issues)
    if not primaries:
        return ""
    hints: list[str] = []
    for frag in primaries:
        key = _classify_validation_fragment(frag)
        builder = _VALIDATION_HINT_BUILDERS.get(key)
        if not builder:
            continue
        if key == "body_too_short":
            hints.append(builder(frag, chars=chars))
        elif key == "body_too_long":
            hints.append(builder(frag))
        else:
            hints.append(builder(chars=chars, type_code=type_code))
    if not hints:
        hints.append(
            f"【本轮】只修校验指出的问题，保持约 {chars} 字，勿整稿重写。"
        )
    return "\n".join(hints) + "\n"


# ── 观感修订：一次只推一个维度 ──

_QUALITY_CON_PRIORITY: tuple[tuple[str, str], ...] = (
    ("收束引话无出处", "quote"),
    ("B事实", "fact"),
    ("C事实", "fact"),
    ("可核对事实", "fact"),
    ("B开场", "opening"),
    ("C开场", "opening"),
    ("C收束缺可拍争法", "c_filmable"),
    ("C中段归属口水战", "c_chatter"),
    ("C收束偏A", "c_de_a"),
    ("好笑不足", "humor"),
    ("格式达标但好笑", "humor"),
    ("绕圈", "redundancy"),
    ("复读拖沓", "redundancy"),
    ("身份/把关话术", "redundancy"),
)


def pick_primary_quality_issue(
    cons: list[str],
) -> tuple[str | None, str | None]:
    """返回 (kind, matched_con_text)。"""
    for needle, kind in _QUALITY_CON_PRIORITY:
        hit = next((c for c in cons if needle in c), None)
        if hit:
            return kind, hit
    return None, None


def revision_scope_kind(
    *,
    primary_kind: str | None,
    escalation: bool,
    closing: bool,
) -> str:
    if primary_kind in ("c_filmable", "c_chatter", "redundancy"):
        return "mid"
    if primary_kind in ("fact", "opening"):
        return "last4" if primary_kind == "fact" else "opening"
    if primary_kind in ("quote", "c_de_a"):
        return "last4"
    if primary_kind == "humor":
        return "mid"
    if closing and not escalation:
        return "last4"
    if escalation:
        return "mid"
    return "mid"


def format_c_dialogue_scope_hint(story: dict, scope: str) -> str:
    dialogue = story.get("dialogue")
    n = len(dialogue) if isinstance(dialogue, list) else 0
    if n < 6:
        return ""
    if scope == "last4":
        start = max(0, n - 4)
        return (
            f"【改稿范围】只改 dialogue 第 {start + 1}–{n} 行（末段收束）；"
            f"第 1–{start} 行须原样保留。"
        )
    end = max(3, n - 4)
    return (
        f"【改稿范围】只改 dialogue 第 3–{end} 行（中段交锋）；"
        "末 4 句收束逐字保留，禁止改坏回旋镖。"
    )

