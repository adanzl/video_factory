"""B 类好笑维硬伤、末段加分与修订 hint。"""

from __future__ import annotations

import re

RE_ALLY = re.compile(
    r"一起|咱俩|别告诉|瞒着|瞒妈|约定|联手|暗号|分工|你望风|你放风|"
    r"放风|望风|说好了|盯门口|你盯|手快|别出声|一人一半|拆包|拆包装",
)
RE_BLAME = re.compile(
    r"都怪你|是你先|你答应|不是我的|你先|赖我|你不是说好|才不是我的",
)
RE_EXPOSED = re.compile(
    r"露馅|完了|糟糕|抓到了|听见了|看见了|妈妈|撞见|藏不住",
)
RE_PLAN_FAIL = re.compile(
    r"多拿|忘藏|说漏|掉了|洒了|露出来|忘了藏|袋口|碎|脚印|油渍|"
    r"响了|破了|更明显|鼓出来",
)
RE_BLAME_MID = re.compile(r"都怪你|是你先|你答应|赖我|你还怪")
_A_STYLE_TAIL = re.compile(r"那不一样|哪里不一样|你刚才说|你自己说")
RE_MOM_PUNISH = re.compile(
    r"站好|过来|罚|不许|今晚|检讨|说清楚|墙角|罚站|别想吃",
)
RE_DOOM = re.compile(r"完蛋|完了|糟糕|死定了|藏不住|露馅")
RE_PACT_DUTY = re.compile(
    r"望风|放风|暗号|分工|你拿|我盯|你拆|我望|别告诉|一人一半",
)
RE_CHAIN_ACTION = re.compile(
    r"掉|碎|滑|洒|蹭|捡|塞|压|挡|擦|摸|踩|响|破|油|印|鼓|露|咽",
)
RE_ABSURD_FIX = re.compile(
    r"鞋底|洒水|塞嘴里|靠垫|沙发垫|用脚|蹭碎|更糟|更明|别出声",
)
RE_PACT_CHATTER = re.compile(
    r"望风|盯着|快拿|赶紧|门口|咳嗽|别磨蹭|你看着",
)
RE_EMPTY_ARGUE = re.compile(
    r"你挡|我不挡|你笨|你慢|烦死了|凭什么",
)
RE_LANDING_GROUND = re.compile(
    r"藏不住|傻眼|愣住|愣住了|低头|不敢动|僵住|对视|一起完|咱俩完|"
    r"两个人都|妈都看见|一听就完|也完了|一起挨|一块儿完|咱俩全完|一起完蛋",
)
RE_STUBBORN_LAST = re.compile(r"哼|才不是|才不是我的主意")
_SIBLING = frozenset({"昭昭", "灿灿"})

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("偏A式末四拍", 6),
    ("缺结盟约定", 5),
    ("缺互甩锅", 7),
    ("偏C式争公平", 5),
    ("中段甩锅拖沓", 8),
    ("收束戛然而止", 6),
    ("走样连锁中甩锅打断", 7),
    ("收束缺权威落槌", 7),
    ("好笑缺越补越糟", 7),
    ("好笑空吵无场面", 6),
    ("甩锅不扣分工", 5),
    ("结盟分工复读", 6),
    ("惩罚后甩锅过长", 7),
    ("B收束惩罚缺底", 13),
)


def _find_last_mom_punish(
    lines: list[str],
    speakers: list[str],
    *,
    tail_window: int = 12,
) -> int | None:
    n = len(lines)
    for i in range(n - 1, max(-1, n - tail_window), -1):
        if speakers[i] == "妈妈" and RE_MOM_PUNISH.search(lines[i]):
            return i
    return None


def _trim_stubborn_tail(
    post_lines: list[str],
    post_speakers: list[str],
) -> tuple[list[str], list[str]]:
    if (
        post_lines
        and post_speakers
        and post_speakers[-1] in _SIBLING
        and RE_STUBBORN_LAST.search(post_lines[-1])
    ):
        return post_lines[:-1], post_speakers[:-1]
    return post_lines, post_speakers


