"""K 类正文本地修稿：末段剥 H 式和好，补僵持/劝失败。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.k.validate import (
    RE_H_RECONCILE,
    RE_PARENT_FAIL,
    RE_STALEMATE,
)

_PARENT_FAIL_LINE = "再叫你们分开也不听，我管不了你们了。"
_PARENT_ADVISE_LINE = "别闹了！快分开！再闹我可要生气了！"
_KID_TOP_LINE = "妈妈你别管！"
# 劝止与劝失败之间：原冲突续行（求饶/继续压），非纯顶妈妈
_RE_CONFLICT_RESUME = re.compile(
    r"松手|别挠|还敢|再挠|哭不哭|疼|痒|还嘴硬|不服|撑多久"
)
_RE_PURE_MOM_TOP = re.compile(r"妈妈你别管|你管不着|别管我们|别管我")
_KID_STALEMATE_AFTER = (
    {"speaker": "昭昭", "line": "哼，我就不理你了！"},
    {"speaker": "灿灿", "line": "不理就不理，谁稀罕！"},
)
# 败方哭后禁回勇（抽象：不怕/挑衅/追跑）
_RE_LOSER_POST_CRY_DEFIANCE = re.compile(
    r"我才不怕|偏不还|偏不让步|追不上|来追我|略略略|你试试看|"
    r"抓不到|扔沙发|笔归我|你别过来"
)
_PARENT_WATCH_LINE = "唉，我管不了你们了。"  # 薄旁观升格劝失败，审稿要「劝失败」落点
_KID_WIN_CLOSE = "哼，再闹我也不怕！"
_KID_STALEMATE_LAST = "我才不理你！"
_KID_STALEMATE_MID = "哼，我才不理你！"
_KID_STALEMATE_LINE = _KID_STALEMATE_LAST  # 兼容旧引用
_PARENT_SPEAKERS = frozenset({"妈妈", "爸爸"})
_KID_SPEAKERS = frozenset({"昭昭", "灿灿"})
_RE_K_PRESS_ACTION = re.compile(
    r"按.{0,6}沙发上?挠|按.{0,6}沙发|挠痒痒逼哭|挠痒|逼哭|继续挠"
)


def _k_press_roles_from_core(core: str) -> tuple[str, str]:
    """从 conflict 取压制方/败方：动作前最近人名，避免「昭昭抢…灿灿按」误判。"""
    text = str(core or "")
    action = _RE_K_PRESS_ACTION.search(text)
    if action:
        before = text[: action.start()]
        names = list(re.finditer(r"昭昭|灿灿", before))
        if names:
            winner = names[-1].group(0)
            loser = "灿灿" if winner == "昭昭" else "昭昭"
            return winner, loser
    # 无明确动作时再退回短窗；先灿灿后昭昭，降低抢物主语误伤
    if re.search(r"灿灿.{0,12}(?:挠痒|挠|逼哭|按.{0,6}沙发)", text):
        return "灿灿", "昭昭"
    if re.search(r"昭昭.{0,12}(?:挠痒|挠|逼哭|按.{0,6}沙发)", text):
        return "昭昭", "灿灿"
    return "灿灿", "昭昭"


# 家长写成 H 式定责/劝还物（K 应旁观看戏）
_RE_PARENT_MEDIATE = re.compile(
    r"还给|说清楚|谁先动手|闹够了|听我的|别吵了|"
    r"还给(?:姐姐|昭昭|灿灿|笔)|笔还给|笔还了|还了没|"
    r"谁让你先|自己受着"
)
_RE_PARENT_THIN_WATCH = re.compile(
    r"^你们闹吧，?我看着[！。]?$|"
    r"闹吧.{0,12}看着|我在.{0,6}看着|看着呢"
)
_RE_K_PRESS_WIN = re.compile(r"还不哭|活该|看你还|我继续|再闹我|继续挠")
_RE_K_MIRROR_STALE = re.compile(r"不理你|谁怕谁")
_RE_POST_PRESS_KEEP = re.compile(
    r"哭|告|妈妈|瞪|不服|不理|谁怕谁|管不了|劝不"
)
_RE_POST_PRESS_FILLER = re.compile(
    r"推你|来吵|再吼|偏要吼|还骂|更凶|再闹我就打|试试看"
)
# 与 quality._LIMP_SOFT_CLOSE_MARKERS 对齐的末句软收（K 勿末句落这些）
_LIMP_LAST_MARKERS = (
    "给你",
    "算了",
    "好吧",
    "好了好了",
    "行吧",
    "随你",
    "我不管",
    "不管了",
    "随便你",
    "那行",
    "行行行",
    "哼",
    "吃吧",
    "你赢",
)
_PUNCH_BEFORE_SOFT = (
    "不和好",
    "别管",
    "越劝越",
    "管不了",
    "谁怕谁",
    "僵持",
)
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
    r"非治你|非收拾你|今天非.{0,10}|"
    r"不服也得挨着|也得挨着|轮不到你.{0,4}说|"
    r"这茬我记下|记下了|我数三下|数三下|服软",
)
# 「越劝」应对劝架大人；对弟妹说「你越劝」属指代事故
_RE_YUEQUAN_TO_PEER = re.compile(r"你越劝|越劝我越打")
_RE_BITE_HAND_REPLY = re.compile(r"别咬我手|咬我的手|咬我手")
# 点题/分镜式宣告（抽象句式）
_RE_META_STALEMATE = re.compile(r"就僵着|僵着呗|谁先软谁输")
_RE_ACTION_NARR = re.compile(
    r"(?:我躲|我躲到|我跑到|我缩到).{0,8}|"
    r"我拧你耳朵|我拧你|"
    r"(?:松手[，,]?\s*)?叉着?腰|"
    r"按在沙发上|按你沙发上|抓着胳膊|按着(?:他|她|你)|"
    r"加码挠腰|加码挠|"
    r"故意挠你(?:痒痒)?|看我挠不挠|"
    r"我继续顶着(?:好不好)?|我手可没停(?:吧)?|"
    r"我蹬腿|我使劲蹬|使劲蹬|"
    r"我把你[，,]|我把你|"
    r"我挠你腋下|抽泣抹泪|不服气瞪你|还逼我哭|"
    r"挠他痒痒|不松手，看你|我叹口气|"
    r"按着我胳膊|我起不来|厨房都听见",
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


def _k_content_anchor(story: dict, prev_line: str = "") -> str:
    """从上一句 / key / conflict_core 抽 2 字实义锚，供末句挂接（非单篇词表）。"""
    skip = {
        "你们",
        "我们",
        "什么",
        "怎么",
        "一个",
        "这个",
        "那个",
        "不是",
        "就是",
        "可以",
        "已经",
        "真的",
        "不管",
        "不理",
        "继续",
        "妈妈",
        "爸爸",
        "昭昭",
        "灿灿",
        "兄妹",
        "姐弟",
        "无奈",
        "旁观",
        "扶额",
    }
    for src in (
        prev_line,
        str(story.get("key") or ""),
        str(story.get("conflict_core") or ""),
        str(story.get("scene_title") or ""),
    ):
        for m in re.finditer(r"[\u4e00-\u9fff]{2}", str(src or "")):
            tok = m.group(0)
            if tok in skip or tok[-1] in "了的吗呢吧啊呀嘛":
                continue
            return tok
    return ""


def _k_stalemate_last_line(story: dict, prev_line: str = "") -> str:
    """末句僵持：尽量挂前文/主题锚，避免「你服不服→我才不理你」脱节。"""
    anchor = _k_content_anchor(story, prev_line)
    if anchor:
        line = f"这{anchor}我才不理你！"
        if len(line) <= 24:
            return line
    return _KID_STALEMATE_LAST


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
    return _KID_STALEMATE_MID


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
                row[key] = "我才不理你"
        out.append(row)
    return out


def patch_k_parent_advise_fail(story: dict) -> list[str]:
    """大人劝失败须有「劝→失败」两拍：仅一句管不了太薄。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return notes
    mom_idxs = [
        i
        for i, item in enumerate(dialogue)
        if isinstance(item, dict)
        and str(item.get("speaker") or "").strip() in _PARENT_SPEAKERS
    ]
    if not mom_idxs:
        return notes
    has_try = False
    has_fail = False
    for i in mom_idxs:
        line = str(dialogue[i].get("line") or "")
        if re.search(r"别闹|别打|别吵|住手|分开|听我", line):
            has_try = True
        if RE_PARENT_FAIL.search(line) or "管不了" in line or "劝不了" in line:
            has_fail = True
    if has_try and has_fail:
        return notes
    # 末句家长改劝失败；其前插一句劝止（若尚无）
    last_i = mom_idxs[-1]
    if not has_fail:
        dialogue[last_i]["line"] = _PARENT_FAIL_LINE
        notes.append(f"K家长收束→劝失败[{last_i + 1}]")
    if not has_try:
        dialogue.insert(
            last_i,
            {"speaker": "妈妈", "line": "你们别闹了，快分开！"},
        )
        notes.append("K补劝止一拍")
        # 劝后孩子须顶一句，否则像旁白切镜
        insert_at = last_i + 1
        if insert_at < len(dialogue) and str(
            dialogue[insert_at].get("speaker") or ""
        ).strip() in _PARENT_SPEAKERS:
            dialogue.insert(
                insert_at,
                {"speaker": "灿灿", "line": "妈妈你别管，谁怕谁！"},
            )
            notes.append("K劝后补顶嘴")
    story["dialogue"] = dialogue
    return notes


