"""C 类正文本地修稿（仅确定性结构）。

加规则红线（新增前必读）：
- patch 只做**类型级**结构修补：删句/去重/改 speaker/引话接地。
- 禁止绑定具体 theme 的规则（按主题关键词分支改写台词）。
  内容不合格一律交 LLM 重试，不在本地按主题造句。
"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN

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
    total = sum(len(str(d.get("line") or "")) for d in dialogue)
    if total - (len(line) - len(rest)) < DAILY_STORY_BODY_CHARS_MIN:
        return notes  # 别把正文削到硬卡下限以下
    third["line"] = rest
    notes.append("C正文首句无前文自证删前缀")
    return notes


def _c_default_stubborn_tail(soft: str) -> str:
    """软收词后补一句通用嘴硬话（用户定 2026-08-08：禁光杆叹词收尾）。

    只做**通用**收束，不绑定具体 theme（patch 红线：禁止按主题造句）；
    「明天我赢过你」对任何赛规都成立（仪式判据/先到先得都不错位，用户
    2026-08-09 v26 定：末句嘴硬锚定的比法必须字面在本场立规句里，
    「比你早/比你举得久」都可能发明本场没有的比法，万能胜负最稳）。
    """
    if soft in ("哼", "切", "嘁"):
        return "哼，明天我赢过你！"
    return "行吧，算你手快！"


def patch_c_trim_soft_last(story: dict) -> list[str]:
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
    new_line = _c_default_stubborn_tail(soft)
    total = sum(len(str(d.get("line") or "")) for d in dialogue)
    if total - (len(line) - len(new_line)) < 280:  # 别把正文削到 280 硬卡以下
        return notes
    last["line"] = new_line
    notes.append("C末句软收截断")
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

    last = dialogue[-1]
    prev = dialogue[-2]
    if not isinstance(last, dict) or not isinstance(prev, dict):
        return notes

    last_sp = str(last.get("speaker") or "").strip()
    prev_sp = str(prev.get("speaker") or "").strip()
    if last_sp != "妈妈":
        notes.extend(patch_c_trim_soft_last(story))
        return notes

    if prev_sp in ("昭昭", "灿灿"):
        alt = "灿灿" if prev_sp == "昭昭" else "昭昭"
        last["speaker"] = alt
        notes.append("C末句speaker妈妈→姐弟")
    notes.extend(patch_c_trim_soft_last(story))
    return notes