def analyze_punish_landing(
    lines: list[str],
    speakers: list[str] | None,
) -> tuple[bool, str]:
    """返回 (是否缺底, 细分标签)。认栽底 = 惩罚令后、互甩前的同框定格一拍。"""
    n = len(lines)
    if n < 6 or not speakers or len(speakers) != n:
        return False, ""

    punish_i = _find_last_mom_punish(lines, speakers)
    if punish_i is None:
        return False, ""

    post_lines = lines[punish_i + 1 :]
    post_speakers = speakers[punish_i + 1 :]
    if not post_lines:
        return True, "惩罚令后无姐弟反应"

    body_lines, body_speakers = _trim_stubborn_tail(post_lines, post_speakers)
    post_text = "".join(body_lines)
    post_doom_speakers = {
        sp
        for sp, ln in zip(body_speakers, body_lines)
        if sp in _SIBLING and RE_DOOM.search(ln)
    }
    post_blame_n = sum(
        1
        for sp, ln in zip(body_speakers, body_lines)
        if sp in _SIBLING and RE_BLAME.search(ln)
    )
    if RE_LANDING_GROUND.search(post_text) or len(post_doom_speakers) >= 2:
        if post_blame_n > 2:
            return True, "认栽后甩锅抢拍过长"
        return False, ""

    if not post_doom_speakers:
        pre_doom = any(
            RE_DOOM.search(ln)
            for ln in lines[max(0, punish_i - 4) : punish_i]
        )
        if pre_doom and post_blame_n > 0:
            return True, "完蛋写在惩罚前缺落槌底"
        if post_blame_n > 0:
            return True, "惩罚后无完蛋直接甩锅"
        if pre_doom:
            return True, "完蛋写在惩罚前缺落槌底"
        return True, "惩罚后缺认栽反应"

    return True, "仅单人认栽缺同框底"


def is_weak_punish_landing(
    lines: list[str],
    speakers: list[str] | None,
) -> bool:
    return analyze_punish_landing(lines, speakers)[0]


def landing_revision_hint(tag: str) -> str:
    if tag == "惩罚后无完蛋直接甩锅":
        return (
            "妈妈惩罚令后先写姐弟认栽（完蛋了/咱俩完了/低头不敢动），"
            "再各甩 1 句；禁止站好后下一句就「都怪你」。"
        )
    if tag == "完蛋写在惩罚前缺落槌底":
        return (
            "露馅慌张可说「完了」，但惩罚令后须再写一拍认栽底"
            "（俩人一起完蛋或傻眼对视），再甩锅。"
        )
    if tag == "仅单人认栽缺同框底" or tag == "单人完蛋后立刻甩锅":
        return (
            "惩罚令后须俩人都有认栽反应：一人完蛋→另一人也完了/咱俩完了，"
            "或俩人低头不敢动/傻眼对视；勿仅一人完蛋后另一人直接甩锅。"
        )
    if tag == "认栽后甩锅抢拍过长":
        return "认栽底后互甩各 1 句即到末句哼，勿连甩 2–3 句。"
    return (
        "惩罚令后补同框认栽底：俩人一起完蛋/低头不敢动/傻眼对视，"
        "再各甩 1 句→哼。"
    )


