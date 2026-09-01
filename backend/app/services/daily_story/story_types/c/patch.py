"""C 类正文本地修稿（仅确定性结构）。

加规则红线（新增前必读）：
- patch 只做**类型级**结构修补：删句/去重/改 speaker/引话接地。
- 禁止绑定具体 theme 的规则（按主题关键词分支改写台词）。
  内容不合格一律交 LLM 重试，不在本地按主题造句。
"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.c.line import C_WHOLE_ITEM_PATCH_CHAR_DEFICIT
from app.services.daily_story.story_types.quality import (
    RE_BOOMERANG_RULE,
    RE_C_STUBBORN_LAST,
)

# 末句嘴硬软收词（可在句首，可带 …… 前缀）
_RE_C_SOFT_HEAD = re.compile(
    r"^[……。！？\s]*(哼|行吧|随便|算了|好吧|认栽|服了|算了算)[，,。！？…]?",
)

# 正文首句「我早就不X了/我早好了/我早没事」顶回式反驳前缀——
# 语义是反驳前文存在的指控（你…疼/病/牙），无指控即悬空自证（用户 2026-08-09 v23 抓）。
# 只匹配「我早…(不X)了」否定恢复与「好了/没事」，不碰「我早就拿到了」这类占有宣告。
_RE_C_REBUT_PREFIX = re.compile(
    r"^(?:我早(?:就?不[^，。！？]{1,6}了|就?好了|没事(?:了)?))[，,]"
)
# 开场第 2 句的「对方弱项」指控（你上次…/你…疼病牙肚子…），是「我早就不X了」的合法对象
_RE_C_WEAK_POINT_ACCUSATION = re.compile(
    r"你(?:上次|之前|才|又|还没|牙齿|总是|只会)?[^，。！？]{0,8}"
    r"(?:疼|病|牙|肚子|酸|困|感冒|难受|咳|烫|摔|伤)"
)


from app.services.daily_story.story_types.c.validate import (
    _RE_RELEASE_RITUAL,
    _RE_WHOLE_ITEM_ANCHOR,
)

# 整件物·近失整句 repair（2026-08-21 GPT P0）：clause 级改写，不做 token 替换。
# 只处理 release/数三/松手判据等已知病灶；冲突动作（你手拿开）不碰。
_RE_WI_COUNT_RULE = re.compile(
    r"数(?:到|满)?[一二三四五六七八九十\d]+|我数[一二三四五六七八九十\d]+下",
)
_RE_WI_RELEASE_CRITERION = re.compile(
    r"(?:还没|没有|尚未|仍).{0,8}(?:松手|放手|撒手|松开|手松)|"
    r"手松(?:了|的)|"
    r"(?:松手|放手|撒手).{0,6}(?:不算|才算|归|该|赢|算)|"
    r"(?:你|快).{0,3}(?:松手|放手|撒手)",
)
# (pattern, replacement) — replacement 可为 str 或 callable(match, line) -> str
_WHOLE_ITEM_CLAUSE_REPAIRS: tuple[
    tuple[re.Pattern[str], str | re.Pattern[str]],
    ...,
] = (
    (
        re.compile(
            r"可你抢的时候我(?:还没|没有|尚未)(?:松手|放手|撒手|松开|手松)了呢?",
        ),
        "可你抢的时候我还攥在手里呢",
    ),
    (
        re.compile(
            r"你那是抢，不算拿到，我(?:还没|没有|尚未)(?:松手|放手|撒手|松开|手松)了呢?",
        ),
        "你那是抢，不算拿到，我还攥在手里呢",
    ),
    (
        re.compile(r"你手松了，(.{0,6})归我"),
        r"已经到我怀里，\1归我",
    ),
    (
        re.compile(r"手松了，(.{0,6})归"),
        r"已经到我怀里，\1归",
    ),
    (
        re.compile(r"我先(?:攥|抢|拿)[^，。！？]{0,8}，你松手"),
        "我先攥在手里了，你还想抢",
    ),
    (
        re.compile(r"我先抢到的，[^，。！？]{0,8}你松手"),
        "我先抢到的，你还攥着角呢",
    ),
    (
        re.compile(r"我先抱的，你松手[。！？]?"),
        "我先抱的，你还想抢！",
    ),
    (
        re.compile(r"，你松手[。！？]?$"),
        "，你还想抢！",
    ),
    (
        re.compile(r"你松手[！。！？]"),
        "你还想抢！",
    ),
    (
        re.compile(r"碰不算"),
        "攥着不算",
    ),
    (
        re.compile(r"摸不算"),
        "攥着不算",
    ),
    (
        re.compile(r"搭着边"),
        "捏着边",
    ),
    (
        re.compile(r"搭个边儿"),
        "捏个边儿",
    ),
    (
        re.compile(r"你只搭"),
        "你只捏",
    ),
    (
        re.compile(r"谁先松手谁"),
        "谁先攥在手里谁",
    ),
    (
        re.compile(r"得看谁先松手"),
        "得看谁先环住",
    ),
    (
        re.compile(r"你松手了，我赢"),
        "你还攥着角，我赢",
    ),
    (
        re.compile(r"好，我数三下，谁先抢到归谁了吧?"),
        "好，谁先抢到，谁就归谁！",
    ),
    (
        re.compile(r"好，我数[^，。！？]{0,8}，谁先(?:抢到|拿到)[^。！？]*"),
        "好，谁先抢到，谁就归谁！",
    ),
    (
        re.compile(r"行，(?:我)?数[^，。！？]{0,10}，谁先(?:抢到|拿到)[^。！？]*"),
        "行，谁先抢到，谁就归谁！",
    ),
    (
        re.compile(r"我数三下，你(?:松手|放手)(?:才算|才算你)[^。！？]*"),
        "你攥在手里才算你赢！",
    ),
    (
        re.compile(r"我数三下，你(?:松手|放手)[^。！？]*"),
        "你攥在手里才算你赢！",
    ),
)


def _repair_whole_item_count_line(line: str) -> str | None:
    """数到三/数三下赛制 → 占有判据整句。"""
    if not _RE_WI_COUNT_RULE.search(line):
        return None
    if _RE_RELEASE_RITUAL.search(line):
        return "行，谁先抢到，谁就归谁！"
    if re.search(r"谁先(?:抢到|拿到|攥)", line):
        return "好，谁先抢到，谁就归谁！"
    if re.search(r"(?:松手|放手|一起松)", line):
        return "行，谁先抢到，谁就归谁！"
    return None


def patch_c_whole_item_near_miss(story: dict) -> list[str]:
    """整件物 C 类：validate 前近失整句 repair（松手判据/数三赛制 → 占有系）。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes
    anchor = (
        str(story.get("theme") or story.get("_theme") or "")
        + str(story.get("conflict_core") or "")
        + str(story.get("setting") or "")
    )
    if not _RE_WHOLE_ITEM_ANCHOR.search(anchor):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes

    def _apply(line: str) -> tuple[str, bool]:
        new_line = line
        changed = False
        if _RE_WI_COUNT_RULE.search(new_line) or _RE_RELEASE_RITUAL.search(new_line):
            fixed = _repair_whole_item_count_line(new_line)
            if fixed and fixed != new_line:
                return fixed, True
        for pat, repl in _WHOLE_ITEM_CLAUSE_REPAIRS:
            if pat.search(new_line):
                subbed = pat.sub(repl, new_line)  # type: ignore[union-attr]
                if subbed != new_line:
                    new_line = subbed
                    changed = True
        if _RE_WI_RELEASE_CRITERION.search(new_line):
            subbed = re.sub(
                r"(?:还没|没有|尚未|仍).{0,8}(?:松手|放手|撒手|松开|手松)",
                "还攥在手里",
                new_line,
            )
            if subbed != new_line:
                new_line = subbed
                changed = True
            subbed2 = re.sub(
                r"手松(?:了|的)",
                "已经到我怀里",
                new_line,
            )
            if subbed2 != new_line:
                new_line = subbed2
                changed = True
        return new_line, changed

    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if not line:
            continue
        new_line, changed = _apply(line)
        if changed and new_line != line:
            item["line"] = new_line
            notes.append(f"整件物近失repair[{i}]")
    return notes


