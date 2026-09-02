"""K 类正文本地修稿：末段剥 H 式和好，补僵持/劝失败。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.k.validate import (
    RE_H_RECONCILE,
    RE_PARENT_FAIL,
    RE_STALEMATE,
)

_PARENT_FAIL_LINE = "唉，我管不了你们了。"
_KID_STALEMATE_LINE = "哼，我才不理你！"
_PARENT_SPEAKERS = frozenset({"妈妈", "爸爸"})
_KID_SPEAKERS = frozenset({"昭昭", "灿灿"})
# 家长旁观评点/解说腔（非劝失败口语）
_RE_PARENT_META = re.compile(
    r"真绝了|太好笑|笑死|胜不骄|败不馁|这下好看|好看了|"
    r"我不管你们了吧呢"
)
# 串型：J 求否句不该出现在 K
_RE_CROSS_J_PLEA = re.compile(
    r"再求你一次|那我保证|就这一次|规矩就是这样|"
    r"保证也没用|少讨价还价|这回听我安排|这回你就松口",
)
# 成人腔威胁（抽象句式，非单篇词表）
_RE_ADULT_THREAT = re.compile(
    r"警告你|今天.{0,8}教训|好好教训|我非要教训|说一不二|"
    r"非治你|非收拾你|今天非.{0,6}不可|"
    r"不服也得挨着|也得挨着|轮不到你.{0,4}说|"
    r"这茬我记下|记下了",
)
# 「越劝」应对劝架大人；对弟妹说「你越劝」属指代事故
_RE_YUEQUAN_TO_PEER = re.compile(r"你越劝|越劝我越打")
_RE_BITE_HAND_REPLY = re.compile(r"别咬我手|咬我的手|咬我手")
# 点题/分镜式宣告（抽象句式）
_RE_META_STALEMATE = re.compile(r"就僵着|僵着呗|谁先软谁输")
_RE_ACTION_NARR = re.compile(
    r"(?:我躲|我躲到|我跑到|我缩到).{0,8}|"
    r"我拧你耳朵|我拧你",
)
_HAND_PAIN_LINE = "哎哟，我手好疼！"
_RE_PAD_JUNK_LINE = re.compile(
    r"^(?:了吧真的|真的呀真的|了呢真的)[，,]?",
)
_RE_PARTICLE_ONLY = re.compile(
    r"^[嘛呢吧呀啊啦了真的不行好偏哼]+[！？。!?]*$",
)
_RE_TRAILING_PAD = re.compile(
    r"(?:真的呢|真的吧|不行真的吧|真的呀真的|好不好呀|"
    r"真的(?:呀|呢|吧)?|不行嘛|嘛呀|了呢)+[！？。!?]*$",
)
_RE_MID_PAD_JUNK = re.compile(
    r"(?:真的(?:呀|呢|吧|啊)?){2,}|"
    r"(?:不行(?:真的|了?[啊吧呀呢嘛])?){2,}|"
    r"(?:了[啊吧呀呢]){2,}|"
    r"不行真的不行|真的了啊|真的呀不行|了吧不行|了啊不行|"
    r"真的呀不行嘛|嘛不行嘛呀|嘛不行嘛|不行嘛呀|嘛不行|嘛呀",
)
_PAD_JUNK_REPLACEMENTS = (
    ("活该嘛呀", "活该"),
    ("活该了呢", "活该"),
)


def _is_k(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    return code == "K"


def _dialogue_idxs(dialogue: list) -> list[int]:
    out: list[int] = []
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("line") or "").strip():
            out.append(i)
    return out


def _rewrite_h_line(speaker: str, line: str) -> str:
    """把末段 H 式和好改成 K 劝失败/僵持（抽象槽位，非单篇词表）。"""
    sp = str(speaker or "").strip()
    text = str(line or "").strip()
    if not text or not RE_H_RECONCILE.search(text):
        return text
    if sp in _PARENT_SPEAKERS:
        return _PARENT_FAIL_LINE
    return _KID_STALEMATE_LINE


def sanitize_k_dialogue_seed(seed: list | None) -> list:
    """K：seed 里带 H 式和好的 intent 改成劝失败/僵持，避免 Pass1 被带偏。"""
    if not isinstance(seed, list):
        return []
    out: list = []
    for item in seed:
        if not isinstance(item, dict):
            out.append(item)
            continue
        row = dict(item)
        sp = str(row.get("speaker") or "").strip()
        key = "intent" if str(row.get("intent") or "").strip() else "line"
        text = str(row.get(key) or "").strip()
        if text and RE_H_RECONCILE.search(text):
            if sp in _PARENT_SPEAKERS:
                row[key] = "唉，我管不了你们了"
            else:
                row[key] = "哼，我才不理你"
        out.append(row)
    return out


def patch_k_punchline_prefix(story: dict) -> list[str]:
    """gold_chat：punchline_explain 补 K类 前缀。"""
    if not _is_k(story):
        return []
    explain = str(story.get("punchline_explain") or "").strip()
    if not explain or explain.upper().startswith("K"):
        return []
    story["punchline_explain"] = f"K类：{explain}"
    return ["K punchline→K类"]


def patch_k_close_stalemate(story: dict) -> list[str]:
    """末 4 句：剥 H 式和好；缺僵持则补；家长无劝失败则改一句。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    idxs = _dialogue_idxs(dialogue)
    if len(idxs) < 10:
        return notes

    tail_idxs = idxs[-4:]
    for i in tail_idxs:
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        new_line = _rewrite_h_line(sp, line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"K末段剥和好[{i + 1}]")

    lines = [
        str(dialogue[i].get("line") or "").strip()
        for i in idxs
        if isinstance(dialogue[i], dict)
    ]
    tail4 = "".join(lines[-4:])
    body = "".join(lines)

    if not RE_STALEMATE.search(tail4):
        target: int | None = None
        for i in reversed(tail_idxs):
            sp = str(dialogue[i].get("speaker") or "").strip()
            if sp in _KID_SPEAKERS:
                target = i
                break
        if target is None:
            for i in reversed(idxs):
                sp = str(dialogue[i].get("speaker") or "").strip()
                if sp in _KID_SPEAKERS:
                    target = i
                    break
        if target is not None:
            dialogue[target]["line"] = _KID_STALEMATE_LINE
            notes.append("K补僵持收束")

    parent_n = sum(
        1
        for i in idxs
        if str(dialogue[i].get("speaker") or "").strip() in _PARENT_SPEAKERS
    )
    if parent_n >= 1 and not RE_PARENT_FAIL.search(body):
        for i in idxs:
            sp = str(dialogue[i].get("speaker") or "").strip()
            if sp not in _PARENT_SPEAKERS:
                continue
            dialogue[i]["line"] = _PARENT_FAIL_LINE
            notes.append(f"K家长→劝失败[{i + 1}]")
            break

    # 末段家长若写成旁观评点/解说，收回劝失败口语
    for i in idxs[-4:]:
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp not in _PARENT_SPEAKERS:
            continue
        if _RE_PARENT_META.search(line):
            item["line"] = _PARENT_FAIL_LINE
            notes.append(f"K家长评点→劝失败[{i + 1}]")

    story["dialogue"] = dialogue
    return notes