def _longest_chain_run(lines: list[str], pattern: re.Pattern[str]) -> int:
    best = 0
    cur = 0
    for ln in lines:
        if pattern.search(ln):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE

    cons: list[str] = []
    n = len(lines)
    if n < 6:
        return cons

    head6 = "".join(lines[:6])
    head8 = "".join(lines[:8])
    tail6 = "".join(lines[-6:])
    tail4 = "".join(lines[-4:])
    tail8 = "".join(lines[-8:]) if n >= 8 else "".join(lines)
    body = lines[:-6] if n > 6 else lines[:-1]
    body_text = "".join(body)

    if _A_STYLE_TAIL.search(tail4) and not RE_BLAME.search(tail6):
        cons.append("B收束偏A式末四拍")

    if not RE_ALLY.search(head6) and not RE_ALLY.search("".join(lines[: n // 3])):
        cons.append("B缺结盟约定")

    if RE_EXPOSED.search(tail4) and not RE_BLAME.search(tail6):
        cons.append("B露馅前缺互甩锅")

    body_pre = "".join(lines[: max(0, n - 8)])
    if body_pre.count("不公平") >= 2 and not RE_ALLY.search(head6):
        cons.append("B偏C式争公平口号")

    if RE_BOOMERANG_RULE.search(tail4) and not RE_BLAME.search(tail6):
        cons.append("B收束偏回旋镖非甩锅")

    body_mid = lines[6 : max(6, n - 8)]
    blame_mid = sum(1 for ln in body_mid if RE_BLAME_MID.search(ln))
    if blame_mid >= 4:
        cons.append("B中段甩锅拖沓")

    chain_zone = lines[6 : min(n - 6, 20)]
    fail_i = next(
        (i for i, ln in enumerate(chain_zone) if RE_PLAN_FAIL.search(ln)),
        None,
    )
    if fail_i is not None:
        chain_slice = chain_zone[fail_i : fail_i + 6]
        if any(RE_BLAME_MID.search(ln) for ln in chain_slice):
            cons.append("B走样连锁中甩锅打断")

    mid_chain = body[1:] if len(body) > 1 else body
    chain_run = _longest_chain_run(mid_chain, RE_CHAIN_ACTION)
    fail_hits = sum(1 for ln in mid_chain if RE_PLAN_FAIL.search(ln))
    if chain_run < 3 and fail_hits < 2:
        cons.append("B好笑缺越补越糟连锁")

    empty_argue = sum(1 for ln in body_mid if RE_EMPTY_ARGUE.search(ln))
    if empty_argue >= 3 and chain_run < 3:
        cons.append("B好笑空吵无场面")

    blame_lines = [ln for ln in body_mid if RE_BLAME_MID.search(ln)]
    if blame_lines and RE_PACT_DUTY.search(head8):
        if not any(RE_PACT_DUTY.search(ln) for ln in blame_lines):
            cons.append("B甩锅不扣分工")

    if len(head8) > 80 and not RE_PLAN_FAIL.search("".join(lines[6:12])):
        if head8.count("不许") + head8.count("规矩") >= 2:
            cons.append("B同盟严肃说明书不好笑")

    pact_chatter = sum(1 for ln in lines[:14] if RE_PACT_CHATTER.search(ln))
    if pact_chatter >= 5:
        cons.append("B结盟分工复读拖沓")

    doom_i = next((i for i, ln in enumerate(lines) if RE_DOOM.search(ln)), None)
    punish_i = next(
        (i for i, ln in enumerate(lines) if RE_MOM_PUNISH.search(ln)),
        None,
    )
    if (
        doom_i is not None
        and punish_i is not None
        and doom_i > punish_i
        and doom_i < n - 1
    ):
        tail_blame = sum(
            1 for ln in lines[doom_i + 1 : -1] if RE_BLAME_MID.search(ln)
        )
        if tail_blame >= 3:
            cons.append("B惩罚后甩锅过长")

    last = lines[-1] if lines else ""
    if RE_EXPOSED.search(tail6) and not re.search(r"哼|才不是|才不是我的", last):
        if RE_BLAME.search(last):
            cons.append("B收束戛然而止缺嘴硬余韵")

    mom_late = bool(
        speakers
        and len(speakers) == n
        and any(speakers[i] == "妈妈" for i in range(max(0, n - 8), n))
    )
    if mom_late or RE_EXPOSED.search(tail8):
        if not RE_MOM_PUNISH.search(tail8) or not RE_DOOM.search(tail8):
            cons.append("B收束缺权威落槌")

    if is_weak_punish_landing(lines, speakers):
        _, landing_tag = analyze_punish_landing(lines, speakers)
        cons.append(
            f"B收束惩罚缺底"
            + (f"（{landing_tag}）" if landing_tag else ""),
        )

    return cons


def score_funniness_tail(
    lines: list[str],
    speakers: list[str] | None = None,
) -> tuple[int, list[str]]:
    n = len(lines)
    body = lines[:-6] if n > 6 else lines[:-1]
    tail8 = "".join(lines[-8:]) if n >= 8 else "".join(lines)
    late4 = lines[-4:] if n >= 4 else lines
    late4_text = "".join(late4)
    weak_landing = is_weak_punish_landing(lines, speakers)

    points = 0
    pros: list[str] = []

    mid_chain = body[1:] if len(body) > 1 else body
    chain_run = _longest_chain_run(mid_chain, RE_CHAIN_ACTION)
    if chain_run >= 4:
        points += 6
        pros.append("越补越糟连锁好笑")
    elif chain_run >= 3:
        points += 4
        pros.append("走样连锁好笑")

    absurd_n = sum(1 for ln in mid_chain if RE_ABSURD_FIX.search(ln))
    if absurd_n >= 2:
        points += 3
        pros.append("荒谬补救好笑")

    if (
        RE_MOM_PUNISH.search(tail8)
        and RE_DOOM.search(tail8)
        and not weak_landing
    ):
        points += 2
        pros.append("惩罚落槌好笑")

    if RE_BLAME.search(late4_text) and RE_DOOM.search(late4_text) and not weak_landing:
        points += 2
        pros.append("完蛋互甩好笑")

    if RE_ALLY.search("".join(lines[: max(1, n // 4)])) and RE_PLAN_FAIL.search(
        "".join(body),
    ):
        points += 1
        pros.append("同盟翻车好笑")

    return points, pros


def humor_revision_hint(issue: str) -> str | None:
    if "缺结盟" in issue:
        return (
            f"【好笑·B】{issue}。"
            "前 6 句姐弟亲口约定分工或暗号（望风/下手/别告诉妈），扣主题实物。"
        )
    if "缺互甩锅" in issue:
        return (
            f"【好笑·B】{issue}。"
            "露馅前先互甩 2 句：都怪你/是你先/你答应的；须扣同盟分工。"
        )
    if "偏A" in issue:
        return (
            f"【好笑·B】{issue}。"
            "收束用互甩锅+一起露馅+末句嘴硬推给对方；"
            "勿「那不一样/哪里不一样」四连拍。"
        )
    if "偏C" in issue or "回旋镖" in issue:
        return (
            f"【好笑·B】{issue}。"
            "主线是同盟裂了互推，不是争公平赛规或回旋镖扣原话。"
        )
    if "拖沓" in issue or "空吵" in issue or "复读" in issue or "过长" in issue:
        return (
            f"【好笑·B】{issue}。"
            "删口头互怼；结盟分工说清一次即进连锁；"
            "惩罚后：完蛋→各甩1句→哼，勿再吵一轮。"
        )
    if "戛然而止" in issue:
        return (
            f"【好笑·B】{issue}。"
            "末句加哼/才不是/才不是我的主意，短句嘴硬收束。"
        )
    if "连锁" in issue and "好笑" not in issue:
        return (
            f"【好笑·B】{issue}。"
            "连锁期间只写动作与慌张，勿插入都怪你。"
        )
    if "越补越糟" in issue or "说明书" in issue:
        return (
            f"【好笑·B】{issue}。"
            "结盟 2–3 句即可；立刻写意外连锁："
            "如滑了→鞋底蹭→更脏→踩袋响→油印；好笑在补救越帮越倒忙。"
        )
    if "权威落槌" in issue or "惩罚缺底" in issue:
        tag = ""
        if "（" in issue and "）" in issue:
            tag = issue.split("（", 1)[-1].rstrip("）")
        return (
            f"【好笑·B】{issue}。"
            + landing_revision_hint(tag)
        )
    if "分工" in issue:
        return (
            f"【好笑·B】{issue}。"
            "甩锅须扣望风/暗号/谁多拿：「都怪你没咳嗽」「是你让我换那片」。"
        )
    if any(k in issue for k in ("好笑", "幽默", "不足")):
        return (
            f"【好笑·B】{issue}。"
            "中段用 3–5 句越补越糟动作链（少吵）；"
            "末段妈妈惩罚令→完蛋→互甩→哼收束。"
        )
    from app.services.daily_story.story_types.b.facts import fact_revision_hint
    from app.services.daily_story.story_types.b.opening import opening_revision_hint

    return fact_revision_hint(issue) or opening_revision_hint(issue)
