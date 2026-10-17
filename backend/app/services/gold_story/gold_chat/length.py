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
from app.services.gold_story.gold_chat.validate import gold_chat_effective_min_chars
from app.services.gold_story.scene import sanitize_dialogue_meta_label_suffix

# 240 是硬线；本地机械收口不再为追求 250 软余量额外灌字。
GOLD_CHAT_LOCAL_LENGTH_TARGET = DAILY_STORY_BODY_CHARS_MIN


def _gold_chat_length_floor_met(story: dict[str, Any]) -> bool:
    """联合判据下已达标：句数够时字数下限放宽一行，无需再垫字数/插反应句。

    本地垫字（粒子/中段反应句）只在真正低于下限时才动，否则为凑 240 补出来的
    句尾粒子会被终检当成语病，反而多烧一轮修稿预算。
    """
    return dialogue_total_chars(story) >= gold_chat_effective_min_chars(
        story.get("dialogue")
    )


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


def patch_sanitize_dialogue_meta_labels(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """剥句尾“一锤定音/镇住话题”等结构标签，保留真正口语内容。"""
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old:
            continue
        new = sanitize_dialogue_meta_label_suffix(old)
        if new != old:
            item["line"] = new
            changed = True
    return out, changed


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
# N：两人手只有 1 个孩子可垫，字数易近失；只补不改语义的短尾/称呼
_N_SAFE_NATURAL_EXPAND: tuple[str, ...] = ("，真的", "，你信不信", "，就这样")
_N_PARENT_SAFE_TAILS: tuple[str, ...] = ("，你说呢", "，真的")
# N 收束句特征：决定垫字/补位一律不能越过它（越过就会把收束挤出末段窗口）
_N_CLOSE_LINE_RE = re.compile(
    r"行吧|服了|说不出|接不住|算了|那……|打草稿|以后说话"
)
# 禁「现在/立刻/马上/快点」——near-miss 多轮会叠成句尾垃圾
_C_SAFE_PAD_PHRASES = (
    "真的",
    "不行",
)
# 普通类型禁止用无上下文的抬杠反应句补字；类型化中段句只走下方专用池。
_GOLD_CHAT_REACT_LINES: tuple[tuple[str, str], ...] = ()
# N：只在已有「追问→因果回答」后补抽象复述，不新增剧情事实；说话人运行时按理由方映射。
_N_NATURAL_MID_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("你还真是照这个道理认真想的？", "当然，我刚才就是这么认真回答的。"),
    ("所以你刚才不是随口乱说的？", "不是，我就是按自己的想法认真说的。"),
    ("你怎么还能一本正经继续解释？", "因为我觉得前面那个理由就是能说通。"),
)
# N：家长额度已满时的补字对——旁观手足只做反应式帮腔，**不得**代问关键追问
_N_VIEWER_ECHO_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("反正我就这么说，你信不信都行。", "哈哈，妈你记下来没，他这是越说越像真的！"),
    ("我说完了，你自己想吧。", "哎哟，这一本正经的劲儿我可学不来。"),
)
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
_O_GOLD_CHAT_PAD_TAILS = ("呀", "啊", "吧")  # 单语气词；禁 particle_upgrade 叠字# O 句内扩写：只允许过程/催夹实义，禁抬杠/记仇类 clutter
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
# A（权威翻车）：字数不够时插「施压→顶回」实义对；说话人运行时按契约角色映射
# （挑战方＝指认/翻旧账方；施压方＝权威方是孩子时才用它，否则换另一位孩子，
# 避免吃掉家长台词额度）。只写抽象规矩/公平话，不绑单篇道具，也不碰末四拍。
_A_NATURAL_MID_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("你先照规矩做，别拖着了。", "凭什么单让我做，你倒说说看？"),
    ("按说好的来，快点动手吧。", "行，那你先做到，我立马照做。"),
    ("别磨蹭了，这事先这么定。", "你先答应我那件事，我这就去。"),
)
# E（妈妈破功）：字数不够时补一组「孩子追问」实义对，插在收束两拍之前。
# 只用两个孩子，不占妈妈额度（E 中段妈妈只准一句短反应），也不新增道具。
_E_NATURAL_MID_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("那你刚才说的还算不算数？", "你自己都做不到，凭什么让我听？"),
    ("先把这事说清楚再讲道理。", "你讲的那套，怎么到自己就变了？"),
    ("你再解释一遍，我听着呢。", "解释不通就别拿辈分压人。"),
)
# E 单孩稿（孩子+家长）：家长那句只能是短反应，且须避开破功词/大人例外/翻旧账，
# 否则 E 硬卡（末句破功、中段漏新开脱）会判不合格。
_E_NATURAL_MID_PARENT_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("你别绕，先把我问的说清楚。", "我听着呢，你慢慢说。"),
    ("那你给我个准话。", "先别嚷，我这就说。"),
    ("这话是你自己讲的吧？", "是，我是这么说过。"),
)
def _parent_holds_secret(
    beat_chain: list[Any] | None,
    dialogue: list[Any],
) -> bool:
    """把柄是否在家长手上（把柄稿：孩子当面拆穿家长）。

    读 beat_chain 的 claim_role=secret_holder（结构化槽位，不读剧情词）；
    缺失时看对白里家长是否与孩子互为对手。把柄稿的中段互呛应发生在
    孩子↔家长之间，而非两个孩子之间——否则模型会拉出第三个孩子当对手，
    终检必报「对话对象乱跳 / 身份立场对不上」。
    """
    if isinstance(beat_chain, list):
        for row in beat_chain:
            if not isinstance(row, dict):
                continue
            if str(row.get("claim_role") or "").strip() != "secret_holder":
                continue
            holder = str(row.get("speaker") or "").strip()
            if holder in {"妈妈", "爸爸"}:
                return True
    return False