# 整件物题：弱接触词本地替换成占有系（类型级结构修补，不绑主题词表）
_RE_WHOLE_ITEM_CONTACT = re.compile(
    r"够(?:不着|不到|到|着|上|一下|得着)?|"
    r"碰(?:到|着|上|的)?|摸(?:到|着|上|的)?|搭(?:到|着|上|的)?|"
    r"触(?:到|着|上)?|沾(?:到|着|上)?|挨(?:到|着|上)?|"
    r"靠(?:着|在)?|贴(?:着|到|上)?|"
    r"环住|够着|悬(?:着|空)?|"
    r"(?:才|还)?(?:抢|碰|摸)?(?:到|着)?边(?:呢|啊|呀|嘛)?",
)
_WHOLE_ITEM_CONTACT_REPL: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"挨着[^。！？]{0,8}不算"), "光抱着不行"),
    (re.compile(r"靠着[^。！？]{0,8}不算"), "光抱着不行"),
    (re.compile(r"贴着[^。！？]{0,8}不算"), "光抱着不行"),
    (re.compile(r"碰到[^。！？]{0,8}不算"), "光抱着不行"),
    (re.compile(r"够不着"), "抢不到"),
    (re.compile(r"够不到"), "抢不到"),
    (re.compile(r"够着"), "抢到"),
    (re.compile(r"够到"), "抢到"),
    (re.compile(r"我挨着"), "我抱住"),
    (re.compile(r"挨着"), "抱住"),
    (re.compile(r"靠着"), "抱住"),
    (re.compile(r"贴着"), "抱住"),
    (re.compile(r"碰到"), "抢到"),
    (re.compile(r"摸到"), "拿到"),
    (re.compile(r"搭到"), "抢到"),
    (re.compile(r"触到"), "按住"),
    (re.compile(r"沾到"), "按住"),
    (re.compile(r"挨到"), "按住"),
    (re.compile(r"环住"), "圈住"),
    (re.compile(r"手还悬着"), "手还空着"),
    (re.compile(r"还悬着"), "还空着"),
    (re.compile(r"抢到边"), "抢到"),
    (re.compile(r"碰到边"), "抢到"),
    (re.compile(r"摸到边"), "拿到"),
    (re.compile(r"我手都碰"), "我早抢"),
    (re.compile(r"才刚碰"), "才刚抢"),
)
_WHOLE_ITEM_CONTACT_MAX_ROUNDS = 5

