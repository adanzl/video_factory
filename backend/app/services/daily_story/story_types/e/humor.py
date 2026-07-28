"""E 类好笑维硬伤与修订 hint。"""

from __future__ import annotations

import re

RE_MOM_RULE = re.compile(
    r"应该|必须|规矩|听我的|我说|不行|不能|不许|别吃|得睡|别玩",
)
RE_KID_ASK = re.compile(
    r"为什么|凭什么|那你|你也|上次|妈妈你也|算不算|怎么又",
)
RE_MOM_WAFFLE = re.compile(
    r"不是|不一样|那是|总之|反正|不是那个|不算|尝咸淡|大人|工作需要",
)
RE_LIE_TOPIC = re.compile(r"说谎|撒谎|敷衍|诚实|假话|骗")
RE_LIE_MOM_RULE = re.compile(r"不能说谎|不许说谎|要诚实|别说谎|老实")
RE_LIE_WAFFLE = re.compile(
    r"不是敷衍|善意谎言|让奶奶放心|特殊情况|为了不让|不是骗",
)
RE_SNACK_BLEED = re.compile(
    r"那一口算不算|尝咸淡|咽下去|三大勺|勺上|吐回锅里|试吃|偷吃零",
)
RE_LIE_FOOD_ITEM = re.compile(r"红烧|清蒸|排骨汤|白米饭|两碗汤|清蒸虾|红烧鱼")
RE_MOM_DENY_QUOTE = re.compile(
    r"我说什么了|没说吃|挺好的呀|没骗|没说谎|就说我们挺好",
)
RE_KID_QUOTE_EAT = re.compile(r"吃了好多|吃撑|三碗|好几碗|咕咕叫")
RE_SNACK_TOPIC = re.compile(r"零食|尝菜|偷吃|饭前不吃|试吃|试菜")
RE_SLEEP_TOPIC = re.compile(r"睡觉|九点|早睡|刷手机|卧床|被窝|挂钟")
RE_WEAK_TASTE_EYE = re.compile(r"汤汁|舀汤|舔勺|喝了一口汤|偷尝了汤|尝了汤")
RE_STRONG_TASTE_EYE = re.compile(
    r"勺子|勺上|尝菜|试吃|试菜|嘴角|油渍|油花|菜叶|三大勺|咽|黏黏",
)
RE_LOOP = re.compile(
    r"你自己说|你刚才|那你也是|你也这样|那你现在|妈妈你也",
)
RE_MOM_SOFT = re.compile(r"唉|行了|好吧|随便|说不通|行行行|算了")
_A_STYLE = re.compile(r"那不一样.*哪里不一样|哪里不一样.*都是听")
_EMPTY = re.compile(r"你赢了|算你厉害|谁对谁错|我不听了")

HUMOR_ISSUE_CAPS: tuple[tuple[str, int], ...] = (
    ("偏A式末四拍", 6),
    ("缺妈妈立论", 6),
    ("缺孩子追问", 6),
    ("缺妈妈改口", 6),
    ("缺追问闭环", 7),
    ("末句非妈妈破功", 7),
    ("妈妈说教过长", 5),
    ("空说教注水", 5),
    ("中段拖沓注水", 5),
    ("破功过早", 5),
    ("补字残留", 8),
    ("尝菜眼太弱", 7),
    ("尝菜串场", 8),
    ("偏A式那不一样", 6),
    ("妈妈否认引话", 7),
    ("谎题堆菜品", 6),
    ("说谎先狡辩", 6),
)


