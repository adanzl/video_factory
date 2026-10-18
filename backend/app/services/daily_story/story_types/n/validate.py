"""N 类正文硬卡（设问 + 荒诞自洽 + 愣住）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

# 抽象不变量：追问链 + 因果自洽 + 愣住；禁单篇香蕉/苹果词表
# 设问/考验：家长把问题摆出来当考题。
# 原先只认「如果/还是/喜欢谁」这类二选一问法，漏了**归属/身份类设问**
# （「这算谁的」「妈妈是谁的妈妈」「谁才是老大」——同样是家长出题，
# 只是问的是归属不是喜好）。#135 实测：19 句稿只差这一条判词。
RE_CHALLENGE = re.compile(
    r"如果|还是|先吃|先|喜欢谁|怎么办|你说|"
    r"(?:是|归|算)谁的|谁才是|哪个(?:是|归|才算)|"
    r"的.{0,6}是谁|是谁(?:呀|啊|呢|[？?])"
)
# 追问＝接着问下去，不限于字面「为什么」（追问意思/出处同样算追问拍）
RE_WHY = re.compile(
    r"为什么|为啥|怎么想|怎么会|哪有|什么意思|啥意思|谁教|哪来|哪儿来|凭什么"
)
RE_SOLEMN_REASON = re.compile(r"因为|所以|这样就能|等到|长成|就能|有籽")
RE_STUN_CLOSE = re.compile(
    r"那……|那\.\.\.|行吧|服了|说不出|无语|愣住|哭笑|"
    r"接不住|被噎|算了|放弃"
)


def stun_close_hit(lines: list[str]) -> bool:
    """收束窗（末四句，或倒数第二句 + 末句合并）内的愣住/接不住。

    唯一判据：quality 与 humor 共用，避免「中段追问里的语气词」被一边
    当成愣住、另一边判缺落点（同一稿两份矛盾判词）。

    两条硬约束：
    - 只看收束窗，中段「行吧，那苹果呢？」不算收束；
    - 「行吧/算了」类语气词出现在**疑问句**里不算愣住（那是追问不是破功）。
    """
    texts = [str(x or "").strip() for x in (lines or []) if str(x or "").strip()]
    if not texts:
        return False
    window = list(texts[-4:])
    if len(texts) >= 2:
        window.append(texts[-2] + texts[-1])
    for text in window:
        if not RE_STUN_CLOSE.search(text):
            continue
        if re.search(r"[？?]\s*$", text):
            continue
        return True
    return False


RE_C_BOOMERANG_CLOSE = re.compile(r"你刚说|你说的|八百|吃商|心眼子")
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|自相矛盾|你刚才说")
RE_I_SOUL = re.compile(r"爱学习|你爱吗|灵魂|拷问")
RE_E_THESIS_FLIP = re.compile(r"我改口|我说错了|不算了.*改|重新立")


def _lines_and_speakers(story: dict) -> tuple[list[str], list[str]]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return [], []
    lines: list[str] = []
    speakers: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        ln = str(item.get("line") or "").strip()
        if not ln:
            continue
        speakers.append(sp)
        lines.append(ln)
    return lines, speakers


def append_n_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "N":
        return
    lines, _speakers = _lines_and_speakers(story)
    if len(lines) < 6:
        return

    body = "".join(lines)
    tail5 = "".join(lines[-5:])
    if not RE_CHALLENGE.search(body):
        errors.append("N类：正文须有设问/考验（如果/还是/喜欢谁等）")
    if not RE_WHY.search(body):
        errors.append("N类：正文须有追问（为什么/为啥等）")
    if not RE_SOLEMN_REASON.search(body):
        errors.append("N类：须有一本正经自洽（因为/所以/就能等）")
    if not stun_close_hit(lines):
        errors.append("N类：收束须愣住/接不住（行吧/服了/那……等，落在末四句）")
    if RE_A_BACKFIRE.search(tail5):
        errors.append("N类：末段勿 A 式反噬/破功链")
    if RE_C_BOOMERANG_CLOSE.search(tail5) and not stun_close_hit(lines):
        errors.append("N类：末段勿套 C 回旋镖收束，须落愣住/接不住")
    if RE_I_SOUL.search(body):
        errors.append("N类：勿写成 I 灵魂拷问（爱学习/你爱吗）")
    if RE_E_THESIS_FLIP.search(body):
        errors.append("N类：勿写成 E 立论改口链")