# 句尾连续语气词（Run1 病句尾；专家 P2 兜底）
_RE_WI_DOUBLE_TAIL_PARTICLE = re.compile(
    r"(呢呀|嘛呀|着呀|哦呀|呀嘛|了呢呀|了吗呀)[！。！？…]?$",
)


def _sanitize_whole_item_contact_line(line: str) -> str:
    new_line = line
    for pat, repl in _WHOLE_ITEM_CONTACT_REPL:
        new_line = pat.sub(repl, new_line)
    return new_line


# 整件物·垫字语气（专家 P1：你听着呀/好不好呀）
_RE_WI_FILLER_PHRASE = re.compile(
    r"你听着呀|好不好呀|真的呀|才刚",
)
_WI_FILLER_REPL: tuple[tuple[str, str], ...] = (
    ("你听着呀", ""),
    ("，你听着呀", ""),
    ("你听着，", ""),
    ("好不好呀", "好不好"),
    ("真的呀", "真的"),
    ("才刚", "刚"),
)


def patch_c_whole_item_filler(story: dict) -> list[str]:
    """整件物：删「你听着呀/好不好呀」等垫字。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes
    anchor = (
        str(story.get("theme") or story.get("_theme") or "")
        + str(story.get("conflict_core") or "")
        + str(story.get("setting") or "")
    )
    if not _RE_WHOLE_ITEM_ANCHOR.search(anchor):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        new_line = line
        for old, repl in _WI_FILLER_REPL:
            new_line = new_line.replace(old, repl)
        new_line = re.sub(r"[，,]{2,}", "，", new_line)
        new_line = re.sub(r"^[，,]", "", new_line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"整件物垫字[{i}]")
    return notes


def patch_c_whole_item_tone_tail(story: dict) -> list[str]:
    """整件物：句尾连续语气词「呢呀/嘛呀」删成单语气词。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes
    anchor = (
        str(story.get("theme") or story.get("_theme") or "")
        + str(story.get("conflict_core") or "")
        + str(story.get("setting") or "")
    )
    if not _RE_WHOLE_ITEM_ANCHOR.search(anchor):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        m = _RE_WI_DOUBLE_TAIL_PARTICLE.search(line)
        if not m:
            continue
        bad = m.group(1)
        fixed_particle = bad[:-1]
        new_line = line[: m.start()] + fixed_particle + line[m.end() :]
        if new_line != line:
            item["line"] = new_line
            notes.append(f"整件物语气尾[{i}]")
    return notes