def patch_k_strip_hard_win_close(story: dict) -> list[str]:
    """点题后禁写成夺回/结案胜利（笔归我了等），改僵持口吻。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    winner, _loser = _k_press_roles_from_core(
        str(story.get("conflict_core") or "")
    )
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != winner:
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        if re.search(r"笔归我了|拿回来了|东西归我|我赢了|算我赢|笔我拿回来|笔是我抢回来", line):
            item["line"] = "哼，再闹我也不怕！"
            notes.append(f"K硬胜利→僵持[{i + 1}]")
    return notes


def patch_k_dedupe_cry_and_defiance(story: dict) -> list[str]:
    """破功哭腔只留一次；哭后勿再堆败方「不怕/偏不让」。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    _winner, loser = _k_press_roles_from_core(
        str(story.get("conflict_core") or "")
    )
    cry_i = -1
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != loser:
            continue
        line = str(item.get("line") or "")
        if re.search(r"我哭了|眼泪|哇", line):
            cry_i = i
            break
    if cry_i < 0:
        return notes
    drop: set[int] = set()
    for i in range(cry_i + 1, len(dialogue)):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != loser:
            continue
        line = str(item.get("line") or "")
        if re.search(r"我哭了|眼泪都", line):
            drop.add(i)
            continue
        if re.search(r"我才不怕|偏不让步|我继续顶着", line):
            item["line"] = "哼，我不理你！"
            notes.append(f"K哭后不服改僵持[{i + 1}]")
    # 哭腔句内剥顶着/不怕尾巴
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != loser:
            continue
        line = str(item.get("line") or "")
        if not re.search(r"哭了|眼泪|哇", line):
            continue
        cleaned = re.sub(r"[，,]?\s*我继续顶着[^！？。!?]*", "", line)
        cleaned = re.sub(r"[，,]?\s*我才不怕[^！？。!?]*", "", cleaned)
        cleaned = cleaned.strip("，。！？ ")
        if cleaned and cleaned != line:
            if cleaned[-1] not in "？！。!?":
                cleaned = f"{cleaned}！"
            item["line"] = cleaned
            notes.append("K哭腔剥顶着")
    if drop:
        story["dialogue"] = [
            x for i, x in enumerate(dialogue) if i not in drop
        ]
        notes.append(f"K去重哭腔×{len(drop)}")
    return notes


