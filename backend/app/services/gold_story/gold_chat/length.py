"""gold_chat 对白长度修整与垫字痕迹清理。

通用截短、垫字、可读扩写与中段补句；类型契约和 LLM 重写仍由
``convert.py`` / ``story_types`` 编排。
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MIN,
    dialogue_total_chars,
)
from app.services.gold_story.gold_chat.pad_stack import (
    apply_clear_pad_sanitize,
    pad_stack_issue_for_line,
    sanitize_pad_stack_line,
)
from app.services.gold_story.gold_chat.prompts import CHAT_MAX_LINE_CHARS

# 240 是硬线；本地机械收口不再为追求 250 软余量额外灌字。
GOLD_CHAT_LOCAL_LENGTH_TARGET = DAILY_STORY_BODY_CHARS_MIN


_LINE_TRIM_SUFFIXES = (
    "！",
    "。",
    "!",
    "？",
    "?",
    "啊",
    "呢",
    "吧",
    "嘛",
    "呀",
    "哦",
)

# 已停用灌尾巴（毁可读性）；保留常量供机审/剥除识别。
_GOLD_CHAT_LINE_EXPAND: tuple[str, ...] = (
    "，你给我听好了",
    "，这回算清楚",
    "，别再装傻",
    "，我可记住了",
    "，说了就不改",
    "，再闹我可恼了",
)
_GOLD_CHAT_EXPAND_CLUTTER: tuple[str, ...] = tuple(
    clause.lstrip("，,") for clause in _GOLD_CHAT_LINE_EXPAND
) + (
    "少废话听我的",
    "你少来这套",
    "我就不服",
    "你再闹试试",
    "凭什么听你的",
    "我说怎样就怎样",
)

# 历史通用 near-miss 尾巴：保留仅用于清理/兼容旧候选，禁止再作为补字源。
# 这些短语会无视上下文强化人物态度，曾制造「我偏就不信/说一不二」等机械拼接。
_GOLD_CHAT_LEGACY_ATTITUDE_EXPAND: tuple[str, ...] = (
    "，我偏就不信",
    "，你试试看啊",
    "，我才不怕呢",
    "，少跟我吵啊",
    "，马上给我挪开",
    "，不许再耍赖了",
    "，别再乱动了",
    "，我可记住啦",
    "，说一不二",
    "，再闹我恼了",
    "，给我站住",
    "，轮不到你",
    "，我先说定",
)
# 普通类型不做固定态度句内扩写；O/K 等必须走各自类型专用实义扩写。
_GOLD_CHAT_NATURAL_EXPAND: tuple[str, ...] = ()
_GOLD_CHAT_EXPAND_SOFT_CLUTTER: tuple[str, ...] = (
    "听见没有呀",
    "这回听清楚",
    "听见没有",
    "这回听清楚",
    "你听着了呀",
    "你听着呀",
    "你听着",
)


def _overlong_line_indices(
    story: dict[str, Any],
    max_chars: int = CHAT_MAX_LINE_CHARS,
) -> list[int]:
    out: list[int] = []
    for index, item in enumerate(story.get("dialogue") or [], 1):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if len(line) > max_chars:
            out.append(index)
    return out


def _trim_line_det(
    line: str,
    max_chars: int = CHAT_MAX_LINE_CHARS,
) -> str:
    """超长不多时去尾语气/标点，避免整稿重抽。"""
    text = str(line or "").strip()
    guard = 0
    while len(text) > max_chars and guard < 8:
        guard += 1
        trimmed = False
        for suffix in _LINE_TRIM_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
                trimmed = True
                break
        if not trimmed:
            break
    return text


def _apply_deterministic_shorten(
    story: dict[str, Any],
    *,
    max_chars: int = CHAT_MAX_LINE_CHARS,
) -> tuple[dict[str, Any], bool]:
    """逐句微 trim；有改动则返回新 story。"""
    indices = _overlong_line_indices(story, max_chars)
    if not indices:
        return story, False
    out = copy.deepcopy(story)
    rows = out.get("dialogue") or []
    changed = False
    for number in indices:
        index = number - 1
        if not (0 <= index < len(rows) and isinstance(rows[index], dict)):
            continue
        old = str(rows[index].get("line") or "").strip()
        new = _trim_line_det(old, max_chars)
        if new != old and len(new) <= max_chars:
            rows[index]["line"] = new
            changed = True
    return out, changed


def _sanitize_pad_suffix_line(line: str) -> str:
    """机械去叠语气词（与 pad_stack 共用）。"""
    return sanitize_pad_stack_line(line)


def patch_sanitize_pad_suffix(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """垫字后收口：去掉呢呢/啊呢/复合真的了呢等叠尾。"""
    return apply_clear_pad_sanitize(story)


def _strip_extra_natural_expands(line: str) -> str:
    """句内最多保留 1 条可读扩写尾巴；剥软灌尾。"""
    text = str(line or "").strip()
    if not text:
        return text
    tail_mark = text[-1] if text[-1] in "！。？…!" else ""
    body = text[:-1] if tail_mark else text
    for soft in _GOLD_CHAT_EXPAND_SOFT_CLUTTER:
        body = body.replace(f"，{soft}", "").replace(soft, "")
    bare_all = [
        clause.lstrip("，,") for clause in _GOLD_CHAT_LEGACY_ATTITUDE_EXPAND
    ]
    for bare in bare_all:
        while body.count(bare) > 1:
            body = body.replace(bare, "", 1)
    hits = [(body.find(bare), bare) for bare in bare_all if bare in body]
    if len(hits) <= 1:
        body = re.sub(r"[，,]{2,}", "，", body).strip("，, ")
        return (body + tail_mark) if body else text
    hits.sort(key=lambda item: item[0])
    for _, bare in hits[1:]:
        body = body.replace(f"，{bare}", "").replace(bare, "")
    body = re.sub(r"[，,]{2,}", "，", body).strip("，, ")
    if not body:
        return text
    return body + (tail_mark or "！")


def patch_sanitize_natural_expand_stack(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """每句最多 1 条 near-miss 扩写尾巴，防垫字感堆叠。"""
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        new = _strip_extra_natural_expands(old)
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_sanitize_pad_particles(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """剥句尾「了呀/了吧/了啊」与软灌尾。"""
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        cleaned = re.sub(r"([！。？])[呀啊吧]+([！。？])$", r"\1", old)
        if cleaned != old:
            item["line"] = cleaned
            changed = True
            old = cleaned
        tail_mark = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if tail_mark else old
        new_body = re.sub(r"了[呀吧啊]{2,}$", "了", body)
        new_body = re.sub(r"啊{2,}$", "啊", new_body)
        new_body = re.sub(r"吧{2,}", "吧", new_body)
        new_body = re.sub(r"吗吧+", "吗", new_body)
        new_body = re.sub(r"呀呀+", "呀", new_body)
        new_body = re.sub(r"来呀来呀", "来呀", new_body)
        new_body = re.sub(r"呀吧$", "呀", new_body)
        new_body = re.sub(r"吗啊+", "吗", new_body)
        new_body = re.sub(r"了[呀吧啊]$", "", new_body)
        new_body = re.sub(r"了呢呀$", "了呢", new_body)
        new_body = re.sub(r"了啊呀$", "了啊", new_body)
        new_body = re.sub(r"这?我不我", "我", new_body)
        new_body = re.sub(r"我我(?=[才不])", "我", new_body)
        new_body = re.sub(r"这你(?:等|还)我才", "我才", new_body)
        new_body = re.sub(r"这还不?我才", "我才", new_body)
        new_body = re.sub(r"哼吧", "哼", new_body)
        new_body = re.sub(r"…+吧…*", "……", new_body)
        new_body = re.sub(r"吧{2,}", "吧", new_body)
        for soft in _GOLD_CHAT_EXPAND_SOFT_CLUTTER:
            new_body = new_body.replace(f"，{soft}", "").replace(soft, "")
        new_body = re.sub(r"[，,]{2,}", "，", new_body).strip("，, ")
        if new_body != body and new_body:
            item["line"] = new_body + (tail_mark or "！")
            changed = True
    return out, changed


def patch_strip_all_natural_expands(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """终稿：剥尽 near-miss 可读扩写尾巴，改由粒子补字。"""
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        tail_mark = old[-1] if old[-1] in "！。？…!" else ""
        body = old[:-1] if tail_mark else old
        for bare in sorted(
            [
                clause.lstrip("，,")
                for clause in _GOLD_CHAT_LEGACY_ATTITUDE_EXPAND
            ],
            key=len,
            reverse=True,
        ):
            body = body.replace(f"，{bare}", "").replace(bare, "")
        for soft in _GOLD_CHAT_EXPAND_SOFT_CLUTTER:
            body = body.replace(f"，{soft}", "").replace(soft, "")
        body = re.sub(r"了[呀吧啊]$", "", body)
        body = re.sub(r"[，,]{2,}", "，", body).strip("，, ")
        if not body:
            continue
        new = body + (tail_mark or "！")
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


def patch_sanitize_bridge_lines(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """桥接句保持短句，勿叠 near-miss 扩写尾巴。"""
    bridges = (
        "等等，先听我说完",
        "你别插嘴，轮到我了",
        "你别插嘴，轮到我",
        "先别吵，听清楚",
    )
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        for bridge in bridges:
            if bridge in line and line != f"{bridge}！":
                item["line"] = f"{bridge}！"
                changed = True
                break
    return out, changed


def _strip_expand_clutter_line(line: str) -> str:
    """剥句内扩写灌尾巴（可读性硬伤）。"""
    text = str(line or "").strip()
    if not text:
        return text
    tail_mark = text[-1] if text[-1] in "！。？…!" else ""
    body = text[:-1] if tail_mark else text
    for clause in _GOLD_CHAT_EXPAND_CLUTTER:
        body = body.replace(f"，{clause}", "").replace(clause, "")
    body = re.sub(r"[，,]{2,}", "，", body).strip("，, ")
    if not body:
        return text
    return body + (tail_mark or "！")


def patch_sanitize_expand_clutter(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """剥扩写灌尾巴；字数跌破 min 交上层重生成，勿再灌回去。"""
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old or not any(clause in old for clause in _GOLD_CHAT_EXPAND_CLUTTER):
            continue
        new = _strip_expand_clutter_line(old)
        if new != old:
            item["line"] = new
            changed = True
    return out, changed

# 差 ≤60 字本地可读扩写/粒子收口（FIX 常停在 190–220）
GOLD_CHAT_NEAR_MISS_DEFICIT_MAX = 60
_B_GOLD_CHAT_PAD_TAILS = ("呀", "啊", "嘛", "呢", "吧")
_F_GOLD_CHAT_PAD_TAILS = ("呀", "啊", "嘛", "呢", "吧")
# K：禁「真的呀/好不好/嘛」多轮升级成嘛呀/真的呀真的
_K_GOLD_CHAT_PAD_TAILS = ("啊", "吧", "呀")


_C_SAFE_PAD_TAILS = ("啊", "吧")  # 单语气词；禁叠成了呢了呀
# 禁「现在/立刻/马上/快点」——near-miss 多轮会叠成句尾垃圾
_C_SAFE_PAD_PHRASES = (
    "真的",
    "不行",
)
# 普通类型禁止用无上下文的抬杠反应句补字；类型化中段句只走下方专用池。
_GOLD_CHAT_REACT_LINES: tuple[tuple[str, str], ...] = ()
# O：字数不够只插「死磕过程 / 资源溜走」实义对，禁止复用抬杠反应库
_O_NATURAL_MID_PAIRS: tuple[tuple[tuple[str, str], tuple[str, str]], ...] = (
    (
        ("昭昭", "认真出！我这回稳赢！"),
        ("灿灿", "你赢你的，我先动筷了。"),
    ),
    (
        ("昭昭", "再来一把，看谁先赢够！"),
        ("灿灿", "你接着比，桌上可不等你。"),
    ),
    (
        ("昭昭", "嘿，又是我赢！"),
        ("灿灿", "赢了就快点夹，别磨蹭。"),
    ),
    (
        ("昭昭", "专心比，我还能再赢！"),
        ("灿灿", "你比你的，我吃我的。"),
    ),
    (
        ("昭昭", "出拳！我还没玩够！"),
        ("灿灿", "你玩你的，份额可越来越少。"),
    ),
)
_O_GOLD_CHAT_PAD_TAILS = ("呀", "啊", "吧")  # 单语气词；禁 particle_upgrade 叠字
# O 句内扩写：只允许过程/催夹实义，禁抬杠/记仇类 clutter
_O_SAFE_NATURAL_EXPAND: tuple[str, ...] = (
    "，认真点",
    "，别磨蹭",
    "，接着比",
    "，快点夹",
    "，桌上见底了",
)
# 可读中段加句（FIX 停滞时插；J：昭求/灿否成对，禁角色对调）
_GOLD_CHAT_NATURAL_MID_PAIRS: tuple[tuple[tuple[str, str], tuple[str, str]], ...] = (
    (
        ("昭昭", "再求你一次，这回你就松口吧！"),
        ("灿灿", "不行，规矩就是这样定的！"),
    ),
    (
        ("昭昭", "那我保证，这次一定听你的！"),
        ("灿灿", "保证也没用，现在先听我的！"),
    ),
    (
        ("昭昭", "就这一次，下次再听你安排！"),
        ("灿灿", "少讨价还价，这回听我安排！"),
    ),
)
_M8_J_NATURAL_MID_PAIRS: tuple[tuple[tuple[str, str], tuple[str, str]], ...] = (
    (
        ("昭昭", "我才不服，再来一回合！"),
        ("灿灿", "来啊，看谁先认输！"),
    ),
    (
        ("昭昭", "你别得意，我还没发力呢！"),
        ("灿灿", "行了，谁赢谁说了算，别磨蹭！"),
    ),
    (
        ("昭昭", "你真敢跟我动手啊？"),
        ("灿灿", "规矩先讲好，输了别赖账！"),
    ),
)
# K：只补抽象互顶与僵持，不凭空新增道具、追跑或肢体动作。
_K_NATURAL_MID_PAIRS: tuple[tuple[tuple[str, str], tuple[str, str]], ...] = (
    (
        ("昭昭", "你别想让我认输，这事还没完！"),
        ("灿灿", "没完就没完，我也不会让你！"),
    ),
    (
        ("昭昭", "你再说一遍试试，我就是不服！"),
        ("灿灿", "说就说，谁怕谁啊！"),
    ),
    (
        ("昭昭", "我偏不让步，你能怎么样！"),
        ("灿灿", "我也不让，咱们就这么僵着！"),
    ),
    (
        ("昭昭", "我瞪你！下次记着！"),
        ("灿灿", "瞪吧，谁怕谁啊！"),
    ),
    (
        ("昭昭", "你别得意，我可没认输！"),
        ("灿灿", "不认就不认，我也不理你！"),
    ),
    (
        ("昭昭", "你等着，我记仇！"),
        ("灿灿", "记就记，这事谁也别想糊弄过去！"),
    ),
)
# K near-miss 可读扩写：按说话人分流，禁串角/禁粘护手句
_K_ZHAO_NATURAL_EXPAND: tuple[str, ...] = (
    "，我才不怕呢",
    "，你试试看啊",
    "，我偏不让步",
    "，我继续顶着",
)
_K_CAN_NATURAL_EXPAND: tuple[str, ...] = (
    "，再闹我恼了",
    "，轮不到你说",
    "，我继续顶着",
    "，谁怕谁啊",
)
_K_GOLD_CHAT_NATURAL_EXPAND: tuple[str, ...] = (
    _K_ZHAO_NATURAL_EXPAND + _K_CAN_NATURAL_EXPAND
)
_RE_K_NO_EXPAND_LINE = re.compile(r"弄疼我手|打归打|手疼|护手")
# J 扩写尾巴 speaker 禁忌（防权威/挑衅语气错位）
_J_ZHAO_FORBIDDEN_EXPAND: frozenset[str] = frozenset(
    {
        "少跟我吵",
        "轮不到你",
        "不许再耍赖",
        "马上给我挪开",
        "给我站住",
        "我先说定",
        "说一不二",
    }
)
_J_CAN_FORBIDDEN_EXPAND: frozenset[str] = frozenset(
    {"你试试看", "少跟我吵", "我才不怕", "你凭什么"}
)
# I：禁语义错位/审稿点名凑字尾巴（抽象禁表，不绑单篇）
_I_FORBIDDEN_EXPAND: frozenset[str] = frozenset(
    {
        "我可记住啦",
        "别再乱动了",
        "马上给我挪开",
        "给我站住",
        "说一不二",
        "轮不到你",
        "我偏就不信",
    }
)


def _j_lose_line_index(dialogue: list[Any]) -> int:
    for i, x in enumerate(dialogue):
        if not isinstance(x, dict):
            continue
        if (
            str(x.get("speaker") or "").strip() == "昭昭"
            and re.search(r"我输了|认输", str(x.get("line") or ""))
        ):
            return i
    return -1


def _j_expand_bare_allowed(bare: str, speaker: str) -> bool:
    """near-miss 扩写按 speaker 过滤，防权威/挑衅错位。"""
    sp = str(speaker or "").strip()
    b = str(bare or "").strip()
    if not b:
        return False
    if sp == "昭昭" and any(x in b or b in x for x in _J_ZHAO_FORBIDDEN_EXPAND):
        return False
    if sp == "灿灿" and any(x in b or b in x for x in _J_CAN_FORBIDDEN_EXPAND):
        return False
    return True


def _pad_gold_chat_single_particle(
    line: str,
    need: int,
    *,
    used: set[str] | None = None,
    tails: tuple[str, ...] = ("啊", "呢", "吧", "呀"),
) -> tuple[str, int]:
    """gold_chat 安全 near-miss：最多补一个单粒子，已有语气词绝不升级。"""
    text = str(line or "").strip()
    if need <= 0 or not text:
        return text, 0
    trail = ""
    core = text
    if core[-1] in "。！？…!?":
        trail = core[-1]
        core = core[:-1]
    if not core or core[-1] in "啦嘛呀啊呢吧哦喔咯呗":
        return text, 0
    room = max(0, CHAT_MAX_LINE_CHARS - len(text))
    if room <= 0:
        return text, 0
    for tail in tails:
        if len(tail) != 1 or len(tail) > need or len(tail) > room:
            continue
        if used is not None and tail in used:
            continue
        if used is not None:
            used.add(tail)
        return f"{core}{tail}{trail}", 1
    return text, 0


def _pad_gold_chat_line(
    line: str,
    need: int,
    *,
    used: set[str] | None = None,
    story_type: str = "",
    speaker: str = "",
) -> tuple[str, int]:
    """near-miss 本地垫字：类型专用规则优先；普通类型只补单粒子。"""
    st = str(story_type or "").strip().upper()
    if st == "C":
        s = str(line or "").strip()
        if need <= 0:
            return s, 0
        from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX

        core = s.rstrip("！。？…!")
        tail_mark = s[len(core) :]
        room = max(0, DAILY_STORY_LINE_CHARS_MAX - len(s))
        if room <= 0:
            return s, 0
        if not re.search(r"[呢嘛呀啊吧了]$", core):
            for tail in _C_SAFE_PAD_TAILS:
                if used is not None and tail in used:
                    continue
                if len(tail) > need or len(tail) > room:
                    continue
                if used is not None:
                    used.add(tail)
                return core + tail + tail_mark, len(tail)
        for phr in _C_SAFE_PAD_PHRASES:
            if used is not None and phr in used:
                continue
            if core.endswith(phr):
                continue
            if len(phr) > need or len(phr) > room:
                continue
            if used is not None:
                used.add(phr)
            return core + phr + tail_mark, len(phr)
        return s, 0
    if st == "J":
        return _pad_gold_chat_single_particle(
            line,
            need,
            used=used,
            tails=("啊", "吧"),
        )
    if st == "O":
        # O：优先单语气词；已有语气词则改补安全实义尾巴（禁 particle_upgrade）
        from app.services.daily_story.dialogue_text import (
            DAILY_STORY_LINE_CHARS_MAX,
            dialogue_char_count,
        )

        text = str(line or "").strip()
        if need <= 0 or not text:
            return line, 0
        trail = ""
        core = text
        if core[-1] in "。！？…":
            trail = core[-1]
            core = core[:-1]
        if not core:
            return line, 0
        room = max(0, DAILY_STORY_LINE_CHARS_MAX - dialogue_char_count(text))
        if not re.search(r"[呢嘛呀啊吧了呗]$", core):
            for tail in _O_GOLD_CHAT_PAD_TAILS:
                if used is not None and tail in used:
                    continue
                if len(tail) > need or len(tail) > room:
                    continue
                if used is not None:
                    used.add(tail)
                return f"{core}{tail}{trail}", len(tail)
        # 大缺口才补实义尾巴；仅死磕/催夹句可扩，避免「少了？+接着比」错位
        if (
            need >= 4
            and "，" not in core
            and "," not in core
            and re.search(r"赢|再来|夹|比|出拳|认真", core)
        ):
            for phr in _O_SAFE_NATURAL_EXPAND:
                bare = phr.lstrip("，,")
                if used is not None and bare in used:
                    continue
                if bare in core or core.endswith(bare):
                    continue
                if len(phr) > need or len(phr) > room:
                    continue
                if used is not None:
                    used.add(bare)
                return f"{core}{phr}{trail}", len(phr)
        return line, 0
    if st == "B":
        return _pad_gold_chat_single_particle(
            line,
            need,
            used=used,
            tails=_B_GOLD_CHAT_PAD_TAILS,
        )
    if st == "F":
        return _pad_gold_chat_single_particle(
            line,
            need,
            used=used,
            tails=_F_GOLD_CHAT_PAD_TAILS,
        )
    if st == "K":
        # K：只在句尾无语气词时补一个呀/啊/吧；禁止 particle_upgrade 叠成了呀
        from app.services.daily_story.dialogue_text import (
            DAILY_STORY_LINE_CHARS_MAX,
            dialogue_char_count,
        )

        text = str(line or "").strip()
        if need <= 0 or not text or _RE_K_NO_EXPAND_LINE.search(text):
            return line, 0
        trail = ""
        core = text
        if core[-1] in "。！？…":
            trail = core[-1]
            core = core[:-1]
        if not core or re.search(r"[呢嘛呀啊吧了呗]$", core):
            return line, 0
        room = max(0, DAILY_STORY_LINE_CHARS_MAX - dialogue_char_count(text))
        for tail in _K_GOLD_CHAT_PAD_TAILS:
            if used is not None and tail in used:
                continue
            if len(tail) > need or len(tail) > room:
                continue
            if used is not None:
                used.add(tail)
            return f"{core}{tail}{trail}", len(tail)
        return line, 0
    return _pad_gold_chat_single_particle(
        line,
        need,
        used=used,
    )


def _o_goal_punch_index(dialogue: list[Any]) -> int:
    """O 点题认栽句下标；无则 -1。"""
    from app.services.daily_story.story_types.o.validate import RE_GOAL_PUNCH

    idxs = [
        i
        for i, item in enumerate(dialogue)
        if isinstance(item, dict)
        and RE_GOAL_PUNCH.search(str(item.get("line") or ""))
    ]
    return idxs[-1] if idxs else -1


def _gold_chat_pad_indices(
    dialogue: list[Any],
    *,
    story_type: str,
) -> list[int]:
    """可垫字行号；I 排除收束段；O 排除点题句及之后。"""
    indices = [
        i
        for i, item in enumerate(dialogue)
        if isinstance(item, dict)
        and str(item.get("speaker") or "") in {"昭昭", "灿灿"}
    ] or list(range(len(dialogue)))
    st = str(story_type or "").strip().upper()
    if st == "O":
        punch = _o_goal_punch_index(dialogue)
        if punch >= 0:
            kept = [i for i in indices if i < punch]
            return kept or indices
        return indices
    if st != "I":
        return indices
    from app.services.daily_story.story_types.i.validate import (
        RE_SPEECHLESS,
        RE_WIN_STUBBORN,
    )

    lines = [
        str(item.get("line") or "")
        for item in dialogue
        if isinstance(item, dict)
    ]
    protected: set[int] = set()
    for i, ln in enumerate(lines):
        if RE_SPEECHLESS.search(ln):
            protected.update(range(i, len(dialogue)))
            break
    for i, item in enumerate(dialogue):
        if isinstance(item, dict) and RE_WIN_STUBBORN.search(
            str(item.get("line") or "")
        ):
            protected.add(i)
    if len(dialogue) > 2:
        protected.add(len(dialogue) - 1)
        protected.add(len(dialogue) - 2)
    kept = [i for i in indices if i not in protected]
    return kept or indices


def _patch_gold_chat_near_miss_chars(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """240 hard 不变；差 ≤NEAR_MISS 字时本地垫字收口。"""
    import copy

    total = dialogue_total_chars(story)
    need = DAILY_STORY_BODY_CHARS_MIN - total
    if need <= 0 or need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return story, False

    story_type = str(story.get("story_type") or "").strip().upper()
    indices = _gold_chat_pad_indices(dialogue, story_type=story_type)

    changed = False
    used_pads: set[str] = set()
    story_type = str(story.get("story_type") or "").strip().upper()
    if story_type == "O":
        natural_bares = {c.lstrip("，,") for c in _O_SAFE_NATURAL_EXPAND}
    elif story_type == "K":
        natural_bares = {c.lstrip("，,") for c in _K_GOLD_CHAT_NATURAL_EXPAND}
    else:
        natural_bares = {c.lstrip("，,") for c in _GOLD_CHAT_NATURAL_EXPAND}
    for idx in reversed(indices):
        item = dialogue[idx]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        # 已有可读扩写尾巴的句子勿再叠粒子垫字
        if any(b in line for b in natural_bares):
            continue
        new_line, added = _pad_gold_chat_line(
            line,
            need,
            used=used_pads,
            story_type=story_type,
            speaker=str(item.get("speaker") or ""),
        )
        if added <= 0:
            continue
        item["line"] = new_line
        need -= added
        changed = True
        if need <= 0:
            break
    return out, changed


def _pad_gold_chat_to_min_chars(
    story: dict[str, Any],
    *,
    min_chars: int | None = None,
    particle_only: bool = False,
    max_rounds: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """精修改短/删尾后垫字至 hard min（不限 near_miss 3 字）。"""
    import copy

    floor = int(min_chars or DAILY_STORY_BODY_CHARS_MIN)
    total = dialogue_total_chars(story)
    need = floor - total
    if need <= 0:
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return story, False

    indices = _gold_chat_pad_indices(
        dialogue, story_type=str(story.get("story_type") or "")
    )

    changed = False
    used_pads: set[str] | None = None if particle_only else set()
    story_type = str(story.get("story_type") or "").strip().upper()
    # K：粒子叠垫必脏，改走可读尾巴/中段句
    if story_type == "K" and particle_only:
        particle_only = False
        used_pads = set()
    if story_type == "O":
        expand_src = _O_SAFE_NATURAL_EXPAND
    elif story_type == "K":
        expand_src = _K_GOLD_CHAT_NATURAL_EXPAND
    elif story_type == "I":
        expand_src = tuple(
            c
            for c in _GOLD_CHAT_NATURAL_EXPAND
            if not any(f in c for f in _I_FORBIDDEN_EXPAND)
        )
    else:
        expand_src = _GOLD_CHAT_NATURAL_EXPAND
    natural_bares = {c.lstrip("，,") for c in expand_src}
    pad_rounds = (
        max_rounds
        if max_rounds is not None
        else (48 if particle_only else (24 if need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX else 12))
    )
    # 多轮垫字：单轮每句最多补一尾巴，循环直到满或停步
    for _ in range(pad_rounds):
        need = floor - dialogue_total_chars(out)
        if need <= 0:
            break
        progressed = False
        for idx in reversed(indices):
            need = floor - dialogue_total_chars(out)
            if need <= 0:
                break
            item = dialogue[idx]
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "").strip()
            if (not particle_only) and any(b in line for b in natural_bares):
                continue
            new_line, added = _pad_gold_chat_line(
                line,
                need,
                used=used_pads,
                story_type=story_type,
                speaker=str(item.get("speaker") or ""),
            )
            if added <= 0:
                continue
            item["line"] = new_line
            changed = True
            progressed = True
        if not progressed:
            # 垫词用尽时清空复用，优先把 near-miss 垫满
            # O：不清空，避免同一实义尾巴复读成模板
            if story_type == "O":
                break
            if used_pads is not None and used_pads:
                used_pads.clear()
                continue
            break
    return out, changed


def _ensure_gold_chat_min_lines(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """已停用脏反应句灌句；改走 `_boost_short_with_mid_lines` 可读中段加句。"""
    return story, False


def _boost_short_with_mid_lines(
    story: dict[str, Any],
    *,
    mechanism: str = "",
    structure_type: str = "",
) -> tuple[dict[str, Any], bool]:
    """FIX/扩写 写不满时：收束前插入成对句，保 J 权威方向。

    M8+J 插互顶/立规对；M5+J 等插昭求/灿否对。
    O 只插死磕/资源溜走实义对，且必须在点题句之前。
    大缺口（>near_miss）时允许句数 <12 先插对补句数/字数。
    """
    import copy

    from app.services.gold_story.scene import (
        CHAT_LINE_COUNT_MAX,
        CHAT_LINE_COUNT_MIN,
    )
    from app.services.gold_story.gold_chat.type_bridge import (
        is_m8_j_domination,
    )

    total = dialogue_total_chars(story)
    need = DAILY_STORY_BODY_CHARS_MIN - total
    if need <= 0:
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False

    st = str(structure_type or story.get("story_type") or "").strip().upper()
    # K：顶满 24 句时仍可能差字，允许至 26 以便插实义中段对
    line_cap = CHAT_LINE_COUNT_MAX + (2 if st == "K" else 0)
    m8_j = is_m8_j_domination(mechanism=mechanism, structure_type=st)
    large_gap = need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX
    if total < 100 and not large_gap:
        return story, False
    if len(dialogue) < CHAT_LINE_COUNT_MIN and not large_gap:
        return story, False

    existing = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    blob = "".join(existing)
    if m8_j:
        if _j_lose_line_index(dialogue) >= 0:
            return story, False
        if len(dialogue) >= CHAT_LINE_COUNT_MIN:
            return story, False
    elif st == "J" and ("再求你一次" in blob or "那我保证" in blob):
        # 已有求否加码，勿再插第二对
        return story, False
    # K：僵持词已在不挡大缺口补句；小缺口且已有僵持点则不再插
    insert_at = max(2, len(dialogue) - 2)
    if st == "K":
        from app.services.daily_story.story_types.k.close_mode import (
            K_A_PARENT_FAIL_STALEMATE,
            k_close_mode_from_story,
        )

        if k_close_mode_from_story(out) == K_A_PARENT_FAIL_STALEMATE:
            # 插在劝失败/劝止前，避免封口后再灌尾
            for i, item in enumerate(dialogue):
                if not isinstance(item, dict):
                    continue
                if str(item.get("speaker") or "").strip() not in ("妈妈", "爸爸"):
                    continue
                line = str(item.get("line") or "")
                if re.search(r"管不了|劝不了|别闹|别打|别吵|看着", line):
                    insert_at = max(2, i)
                    break
        else:
            insert_at = max(2, len(dialogue) // 2)
    if st == "O":
        punch = _o_goal_punch_index(dialogue)
        if punch >= 0:
            # 插在点题前；若点题前是昭昭连说，再往前挪到可交替处
            insert_at = punch
            while insert_at > 2:
                prev_item = dialogue[insert_at - 1]
                if not isinstance(prev_item, dict):
                    break
                if str(prev_item.get("speaker") or "").strip() != "昭昭":
                    break
                insert_at -= 1
    if m8_j:
        ko_idx = next(
            (
                i
                for i, x in enumerate(dialogue)
                if isinstance(x, dict)
                and re.search(r"草莓熊|肘击", str(x.get("line") or ""))
            ),
            -1,
        )
        if ko_idx >= 2:
            insert_at = min(insert_at, ko_idx)
    prev = dialogue[insert_at - 1] if insert_at > 0 else None
    if (
        st != "O"
        and isinstance(prev, dict)
        and str(prev.get("speaker") or "").strip() == "昭昭"
    ):
        insert_at = min(insert_at + 1, len(dialogue))
    if m8_j:
        pair_pool = _M8_J_NATURAL_MID_PAIRS
    elif st == "J":
        pair_pool = _GOLD_CHAT_NATURAL_MID_PAIRS
    elif st == "K":
        pair_pool = _K_NATURAL_MID_PAIRS
    elif st == "O":
        pair_pool = _O_NATURAL_MID_PAIRS
    else:
        pair_pool = tuple(
            (_GOLD_CHAT_REACT_LINES[i], _GOLD_CHAT_REACT_LINES[i + 1])
            for i in range(0, len(_GOLD_CHAT_REACT_LINES) - 1, 2)
        )
    changed = False
    pairs_used = 0
    max_pairs = 1 if m8_j else (2 if large_gap else 1)
    if st == "K":
        # 已有压制点题：只允许插在点题前，避免破功后再灌互顶
        if "还不哭" in blob or "继续挠" in blob or "看你哭" in blob:
            punch_i = next(
                (
                    i
                    for i, x in enumerate(dialogue)
                    if isinstance(x, dict)
                    and re.search(
                        r"还不哭|继续挠|看你哭",
                        str(x.get("line") or ""),
                    )
                ),
                -1,
            )
            if punch_i >= 4 and need >= 12:
                catch_i = next(
                    (
                        i
                        for i, x in enumerate(dialogue)
                        if isinstance(x, dict)
                        and re.search(
                            r"逮住|逮着|按住你|按着你|追到你了|抓到你",
                            str(x.get("line") or ""),
                        )
                    ),
                    -1,
                )
                limit = punch_i
                if catch_i >= 4:
                    limit = min(limit, catch_i)
                insert_at = min(insert_at, limit)
                max_pairs = 2 if need >= 40 else 1
            else:
                max_pairs = 0
        else:
            max_pairs = 3 if need >= 40 else (2 if need >= 20 else 1)
    if st == "O":
        max_pairs = 1

    def _norm_pad_line(text: str) -> str:
        return re.sub(r"[呀啊吧呢嘛了呗！？。!?，,\s]", "", str(text or ""))

    existing_norm = {_norm_pad_line(x) for x in existing if x}
    for pair in pair_pool:
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        if pairs_used >= max_pairs:
            break
        if len(dialogue) + 2 > line_cap:
            break
        lines_ok = True
        for _sp, line in pair:
            text = str(line).strip()
            if not text or text in existing or _norm_pad_line(text) in existing_norm:
                lines_ok = False
                break
        if not lines_ok:
            continue
        # 避免插出同角色连说（上一句说话人 == 对首句）
        first_sp = str(pair[0][0]).strip()
        while insert_at > 0 and insert_at <= len(dialogue):
            prev_item = dialogue[insert_at - 1]
            if not isinstance(prev_item, dict):
                break
            if str(prev_item.get("speaker") or "").strip() != first_sp:
                break
            if insert_at >= len(dialogue):
                break
            insert_at += 1
            if st == "O":
                punch = _o_goal_punch_index(dialogue)
                if punch >= 0 and insert_at > punch:
                    insert_at = punch
                    break
        if st == "O":
            punch = _o_goal_punch_index(dialogue)
            if punch >= 0 and insert_at > punch:
                continue
        if insert_at > 0 and insert_at <= len(dialogue):
            prev_item = dialogue[insert_at - 1]
            if (
                isinstance(prev_item, dict)
                and str(prev_item.get("speaker") or "").strip() == first_sp
            ):
                continue
        for speaker, line in pair:
            text = str(line).strip()
            dialogue.insert(insert_at, {"speaker": speaker, "line": text})
            existing.add(text)
            existing_norm.add(_norm_pad_line(text))
            insert_at += 1
        pairs_used += 1
        changed = True
    return out, changed


def _expand_short_gold_chat_lines(
    story: dict[str, Any],
    *,
    ignore_deficit_cap: bool = False,
) -> tuple[dict[str, Any], bool]:
    """句数已满、字数 near-miss 时，句内加可读实词尾巴（禁旧灌尾）。

    每句最多一条、优先不重复；大缺口仍交 扩写/FIX，勿靠本地硬灌过关。
    """
    import copy

    from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False
    rows = [x for x in dialogue if isinstance(x, dict) and str(x.get("line") or "").strip()]
    if len(rows) < CHAT_LINE_COUNT_MIN:
        return story, False

    total = dialogue_total_chars(story)
    need = DAILY_STORY_BODY_CHARS_MIN - total
    # 只接手 near-miss；大缺口交 FIX（temp↑）写满，勿本地叠灌
    if need <= 0 or ((not ignore_deficit_cap) and need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX):
        return story, False

    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list):
        return story, False

    changed = False
    expand_count: dict[int, int] = {}
    used: set[str] = set()
    st = str(story.get("story_type") or "").strip().upper()
    if st == "O":
        expand_src = _O_SAFE_NATURAL_EXPAND
    elif st == "K":
        expand_src = _K_GOLD_CHAT_NATURAL_EXPAND
    elif st == "I":
        expand_src = tuple(
            c
            for c in _GOLD_CHAT_NATURAL_EXPAND
            if not any(f in c for f in _I_FORBIDDEN_EXPAND)
        )
    else:
        expand_src = _GOLD_CHAT_NATURAL_EXPAND
    bare_all = {c.lstrip("，,") for c in expand_src}
    o_punch = _o_goal_punch_index(dialogue) if st == "O" else -1
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        hits = [b for b in bare_all if b in line]
        if hits:
            expand_count[i] = min(1, len(hits))
            used.update(hits)
    for _ in range(24):
        need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(out)
        if need <= 0:
            break
        candidates = [
            (i, item)
            for i, item in enumerate(dialogue)
            if isinstance(item, dict)
            and expand_count.get(i, 0) < 1
            and str(item.get("speaker") or "") in {"昭昭", "灿灿"}
            and 4 <= len(str(item.get("line") or "").strip()) < 20
            and i >= 2
            and i < len(dialogue) - 2  # 首尾句不垫尾巴，保开场/收场干净
            and (o_punch < 0 or i < o_punch)
            and (
                st != "O"
                or bool(
                    re.search(
                        r"赢|再来|夹|比|出拳|认真",
                        str(item.get("line") or ""),
                    )
                )
            )
            and not any(
                br in str(item.get("line") or "")
                for br in (
                    "等等，先听我说完",
                    "你别插嘴，轮到我了",
                    "你别插嘴，轮到我",
                    "先别吵，听清楚",
                )
            )
            and "我输了" not in str(item.get("line") or "")
            and not _RE_K_NO_EXPAND_LINE.search(str(item.get("line") or ""))
        ]
        if not candidates:
            break
        candidates.sort(key=lambda x: len(str(x[1].get("line") or "")))
        progressed = False
        for idx, item in candidates:
            need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(out)
            if need <= 0:
                break
            line = str(item.get("line") or "").strip()
            core = line.rstrip("！。？…!")
            tail_mark = line[len(core) :] or "！"
            room = max(0, DAILY_STORY_LINE_CHARS_MAX - len(line))
            if room < 5:
                expand_count[idx] = 1
                continue
            sp = str(item.get("speaker") or "").strip()
            if st == "K":
                if sp == "昭昭":
                    src = _K_ZHAO_NATURAL_EXPAND
                elif sp == "灿灿":
                    src = _K_CAN_NATURAL_EXPAND
                else:
                    expand_count[idx] = 1
                    continue
            else:
                src = expand_src
            pool = [
                c
                for c in src
                if c.lstrip("，,") not in used
                and c.lstrip("，,") not in "".join(
                    str(x.get("line") or "")
                    for x in dialogue
                    if isinstance(x, dict)
                )
                and _j_expand_bare_allowed(
                    c.lstrip("，,"),
                    sp,
                )
            ]
            if not pool:
                break
            for clause in pool:
                bare = clause.lstrip("，,")
                if bare in core:
                    continue
                if len(clause) > room or len(clause) > need + 2:
                    continue
                item["line"] = (core + clause + tail_mark)[:DAILY_STORY_LINE_CHARS_MAX]
                used.add(bare)
                expand_count[idx] = expand_count.get(idx, 0) + 1
                changed = True
                progressed = True
                break
            if progressed:
                break
        if not progressed:
            break
    return out, changed


_RE_C_TONE_STACK = re.compile(
    r"(?:[呢嘛的了着好]{2,}呀|呢了|呢呀)[！。！？…]?$"
)


def _strip_c_tone_stack_line(line: str) -> str:
    """C 类硬卡：句尾语气词堆砌 → 剥成无叠尾。"""
    s = str(line or "").strip()
    if not s or not _RE_C_TONE_STACK.search(s):
        return s
    tail_mark = s[-1] if s[-1] in "！。？…!" else ""
    body = s[:-1] if tail_mark else s
    body = re.sub(r"[呢嘛呀啊吧了着的好]+$", "", body)
    return (body + tail_mark) if body else s


def patch_sanitize_c_tone_stack(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """剥 C 类句尾叠语气词（垫字副作用）。"""
    import copy

    if str(story.get("story_type") or "").strip().upper() != "C":
        return story, False
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        new = _strip_c_tone_stack_line(old)
        if new != old:
            item["line"] = new
            changed = True
    return out, changed

def _ensure_gold_chat_min_chars(
    story: dict[str, Any],
    *,
    mechanism: str = "",
    structure_type: str = "",
) -> tuple[dict[str, Any], bool]:
    """near-miss 垫到 hard min；大缺口先可读中段加句，再交 扩写/FIX。

    剥旧灌尾 → 可读句内扩写 → 中段加句 → 粒子 near-miss（差 ≤60）。
    """
    data, clutter_changed = patch_sanitize_expand_clutter(story)
    data, changed_lines = _ensure_gold_chat_min_lines(data)
    data, changed_exp = _expand_short_gold_chat_lines(data)
    changed = clutter_changed or changed_lines or changed_exp
    # 仅大缺口才插求否对；near-miss 交给句内扩写/粒子，避免一锤后拉锯灌尾
    need_now = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
    changed_mid = False
    st = str(structure_type or story.get("story_type") or "").strip().upper()
    mech = str(mechanism or "").strip()
    if need_now > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
        data, changed_mid = _boost_short_with_mid_lines(
            data,
            mechanism=mech,
            structure_type=st,
        )
    changed = changed or changed_mid

    data2, changed_pad = _patch_gold_chat_near_miss_chars(data)
    data, changed = data2, changed or changed_pad

    # 中段加句后再试 near-miss 粒子；大缺口仍留给 FIX/重抽
    need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
    if 0 < need <= GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
        data3, changed3 = _pad_gold_chat_to_min_chars(data)
        data, changed = data3, changed or changed3

    # 只剥叠；near-miss 再垫粒子。禁止二次 expand（尾巴叠灌）
    for _ in range(4):
        data, san = patch_sanitize_c_tone_stack(data)
        data, san2 = patch_sanitize_pad_suffix(data)
        data, san3 = patch_sanitize_expand_clutter(data)
        data, san4 = patch_sanitize_pad_particles(data)
        changed = changed or san or san2 or san3 or san4
        if dialogue_total_chars(data) >= DAILY_STORY_BODY_CHARS_MIN:
            data, san_stack = patch_sanitize_natural_expand_stack(data)
            data, san_part = patch_sanitize_pad_particles(data)
            changed = changed or san_stack or san_part
            # 剥叠后可能又掉到 hard min 下：near-miss 再垫一轮再返回
            need_after = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
            if 0 < need_after <= GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
                data, pad_fix = _pad_gold_chat_to_min_chars(data)
                changed = changed or pad_fix
                if dialogue_total_chars(data) < DAILY_STORY_BODY_CHARS_MIN:
                    data, force_fix = _gold_chat_force_min_chars(data)
                    changed = changed or force_fix
            return data, changed
        need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
        if need <= 0 or need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
            # 仍差很多时再试一次中段加句
            if need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
                data, mid2 = _boost_short_with_mid_lines(
                    data,
                    mechanism=mech,
                    structure_type=st,
                )
                changed = changed or mid2
                need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
                if need <= 0 or need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
                    break
            else:
                break
        before = dialogue_total_chars(data)
        data, pad_again = _pad_gold_chat_to_min_chars(data)
        changed = changed or pad_again
        if (not pad_again) or dialogue_total_chars(data) <= before:
            break
    data, san_stack = patch_sanitize_natural_expand_stack(data)
    data, san_part = patch_sanitize_pad_particles(data)
    changed = changed or san_stack or san_part
    need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
    if 0 < need <= GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
        data, pad_final = _pad_gold_chat_to_min_chars(data)
        changed = changed or pad_final
        if dialogue_total_chars(data) < DAILY_STORY_BODY_CHARS_MIN:
            data, force_final = _gold_chat_force_min_chars(data)
            changed = changed or force_final
        if (
            0
            < DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
            <= GOLD_CHAT_NEAR_MISS_DEFICIT_MAX
        ):
            data, ins = _gold_chat_insert_body_lines_for_min(data)
            changed = changed or ins
            if dialogue_total_chars(data) < DAILY_STORY_BODY_CHARS_MIN:
                data, pad2 = _pad_gold_chat_to_min_chars(data, max_rounds=24)
                changed = changed or pad2
    return data, changed


def _stabilize_local_length_candidate(
    candidate: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    target_chars: int = GOLD_CHAT_LOCAL_LENGTH_TARGET,
) -> tuple[dict[str, Any], bool]:
    """统一机械收口：句长压缩 + near-miss 补字；最终不得靠垫字痕迹过线。"""
    data, shortened = _apply_deterministic_shorten(candidate)
    changed = shortened

    total = dialogue_total_chars(data)
    hard_deficit = DAILY_STORY_BODY_CHARS_MIN - total
    if not (0 < hard_deficit <= GOLD_CHAT_NEAR_MISS_DEFICIT_MAX):
        return data, changed

    data, expanded = _ensure_gold_chat_min_chars(
        data,
        mechanism=mechanism,
        structure_type=structure_type,
    )
    changed = changed or expanded
    total = dialogue_total_chars(data)
    target = min(
        max(DAILY_STORY_BODY_CHARS_MIN, int(target_chars)),
        total + max(0, GOLD_CHAT_NEAR_MISS_DEFICIT_MAX - hard_deficit),
    )
    if total < target:
        data, padded = _pad_gold_chat_to_min_chars(
            data,
            min_chars=target,
            max_rounds=48,
        )
        changed = changed or padded

    # `_pad_gold_chat_to_min_chars` 是兜底工具，可能留下「好不好」等机审痕迹。
    # 对所有机审命中的姐弟句直接调用安全 sanitizer（真实问句会被保留），
    # 再用实义句内扩写/中段补句恢复 hard min；最终不再用粒子 pad 回填。
    rows = data.get("dialogue")
    if isinstance(rows, list):
        for line_no, item in enumerate(rows, 1):
            if not isinstance(item, dict):
                continue
            speaker = str(item.get("speaker") or "").strip()
            line = str(item.get("line") or "").strip()
            if speaker not in {"昭昭", "灿灿"} or not line:
                continue
            if pad_stack_issue_for_line(line, line_no) is None:
                continue
            cleaned = sanitize_pad_stack_line(line)
            if cleaned and cleaned != line:
                item["line"] = cleaned
                changed = True

    for _ in range(3):
        if dialogue_total_chars(data) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        before = dialogue_total_chars(data)
        data, natural = _expand_short_gold_chat_lines(
            data,
            ignore_deficit_cap=True,
        )
        changed = changed or natural
        if dialogue_total_chars(data) < DAILY_STORY_BODY_CHARS_MIN:
            data, mid = _boost_short_with_mid_lines(
                data,
                mechanism=mechanism,
                structure_type=structure_type,
            )
            changed = changed or mid
        if dialogue_total_chars(data) <= before:
            break

    # 实义扩写后再做一次句长与垫字清理；清理后若仍 >= hard min 即接受，
    # 不为追求 250 的软余量重新塞语气尾巴。
    data, shortened2 = _apply_deterministic_shorten(data)
    changed = changed or shortened2
    rows = data.get("dialogue")
    if isinstance(rows, list):
        for line_no, item in enumerate(rows, 1):
            if not isinstance(item, dict):
                continue
            speaker = str(item.get("speaker") or "").strip()
            line = str(item.get("line") or "").strip()
            if speaker not in {"昭昭", "灿灿"} or not line:
                continue
            if pad_stack_issue_for_line(line, line_no) is None:
                continue
            cleaned = sanitize_pad_stack_line(line)
            if cleaned and cleaned != line:
                item["line"] = cleaned
                changed = True
    return data, changed


def _gold_chat_insert_body_lines_for_min(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """删句后 pad/expand 顶格时：中段插 1–2 条抽象反应句补 min（非求拒）。"""
    import copy

    from app.services.gold_story.scene import CHAT_LINE_COUNT_MAX

    need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(story)
    if need <= 0:
        return story, False
    out = copy.deepcopy(story)
    dialogue = out.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return story, False
    existing = {
        str(x.get("line") or "").strip()
        for x in dialogue
        if isinstance(x, dict)
    }
    insert_at = min(max(3, len(dialogue) // 3), len(dialogue) - 3)
    changed = False
    inserted = 0
    for sp, line in _GOLD_CHAT_REACT_LINES:
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        if len(dialogue) >= CHAT_LINE_COUNT_MAX:
            break
        if inserted >= 2:
            break
        text = str(line).strip()
        if not text or text in existing:
            continue
        dialogue.insert(insert_at, {"speaker": sp, "line": text})
        existing.add(text)
        insert_at += 1
        inserted += 1
        changed = True
    if changed:
        out2, cp = _pad_gold_chat_to_min_chars(out, max_rounds=48)
        out = out2
        changed = True
    return out, changed


def _gold_chat_force_min_chars(story: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """终稿仍差 min 时：句内扩写 → 粒子/可读垫满 → 中段插反应句（禁插求否对）。"""
    import copy

    from app.services.gold_story.scene import CHAT_LINE_COUNT_MIN

    from app.services.daily_story.story_types import (
        patch_j_cap_trailing_particles,
        patch_j_cap_ya_particles,
        patch_j_dedupe_cross_line_phrases,
        patch_j_strip_role_mismatch_expands,
    )

    need = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(story)
    if need <= 0:
        return story, False
    st = str(story.get("story_type") or "").strip().upper()
    if st == "O":
        # O：最多插 2 对中段实义；其余靠单语气词/安全扩写，禁止抬杠灌句
        out = copy.deepcopy(story)
        out["story_type"] = "O"
        changed = False
        boost_used = 0
        for _ in range(8):
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            before = dialogue_total_chars(out)
            if boost_used < 1:
                out2, c1 = _boost_short_with_mid_lines(out, structure_type="O")
                out = out2
                if c1:
                    boost_used += 1
                changed = changed or c1
            out, _ = patch_sanitize_pad_suffix(out)
            out, _ = patch_sanitize_pad_particles(out)
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            out2, cp = _pad_gold_chat_to_min_chars(out, max_rounds=24)
            out = out2
            out, _ = patch_sanitize_pad_suffix(out)
            out, _ = patch_sanitize_pad_particles(out)
            changed = changed or cp
            if dialogue_total_chars(out) <= before:
                out2, ce = _expand_short_gold_chat_lines(
                    out, ignore_deficit_cap=True
                )
                out = out2
                changed = changed or ce
                if dialogue_total_chars(out) <= before:
                    break
        return out, changed
    if st == "K":
        out = copy.deepcopy(story)
        out["story_type"] = "K"
        changed = False
        boost_used = 0
        for _ in range(12):
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            before = dialogue_total_chars(out)
            # K：中段实义对优先（最多 4 轮）；再粒子/句内扩写补齐 hard min
            if boost_used < 4:
                out2, c1 = _boost_short_with_mid_lines(out, structure_type="K")
                out = out2
                if c1:
                    boost_used += 1
                changed = changed or c1
            out, _ = patch_sanitize_pad_suffix(out)
            out, _ = patch_sanitize_pad_particles(out)
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            out2, cp = _pad_gold_chat_to_min_chars(out, max_rounds=32)
            out = out2
            out, _ = patch_sanitize_pad_suffix(out)
            out, _ = patch_sanitize_pad_particles(out)
            changed = changed or cp
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            out2, ce = _expand_short_gold_chat_lines(
                out, ignore_deficit_cap=True
            )
            out = out2
            out, _ = patch_sanitize_pad_suffix(out)
            out, _ = patch_sanitize_pad_particles(out)
            changed = changed or ce
            if dialogue_total_chars(out) <= before:
                break
        return out, changed
    dialogue = story.get("dialogue")
    if isinstance(dialogue, list) and len(dialogue) >= CHAT_LINE_COUNT_MIN + 2:
        out = copy.deepcopy(story)
        changed = False
        for _ in range(8):
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            before = dialogue_total_chars(out)
            out2, cx = _expand_short_gold_chat_lines(out, ignore_deficit_cap=True)
            out = out2
            out, _ = patch_sanitize_natural_expand_stack(out)
            out, _ = patch_j_dedupe_cross_line_phrases(out)
            out, _ = patch_j_strip_role_mismatch_expands(out)
            changed = changed or cx
            if dialogue_total_chars(out) <= before:
                out2, cp = _pad_gold_chat_to_min_chars(out, max_rounds=48)
                out = out2
                out, _ = patch_sanitize_pad_particles(out)
                out, _ = patch_j_cap_ya_particles(out)
                changed = changed or cp
                if dialogue_total_chars(out) <= before:
                    break
        if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
            out2, ci = _gold_chat_insert_body_lines_for_min(out)
            out = out2
            changed = changed or ci
            if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
                out2, cp = _pad_gold_chat_to_min_chars(out, max_rounds=48)
                out = out2
                changed = changed or cp
        return out, changed
    out = copy.deepcopy(story)
    changed = False
    for _ in range(4):
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        out2, c5 = _expand_short_gold_chat_lines(out, ignore_deficit_cap=True)
        out = out2
        out, _ = patch_sanitize_natural_expand_stack(out)
        changed = changed or c5
    for _ in range(8):
        if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
            break
        before = dialogue_total_chars(out)
        out2, c4 = _pad_gold_chat_to_min_chars(
            out, particle_only=True, max_rounds=24
        )
        out = out2
        out, _ = patch_sanitize_pad_particles(out)
        changed = changed or c4
        if dialogue_total_chars(out) <= before:
            out2, c6 = _pad_gold_chat_to_min_chars(
                out, particle_only=False, max_rounds=12
            )
            out = out2
            changed = changed or c6
            if dialogue_total_chars(out) <= before:
                break
    if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
        for _ in range(4):
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            before = dialogue_total_chars(out)
            out2, ci = _gold_chat_insert_body_lines_for_min(out)
            out = out2
            changed = changed or ci
            if dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN:
                break
            out2, cp = _pad_gold_chat_to_min_chars(out, max_rounds=48)
            out = out2
            changed = changed or cp
            if dialogue_total_chars(out) <= before:
                break
    out, _ = patch_sanitize_natural_expand_stack(out)
    out, _ = patch_j_dedupe_cross_line_phrases(out)
    out, _ = patch_j_cap_trailing_particles(out, max_lines=3)
    out, _ = patch_sanitize_pad_particles(out)
    if dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN:
        out2, cp = _pad_gold_chat_to_min_chars(
            out, particle_only=True, max_rounds=24
        )
        out = out2
        out, _ = patch_j_cap_trailing_particles(out, max_lines=3)
        changed = changed or cp
    return out, changed