def patch_c_whole_item_contact(story: dict) -> list[str]:
    """整件争点稿：弱接触词替换成占有系动词，循环扫描至干净或达上限。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes
    anchor = (
        str(story.get("theme") or story.get("_theme") or "")
        + str(story.get("conflict_core") or "")
        + str(story.get("setting") or "")
    )
    if not _RE_WHOLE_ITEM_ANCHOR.search(anchor):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    for _round in range(_WHOLE_ITEM_CONTACT_MAX_ROUNDS):
        changed = False
        for i, item in enumerate(dialogue):
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "")
            if not _RE_WHOLE_ITEM_CONTACT.search(line):
                continue
            new_line = _sanitize_whole_item_contact_line(line)
            if new_line != line:
                item["line"] = new_line
                notes.append(f"整件物弱接触→占有[{i}]")
                changed = True
        if not changed:
            break
    return notes


def patch_c_stray_rebuttal(story: dict) -> list[str]:
    """正文首句「我早就不X了」须有前文指控，无指控删前缀（用户 2026-08-09 v23 抓）。

    C 类第 3 句（正文第 1 句）用「我早就不疼了/我早好了」顶回式反驳，只在前文
    第 2 句真说过「你…疼/病/牙」类弱项指控时成立；若开场理由换成别的类型
    （「上次我让了你」=先后欠账），模型照抄合规示范句式会把「我早就不疼了」
    顶回一个没人说过的理由——悬空自证。本地删前缀，保留后半段抛占有判据
    （line.py 允许未动手正文首句「顶回理由或抛判据」，删后仍合法）。
    只做类型级结构修补，不绑定具体 theme（patch 红线）。
    """
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 3:
        return notes
    second = dialogue[1]
    third = dialogue[2]
    if not isinstance(second, dict) or not isinstance(third, dict):
        return notes
    line = str(third.get("line") or "").strip()
    if not line:
        return notes
    m = _RE_C_REBUT_PREFIX.match(line)
    if not m:
        return notes
    # 前文第 2 句有弱项指控 → 顶回有对象，合法
    if _RE_C_WEAK_POINT_ACCUSATION.search(str(second.get("line") or "")):
        return notes
    rest = line[m.end():].strip()
    if not rest or len(rest) < 4:
        return notes  # 删完只剩光杆/太短，不动（交给 LLM 重试）
    from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN

    total = sum(len(str(d.get("line") or "")) for d in dialogue)
    if total - (len(line) - len(rest)) < DAILY_STORY_BODY_CHARS_MIN:
        return notes  # 别把正文削到硬卡下限以下
    third["line"] = rest
    notes.append("C正文首句无前文自证删前缀")
    return notes


def _c_default_stubborn_tail(soft: str, *, whole_item: bool = False) -> str:
    """软收词后补一句通用嘴硬话（用户定 2026-08-08：禁光杆叹词收尾）。

    只做**通用**收束，不绑定具体 theme（patch 红线：禁止按主题造句）；
    整件物题优先「你赢规则不算赢我」（2026-08-21 专家+幽默 regex）；
    其它题「明天我一定赢过你」对任何赛规都成立。
    """
    if whole_item:
        if soft in ("哼", "切", "嘁"):
            return "哼，你赢规则不算赢我！"
        return "行吧，你赢规则不算赢我！"
    if soft in ("哼", "切", "嘁"):
        return "哼，明天我一定赢过你！"
    return "行吧，算你手快！"


def _c_whole_item_story(story: dict) -> bool:
    anchor = (
        str(story.get("theme") or story.get("_theme") or "")
        + str(story.get("conflict_core") or "")
        + str(story.get("setting") or "")
    )
    return bool(_RE_WHOLE_ITEM_ANCHOR.search(anchor))


def patch_c_trim_soft_last(story: dict, *, whole_item: bool | None = None) -> list[str]:
    """一句一改：末句若「哼/行吧/算了 + 长解释/文字游戏」，截成一句完整嘴硬话。

    C 末句禁光杆叹词收尾（用户定 2026-08-08），须一句有内容的嘴硬话——
    认栽不认输/撂狠话告状/情绪退出；模型常写成「哼，你那是碰，我这是拿，
    不一样！」这类草率续句——本地截断成「哼，明天我比你早！」比整段重试稳。
    软收词后尾巴 ≤8 字（如「……哼，给你吧」）视为合理嘴硬，保留。
    """
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return notes
    last = dialogue[-1]
    if not isinstance(last, dict):
        return notes
    line = str(last.get("line") or "").strip()
    m = _RE_C_SOFT_HEAD.match(line)
    if not m:
        return notes
    soft = m.group(1)
    tail = line[m.end():].strip("，,。！？… \t")
    if not tail or len(tail) < 8:
        return notes
    wi = _c_whole_item_story(story) if whole_item is None else whole_item
    new_line = _c_default_stubborn_tail(soft, whole_item=wi)
    total = sum(len(str(d.get("line") or "")) for d in dialogue)
    if total - (len(line) - len(new_line)) < 280:  # 别把正文削到 280 硬卡以下
        return notes
    last["line"] = new_line
    notes.append("C末句软收截断")
    return notes


# 整件物 near-miss：句数够但字数差一截 → 升级2–3段插占有系短句（禁翻转段/末四拍）
_RE_WI_FLIP_ZONE = re.compile(
    r"哪条作数|按哪条|一条接一条|不加了|我说了算|钻空子|哪条说我",
)
# 升级段锚点（规则定义句之后可插补字；禁用翻转段锚点定位）
_RE_WI_UPGRADE_ANCHOR = re.compile(
    r"光.{0,4}不行|光.{0,4}不算|攥着不算|得.{0,8}才算|才算数|才算真正|"
    r"都得.{0,6}才算|加一条|连续证明|旧规则|须.*批准",
)
# 立规人改定义式加赛（与 humor 同源；整件物最多 3 层，专家 batch4）
_RE_WI_RULE_DEFINITION = re.compile(
    r"光.{0,4}不行|光.{0,4}不算|攥着不算|得.{0,8}才算|才算数|才算真正|"
    r"都得.{0,6}才算",
)
_WI_RULE_LAYER_MAX = 3
# 占有系对白（禁纯动作旁白占末四拍位，2026-08-21 batch）
_WI_SEMANTIC_INSERT_LINES = (
    "我两手都攥紧了，算不算拿到？",
    "我整个抱怀里了，你也没说不行！",
)
_RE_WI_PURE_ACTION = re.compile(
    r"收紧手臂|往怀里扣|往怀里带|没接话",
)
_RE_WI_ESTABLISH_RULE = re.compile(
    r"归谁|谁先|我定|规则|才公平",
)
# 立规人：正文抛完整赛规（非开场「归我」占有宣示）
_RE_WI_RULE_MAKER_LINE = re.compile(
    r"谁先(?:拿到|抢到|攥).{0,8}归|谁先.*归谁|得.{0,8}才算|才算数",
)
_RE_WI_RULE_AUTHORITY_APPEND = re.compile(
    r"我又加一条|再加一条|新规则",
)
_RE_WI_TAIL_RULE_CALLBACK = re.compile(
    r"最开始那条|按最开始|谁先(?:拿到|抢到|攥).{0,8}归",
)
_WI_SEMANTIC_MIN_LINES = 17
_WI_SEMANTIC_MAX_INSERT = 2


def _wi_opposite_speaker(sp: str) -> str:
    return "灿灿" if sp == "昭昭" else "昭昭"


def _wi_insert_alternation_ok(dialogue: list, insert_at: int, alt: str) -> bool:
    """插入后 i-1 / i / i+1 须严格交替。"""
    if insert_at < 1 or insert_at > len(dialogue):
        return False
    prev_sp = str(dialogue[insert_at - 1].get("speaker") or "").strip()
    if prev_sp in ("昭昭", "灿灿") and alt == prev_sp:
        return False
    if insert_at < len(dialogue):
        next_sp = str(dialogue[insert_at].get("speaker") or "").strip()
        if next_sp in ("昭昭", "灿灿") and alt == next_sp:
            return False
    return True


def _find_wi_semantic_insert_at(dialogue: list) -> int | None:
    """定位升级2–3段：最后一个规则定义句之后；禁翻转段与末四拍。"""
    if len(dialogue) < 4:
        return None
    max_insert = max(3, len(dialogue) - 4)
    for i in range(max_insert - 1, 2, -1):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if _RE_WI_FLIP_ZONE.search(line):
            continue
        if not _RE_WI_UPGRADE_ANCHOR.search(line):
            continue
        candidate = i + 1
        if candidate >= max_insert:
            continue
        if candidate < len(dialogue):
            nxt_ln = str(dialogue[candidate].get("line") or "")
            if _RE_WI_FLIP_ZONE.search(nxt_ln):
                continue
        return candidate
    return None


def patch_c_whole_item_cap_rule_layers(story: dict) -> list[str]:
    """整件物：立规人改定义式加赛硬上限 3 层（专家 batch4）。

    删句会破坏交替发言与末四拍，暂只做计数占位；清单化由 humor 压分 + line 提示约束。
    """
    _ = story
    return []


def patch_c_whole_item_semantic_expand(story: dict) -> list[str]:
    """整件物 near-miss：句数≥17 且距 240 字差≤PATCH_CHAR_DEFICIT，在翻转段插 1–2 句占有系对白。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes
    anchor = (
        str(story.get("theme") or story.get("_theme") or "")
        + str(story.get("conflict_core") or "")
        + str(story.get("setting") or "")
    )
    if not _RE_WHOLE_ITEM_ANCHOR.search(anchor):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    from app.services.daily_story.prompts import (
        c_whole_item_char_deficit_to_validate,
        dialogue_total_chars,
    )

    if len(dialogue) < _WI_SEMANTIC_MIN_LINES:
        return notes
    deficit = c_whole_item_char_deficit_to_validate(story)
    if deficit <= 0 or deficit > C_WHOLE_ITEM_PATCH_CHAR_DEFICIT:
        return notes
    insert_at = _find_wi_semantic_insert_at(dialogue)
    if insert_at is None:
        return notes
    prev_sp = str(dialogue[insert_at - 1].get("speaker") or "昭昭").strip()
    if prev_sp not in ("昭昭", "灿灿"):
        return notes
    alt = _wi_opposite_speaker(prev_sp)
    inserted = 0
    templates = list(_WI_SEMANTIC_INSERT_LINES)
    while (
        c_whole_item_char_deficit_to_validate(story) > 0
        and inserted < _WI_SEMANTIC_MAX_INSERT
        and insert_at is not None
    ):
        if not templates:
            break
        tmpl = templates.pop(0)
        if _wi_insert_alternation_ok(dialogue, insert_at, alt):
            dialogue.insert(insert_at, {"speaker": alt, "line": tmpl})
            notes.append(f"整件物语义扩写[{insert_at}]")
            insert_at += 1
            inserted += 1
            alt = _wi_opposite_speaker(alt)
            continue
        if insert_at >= len(dialogue):
            break
        next_sp = str(dialogue[insert_at].get("speaker") or "").strip()
        if (
            next_sp in ("昭昭", "灿灿")
            and next_sp != prev_sp
            and templates
        ):
            tmpl2 = templates.pop(0)
            dialogue.insert(insert_at, {"speaker": alt, "line": tmpl})
            dialogue.insert(
                insert_at + 1,
                {"speaker": _wi_opposite_speaker(alt), "line": tmpl2},
            )
            notes.append(f"整件物语义扩写[{insert_at}]×2")
            insert_at += 2
            inserted += 2
            alt = prev_sp
            continue
        break
    return notes