def patch_k_ensure_press_climax(story: dict) -> list[str]:
    """主题含挠/逼哭时，正文须有可说的压制点题+败方破功，勿只剩追跑空喊。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    meta = " ".join(
        str(story.get(k) or "")
        for k in ("key", "conflict_core", "scene_title", "punchline_explain")
    )
    if not re.search(r"挠|逼哭|还不哭", meta):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return notes
    winner, loser = _k_press_roles_from_core(str(story.get("conflict_core") or ""))
    body = "".join(
        str(x.get("line") or "") for x in dialogue if isinstance(x, dict)
    )
    need_press = "还不哭" not in body and not re.search(r"继续挠|看你哭", body)
    need_tickle = "挠" not in body
    need_cry = not re.search(r"哭了|眼泪", body)
    need_gloat = not re.search(r"嘴硬|哭了还", body)
    # 已有破功但缺得意回扣：只在哭句后补嘴硬，勿整块重插
    if need_gloat and not need_cry and not need_press:
        cry_i = -1
        for i, item in enumerate(dialogue):
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "")
            if re.search(r"我哭了|哭给你看|眼泪", line):
                cry_i = i
        if cry_i >= 0:
            nxt = (
                dialogue[cry_i + 1]
                if cry_i + 1 < len(dialogue)
                else None
            )
            nxt_line = (
                str(nxt.get("line") or "") if isinstance(nxt, dict) else ""
            )
            if "嘴硬" not in nxt_line and "哭了还" not in nxt_line:
                dialogue.insert(
                    cry_i + 1,
                    {
                        "speaker": winner,
                        "line": "哭了还嘴硬？笔在我这儿！",
                    },
                )
                story["dialogue"] = dialogue
                notes.append("K补破功后嘴硬")
                return notes
    if not (need_press or need_tickle or need_cry):
        return notes
    # 插在家长劝失败前；无家长则插在末 3 句前
    insert_at = len(dialogue)
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() in _PARENT_SPEAKERS:
            insert_at = i
            break
    insert_at = max(4, min(insert_at, len(dialogue) - 2))
    block: list[dict] = []
    if need_tickle or need_press:
        block.append(
            {
                "speaker": winner,
                "line": "还不哭？我继续挠，看你服不服！",
            }
        )
    if need_cry or need_press:
        block.append(
            {
                "speaker": loser,
                "line": "哇，我哭了，你快松手啊！",
            }
        )
        block.append(
            {
                "speaker": winner,
                "line": "哭了还嘴硬？笔在我这儿！",
            }
        )
    if not block:
        return notes
    story["dialogue"] = dialogue[:insert_at] + block + dialogue[insert_at:]
    notes.append(f"K补压制破功{len(block)}句")
    return notes


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
            # 末句禁用「哼…」软收模板，避免观感无破功软收 -20
            if target == idxs[-1]:
                prev_line = ""
                if len(idxs) >= 2:
                    prev_i = idxs[-2]
                    prev_line = str(dialogue[prev_i].get("line") or "").strip()
                dialogue[target]["line"] = _k_stalemate_last_line(story, prev_line)
            else:
                dialogue[target]["line"] = _KID_STALEMATE_MID
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

    # 家长定责/劝还物 → 旁观看戏（勿套 H）
    for i in idxs:
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp not in _PARENT_SPEAKERS or not line:
            continue
        if _RE_PARENT_MEDIATE.search(line):
            item["line"] = _PARENT_FAIL_LINE
            notes.append(f"K家长劝和→劝失败[{i + 1}]")
        elif _RE_PARENT_THIN_WATCH.search(line):
            item["line"] = _PARENT_FAIL_LINE
            notes.append(f"K薄旁观→劝失败[{i + 1}]")

    # 末段孩子「还你」软收 → 僵持（即使带哼也要剥还物）
    for i in idxs[-4:]:
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp not in _KID_SPEAKERS or not line:
            continue
        if re.search(r"(?:笔)?还你|还给你", line):
            item["line"] = (
                _KID_STALEMATE_LAST if i == idxs[-1] else _KID_STALEMATE_MID
            )
            notes.append(f"K末段剥还你软收[{i + 1}]")

    # 末两句孩子对称「不理你」空喊：压制方改得意僵持，勿对等赌气
    winner = ""
    for i in idxs:
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if sp in _KID_SPEAKERS and _RE_K_PRESS_WIN.search(line):
            winner = sp
    if not winner:
        winner = "灿灿"
    mirror_idxs = [
        i
        for i in idxs[-3:]
        if isinstance(dialogue[i], dict)
        and str(dialogue[i].get("speaker") or "").strip() in _KID_SPEAKERS
        and _RE_K_MIRROR_STALE.search(str(dialogue[i].get("line") or ""))
    ]
    if len(mirror_idxs) >= 2:
        for i in mirror_idxs:
            sp = str(dialogue[i].get("speaker") or "").strip()
            if sp == winner:
                dialogue[i]["line"] = _KID_WIN_CLOSE
                notes.append(f"K对称空喊→赢家压制[{i + 1}]")
                break

    story["dialogue"] = dialogue
    return notes


def patch_k_fix_limp_soft_close(story: dict) -> list[str]:
    """末句若落 limp 软收且前文无破功锚，改成不带哼的僵持句。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    idxs = _dialogue_idxs(dialogue)
    if len(idxs) < 4:
        return notes
    last_i = idxs[-1]
    last_item = dialogue[last_i]
    if not isinstance(last_item, dict):
        return notes
    last = str(last_item.get("line") or "").strip()
    if not last:
        return notes
    limp = any(m in last for m in _LIMP_LAST_MARKERS)
    if not limp:
        return notes
    prev2 = "".join(
        str(dialogue[i].get("line") or "").strip()
        for i in idxs[-3:-1]
        if isinstance(dialogue[i], dict)
    )
    punched = any(m in prev2 for m in _PUNCH_BEFORE_SOFT) or any(
        m in last for m in _PUNCH_BEFORE_SOFT
    )
    if punched and not last.startswith("哼"):
        # 先破功再软收可留；但「哼」起笔仍易被审稿打成软塌，末句去掉
        return notes
    if punched and last.startswith("哼"):
        # 去哼留僵持语义
        cleaned = re.sub(r"^哼[，, ]*", "", last).strip()
        if cleaned and cleaned != last:
            last_item["line"] = cleaned
            notes.append(f"K末句去哼[{last_i + 1}]")
            story["dialogue"] = dialogue
            return notes
    sp = str(last_item.get("speaker") or "").strip()
    prev_line = ""
    if len(idxs) >= 2:
        prev_line = str(dialogue[idxs[-2]].get("line") or "").strip()
    replacement = _k_stalemate_last_line(story, prev_line)
    if sp not in _KID_SPEAKERS:
        # 找末段孩子句改
        for i in reversed(idxs[-4:]):
            item = dialogue[i]
            if not isinstance(item, dict):
                continue
            if str(item.get("speaker") or "").strip() in _KID_SPEAKERS:
                item["line"] = replacement
                notes.append(f"K末段软收→僵持[{i + 1}]")
                story["dialogue"] = dialogue
                return notes
        return notes
    last_item["line"] = replacement
    notes.append(f"K末句软收→僵持[{last_i + 1}]")
    story["dialogue"] = dialogue
    return notes