# F（互呛加码）：字数不够时补一组短接话互呛对，插在收场之前。
# 两句须是**同一方向的对呛**（前者挑、后者接），否则会被读成自问自答；
# 且须带 F 硬卡机读的加码标记（还…呢/再说/试试/更/再来），否则中段加码判不过。
# 非把柄稿（姐弟互呛）用这两条。
_F_NATURAL_MID_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("你还敢再说一遍呢！", "说就说，我又不怕你！"),
    ("你再说，我可要吼了！", "吼啊，你试试看！"),
    ("你还来劲儿了呢！", "再来我也不认你这话！"),
)
def _kid_and_parent(dialogue: list[Any]) -> tuple[str, str]:
    """对白里的孩子与家长（各取第一位出场者）。"""
    kid = ""
    parent = ""
    for row in dialogue:
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        if sp in {"昭昭", "灿灿"} and not kid:
            kid = sp
        elif sp in {"妈妈", "爸爸"} and not parent:
            parent = sp
    return kid, parent


# 把柄稿（孩子拆穿家长）的中段互呛对：孩子在顶、家长在挡。
# 只用一对（重复是终检高频扣分项），且**不伪造引文**——凭空替对方引一句话
# 会被判「引用无据」，故只写加压语气，不复述台词。家长那句须是挡/辩，
# 不能是认输破功（F 不走 E 的破功收束）。
_F_PARENT_MID_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("这事儿没完，你还想赖呢！", "我没赖，你先别嚷。"),
)
# E/F 句内实义尾巴：只能加在孩子的追问/顶回句上（家长句有额度与破功约束，
# 不在此扩写）。禁记仇/威胁类空转，避免 E 中段不变量被判不合格。
_E_SAFE_NATURAL_EXPAND: tuple[str, ...] = (
    "，你自己说说看",
    "，我记着呢",
    "，你先给我讲清楚",
    "，这话可不算完",
)
_F_SAFE_NATURAL_EXPAND: tuple[str, ...] = (
    "，你敢不敢",
    "，我又不怕你",
    "，你接着说",
)
# G/M4 行动软化的收拾类 near-miss：只补同域动作对白，不凭空制造护短/真情戏。
_G_CLEANUP_NATURAL_MID_PAIRS: tuple[tuple[tuple[str, str], tuple[str, str]], ...] = (
    (
        ("昭昭", "你还真要把这些都收好啊？"),
        ("灿灿", "我先把手边这些放回去。"),
    ),
)
# 垫字插入点的归一化与近似判重：模板对整对灌入时，只有逐字比对会漏掉
# 只差语气词/标点的同义句（如稿内已有「…这事还没完啊！」又要插「…这事还没完！」）。
_PAD_LINE_NOISE = re.compile(r"[呀啊吧呢嘛了呗哦么！？。!?，,、…\s]")
_PAD_SIM_THRESHOLD = 0.6
# 垫字插入安全区：句首过近会打乱开场因果，末段留出收束槽位不许动。
_PAD_MIN_INSERT_AT = 2
_PAD_TAIL_KEEP = 4


def _norm_pad_line(text: str) -> str:
    """垫字判重用的归一化：去语气词/标点，只留实义汉字与字母数字。"""
    return _PAD_LINE_NOISE.sub("", str(text or ""))


def _pad_line_bigrams(text: str) -> set[str]:
    normalized = _norm_pad_line(text)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[i : i + 2] for i in range(len(normalized) - 1)}


def _pad_line_similarity(left: str, right: str) -> float:
    """归一化字符二元组 Jaccard；口语垫字句的近似重复判定。"""
    a = _pad_line_bigrams(left)
    b = _pad_line_bigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _pad_line_is_duplicate(text: str, existing: list[str]) -> bool:
    """逐字、归一化、近似（相似度阈值）三级判重。"""
    target = _norm_pad_line(text)
    if not target:
        return True
    for item in existing:
        other = _norm_pad_line(item)
        if not other:
            continue
        if target == other:
            return True
        if _pad_line_similarity(text, item) >= _PAD_SIM_THRESHOLD:
            return True
    return False