def _whole_item_rule_maker(dialogue: list) -> str | None:
    for i, item in enumerate(dialogue):
        if i < 2 or not isinstance(item, dict):
            continue
        ln = str(item.get("line") or "")
        if not _RE_WI_RULE_MAKER_LINE.search(ln):
            continue
        sp = str(item.get("speaker") or "").strip()
        if sp in ("昭昭", "灿灿"):
            return sp
    return None


def patch_c_whole_item_closing(story: dict) -> list[str]:
    """整件物：末段纯动作→对白；回旋镖/嘴硬 speaker 对齐立规人。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes
    anchor = (
        str(story.get("theme") or story.get("_theme") or "")
        + str(story.get("conflict_core") or "")
        + str(story.get("setting") or "")
    )
    if not _RE_WHOLE_ITEM_ANCHOR.search(anchor):
        return notes
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 4:
        return notes
    maker = _whole_item_rule_maker(dialogue)
    if not maker:
        return notes
    opp = "灿灿" if maker == "昭昭" else "昭昭"

    for item in dialogue:
        if not isinstance(item, dict):
            continue
        ln = str(item.get("line") or "")
        if (
            str(item.get("speaker") or "") == maker
            and _RE_WI_RULE_AUTHORITY_APPEND.search(ln)
        ):
            new_ln = re.sub(
                r"我又加一条[，,]?|再加一条[，,]?|新规则[，,]?",
                "不加了，",
                ln,
            )
            if "现在规则我说了算" not in new_ln:
                new_ln = "不加了，现在规则我说了算！"
            if new_ln != ln:
                item["line"] = new_ln
                notes.append("整件物翻转→权力终止")

    if len(dialogue) >= 5:
        prev5 = dialogue[-5]
        first_tail = dialogue[-4]
        if isinstance(prev5, dict) and isinstance(first_tail, dict):
            s5 = str(prev5.get("speaker") or "").strip()
            s4 = str(first_tail.get("speaker") or "").strip()
            if s5 in ("昭昭", "灿灿") and s5 == s4:
                first_tail["speaker"] = _wi_opposite_speaker(s5)
                notes.append("整件物末四拍首句→与前拍交替")

    tail_start = max(0, len(dialogue) - 4)
    for i in range(len(dialogue) - 1, tail_start - 1, -1):
        item = dialogue[i]
        if not isinstance(item, dict):
            continue
        ln = str(item.get("line") or "")
        if not _RE_WI_PURE_ACTION.search(ln):
            continue
        dialogue.pop(i)
        notes.append(f"整件物末段删纯动作[{i}]")

    last = dialogue[-1]
    prev = dialogue[-2]
    if not isinstance(last, dict) or not isinstance(prev, dict):
        return notes
    last_ln = str(last.get("line") or "")
    prev_ln = str(prev.get("line") or "")

    def _stubborn_line(ln: str) -> bool:
        return bool(
            _RE_C_SOFT_HEAD.match(ln)
            or RE_C_STUBBORN_LAST.search(ln)
            or "让着你" in ln
            or "赢规则" in ln
        )

    if RE_BOOMERANG_RULE.search(last_ln) and _stubborn_line(prev_ln):
        last["speaker"], prev["speaker"] = prev.get("speaker"), last.get("speaker")
        last["line"], prev["line"] = prev_ln, last_ln
        notes.append("整件物末两拍顺序纠错")
        last_ln, prev_ln = str(last.get("line") or ""), str(prev.get("line") or "")

    if _stubborn_line(last_ln) and str(last.get("speaker") or "") != maker:
        last["speaker"] = maker
        notes.append("整件物末句嘴硬→立规人")
    if RE_BOOMERANG_RULE.search(prev_ln) and str(prev.get("speaker") or "") != opp:
        prev["speaker"] = opp
        notes.append("整件物回旋镖→对方")

    from app.services.daily_story.possession_contract import (
        align_whole_item_final_four_speakers,
    )

    notes.extend(
        align_whole_item_final_four_speakers(dialogue, maker=maker, opp=opp)
    )

    last_ln = str(last.get("line") or "")
    if str(last.get("speaker") or "") == maker and re.search(
        r"明天我(?:抢先|比你早|一定赢)",
        last_ln,
    ) and "赢规则" not in last_ln:
        m = _RE_C_SOFT_HEAD.match(last_ln)
        soft = m.group(1) if m else "哼"
        new_ln = _c_default_stubborn_tail(soft, whole_item=True)
        if new_ln != last_ln:
            last["line"] = new_ln
            notes.append("整件物末句→主题嘴硬")
    return notes


def patch_c_body(story: dict) -> list[str]:
    """C 类：末句 speaker 勿为妈妈 + 末句软收截断 + 正文首句无前文自证删前缀。"""
    notes: list[str] = []
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "C":
        return notes

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 2:
        return notes

    notes.extend(patch_c_stray_rebuttal(story))
    notes.extend(patch_c_whole_item_near_miss(story))
    notes.extend(patch_c_whole_item_tone_tail(story))
    wi = _c_whole_item_story(story)
    if not wi:
        notes.extend(patch_c_whole_item_contact(story))

    notes.extend(patch_c_whole_item_semantic_expand(story))
    notes.extend(patch_c_whole_item_filler(story))
    notes.extend(patch_c_whole_item_cap_rule_layers(story))

    last = dialogue[-1]
    prev = dialogue[-2]
    if not isinstance(last, dict) or not isinstance(prev, dict):
        return notes

    wi = _c_whole_item_story(story)
    last_sp = str(last.get("speaker") or "").strip()
    prev_sp = str(prev.get("speaker") or "").strip()
    if last_sp != "妈妈":
        notes.extend(patch_c_trim_soft_last(story, whole_item=wi))
        return notes

    if prev_sp in ("昭昭", "灿灿"):
        alt = "灿灿" if prev_sp == "昭昭" else "昭昭"
        last["speaker"] = alt
        notes.append("C末句speaker妈妈→姐弟")
    notes.extend(patch_c_trim_soft_last(story, whole_item=wi))
    return notes