def patch_k_tail_anchor(story: dict) -> list[str]:
    """末 4 句若完全丢掉主题/冲突锚，末句挂回一层实义，防空喊互打收场。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    idxs = _dialogue_idxs(dialogue)
    if len(idxs) < 4:
        return notes
    anchor = _k_content_anchor(story)
    if not anchor:
        return notes
    tail = "".join(
        str(dialogue[i].get("line") or "")
        for i in idxs[-4:]
        if isinstance(dialogue[i], dict)
    )
    if anchor in tail:
        return notes
    # 末句孩子台词回扣锚点（不新增句，避免冲字数/交替）
    for i in reversed(idxs[-4:]):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() not in _KID_SPEAKERS:
            continue
        prev_line = ""
        pos = idxs.index(i)
        if pos > 0:
            prev_line = str(dialogue[idxs[pos - 1]].get("line") or "").strip()
        item["line"] = _k_stalemate_last_line(story, prev_line or anchor)
        notes.append(f"K末段回扣主题锚[{i + 1}:{anchor}]")
        story["dialogue"] = dialogue
        return notes
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
        # 仅尾挂成人腔：先剥尾巴，尽量保住现场气话
        soft = re.sub(
            r"[，,]?\s*(?:轮不到你说|说一不二|我数三下)[！？。!?]*",
            "",
            line,
        ).strip("，。 ")
        if soft and soft != line and not _RE_ADULT_THREAT.search(soft):
            if soft[-1] not in "！？!?":
                soft = f"{soft}！"
            item["line"] = soft
            notes.append(f"K成人腔剥尾[{i + 1}]")
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
    if len(kept) < 12:
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
    # 保 ≥12 句；字数过砍交给下游 boost，但勿一次砍到不可再生
    if len(kept) < 12:
        return notes
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )

    probe = dict(story)
    probe["dialogue"] = kept
    if dialogue_total_chars(probe) < DAILY_STORY_BODY_CHARS_MIN - 40:
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
            # 先剥嵌入的分镜词，尽量保住「还不哭」等可说点题
            cleaned = _RE_ACTION_NARR.sub("", new_line)
            cleaned = re.sub(r"[，,]{2,}", "，", cleaned).strip("，。！？ ")
            if cleaned and not _RE_ACTION_NARR.search(cleaned):
                new_line = cleaned
            else:
                parts = re.split(r"[！!?？]", new_line)
                kept: list[str] = []
                for part in parts:
                    p = part.strip("，, ")
                    if not p or _RE_ACTION_NARR.search(p):
                        continue
                    kept.append(p)
                if kept:
                    new_line = "！".join(kept) + "！"
                else:
                    new_line = "你别过来！" if sp == "昭昭" else "还不哭？你服不服！"
        # 「继续挠」偏指令：有还不哭时改成可说压迫
        if "还不哭" in new_line and re.search(r"继续挠|我挠你", new_line):
            new_line = "还不哭？看你能撑多久！"
        elif re.search(r"我继续挠", new_line):
            new_line = re.sub(
                r"[，,]?\s*我继续挠[^！？。!?]*",
                "",
                new_line,
            ).strip("，。 ") or "看你还敢不敢！"
        # 败方口中的施压动作：改成求饶
        if sp == "昭昭" and re.search(
            r"伸手挠|挠你腋下|挠你痒|看你松不松手",
            new_line,
        ):
            new_line = "放开我！别挠了！"
        # 剥旁白后残留「哇，！」类空标点
        new_line = re.sub(r"，\s*[！!?？]", "！", new_line)
        new_line = re.sub(r"[！?]{2,}", "！", new_line)
        new_line = re.sub(r"了{2,}", "了", new_line)
        if re.search(r"我把你|还跑啊了", new_line):
            new_line = "逮住你了！看你还跑不跑！"
        if new_line.startswith("呀！") or new_line.startswith("啊！"):
            new_line = new_line[2:].strip() or (
                "你再闹试试！" if sp == "灿灿" else "我才不怕你！"
            )
        # 追捕方说「别过来」属角色方向幻觉
        if sp == "灿灿" and re.search(r"你别过来|别过来", new_line):
            new_line = "你站住！把笔还我！"
        # 拽胳膊/别按我等姿态旁白
        if re.search(r"拽我胳膊|别按我|按着我肩膀|按着我干", new_line):
            new_line = (
                "放开我！别挠了！" if sp == "昭昭" else "逮住你了！看你还跑！"
            )
        if re.match(r"^[吧呀啊呢嘛，,\s]+", new_line) or new_line in {
            "啊！",
            "啊",
            "吧！",
            "呀！",
            "呢！",
        }:
            new_line = "你再闹试试！" if sp == "灿灿" else "哼，我不理你！"
        # 纯语气/空喊：内容字过少
        bare = re.sub(r"[！？。!?，,\s哈呵哦嗯啊呀吧呢嘛啦]", "", new_line)
        if len(bare) < 2:
            new_line = "你再闹试试！" if sp == "灿灿" else "我才不怕你！"
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
        "拿桶",
        "扔笔",
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
        new_line = re.sub(r"这记仇我才", "我才", new_line)
        new_line = re.sub(r"这还不?我才", "我才", new_line)
        new_line = re.sub(r"这你(?:等|还)我才", "我才", new_line)
        new_line = re.sub(r"这笔还我才", "我才", new_line)
        new_line = re.sub(r"(?:这)?我才我才", "我才", new_line)
        new_line = re.sub(r"这那你我才", "我才", new_line)
        new_line = re.sub(r"这那你", "那你", new_line)
        new_line = re.sub(r"这别闹我才", "我才", new_line)
        new_line = re.sub(r"这我瞪我才", "我才", new_line)
        new_line = re.sub(r"这我瞪", "我", new_line)
        new_line = re.sub(r"这我管我才", "我才", new_line)
        new_line = re.sub(r"这我管", "", new_line)
        new_line = re.sub(r"啦呀", "啦", new_line)
        new_line = re.sub(r"(?:哈){2,}…+", "哈哈", new_line)
        new_line = re.sub(r"哇——+", "哇，", new_line)
        new_line = re.sub(r"这再闹我才", "我才", new_line)
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


def patch_k_trim_post_press_filler(story: dict) -> list[str]:
    """压制点题（还不哭等）后勿再堆推/吼/骂空打，直接进不服→劝失败→僵持。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 12:
        return notes
    punch_i = -1
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if "还不哭" in line or (
            _RE_K_PRESS_WIN.search(line)
            and str(item.get("speaker") or "").strip() in _KID_SPEAKERS
        ):
            punch_i = i
            break
    if punch_i < 0 or punch_i >= len(dialogue) - 3:
        return notes
    after_items = dialogue[punch_i + 1 :]
    drop_idxs: list[int] = []
    for j, item in enumerate(after_items):
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        abs_i = punch_i + 1 + j
        if sp in _PARENT_SPEAKERS:
            continue
        if not line:
            continue
        if _RE_POST_PRESS_KEEP.search(line) and not _RE_POST_PRESS_FILLER.search(
            line
        ):
            continue
        if _RE_POST_PRESS_FILLER.search(line):
            drop_idxs.append(abs_i)
            continue
        if _RE_K_MIRROR_STALE.search(line) or re.search(r"哭|告|疼|松手", line):
            continue
        drop_idxs.append(abs_i)
    # 少许垫打可留；删多了会不够 12 句/240 字
    if len(drop_idxs) < 3:
        return notes
    keep_min = 12
    max_drop = max(0, len(dialogue) - keep_min)
    drop_idxs = drop_idxs[:max_drop]
    if not drop_idxs:
        return notes
    drop_set = set(drop_idxs)
    kept = [x for i, x in enumerate(dialogue) if i not in drop_set]
    if len(kept) >= keep_min:
        story["dialogue"] = kept
        notes.append(f"K剥点题后空打{len(drop_idxs)}句")
    return notes