def patch_k_strip_cross_type_plea(story: dict) -> list[str]:
    """K：剥误插的 J 求否句，避免中段垫字串型。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 12:
        return notes
    kept: list = []
    removed = 0
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if line and _RE_CROSS_J_PLEA.search(line):
            removed += 1
            continue
        kept.append(item)
    if removed and len(kept) >= 10:
        story["dialogue"] = kept
        notes.append(f"K剥串型求否{removed}句")
    return notes


def patch_k_strip_adult_threat(story: dict) -> list[str]:
    """K：成人腔威胁改成短促现场气话。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp not in _KID_SPEAKERS or not line:
            continue
        if not _RE_ADULT_THREAT.search(line):
            continue
        if sp == "灿灿":
            item["line"] = "你再闹试试！"
        else:
            item["line"] = "谁怕谁！"
        notes.append(f"K成人腔→气话[{i + 1}]")
    return notes


def patch_k_strip_orphan_reply(story: dict) -> list[str]:
    """剥失去前文支撑的应答尾巴（如「记就记着」无「记下」）。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    def _norm(text: str) -> str:
        return re.sub(r"[呀啊吧呢嘛了呗！？。!?，,\s]", "", str(text or ""))

    body = "".join(
        str(x.get("line") or "")
        for x in dialogue
        if isinstance(x, dict)
    )
    has_record = bool(re.search(r"记下|记着这|我记", body))
    existing_norm = {
        _norm(str(x.get("line") or ""))
        for x in dialogue
        if isinstance(x, dict)
    }
    can_fallbacks = ("来啊！谁怕谁！", "那就接着打！", "再凶一点！")
    zhao_fallbacks = ("哼，我偏不认！", "我才不认输！", "你凶啥凶！")
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        need = False
        if re.search(r"记就记着|记着谁怕", line) and not has_record:
            need = True
        elif len(re.sub(r"[！？。!?，,\s]", "", line)) <= 1:
            need = True
        if not need:
            continue
        pool = can_fallbacks if sp == "灿灿" else zhao_fallbacks
        new_line = None
        for cand in pool:
            if _norm(cand) not in existing_norm:
                new_line = cand
                break
        if not new_line:
            new_line = "你再闹试试！" if sp == "灿灿" else "谁怕谁！"
        item["line"] = new_line
        existing_norm.add(_norm(new_line))
        notes.append(f"K孤儿/残句[{i + 1}]")
    return notes


def patch_k_break_same_speaker_run(story: dict) -> list[str]:
    """K：孩童禁止连说两句（补字/改写事故）。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 3:
        return notes
    drop: set[int] = set()
    for i in range(1, len(dialogue)):
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        sp = str(a.get("speaker") or "").strip()
        if sp != str(b.get("speaker") or "").strip():
            continue
        if sp not in _KID_SPEAKERS:
            continue
        # 留较长句；同长留前
        la = len(str(a.get("line") or "").strip())
        lb = len(str(b.get("line") or "").strip())
        drop.add(i if lb <= la else i - 1)
    if not drop:
        return notes
    kept = [x for i, x in enumerate(dialogue) if i not in drop]
    if len(kept) < 10:
        return notes
    story["dialogue"] = kept
    notes.append(f"K断连说×{len(drop)}")
    return notes


