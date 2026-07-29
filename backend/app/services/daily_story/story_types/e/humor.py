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
    r"不是敷衍|善意.{0,2}谎|让奶奶放心|特殊情况|为了不让|不是骗|"
    r"不算撒谎|不算说谎",
)
RE_LIE_GOOD_WAFFLE = re.compile(r"善意")
RE_SNACK_BLEED = re.compile(
    r"那一口算不算|尝咸淡|三大勺|勺上|吐回锅里|试吃|偷吃零|"
    r"尝菜|调味|油光",
)
RE_LIE_FOOD_ITEM = re.compile(r"红烧|清蒸|排骨汤|白米饭|两碗汤|清蒸虾|红烧鱼")
RE_MOM_DENY_QUOTE = re.compile(
    r"我说什么了|没说吃|挺好的呀|没骗|没说谎|就说我们挺好",
)
RE_KID_QUOTE_EAT = re.compile(r"吃了好多|吃撑|三碗|好几碗|咕咕叫")
RE_LIE_PHYSICAL = re.compile(
    r"空(?:的)?锅|锅是空|锅里.{0,6}(?:没|空)|饭锅|电饭锅|一粒米|"
    r"碗(?:都|还|是|一个)?(?:是)?(?:干|没动|空)|没洗的碗|外卖盒|"
    r"泡面桶|垃圾桶|肚子(?:还|都)?咕咕|盘子还扣着|米还在袋",
)
RE_KID_SELF_APPLY = re.compile(
    r"那我(?:也|跟|对|明天|以后|回头|可以|能)|我也(?:这么|这样|能|可以)|"
    r"我(?:明天|以后|回头)?跟(?:老师|奶奶|爷爷|外婆|同学)说|告老师|考砸了?也说",
)
# 妈妈开脱的各种花样说法（宽口径，只对妈妈的句子计数）
RE_MOM_EXCUSE_ANY = re.compile(
    r"善意|好心|随口|怕她|怕奶奶|为大人|大人.{0,4}(?:着想|需要)|工作需要|"
    r"不算|为了不让|报喜|礼貌|着想|不想让.{0,4}(?:担心|操心)|"
    r"不让.{0,3}(?:担心|操心)|特殊情况|两码事|不一样|分寸|你们还小",
)
# 孩子自套逻辑后，妈妈须当场一口否掉（双标才成立）
RE_MOM_FLAT_REFUSE = re.compile(
    r"不行|不许|不可以|不准|当然不|想都别想|少来|你敢|哪能",
)
RE_LIE_SIDE_PLOT = re.compile(
    r"爸爸|加班|打游戏|作业|写完|三页|鱼腥|倒了.*醋|唠叨|夸奶奶",
)
RE_GARBAGE_FILLER = re.compile(
    r"[呵哈]{2,}|(?:呢|吗|啊|呀|啦|吧|嘛){2,}$|对不对呀真的",
)
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
    ("善意谎言复读", 7),
    ("那是开脱复读", 6),
    ("开脱句连复读", 7),
    ("说谎叠支线", 7),
    ("说谎缺实物反证", 8),
    ("说谎缺自套逻辑反杀", 8),
    ("妈妈一句一个新借口", 8),
    ("语气垫字", 8),
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
    if lie_t and re.search(r"(?:这|那)不一样", all_text):
        cons.append("偏不一样开脱，不好笑")
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
        if sum(
            1
            for i, ln in enumerate(lines)
            if speakers[i] == "妈妈" and "善意" in ln
        ) >= 3:
            cons.append("善意谎言复读，不好笑")
        mom_na = sum(
            1
            for i, ln in enumerate(lines)
            if speakers[i] == "妈妈" and ln.startswith("那是")
        )
        if mom_na >= 3:
            cons.append("那是开脱复读，不好笑")
        mom_waffle_n = sum(
            1
            for i, ln in enumerate(lines)
            if speakers[i] == "妈妈"
            and (
                ln.startswith("那是")
                or RE_LIE_GOOD_WAFFLE.search(ln)
                or "特殊" in ln
            )
        )
        if mom_waffle_n >= 3:
            cons.append("开脱句连复读，不好笑")
        side_text = "".join(
            ln for ln in lines if not RE_KID_SELF_APPLY.search(ln)
        )
        if len(RE_LIE_SIDE_PLOT.findall(side_text)) >= 2:
            cons.append("说谎叠支线，不好笑")
        if not RE_LIE_PHYSICAL.search(all_text):
            cons.append("说谎缺实物反证，不好笑")
        if not RE_KID_SELF_APPLY.search("".join(lines[max(0, len(lines) - 6) :])):
            cons.append("说谎缺自套逻辑反杀，不好笑")
        if sum(
            1
            for sp, ln in zip(speakers or [], lines)
            if sp == "妈妈" and RE_MOM_EXCUSE_ANY.search(ln)
        ) >= 4:
            cons.append("妈妈一句一个新借口，不好笑")

    for ln in lines:
        if RE_GARBAGE_FILLER.search(ln):
            cons.append("语气垫字，不好笑")
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