def patch_k_bind_press_roles(story: dict) -> list[str]:
    """按 conflict 锁压制方/败方：含「还不哭/继续挠」须是压制方，哭/别挠须是败方。

    防止连说改 speaker 把姐弟角色拧反。
    """
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    core = str(story.get("conflict_core") or "")
    winner, loser = _k_press_roles_from_core(core)
    changed = 0
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp not in _KID_SPEAKERS:
            continue
        line = str(item.get("line") or "")
        if re.search(
            r"还不哭|继续挠|我挠你|挠到你|看你哭|看我挠|按沙发|交笔不杀|认输为止",
            line,
        ):
            if sp != winner:
                item["speaker"] = winner
                changed += 1
        elif re.search(
            r"别挠|松手啊|我哭了|笑岔|再挠我|我求你|快松手|眼泪掉|放开我",
            line,
        ):
            if sp != loser:
                item["speaker"] = loser
                changed += 1
    if changed:
        notes.append(f"K压制角色归位{changed}句")
        story["dialogue"] = dialogue
    return notes


def patch_k_fix_consecutive_keep_press(story: dict) -> list[str]:
    """角色归位后的同人连说：插入对方短句桥，勿再改压制/败方 speaker。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    core = str(story.get("conflict_core") or "")
    winner, loser = _k_press_roles_from_core(core)
    out: list = []
    inserted = 0
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        sp = str(row.get("speaker") or "").strip()
        line = str(row.get("line") or "").strip()
        if (
            out
            and sp in _KID_SPEAKERS
            and str(out[-1].get("speaker") or "").strip() == sp
        ):
            other = loser if sp == winner else winner
            bridge = (
                "放开我！别挠了！"
                if other == loser
                else "还不哭？你服不服！"
            )
            out.append({"speaker": other, "line": bridge})
            inserted += 1
        out.append(row)
    if inserted:
        story["dialogue"] = out
        notes.append(f"K连说插桥{inserted}处")
    return notes


def _k_advise_fail_mid_block(story: dict) -> list[dict]:
    """劝止→冲突续行→顶嘴→劝失败→冷战（mom_max=2）。"""
    winner, loser = _k_press_roles_from_core(
        str(story.get("conflict_core") or "")
    )
    return [
        {"speaker": "妈妈", "line": _PARENT_ADVISE_LINE},
        {"speaker": loser, "line": "疼！快松手啊！"},
        {"speaker": winner, "line": _KID_TOP_LINE},
        {"speaker": "妈妈", "line": _PARENT_FAIL_LINE},
        {"speaker": loser, "line": "哼，我就不理你了！"},
        {"speaker": winner, "line": "不理就不理，谁稀罕！"},
    ]


def patch_k_pin_advise_fail_close(story: dict) -> list[str]:
    """导出/封口共用：钉死劝失败中段冲突续行。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    parent_i = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "").strip() in _PARENT_SPEAKERS
        ),
        -1,
    )
    if parent_i < 4:
        return notes
    head = [dict(x) for x in dialogue[:parent_i] if isinstance(x, dict)]
    story["dialogue"] = head + _k_advise_fail_mid_block(story)
    notes.append("K劝失败冲突续行钉死")
    return notes