def patch_k_hand_pain_speech(story: dict) -> list[str]:
    """若笑点/机制含护手怕疼，正文须有可说出口的手疼句。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    blob = " ".join(
        str(story.get(k) or "")
        for k in ("punchline_explain", "conflict_core", "key", "scene_title")
    )
    if not re.search(r"护手|怕疼|手疼|咬.*手|手.*疼", blob):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    # 互咬回应变自护娇气，避免笑点漂成对打反击
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "灿灿":
            continue
        line = str(item.get("line") or "").strip()
        if _RE_BITE_HAND_REPLY.search(line):
            item["line"] = _HAND_PAIN_LINE
            notes.append(f"K护手自护改写[{i + 1}]")
    body = "".join(
        str(x.get("line") or "")
        for x in dialogue
        if isinstance(x, dict)
    )
    has_pain = bool(
        re.search(r"手.{0,6}疼|疼.{0,6}手|弄疼我手|我手|手金贵|手好疼", body)
    )
    if not has_pain:
        for item in reversed(dialogue):
            if not isinstance(item, dict):
                continue
            if str(item.get("speaker") or "").strip() != "灿灿":
                continue
            line = str(item.get("line") or "").strip()
            if not line or line == _PARENT_FAIL_LINE:
                continue
            item["line"] = _HAND_PAIN_LINE
            notes.append("K补手疼口语")
            break
        body = "".join(
            str(x.get("line") or "")
            for x in dialogue
            if isinstance(x, dict)
        )
    # 已有手疼但无拧/咬动作 → 合并进手疼前一句昭昭台词
    if re.search(r"手.{0,6}疼|手好疼", body) and not re.search(
        r"拧|咬你手|咬定", body
    ):
        for i, item in enumerate(dialogue):
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "").strip()
            if not re.search(r"手好疼|我手好疼|手.{0,4}疼", line):
                continue
            prev = dialogue[i - 1] if i >= 1 else None
            if (
                isinstance(prev, dict)
                and str(prev.get("speaker") or "").strip() == "昭昭"
            ):
                prev_line = str(prev.get("line") or "").strip()
                if "妈" in prev_line:
                    prev["line"] = "妈！你再拧我！我咬你手！"
                else:
                    prev["line"] = "你再拧！我咬你手！"
                notes.append(f"K手疼因果前置[{i}]")
            elif i >= 1:
                dialogue.insert(i, {"speaker": "昭昭", "line": "你再拧！我咬你手！"})
                notes.append("K手疼因果插句")
            break
    return notes


def patch_k_dedupe_near_lines(story: dict) -> list[str]:
    """剥去语气词后同义句（防补字插重复对）。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes

    def _norm(text: str) -> str:
        return re.sub(r"[呀啊吧呢嘛了呗！？。!?，,\s]", "", str(text or ""))

    seen: set[str] = set()
    drop: set[int] = set()
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        key = _norm(line)
        if not key:
            continue
        if key in seen:
            drop.add(i)
        else:
            seen.add(key)
    # 同角色连说且后句含前句实义 → 留前删后
    for i in range(1, len(dialogue)):
        if i in drop:
            continue
        a, b = dialogue[i - 1], dialogue[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        if str(a.get("speaker") or "") != str(b.get("speaker") or ""):
            continue
        na, nb = _norm(str(a.get("line") or "")), _norm(str(b.get("line") or ""))
        if not na or not nb:
            continue
        if na in nb or nb in na:
            drop.add(i)
            continue
        # 同角色连说且共享实义核（≥4字）→ 留前删后
        if any(na[j : j + 4] in nb for j in range(max(0, len(na) - 3))):
            drop.add(i)
    if not drop:
        return notes
    kept = [x for i, x in enumerate(dialogue) if i not in drop]
    # 字数由下游 boost 补；此处只保结构下限，勿因短字留下脏重复
    if len(kept) < 10:
        return notes
    story["dialogue"] = kept
    notes.append(f"K近义句去重×{len(drop)}")
    return notes


def patch_k_strip_meta_and_action_narr(story: dict) -> list[str]:
    """剥点题「僵着」与分镜式动作宣告。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        new_line = line
        if _RE_META_STALEMATE.search(new_line):
            new_line = "谁怕谁！来啊！" if sp == "灿灿" else "哼，我不理你！"
        if _RE_ACTION_NARR.search(new_line):
            # 剥动作叙述段，尽量留前半喊话
            parts = re.split(r"[！!]", new_line)
            kept: list[str] = []
            for part in parts:
                p = part.strip("，, ")
                if not p or _RE_ACTION_NARR.search(p):
                    continue
                kept.append(p)
            if kept:
                new_line = "！".join(kept) + "！"
            else:
                new_line = "你别过来！" if sp == "昭昭" else "你再闹试试！"
        if new_line.startswith("呀！") or new_line.startswith("啊！"):
            new_line = new_line[2:].strip() or (
                "你再闹试试！" if sp == "灿灿" else "我才不怕你！"
            )
        if new_line.startswith("哼吧"):
            new_line = "哼，我不理你！"
        if new_line != line:
            if new_line[-1] not in "？！。!?":
                new_line = f"{new_line}！"
            item["line"] = new_line
            notes.append(f"K剥点题/分镜[{i + 1}]")
    return notes


def patch_k_yuequan_address(story: dict) -> list[str]:
    """「越劝」须接劝架大人；对弟妹说「你越劝」改为互顶气话。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp not in _KID_SPEAKERS or not line:
            continue
        if not _RE_YUEQUAN_TO_PEER.search(line):
            continue
        prev_window = dialogue[max(0, i - 3) : i]
        mom_near = any(
            isinstance(x, dict)
            and str(x.get("speaker") or "").strip() in _PARENT_SPEAKERS
            for x in prev_window
        )
        if mom_near and not line.startswith("你越劝"):
            # 「越劝我越打」对妈妈说可留
            continue
        item["line"] = "再闹我就更凶！" if sp == "灿灿" else "我才不怕你！"
        notes.append(f"K越劝指代纠偏[{i + 1}]")
    return notes


def patch_k_fix_truncations(story: dict) -> list[str]:
    """补常见截断口语（你干→你干嘛），去句内叠句。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        new_line = re.sub(r"你干([！。!?]?)$", r"你干嘛\1", line)
        new_line = re.sub(r"再闹我恼([，,！。!?]|$)", r"再闹我恼了\1", new_line)
        new_line = re.sub(r"呗啊([！？。!?]|$)", r"呗\1", new_line)
        new_line = re.sub(r"(.{2,8})，\1([！？。!?]*)$", r"\1\2", new_line)
        new_line = re.sub(r"(.{2,8})\1([！？。!?]*)$", r"\1\2", new_line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"K截断/叠句[{i + 1}]")
    return notes


def patch_k_dedupe_stock_phrases(story: dict) -> list[str]:
    """同一扩写口头禅全篇最多留 1 处，防公式复读。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    # 字数已贴底时不去重砍字，留给中段补句
    total = 0
    for row in dialogue:
        if isinstance(row, dict):
            total += len(str(row.get("line") or "").strip())
    if total <= 248:
        return notes
    stock = (
        "我才不怕呢",
        "我才不怕你",
        "我才不怕",
        "再闹我恼了",
        "再闹我恼",
        "你试试看啊",
        "轮不到你",
    )
    seen: set[str] = set()
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        new_line = line
        for phrase in stock:
            if phrase not in new_line:
                continue
            covered = any(
                phrase != other and phrase in other and other in seen
                for other in stock
            )
            if phrase in seen or covered:
                new_line = new_line.replace(f"，{phrase}", "").replace(phrase, "")
                new_line = re.sub(r"[，,]{2,}", "，", new_line).strip("，。！？ ")
            else:
                seen.add(phrase)
        if new_line == line:
            continue
        if (not new_line) or _RE_PARTICLE_ONLY.match(new_line):
            new_line = "你再闹试试！" if sp == "灿灿" else "谁怕谁！"
        elif new_line[-1] not in "？！。!?":
            new_line = f"{new_line}！"
        item["line"] = new_line
        notes.append(f"K口头禅去重[{i + 1}]")
    return notes


def patch_k_strip_role_expand(story: dict) -> list[str]:
    """剥串角色的扩写尾巴（弟妹说「再闹我恼了」等）。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    zhao_ban = ("再闹我恼了", "再闹我恼", "轮不到你", "不服也得挨着")
    can_ban = ("我才不怕呢", "我才不怕", "你试试看啊")
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        bans = zhao_ban if sp == "昭昭" else (can_ban if sp == "灿灿" else ())
        new_line = line
        for ban in bans:
            if ban in new_line:
                new_line = new_line.replace(f"，{ban}", "").replace(ban, "")
                new_line = re.sub(r"[，,]{2,}", "，", new_line).strip("，。！？ ")
        if new_line == line:
            continue
        if (not new_line) or _RE_PARTICLE_ONLY.match(new_line):
            new_line = "你再闹试试！" if sp == "灿灿" else "我才不怕你！"
        elif new_line[-1] not in "？！。!?":
            new_line = f"{new_line}！"
        item["line"] = new_line
        notes.append(f"K扩写串角[{i + 1}]")
    return notes

def patch_k_strip_pad_junk(story: dict) -> list[str]:
    """剥垫字事故起句与纯语气词句。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        new_line = line
        if _RE_PAD_JUNK_LINE.search(new_line):
            new_line = _RE_PAD_JUNK_LINE.sub("", new_line).strip("，。！？ ")
        # 先剥长叠词，再把「活该+垫字」收成实义，避免短替换拆坏长串
        if _RE_MID_PAD_JUNK.search(new_line):
            new_line = _RE_MID_PAD_JUNK.sub("", new_line)
            new_line = re.sub(r"[，,]{2,}", "，", new_line).strip("，, ")
        for old, new in _PAD_JUNK_REPLACEMENTS:
            if old in new_line:
                new_line = new_line.replace(old, new)
        if _RE_TRAILING_PAD.search(new_line):
            new_line = _RE_TRAILING_PAD.sub("", new_line).strip("，。！？ ")
        for glue in ("，我偏就不信", "我偏就不信"):
            if glue in new_line:
                new_line = new_line.replace(glue, "").strip("，。！？ ")
        # 剥句尾灌上的「不行/真的」（非「就不行」实义）
        new_line = re.sub(
            r"(?<![就])不行(?:真的)?(?:呀|啊|吧|呢|嘛)?([！？。!?]*)$",
            r"\1",
            new_line,
        )
        new_line = re.sub(
            r"(?<![是])真的(?:呀|啊|吧|呢)?([！？。!?]*)$",
            r"\1",
            new_line,
        )
        new_line = re.sub(r"[？!]{2,}", "？", new_line)
        new_line = re.sub(r"？！", "？", new_line)
        if (not new_line) or _RE_PARTICLE_ONLY.match(new_line):
            new_line = "你再闹试试！" if sp == "灿灿" else "我才不怕你！"
        if new_line != line:
            if new_line[-1] not in "？！。!?":
                new_line = f"{new_line}！"
            item["line"] = new_line
            notes.append(f"K剥垫字事故[{i + 1}]")
    return notes


_RE_EMPTY_SHOUT = re.compile(
    r"^(?:哼，?)?(?:谁怕谁|我不?理你|我才不理你|我就不服|我偏不认输|"
    r"不认也没用|那就接着打|来啊)[！？。!?]*$"
)


def patch_k_trim_empty_tail(story: dict) -> list[str]:
    """收尾空喊对超过 1 对时裁掉，保僵持干脆。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 14:
        return notes
    # 找末段家长劝失败句
    parent_i = -1
    for i in range(len(dialogue) - 1, -1, -1):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() not in _PARENT_SPEAKERS:
            continue
        line = str(item.get("line") or "")
        if RE_PARENT_FAIL.search(line) or "管不了" in line:
            parent_i = i
            break
    if parent_i < 8:
        return notes
    # 劝失败前的孩童空喊段
    empty_idxs: list[int] = []
    for i in range(parent_i - 1, max(5, parent_i - 10), -1):
        item = dialogue[i]
        if not isinstance(item, dict):
            break
        if str(item.get("speaker") or "").strip() not in _KID_SPEAKERS:
            break
        line = str(item.get("line") or "").strip()
        if _RE_EMPTY_SHOUT.match(line) or (
            re.search(r"谁怕谁|不理你|不认输|就不服|不认也", line)
            and len(re.sub(r"[！？。!?，,\s哼]", "", line)) <= 8
        ):
            empty_idxs.append(i)
        else:
            # 碰到实义句就停（从后往前）
            if empty_idxs:
                break
            break
    # 只留末 2 句空喊（一对），多的删
    if len(empty_idxs) <= 2:
        return notes
    drop = set(empty_idxs[2:])
    kept = [x for i, x in enumerate(dialogue) if i not in drop]
    if len(kept) < 12:
        return notes
    story["dialogue"] = kept
    notes.append(f"K裁空喊尾×{len(drop)}")
    return notes


def patch_k_body(story: dict) -> list[str]:
    notes = patch_k_punchline_prefix(story)
    notes.extend(patch_k_strip_cross_type_plea(story))
    notes.extend(patch_k_strip_pad_junk(story))
    notes.extend(patch_k_fix_truncations(story))
    notes.extend(patch_k_strip_role_expand(story))
    notes.extend(patch_k_dedupe_stock_phrases(story))
    notes.extend(patch_k_strip_adult_threat(story))
    notes.extend(patch_k_strip_orphan_reply(story))
    notes.extend(patch_k_yuequan_address(story))
    notes.extend(patch_k_strip_meta_and_action_narr(story))
    notes.extend(patch_k_dedupe_near_lines(story))
    notes.extend(patch_k_break_same_speaker_run(story))
    notes.extend(patch_k_hand_pain_speech(story))
    notes.extend(patch_k_strip_adult_threat(story))  # 手疼句被垫回说一不二时再剥
    notes.extend(patch_k_strip_orphan_reply(story))
    notes.extend(patch_k_break_same_speaker_run(story))
    notes.extend(patch_k_close_stalemate(story))
    notes.extend(patch_k_trim_empty_tail(story))
    return notes