def _pad_safe_insert_bounds(count: int) -> tuple[int, int]:
    """垫字可插入区间 [lo, hi]：避开开场前两句与末段收束槽位。"""
    lo = min(_PAD_MIN_INSERT_AT, count)
    return lo, max(lo, count - _PAD_TAIL_KEEP)


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
_J_ZHAO_NATURAL_EXPAND: tuple[str, ...] = (
    "，我照做",
    "，这次听你的",
    "，我不敢再拖",
)
_J_CAN_NATURAL_EXPAND: tuple[str, ...] = (
    "，听我的",
    "，现在照做",
    "，别再找借口",
)
_J_GOLD_CHAT_NATURAL_EXPAND: tuple[str, ...] = (
    _J_ZHAO_NATURAL_EXPAND + _J_CAN_NATURAL_EXPAND
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


def _kid_order_speakers(dialogue: list[Any]) -> list[str]:
    """对白里出现的孩子（按出场顺序，最多两个）。"""
    kids: list[str] = []
    for row in dialogue:
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        if sp in {"昭昭", "灿灿"} and sp not in kids:
            kids.append(sp)
    return kids[:2]


def _e_natural_mid_pairs(
    dialogue: list[Any],
) -> tuple[
    tuple[tuple[tuple[str, str], tuple[str, str]], ...],
    int | None,
]:
    """E 补位：收束两拍（孩子闭环+妈妈破功）之前插一组追问对。

    两个孩子 → 姐弟轮问；单孩+家长 → 孩子追问、家长短反应
    （家长那句不能是破功/开脱加码，否则末句破功与中段不变量会被判不合格）。
    """
    if len(dialogue) < 6:
        return (), None
    kids = _kid_order_speakers(dialogue)
    parent = ""
    parent_lines = 0
    for row in dialogue:
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        if sp in {"妈妈", "爸爸"}:
            parent = parent or sp
            parent_lines += 1
    if len(kids) >= 2:
        pairs = tuple(
            ((kids[0], a), (kids[1], b)) for a, b in _E_NATURAL_MID_TEMPLATES
        )
    elif kids and parent and parent_lines < 3:
        # 家长已满 3 句（契约 mom_lines_max）时不再添家长台词，避免超额度
        pairs = tuple(
            ((kids[0], a), (parent, b))
            for a, b in _E_NATURAL_MID_PARENT_TEMPLATES
        )
    else:
        return (), None
    if not pairs:
        return (), None
    # 收束两拍前的最后可插位：挤进末三句会破坏「孩子闭环+妈妈破功」
    return pairs, max(2, len(dialogue) - 2)


def _last_kid_press_line(dialogue: list[Any], speaker: str) -> str:
    """取该孩子最后一句里的追问话头（用于把接话锚在前文上）。

    通用模板最大的问题是凭空一句「你再说一遍」，而前文没有可被要求重复的话，
    终检必报「接不上」。故接话句尽量复用前文已有的 3–6 字话头片段。
    """
    norm = re.compile(r"[\s，。！？、；：,.!?;:\"'“”‘’（）()《》【】…—-]+")
    for row in reversed(dialogue):
        if not isinstance(row, dict):
            continue
        if str(row.get("speaker") or "").strip() != speaker:
            continue
        core = norm.sub("", str(row.get("line") or ""))
        if len(core) >= 3:
            return core[:6]
    return ""


def _f_natural_mid_pairs(
    dialogue: list[Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[
    tuple[tuple[tuple[str, str], tuple[str, str]], ...],
    int | None,
]:
    """F 补位：收场之前插一组对呛。

    把柄稿（孩子在拆穿家长）走「孩子↔家长」互呛：两个孩子须同侧，
    否则模型会拉出第三个孩子当对手，终检必报对话对象乱跳；
    普通姐弟互呛稿走「姐弟↔姐弟」。
    接话句锚在前文话头上，避免「凭空开火」被判接不上。
    """
    if len(dialogue) < 6:
        return (), None
    if _parent_holds_secret(beat_chain, dialogue):
        kid, parent = _kid_and_parent(dialogue)
        if not kid or not parent:
            return (), None
        pairs = tuple(
            ((kid, a), (parent, b)) for a, b in _F_PARENT_MID_TEMPLATES
        )
        return pairs, max(2, len(dialogue) - 2)
    kids = _kid_order_speakers(dialogue)
    if len(kids) < 2:
        return (), None
    # 不复述对方台词（伪引文会被判引用无据），只做加压
    pairs = tuple(
        (
            (kids[0], "你刚刚那话，还敢再来一遍试试！"),
            (kids[1], b),
        )
        for _a, b in _F_NATURAL_MID_TEMPLATES
    )
    return pairs, max(2, len(dialogue) - 2)


def _a_natural_mid_pairs(
    dialogue: list[Any],
    *,
    beat_chain: list[Any] | None = None,
) -> tuple[
    tuple[tuple[tuple[str, str], tuple[str, str]], ...],
    int | None,
]:
    """A 类安全补位：施压方↔挑战方，插入点固定在末四拍之前。

    挑战方＝契约里指认/翻旧账的那方；权威方是孩子时由它施压，
    权威方是家长时改用另一位孩子施压（家长台词有额度，勿靠补句破额）。
    末四拍（引话→例外→追问→破功）是硬卡，补位只能落在它前面。
    near-miss（≤20 字）仍走句内扩写/粒子，不在此处插对。
    """
    from app.services.gold_story.scene import fact_role_pair

    if len(dialogue) < 8:
        return (), None
    total = sum(
        len(str(row.get("line") or ""))
        for row in dialogue
        if isinstance(row, dict)
    )
    if DAILY_STORY_BODY_CHARS_MIN - total <= GOLD_CHAT_NEAR_MISS_DEFICIT_MAX:
        # 窄缝缺口交句内扩写/粒子收口：插整对会超出软目标且动结构
        return (), None
    challenger, authority = fact_role_pair({"beat_chain": beat_chain or []})
    speakers = [
        str(row.get("speaker") or "").strip()
        for row in dialogue
        if isinstance(row, dict)
    ]
    kids = [sp for sp in dict.fromkeys(speakers) if sp in {"昭昭", "灿灿"}]
    if not challenger and len(kids) == 2:
        # 契约没标语用角色时保守兜底：权威常是破功方（末句），挑战方取另一位
        last_sp = speakers[-1] if speakers else ""
        challenger = next((sp for sp in kids if sp != last_sp), "")
    if not challenger:
        return (), None
    if authority and authority in kids and authority != challenger:
        presser = authority
    else:
        others = [sp for sp in kids if sp != challenger]
        if not others:
            return (), None
        presser = others[0]
    pairs = tuple(
        ((presser, a), (challenger, b)) for a, b in _A_NATURAL_MID_TEMPLATES
    )
    return pairs, max(2, len(dialogue) - 4)


def _n_natural_mid_pairs(
    dialogue: list[Any],
    *,
    beat_chain: list[Any] | None = None,
    dialogue_seed: list[Any] | None = None,
    parent_lines_max: int | None = None,
) -> tuple[
    tuple[tuple[tuple[str, str], tuple[str, str]], ...],
    int | None,
]:
    """N 类按现有因果回答定位安全补位：另一位手足追认，理由方只复述态度。"""
    from app.services.daily_story.story_types.n.validate import (
        RE_SOLEMN_REASON,
        RE_STUN_CLOSE,
        RE_WHY,
    )

    siblings = {"昭昭", "灿灿"}
    reason_idx = -1
    reasoner = ""
    for why_idx, why_item in enumerate(dialogue):
        if not isinstance(why_item, dict):
            continue
        why_line = str(why_item.get("line") or "").strip()
        if not RE_WHY.search(why_line):
            continue
        why_speaker = str(why_item.get("speaker") or "").strip()
        # 与 N 类型补槽规则保持同一局部窗：只认追问后 3 句内的因果回答，
        # 遇到愣住收束或新的追问即停止，避免抓到后段无关的「因为」。
        for idx in range(why_idx + 1, min(len(dialogue), why_idx + 4)):
            item = dialogue[idx]
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "").strip()
            if RE_STUN_CLOSE.search(line) or RE_WHY.search(line):
                break
            speaker = str(item.get("speaker") or "").strip()
            if speaker not in siblings or (why_speaker and speaker == why_speaker):
                continue
            if RE_SOLEMN_REASON.search(line):
                reason_idx = idx
                reasoner = speaker
                break
        if reason_idx >= 0:
            break
    if reason_idx < 0 or not reasoner:
        # 某些 N 候选在扩写早期尚未把「为什么→因为」写全，就先被篇幅校验拦住。
        # 此时契约已经明确谁在嘴硬/解释，不应因为自然改写没命中关键词就放弃本地实义补位。
        # 只用结构标签确认“理由方”；若两个孩子都像理由方则宁可不补，避免串角。
        contract_rows = [
            raw
            for raw in ((beat_chain or []) or (dialogue_seed or []))
            if isinstance(raw, dict)
        ]
        preferred: list[tuple[int, str]] = []
        fallback: list[tuple[int, str]] = []
        for pos, raw in enumerate(contract_rows):
            speaker = str(raw.get("speaker") or "").strip()
            intent = str(raw.get("intent") or raw.get("beat") or "").strip()
            if speaker not in siblings:
                continue
            if re.search(r"回答|作答|解释|自洽|理由", intent):
                preferred.append((pos, speaker))
            elif re.search(r"质疑|反驳|嘴硬", intent):
                fallback.append((pos, speaker))

        role_rows = preferred or fallback
        reasoners = {speaker for _pos, speaker in role_rows}
        if len(reasoners) != 1:
            return (), None
        reasoner = next(iter(reasoners))
        reason_pos = max(pos for pos, speaker in role_rows if speaker == reasoner)

        # 按契约中该角色出现次序，先定位最接近对应 beat 的现有对白。
        # 若契约随后还有家长追问，则补位必须落在追问（以及已有回答）之后，
        # 不能插到 beat2 与 beat3 中间破坏开口因果。
        reason_occurrence = sum(
            1
            for raw in contract_rows[: reason_pos + 1]
            if str(raw.get("speaker") or "").strip() == reasoner
        )
        reason_indices = [
            idx
            for idx, item in enumerate(dialogue)
            if isinstance(item, dict)
            and str(item.get("speaker") or "").strip() == reasoner
        ]
        if not reason_indices:
            return (), None
        reason_idx = reason_indices[min(max(0, reason_occurrence - 1), len(reason_indices) - 1)]

        parent_after = next(
            (
                str(raw.get("speaker") or "").strip()
                for raw in contract_rows[reason_pos + 1 :]
                if str(raw.get("speaker") or "").strip() in {"妈妈", "爸爸"}
                and re.search(
                    r"追问|质问|反问|发问|问",
                    str(raw.get("intent") or raw.get("beat") or ""),
                )
            ),
            "",
        )
        if parent_after:
            parent_idx = next(
                (
                    idx
                    for idx in range(reason_idx + 1, len(dialogue))
                    if isinstance(dialogue[idx], dict)
                    and str(dialogue[idx].get("speaker") or "").strip() == parent_after
                    and re.search(
                        r"[？?]|怎么|为何|为啥|凭什么|是不是|要不要|能不能",
                        str(dialogue[idx].get("line") or ""),
                    )
                ),
                -1,
            )
            if parent_idx < 0:
                pass
            else:
                response_idx = next(
                    (
                        idx
                        for idx in range(parent_idx + 1, len(dialogue))
                        if isinstance(dialogue[idx], dict)
                        and str(dialogue[idx].get("speaker") or "").strip() == reasoner
                    ),
                    -1,
                )
                bumped = response_idx if response_idx >= 0 else parent_idx
                if bumped >= len(dialogue) - 2:
                    return (), None
                reason_idx = bumped

    # 补位只能用契约里真有拍的角色：这里从 beat_chain 取本场合法 speaker。
    # 先前写死「另一位手足」会把契约外的孩子放进对白（#87：契约只有妈妈+昭昭，
    # 补位却塞进灿灿的两句），随后被角色表闸门拦死，等于自己制造违规。
    cast = {
        str(raw.get("speaker") or "").strip()
        for raw in (beat_chain or [])
        if isinstance(raw, dict) and str(raw.get("speaker") or "").strip()
    }
    other_kids = sorted(
        name
        for name in cast
        if name in {"昭昭", "灿灿"} and name != reasoner
    )
    if cast:
        # 契约已知：只能用契约里真有拍的手足；两人手时为空（不补第三方）
        listener = other_kids[0] if other_kids else ""
    else:
        # 契约未知（部分本地收口路径不带 beat_chain）：沿用旧行为
        listener = "灿灿" if reasoner == "昭昭" else "昭昭"
    # 契约把追问拍交给家长时，补位问句必须由该家长说：旁观手足代问会把
    # 立规方挤成「立规 + 收束」两端，N 的破功主体换人（#87 实测）。
    contract_asker = ""
    for raw in (beat_chain or []):
        if not isinstance(raw, dict):
            continue
        speaker = str(raw.get("speaker") or "").strip()
        intent = str(raw.get("intent") or raw.get("beat") or "")
        if speaker in {"妈妈", "爸爸"} and re.search(
            r"追问|质问|设问|发问|问：|问什么|谁教", intent
        ):
            contract_asker = speaker
            break
    # 补位一律不得越过收束句：收束之后再插句会让「愣住/接不住」离开末段窗口，
    # 类型契约随即判收束不合格（#87 实测：补位落在妈妈收束句之后）。
    close_idx = len(dialogue) - 1
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if _N_CLOSE_LINE_RE.search(str(item.get("line") or "")):
            close_idx = i
    asker = contract_asker or listener
    if contract_asker:
        # 家长额度：未知时按契约上限 3 保守估计，避免把家长句补到超额度
        cap = 3 if parent_lines_max is None else max(0, int(parent_lines_max))
        used = sum(
            1
            for item in dialogue
            if isinstance(item, dict)
            and str(item.get("speaker") or "").strip() == contract_asker
            and str(item.get("line") or "").strip()
        )
        if used + 1 > cap:
            # 额度已满：有旁观手足才补帮腔对；两人手没有第三方就干脆不补，
            # 让句内扩写去补字数（绝不允许凭空造一个契约外角色）
            if not listener:
                return (), None
            echo_pairs = tuple(
                ((reasoner, spoken), (listener, echo))
                for spoken, echo in _N_VIEWER_ECHO_TEMPLATES
            )
            insert_at = close_idx - 1
            return (echo_pairs, insert_at) if insert_at >= 2 else ((), None)
    if not asker:
        return (), None
    pairs = tuple(
        ((asker, ask), (reasoner, answer))
        for ask, answer in _N_NATURAL_MID_TEMPLATES
    )
    known_lines = {
        line
        for ask, answer in _N_NATURAL_MID_TEMPLATES
        for line in (ask, answer)
    }
    # 禁止 min(...) 把 insert_at 拉回理由行之前；末两拍 reserved 且无空位则不补。
    if reason_idx >= len(dialogue) - 2:
        return (), None
    insert_at = reason_idx + 1
    while insert_at < len(dialogue):
        item = dialogue[insert_at]
        if not isinstance(item, dict):
            break
        if str(item.get("line") or "").strip() not in known_lines:
            break
        insert_at += 1
    # 补位必须落在收束句之前，且给收束句留出位置
    insert_at = min(insert_at, close_idx - 1)
    if insert_at < 2:
        return (), None
    return pairs, insert_at


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
    # 「了/着/过」也是句末助词：再补「呢」会造出「懂了呢」这类不通的叠尾
    if not core or core[-1] in "啦嘛呀啊呢吧哦喔咯呗了着过":
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
    if st == "N" and speaker:
        # N 两人手：孩子句补中性短尾，家长句补称呼（只加词不加句、不改语义）
        from app.services.daily_story.dialogue_text import DAILY_STORY_LINE_CHARS_MAX

        s = str(line or "").strip()
        if need <= 0 or not s:
            return s, 0
        room = max(0, DAILY_STORY_LINE_CHARS_MAX - len(s))
        if room <= 0:
            return s, 0
        core_head = s.rstrip("！。？…!")
        has_particle = bool(re.search(r"[呢嘛呀啊吧了]$", core_head))
        if has_particle:
            return _pad_gold_chat_single_particle(s, need, used=used)
        if speaker in {"妈妈", "爸爸"}:
            # 家长句只补不点名、不改语义的短尾（点名容易点错孩子，不用称呼）
            for tail in _N_PARENT_SAFE_TAILS:
                bare = tail.lstrip("，,")
                if used is not None and bare in used:
                    continue
                if bare in s:
                    continue
                if len(tail) > need or len(tail) > room:
                    continue
                core = s.rstrip("！。？…!")
                mark = s[len(core) :]
                if used is not None:
                    used.add(bare)
                return f"{core}{tail}{mark}", len(tail)
            return _pad_gold_chat_single_particle(s, need, used=used)
        if not any(b in s for b in _N_SAFE_NATURAL_EXPAND):
            for tail in _N_SAFE_NATURAL_EXPAND:
                bare = tail.lstrip("，,")
                if used is not None and bare in used:
                    continue
                if bare in s:
                    continue
                if len(tail) > need or len(tail) > room:
                    continue
                core = s.rstrip("！。？…!")
                mark = s[len(core) :]
                if used is not None:
                    used.add(bare)
                return f"{core}{tail}{mark}", len(tail)
        return _pad_gold_chat_single_particle(s, need, used=used)
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
    if st in {"E", "F"}:
        # E/F 短稿的儿童句可补实义尾巴（家长句有额度/破功约束，不在此扩写）
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
        room = max(0, DAILY_STORY_LINE_CHARS_MAX - dialogue_char_count(text))
        tails = _E_SAFE_NATURAL_EXPAND if st == "E" else _F_SAFE_NATURAL_EXPAND
        for tail in tails:
            bare = tail.lstrip("，,")
            if used is not None and bare in used:
                continue
            if bare in core or core.endswith(bare):
                continue
            if len(tail) > need or len(tail) > room:
                continue
            if used is not None:
                used.add(bare)
            return f"{core}{tail}{trail}", len(tail)
        return _pad_gold_chat_single_particle(line, need, used=used)
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
    if st == "N":
        # N 两人手只有 1 个孩子可垫，字数易近失；按「可垫句位」放开到家长句
        # （只加词不加句，不碰末句收束），专家口径：mom_lines_max 约束句数不是字数。
        adult_ok = [
            i
            for i, item in enumerate(dialogue)
            if isinstance(item, dict)
            and str(item.get("speaker") or "") in {"妈妈", "爸爸"}
            and i < len(dialogue) - 1
        ]
        merged = sorted({*indices, *adult_ok})
        return merged or indices
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

    if _gold_chat_length_floor_met(story):
        return story, False
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
    elif story_type == "E":
        natural_bares = {c.lstrip("，,") for c in _E_SAFE_NATURAL_EXPAND}
    elif story_type == "F":
        natural_bares = {c.lstrip("，,") for c in _F_SAFE_NATURAL_EXPAND}
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

    if _gold_chat_length_floor_met(story):
        return story, False
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
    elif story_type == "E":
        expand_src = _E_SAFE_NATURAL_EXPAND
    elif story_type == "F":
        expand_src = _F_SAFE_NATURAL_EXPAND
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
    beat_chain: list[Any] | None = None,
    dialogue_seed: list[Any] | None = None,
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
    n_pair_pool, n_insert_at = (
        _n_natural_mid_pairs(
            dialogue,
            beat_chain=beat_chain,
            dialogue_seed=dialogue_seed,
            parent_lines_max=(
                story.get("_gold_chat_mom_lines_max")
                if story.get("_gold_chat_mom_lines_max") is not None
                else story.get("_gold_chat_dad_lines_max")
            ),
        )
        if st == "N"
        else ((), None)
    )
    a_pair_pool, a_insert_at = (
        _a_natural_mid_pairs(dialogue, beat_chain=beat_chain)
        if st == "A"
        else ((), None)
    )
    e_pair_pool, e_insert_at = (
        _e_natural_mid_pairs(dialogue) if st == "E" else ((), None)
    )
    f_pair_pool, f_insert_at = (
        _f_natural_mid_pairs(dialogue, beat_chain=beat_chain)
        if st == "F"
        else ((), None)
    )
    # K：顶满 24 句时仍可能差字，允许至 26 以便插实义中段对
    from app.services.gold_story.scene import chat_line_cap

    line_cap = chat_line_cap(st)
    m8_j = is_m8_j_domination(mechanism=mechanism, structure_type=st)
    large_gap = need > GOLD_CHAT_NEAR_MISS_DEFICIT_MAX
    if total < 100 and not large_gap:
        return story, False
    if (
        len(dialogue) < CHAT_LINE_COUNT_MIN
        and not large_gap
        and not (st == "N" and n_pair_pool)
        # E/F 短稿常卡在 11 句 + 差几字：句中垫粒子补不动，
        # 直接插实义对同时补句数与字数
        and not (st in {"E", "F"} and (e_pair_pool or f_pair_pool))
    ):
        return story, False

    existing = {str(x.get("line") or "").strip() for x in dialogue if isinstance(x, dict)}
    blob = "".join(existing)
    seed_blob = "".join(
        str(item.get("line") or item.get("intent") or "")
        for item in (dialogue_seed or [])
        if isinstance(item, dict)
    )
    g_cleanup = bool(
        st == "G"
        and re.search(r"收(?:好|拾|回|玩具)|放回|整理", f"{blob}{seed_blob}")
    )
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
    if st == "N" and n_insert_at is not None:
        # 紧跟已有因果回答插入，必须落在后续愣住/收束之前。
        insert_at = n_insert_at
    if st == "A" and a_insert_at is not None:
        # 固定落在末四拍之前，保证收束四槽不动
        insert_at = a_insert_at
    if st == "E" and e_insert_at is not None:
        # 落在末句妈妈破功之前
        insert_at = e_insert_at
    if st == "F" and f_insert_at is not None:
        insert_at = f_insert_at
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
        st not in {"N", "O"}
        and isinstance(prev, dict)
        and str(prev.get("speaker") or "").strip() == "昭昭"
    ):
        insert_at = min(insert_at + 1, len(dialogue))
    if m8_j:
        pair_pool = _M8_J_NATURAL_MID_PAIRS
    elif st == "J":
        pair_pool = _GOLD_CHAT_NATURAL_MID_PAIRS
    elif g_cleanup:
        pair_pool = _G_CLEANUP_NATURAL_MID_PAIRS
    elif st == "N":
        pair_pool = n_pair_pool
    elif st == "A":
        pair_pool = a_pair_pool
    elif st == "E":
        pair_pool = e_pair_pool
    elif st == "F":
        pair_pool = f_pair_pool
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
    if st == "N":
        # 一次只插一对；仍不足时由稳定器下一轮选择另一对，避免一次性灌满。
        max_pairs = 1
    if st == "A":
        # 同样一次一对：补满即停，避免中段灌虚
        max_pairs = 1
    if st in {"E", "F"}:
        # 缺口更大时允许两对，仍由字数达标即停
        max_pairs = 2 if need >= 24 else 1

    existing_norm = {_norm_pad_line(x) for x in existing if x}
    existing_lines = [x for x in existing if x]
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
            if (
                not text
                or text in existing
                or _norm_pad_line(text) in existing_norm
                or _pad_line_is_duplicate(text, existing_lines)
            ):
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
        if st == "A" and insert_at > max(2, len(dialogue) - 4):
            # 交替调整把插入点挤进末四拍：宁可少补一对，也不动收束四槽
            break
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
            existing_lines.append(text)
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
    elif st == "J":
        expand_src = _J_GOLD_CHAT_NATURAL_EXPAND
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
            and (2 if st == "J" else 4) <= len(str(item.get("line") or "").strip()) < 20
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
            if st == "J":
                if sp == "昭昭":
                    src = _J_ZHAO_NATURAL_EXPAND
                elif sp == "灿灿":
                    src = _J_CAN_NATURAL_EXPAND
                else:
                    expand_count[idx] = 1
                    continue
            elif st == "K":
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
    beat_chain: list[Any] | None = None,
    dialogue_seed: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """near-miss 垫到 hard min；大缺口先可读中段加句，再交 扩写/FIX。

    剥旧灌尾 → 可读句内扩写 → 中段加句 → 粒子 near-miss（差 ≤60）。
    """
    data, clutter_changed = patch_sanitize_expand_clutter(story)
    data, changed_lines = _ensure_gold_chat_min_lines(data)
    data, changed_exp = _expand_short_gold_chat_lines(data)
    changed = clutter_changed or changed_lines or changed_exp
    # 先剥叠语气词/垫字痕迹，再按联合判据决定是否还需要垫字数：句数达标时字数
    # 下限放宽一行，已达标就只剥不回灌，否则为凑 240 补的句尾粒子会被终检判成语病。
    for _ in range(4):
        data, san = patch_sanitize_c_tone_stack(data)
        data, san2 = patch_sanitize_pad_suffix(data)
        data, san3 = patch_sanitize_expand_clutter(data)
        data, san4 = patch_sanitize_pad_particles(data)
        changed = changed or san or san2 or san3 or san4
        if not (san or san2 or san3 or san4):
            break
    if dialogue_total_chars(data) >= gold_chat_effective_min_chars(data.get("dialogue")):
        return data, changed
    # 仅大缺口才插求否对；near-miss 交给句内扩写/粒子，避免一锤后拉锯灌尾
    need_now = DAILY_STORY_BODY_CHARS_MIN - dialogue_total_chars(data)
    changed_mid = False
    st = str(structure_type or story.get("story_type") or "").strip().upper()
    mech = str(mechanism or "").strip()
    # E/F 的 near-miss 只能靠粒子加 1–4 字：留出窄缝就直接走实义中段对
    mid_pair_gate = (
        5 if st in {"E", "F"} else GOLD_CHAT_NEAR_MISS_DEFICIT_MAX
    )
    if (
        need_now > mid_pair_gate
        or (st == "N" and need_now >= 12)
    ):
        # N 的明显缺口优先补「追问→复述理由」实义对，再考虑单粒子；
        # 避免先把原句改成「抖啊/不信吧/挪开呢」后才发现仍不够长。
        data, changed_mid = _boost_short_with_mid_lines(
            data,
            mechanism=mech,
            structure_type=st,
            beat_chain=beat_chain,
            dialogue_seed=dialogue_seed,
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
                    beat_chain=beat_chain,
                    dialogue_seed=dialogue_seed,
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

    # N 的 near-miss 可能卡在一个窄缝：已有句均接近句长上限时，粒子/句内扩写都
    # 无法前进，但稿内其实已经有可定位的「追问→因果回答」链。此时最后复用 N
    # 专用的抽象复述对补实义，不把 1~60 字的纯篇幅问题继续烧给 LLM repair/重抽。
    # 放在所有轻量收口之后，只处理前面确实无法闭合的稿，避免正常 1~3 字 near-miss
    # 被无谓插入整对台词。
    if st == "N" and dialogue_total_chars(data) < DAILY_STORY_BODY_CHARS_MIN:
        data2, n_mid = _boost_short_with_mid_lines(
            data,
            mechanism=mech,
            structure_type="N",
            beat_chain=beat_chain,
            dialogue_seed=dialogue_seed,
        )
        if n_mid:
            data = data2
            changed = True
    return data, changed


def _sanitize_pad_lines_in_place(data: dict[str, Any]) -> bool:
    """姐弟句本地机械垫字清理：清掉机审命中的句尾垫字，不垫字数、不调 LLM。

    与 review/pad_stack 同口径：`pad_stack_issue_for_line` 命中即清（真实问句由
    sanitizer 内部保留）。必须独立于长度门控调用——此前该清理只挂在
    `_stabilize_local_length_candidate` 的 hard_deficit 门控内，字数已达标
    （≥240）的稿子整段跳过，句尾垫字（如「…这车我占住了好不好」）会一路带到
    终检，被当成必须 LLM 定点改的硬伤，把整轮实跑打死。
    """
    changed = False
    rows = data.get("dialogue")
    if not isinstance(rows, list):
        return changed
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
    return changed


def _stabilize_local_length_candidate(
    candidate: dict[str, Any],
    *,
    structure_type: str,
    mechanism: str,
    beat_chain: list[Any] | None = None,
    dialogue_seed: list[Any] | None = None,
    target_chars: int = GOLD_CHAT_LOCAL_LENGTH_TARGET,
) -> tuple[dict[str, Any], bool]:
    """统一机械收口：句长压缩 + near-miss 补字；最终不得靠垫字痕迹过线。"""
    data, shortened = _apply_deterministic_shorten(candidate)
    changed = shortened

    # 垫字清理先于长度门控：字数已达标时同样要清，否则本地可清的句尾垫字
    # 会带着进终检。清理只会变短，若因此掉到 240 以下再由下方补字路径兜底。
    changed = _sanitize_pad_lines_in_place(data) or changed

    total = dialogue_total_chars(data)
    hard_deficit = DAILY_STORY_BODY_CHARS_MIN - total
    if not (0 < hard_deficit <= GOLD_CHAT_NEAR_MISS_DEFICIT_MAX):
        return data, changed

    data, expanded = _ensure_gold_chat_min_chars(
        data,
        mechanism=mechanism,
        structure_type=structure_type,
        beat_chain=beat_chain,
        dialogue_seed=dialogue_seed,
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
    changed = _sanitize_pad_lines_in_place(data) or changed

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
                beat_chain=beat_chain,
                dialogue_seed=dialogue_seed,
            )
            changed = changed or mid
        if dialogue_total_chars(data) <= before:
            break

    # 实义扩写后再做一次句长与垫字清理；清理后若仍 >= hard min 即接受，
    # 不为追求 250 的软余量重新塞语气尾巴。
    data, shortened2 = _apply_deterministic_shorten(data)
    changed = changed or shortened2
    changed = _sanitize_pad_lines_in_place(data) or changed
    return data, changed


def _gold_chat_insert_body_lines_for_min(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """删句后 pad/expand 顶格时：中段插 1–2 条抽象反应句补 min（非求拒）。"""
    import copy

    from app.services.gold_story.scene import CHAT_LINE_COUNT_MAX

    if _gold_chat_length_floor_met(story):
        return story, False
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

    if _gold_chat_length_floor_met(story):
        return story, False
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