def patch_k_seal_after_parent_fail(story: dict) -> list[str]:
    """劝止→冲突续行→顶嘴→劝失败后封口；中间勿再灌互顶垫句。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return notes
    advise_i = -1
    fail_i = -1
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() not in _PARENT_SPEAKERS:
            continue
        line = str(item.get("line") or "")
        if advise_i < 0 and re.search(r"别闹|别打|别吵|住手|分开|听我", line):
            advise_i = i
        if RE_PARENT_FAIL.search(line) or "管不了" in line or "劝不了" in line or "劝不动" in line:
            fail_i = i
    if fail_i < 0:
        return notes
    from app.services.daily_story.prompts import (
        DAILY_STORY_BODY_CHARS_MIN,
        dialogue_total_chars,
    )

    if advise_i >= 0 and fail_i > advise_i:
        winner, loser = _k_press_roles_from_core(
            str(story.get("conflict_core") or "")
        )
        between = dialogue[advise_i + 1 : fail_i]
        resume = None
        for x in between:
            if not isinstance(x, dict):
                continue
            if str(x.get("speaker") or "").strip() not in _KID_SPEAKERS:
                continue
            line = str(x.get("line") or "").strip()
            if _RE_PURE_MOM_TOP.search(line):
                continue
            if _RE_CONFLICT_RESUME.search(line):
                resume = dict(x)
                break
        if resume is None:
            resume = {"speaker": loser, "line": "疼！快松手啊！"}
        kid_top = {"speaker": winner, "line": _KID_TOP_LINE}
        # 劝失败后只留冷战僵持，勿再叫阵
        after = [dict(x) for x in _KID_STALEMATE_AFTER]
        after[0]["speaker"] = loser
        after[1]["speaker"] = winner
        fail_row = dict(dialogue[fail_i])
        fail_row["line"] = _PARENT_FAIL_LINE
        # 保留劝止前全文，但剥点题/破功后的互顶空喊
        head = list(dialogue[:advise_i])
        climax_i = -1
        # 以末次破功（哭）为峰；无哭再退到末次「还不哭」
        for i, item in enumerate(head):
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "")
            if re.search(r"我哭了|眼泪|哭给你看", line):
                climax_i = i
        if climax_i < 0:
            for i, item in enumerate(head):
                if not isinstance(item, dict):
                    continue
                if "还不哭" in str(item.get("line") or ""):
                    climax_i = i
        if climax_i >= 0:
            cry_item = dict(head[climax_i])
            pre_raw = [
                dict(x)
                for x in head[:climax_i]
                if isinstance(x, dict)
            ]
            # 哭前铺垫：去掉提前嘴硬；点题/逮住后追抢回潮丢掉；点题本身稍后统一钉
            cleaned: list[dict] = []
            seen_press = False
            seen_catch = False
            for x in pre_raw:
                line = str(x.get("line") or "")
                if re.search(
                    r"逮住|逮着|按住你|按着你|追到你了|抓到你",
                    line,
                ):
                    seen_catch = True
                if "还不哭" in line:
                    seen_press = True
                    continue
                if re.search(r"嘴硬|哭了还|笔在我这儿", line):
                    continue
                if (seen_press or seen_catch) and re.search(
                    r"追不上|略略略|满屋子跑|这笔就是我的|"
                    r"拿不回去|还跑啊|不服也白搭|我不服|"
                    r"换个理由|再顶你|你别过来",
                    line,
                ):
                    continue
                cleaned.append(x)
            press_row = {
                "speaker": winner,
                "line": "还不哭？看你能撑多久！",
            }
            # 统一用干净压迫句，勿带回成人腔/垫尾巴
            kept_head = cleaned + [press_row, cry_item]
            kept_head.append(
                {
                    "speaker": winner,
                    "line": "哭了还嘴硬？笔在我这儿！",
                }
            )
            kept_head.append({"speaker": loser, "line": "呜，你欺负人！"})
            head = kept_head
        # 劝止槽钉死（mom 上限 2：劝止+失败；中间=冲突续行+顶嘴）
        advise_row = dict(dialogue[advise_i])
        advise_row["line"] = _PARENT_ADVISE_LINE
        candidate = (
            head
            + [advise_row, resume, kid_top, fail_row]
            + after
        )
        dropped = len(dialogue) - len(candidate)
        story["dialogue"] = candidate
        if dropped > 0:
            notes.append(f"K劝失败段封口去{dropped}句")
        else:
            notes.append("K劝失败后钉僵持尾")
        return notes

    after = dialogue[fail_i + 1 :]
    kid_after = [
        x
        for x in after
        if isinstance(x, dict)
        and str(x.get("speaker") or "").strip() in _KID_SPEAKERS
    ]
    if len(kid_after) <= 2:
        return notes
    kept_tail = kid_after[:2]
    last = kept_tail[-1]
    if not RE_STALEMATE.search(str(last.get("line") or "")):
        last["line"] = _KID_STALEMATE_LAST
    candidate = dialogue[: fail_i + 1] + kept_tail
    probe = {"dialogue": candidate}
    if dialogue_total_chars(probe) < DAILY_STORY_BODY_CHARS_MIN - 20:
        return notes
    dropped = len(kid_after) - len(kept_tail)
    if dropped <= 0:
        return notes
    story["dialogue"] = candidate
    notes.append(f"K劝失败后封口去{dropped}句")
    return notes


def patch_k_loser_monotonic(story: dict) -> list[str]:
    """败方状态单向：挠后/哭后不得回勇挑衅（抽象，不绑单篇）。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    _, loser = _k_press_roles_from_core(str(story.get("conflict_core") or ""))
    seen_tickle = False
    seen_cry = False
    changed = 0
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        if re.search(r"别挠|挠了|痒|还不哭", line):
            seen_tickle = True
        if re.search(r"我哭了|哭给你|眼泪", line):
            seen_cry = True
        if sp != loser or not line:
            continue
        if (seen_tickle or seen_cry) and _RE_LOSER_POST_CRY_DEFIANCE.search(line):
            item["line"] = (
                "呜，你欺负人！"
                if seen_cry
                else "放开我！别挠了！"
            )
            changed += 1
    if changed:
        notes.append(f"K败方单向×{changed}")
    return notes