def collect_humor_issues(
    lines: list[str],
    speakers: list[str] | None,
) -> list[str]:
    cons: list[str] = []
    n = len(lines)
    if n < 6:
        return cons

    tail4 = lines[-4:] if n >= 4 else lines
    tail_text = "".join(tail4)
    body = lines[:-4] if n > 4 else lines[:-2]
    body_text = "".join(body)
    all_text = "".join(lines)
    mid = lines[2:-3] if n > 6 else body

    if _A_STYLE.search(tail_text) or (
        "哪里不一样" in tail_text and "那不一样" in tail_text
    ):
        cons.append("偏A式末四拍，不好笑")

    if not RE_MOM_RULE.search(body_text) and not RE_MOM_RULE.search(
        "".join(lines[: max(1, n // 2)]),
    ):
        cons.append("缺妈妈立论，不好笑")

    if not RE_KID_ASK.search("".join(mid)) and not RE_KID_ASK.search(body_text):
        cons.append("缺孩子追问，不好笑")

    if not RE_MOM_WAFFLE.search(all_text):
        cons.append("缺妈妈改口，不好笑")

    if not RE_LOOP.search(tail_text):
        cons.append("缺追问闭环，不好笑")

    if speakers and len(speakers) == n:
        if speakers[-1] != "妈妈":
            cons.append("末句非妈妈破功，不好笑")
        elif not RE_MOM_SOFT.search(lines[-1]):
            cons.append("末句非妈妈破功，不好笑")

    soft_i = next(
        (i for i, ln in enumerate(lines) if RE_MOM_SOFT.search(ln)),
        None,
    )
    if soft_i is not None and soft_i < n - 2 and speakers:
        # 破功后还继续讲理
        if any(
            speakers[i] == "妈妈" and RE_MOM_RULE.search(lines[i])
            for i in range(soft_i + 1, n)
        ):
            cons.append("破功过早，不好笑")

    lecture_n = sum(
        1
        for i, ln in enumerate(lines)
        if speakers
        and i < len(speakers)
        and speakers[i] == "妈妈"
        and re.search(r"听我的|我说了|必须听|要听话|道理", ln)
    )
    if lecture_n >= 5 or _EMPTY.search(all_text):
        cons.append("空说教注水，不好笑")

    if all_text.count("还在亮") >= 2 or all_text.count("，你看") >= 2:
        cons.append("补字残留，不好笑")

    if RE_SNACK_TOPIC.search(all_text) and RE_WEAK_TASTE_EYE.search(
        "".join(lines[: min(6, n)]),
    ) and not RE_STRONG_TASTE_EYE.search(
        "".join(lines[: min(8, n)]),
    ):
        cons.append("尝菜眼太弱，不好笑")

    lie_t = (
        RE_LIE_TOPIC.search(all_text)
        and not RE_SNACK_TOPIC.search(all_text)
        and not RE_SLEEP_TOPIC.search(all_text)
    )
    if lie_t and RE_SNACK_BLEED.search(all_text):
        cons.append("尝菜串场，不好笑")
    if lie_t and "那不一样" in all_text:
        cons.append("偏A式那不一样，不好笑")
    if lie_t and len(RE_LIE_FOOD_ITEM.findall(all_text)) >= 3:
        cons.append("谎题堆菜品，不好笑")
    if lie_t and speakers and len(speakers) == n:
        for i, ln in enumerate(lines):
            if speakers[i] not in ("昭昭", "灿灿"):
                continue
            if not RE_KID_QUOTE_EAT.search(ln):
                continue
            mom_after = "".join(
                lines[j]
                for j in range(i + 1, n)
                if speakers[j] == "妈妈"
            )
            if RE_MOM_DENY_QUOTE.search(mom_after):
                cons.append("妈妈否认引话，不好笑")
                break
        rule_i = next(
            (
                i
                for i, ln in enumerate(lines)
                if speakers[i] == "妈妈" and RE_LIE_MOM_RULE.search(ln)
            ),
            None,
        )
        if rule_i is not None:
            for i in range(min(rule_i, 4)):
                if speakers[i] == "妈妈" and RE_LIE_WAFFLE.search(lines[i]):
                    cons.append("说谎先狡辩，不好笑")
                    break

    return cons


def humor_revision_hint(issue: str) -> str | None:
    keys = (
        "妈妈",
        "E",
        "闭环",
        "追问",
        "改口",
        "立论",
        "说教",
        "拖沓",
        "末四拍",
        "破功",
    )
    if any(k in issue for k in keys):
        return (
            f"【好笑·E】{issue}。"
            "妈妈短立论→孩子用场面抓现行→妈妈改口开脱→"
            "孩子用原话闭环→末句妈妈行行行；勿A式末四拍、勿长说教。"
        )
    return None