def patch_k_ensure_advise_two_slots(story: dict) -> list[str]:
    """妈妈劝止槽+失败槽；中间至少一句姐弟顶嘴（mom_max=2）。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 10:
        return notes
    # 找现有家长句
    parent_idxs = [
        i
        for i, x in enumerate(dialogue)
        if isinstance(x, dict)
        and str(x.get("speaker") or "").strip() in _PARENT_SPEAKERS
    ]
    if not parent_idxs:
        # 无家长：在末 2 句前插入劝失败中段（含冲突续行）
        insert_at = max(4, len(dialogue) - 2)
        block = _k_advise_fail_mid_block(story)
        story["dialogue"] = dialogue[:insert_at] + block + dialogue[insert_at:]
        notes.append("K补劝失败两槽")
        return notes
    # 规范：最后两句家长必须是劝止→（中间孩子）→失败；若只有一句则拆
    # 交给 seal 封口；这里只保证失败句语义与劝止语义分离
    for i in parent_idxs:
        item = dialogue[i]
        line = str(item.get("line") or "")
        if RE_PARENT_FAIL.search(line) or "管不了" in line:
            item["line"] = _PARENT_FAIL_LINE
        elif re.search(r"别闹|分开|别打|别吵", line):
            item["line"] = _PARENT_ADVISE_LINE
    story["dialogue"] = dialogue
    notes.append("K劝失败两槽语义钉死")
    return notes


def patch_k_force_climax_before_parent(story: dict) -> list[str]:
    """劝止前钉死：还不哭→哭→嘴硬→呜；并剥逮住后的追抢回潮。"""
    notes: list[str] = []
    if not _is_k(story):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 8:
        return notes
    parent_i = next(
        (
            i
            for i, x in enumerate(dialogue)
            if isinstance(x, dict)
            and str(x.get("speaker") or "").strip() in _PARENT_SPEAKERS
        ),
        -1,
    )
    if parent_i < 6:
        return notes
    head = [dict(x) for x in dialogue[:parent_i] if isinstance(x, dict)]
    tail = [dict(x) for x in dialogue[parent_i:] if isinstance(x, dict)]
    cleaned: list[dict] = []
    seen_catch = False
    seen_tickle = False
    for x in head:
        sp = str(x.get("speaker") or "").strip()
        line = str(x.get("line") or "")
        if re.search(r"逮住|逮着|按住你|按着你|追到你了|抓到你", line):
            seen_catch = True
        if re.search(r"别挠|挠了|痒", line):
            seen_tickle = True
        if re.search(r"换个理由|再顶你|不收拾你|服软", line):
            continue
        if (seen_catch or seen_tickle) and re.search(
            r"追不上|略略略|满屋子跑|这笔就是我的|拿不回去|"
            r"抢我笔还嘴硬",
            line,
        ):
            continue
        # 挠后败方回勇挑衅：丢掉（单向）
        if seen_tickle and sp in _KID_SPEAKERS and _RE_LOSER_POST_CRY_DEFIANCE.search(
            line
        ):
            # 保留求饶类
            if not re.search(r"放开|别挠|松手|疼|痒", line):
                continue
        # 旧压迫/破功先剥，后面统一钉
        if re.search(
            r"还不哭|我哭了|嘴硬|哭了还|笔在我这儿|呜，你欺负人|"
            r"轮不到你",
            line,
        ):
            continue
        cleaned.append(x)
    # 挠拍不足时补一轮可说互顶（专家：差字加有效冲突拍）
    has_tickle = any(
        re.search(r"别挠|挠了|痒", str(x.get("line") or ""))
        for x in cleaned
    )
    if not has_tickle:
        cleaned.extend(
            [
                {"speaker": "灿灿", "line": "抢笔就该被挠！看你还跑不跑！"},
                {"speaker": "昭昭", "line": "放开我！别挠了！"},
            ]
        )
    triad = [
        {"speaker": "灿灿", "line": "还不哭？看你能撑多久！"},
        {"speaker": "昭昭", "line": "哇，我哭了，你快松手啊！"},
        {"speaker": "灿灿", "line": "哭了还嘴硬？笔在我这儿！"},
        {"speaker": "昭昭", "line": "呜，你欺负人！"},
    ]
    story["dialogue"] = cleaned + triad + tail
    notes.append("K劝止前钉破功四拍")
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
    notes.extend(patch_k_loser_monotonic(story))
    notes.extend(patch_k_dedupe_near_lines(story))
    notes.extend(patch_k_break_same_speaker_run(story))
    notes.extend(patch_k_hand_pain_speech(story))
    notes.extend(patch_k_strip_adult_threat(story))  # 手疼句被垫回说一不二时再剥
    notes.extend(patch_k_strip_orphan_reply(story))
    notes.extend(patch_k_break_same_speaker_run(story))
    notes.extend(patch_k_trim_post_press_filler(story))
    notes.extend(patch_k_ensure_press_climax(story))
    notes.extend(patch_k_dedupe_cry_and_defiance(story))
    notes.extend(patch_k_strip_hard_win_close(story))
    notes.extend(patch_k_parent_advise_fail(story))
    notes.extend(patch_k_ensure_advise_two_slots(story))
    notes.extend(patch_k_close_stalemate(story))
    notes.extend(patch_k_fix_limp_soft_close(story))
    notes.extend(patch_k_tail_anchor(story))
    notes.extend(patch_k_trim_empty_tail(story))
    # 回扣锚点后再剥一次垫字头，避免「这我才我才」
    notes.extend(patch_k_strip_pad_junk(story))
    notes.extend(patch_k_bind_press_roles(story))
    notes.extend(patch_k_fix_consecutive_keep_press(story))
    notes.extend(patch_k_seal_after_parent_fail(story))
    notes.extend(patch_k_force_climax_before_parent(story))
    notes.extend(patch_k_loser_monotonic(story))
    notes.extend(patch_k_ensure_advise_two_slots(story))
    notes.extend(patch_k_pin_advise_fail_close(story))
    return notes
