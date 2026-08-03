"""E 类正文硬卡（妈妈破功收束）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code, resolve_story_type_code

RE_SOFT_LAST = re.compile(r"哼|行吧|随便|好吧|算了|认栽|说不通|行行行")

RE_A_WHERE_DIFF = re.compile(r"哪里不一样|都是听|大人也要听小孩")
RE_A_CITE_CLOSE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)",
)
RE_MOM_RULE = re.compile(
    r"应该|必须|规矩|听我的|我说|不行|不能|不许|不准|别吃|得睡|别玩|"
    r"得换|要换|得脱|要脱|得吃|要吃|得睡|要睡|"
    r"不(?:能|许|准|让|可以).{0,4}(?:进|玩|吃|睡|挑|看|换|脱)",
)
RE_KID_LOOP = re.compile(
    r"你自己说|自己说|你刚才|那你也是|你也这样|那你现在|妈妈你也",
)
RE_MOM_WAFFLE = re.compile(
    r"不是|不一样|那是|总之|反正|不是那个|不算|尝咸淡|大人|工作需要",
)
RE_SLEEP_TOPIC = re.compile(r"睡觉|九点|早睡|刷手机|卧床|被窝|挂钟")
RE_SNACK_TOPIC = re.compile(r"零食|尝菜|偷吃|薯片|饭前不吃|瓜子|试吃|试菜")
RE_PICKY_TOPIC = re.compile(r"挑食|青菜|拨到碗边|拨开青菜")
RE_PICKY_MOM_RULE = re.compile(
    r"不准挑食|不许挑食|不能挑食|别挑食|挑食不行|"
    r"青菜.{0,6}(?:必须|得|要)吃|饭菜都得吃",
)
RE_PICKY_EYE = re.compile(r"拨到|拨开|碗边|拨了.{0,4}青菜")
RE_PICKY_WAFFLE = re.compile(
    r"晾|配饭|配着饭|等会儿|一会儿|留到最后|饭太烫|再凉|慢慢来|翻一翻|翻个面",
)
RE_PICKY_RELECTURE = re.compile(
    r"一口.{0,4}不(?:动|吃)|怎么不吃|多吃青菜|你要多吃|青菜都不动",
)
RE_PICKY_PAD = re.compile(
    r"数数看|蔫了|证明你不是|打自己脸|说话算话|夹一根青菜|叶子都",
)
RE_LIE_TOPIC = re.compile(r"说谎|撒谎|敷衍|诚实|假话|骗")
RE_LIE_MOM_RULE = re.compile(r"不能说谎|不许说谎|要诚实|别说谎|老实")
RE_LIE_WAFFLE = re.compile(
    r"不是敷衍|善意.{0,2}谎|让奶奶放心|特殊情况|为了不让|不是骗|"
    r"不算撒谎|不算说谎",
)
# 「咽下去/不算吃」在「说吃撑了其实没吃」里是自然说法，纳入会反复误杀
RE_SNACK_BLEED = re.compile(
    r"那一口算不算|尝咸淡|三大勺|勺上|吐回锅里|试吃|偷吃零|"
    r"尝菜|调味|油光",
)
RE_LIE_FOOD_ITEM = re.compile(r"红烧|清蒸|排骨汤|白米饭|两碗汤|清蒸虾|红烧鱼")
RE_MOM_DENY_QUOTE = re.compile(
    r"我说什么了|没说吃|挺好的呀|没骗|没说谎|就说我们挺好",
)
RE_KID_QUOTE_EAT = re.compile(r"吃了好多|吃撑|三碗|好几碗|咕咕叫")
RE_LIE_GOOD_WAFFLE = re.compile(r"善意")
# 说谎题的「眼」：可拍实物反证，不能只靠口头对质
RE_LIE_PHYSICAL = re.compile(
    r"空(?:的)?锅|锅是空|锅里.{0,6}(?:没|空)|饭锅|电饭锅|一粒米|"
    r"碗(?:都|还|是|一个)?(?:是)?(?:干|没动|空)|没洗的碗|外卖盒|"
    r"泡面桶|垃圾桶|肚子(?:还|都)?咕咕|盘子还扣着|米还在袋",
)
# 孩子把妈妈的逻辑套回自己身上（反杀一拍）
RE_KID_SELF_APPLY = re.compile(
    r"那我(?:也|跟|对|明天|以后|回头|可以|能)|我也(?:这么|这样|能|可以)|"
    r"我(?:明天|以后|回头)?跟(?:老师|奶奶|爷爷|外婆|同学)说|告老师|考砸了?也说",
)
RE_MOM_EXCUSE_ANY = re.compile(
    r"善意|好心|随口|怕她|怕奶奶|为大人|大人.{0,4}(?:着想|需要)|工作需要|"
    r"不算|为了不让|报喜|礼貌|着想|不想让.{0,4}(?:担心|操心)|"
    r"不让.{0,3}(?:担心|操心)|特殊情况|两码事|不一样|分寸|你们还小",
)
RE_MOM_FLAT_REFUSE = re.compile(
    r"不行|不许|不可以|不准|当然不|想都别想|少来|你敢|哪能",
)
RE_LIE_SIDE_PLOT = re.compile(
    r"爸爸|加班|打游戏|作业|写完|三页|鱼腥|倒了.*醋|唠叨|夸奶奶",
)
RE_GARBAGE_FILLER = re.compile(
    r"[呵哈]{2,}|(?:呢|吗|啊|呀|啦|吧|嘛){2,}$|对不对呀真的|"
    r"了呢[了呀]|了呀[呢]|嘛了[呀]|了呢呀|"
    r"(?:了呢|了呀|嘛了|呢吧|呀呢|呢嘛)$",
)
RE_WEAK_TASTE_EYE = re.compile(r"汤汁|舀汤|舔勺|喝了一口汤|偷尝了汤|尝了汤")
RE_STRONG_TASTE_EYE = re.compile(
    r"勺子|勺上|尝菜|试吃|试菜|嘴角|油渍|油花|菜叶|三大勺|咽|黏黏",
)

def _dialogue_lines(story: dict) -> tuple[list[str], list[str]]:
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


def append_e_body_errors(story: dict, errors: list[str]) -> None:
    if resolve_story_type_code(story) != "E":
        return

    lines, speakers = _dialogue_lines(story)
    n = len(lines)
    if n < 8:
        errors.append("E类正文过短，不足以完成妈妈破功收束（至少约 8 句对白）")
        return

    topic_anchor = (
        str(story.get("conflict_core") or "")
        + str(story.get("theme") or "")
        + str(story.get("_theme") or "")
    )
    anchor = topic_anchor + (
        str(story.get("punchline_explain") or "")
        + str(story.get("setting") or "")
    )
    sleep_t = bool(RE_SLEEP_TOPIC.search(topic_anchor))
    snack_t = bool(RE_SNACK_TOPIC.search(topic_anchor))
    picky_t = (
        bool(RE_PICKY_TOPIC.search(topic_anchor))
        and not snack_t
        and not sleep_t
    )
    lie_t = (
        bool(RE_LIE_TOPIC.search(topic_anchor))
        and not snack_t
        and not sleep_t
        and not picky_t
    )
    all_text = "".join(lines)
    mom_early = "".join(
        ln
        for sp, ln in zip(speakers[: max(1, n // 2)], lines[: max(1, n // 2)])
        if sp == "妈妈"
    )
    if sleep_t and not snack_t and RE_SNACK_TOPIC.search(mom_early):
        if "九点" not in mom_early and "必须睡觉" not in mom_early:
            errors.append("E类睡觉主题禁串场立零食规矩")
    if snack_t and not sleep_t and RE_SLEEP_TOPIC.search(mom_early):
        errors.append("E类零食主题禁串场立睡觉规矩")

    if snack_t and not sleep_t:
        head_text = "".join(lines[: min(8, n)])
        if RE_WEAK_TASTE_EYE.search(head_text) and not RE_STRONG_TASTE_EYE.search(
            head_text,
        ):
            errors.append(
                "E类尝菜眼须可拍试吃（勺子/嘴角油），汤汁太弱勿当唯一现行",
            )

    if picky_t:
        rule_i = next(
            (
                i
                for i, (sp, ln) in enumerate(zip(speakers, lines))
                if sp == "妈妈" and RE_PICKY_MOM_RULE.search(ln)
            ),
            None,
        )
        eye_i = next(
            (
                i
                for i, (sp, ln) in enumerate(zip(speakers, lines))
                if sp in ("昭昭", "灿灿") and RE_PICKY_EYE.search(ln)
            ),
            None,
        )
        if speakers[0] != "妈妈" or not RE_PICKY_MOM_RULE.search(lines[0]):
            errors.append(
                "E类挑食须妈妈开场训孩子不能挑食"
                "（如「菜吃太少了，不能挑食」），再抓拨开",
            )
        elif rule_i is None or rule_i > 5:
            errors.append(
                "E类挑食前段须妈妈亲口立规矩（不准挑食/青菜都得吃），"
                "勿只说必须吃完却不点挑食",
            )
        elif eye_i is not None and eye_i < rule_i:
            errors.append(
                "E类挑食须先妈妈立「不许挑食」，再抓拨青菜现行；"
                "勿先质问拨开再立同名规矩（因果反了）",
            )
        if eye_i is not None:
            for i in range(eye_i + 1, min(eye_i + 4, n - 1)):
                if speakers[i] != "妈妈":
                    continue
                if RE_PICKY_RELECTURE.search(lines[i]):
                    errors.append(
                        "E类挑食抓现行后禁妈妈回训孩子不吃菜，"
                        "应开脱或由孩子假替妈解释",
                    )
                break
            # 全文须有开脱痕迹（妈妈自辩或孩子假替均可）
            if not (
                RE_PICKY_WAFFLE.search(all_text)
                or re.search(r"你不懂|放凉|大人|不一样|不算挑", all_text)
            ):
                errors.append(
                    "E类挑食抓现行后须有开脱"
                    "（妈妈自辩或孩子假替妈解释均可）",
                )
        if not RE_PICKY_EYE.search(all_text):
            errors.append(
                "E类挑食须有可拍现行（拨到碗边/拨开青菜）",
            )
        waffle_n = sum(
            1
            for sp, ln in zip(speakers, lines)
            if sp == "妈妈" and RE_PICKY_WAFFLE.search(ln)
        )
        if waffle_n >= 3:
            errors.append(
                "E类挑食妈妈开脱过多（晾着/配饭/等会儿宜≤2句一套加码）",
            )
        # 总句数/妈妈句数不再用「开脱≤2」这种口径硬卡，
        # 否则会误伤“句数略多但并未反复用晾着/配饭开脱”的好稿。
        # 保留极端上限防 runaway（仍以全局字数硬卡为主）。
        if n > 20:
            errors.append("E类挑食正文过长（不宜超 20 句）")
        if any(
            sp == "妈妈" and "不一样" in ln
            for sp, ln in zip(speakers, lines)
        ):
            errors.append("E类挑食禁妈妈当真用不一样开脱（孩子讽刺帮腔除外）")
        if RE_PICKY_PAD.search(all_text):
            errors.append(
                "E类挑食禁注水（数叶子/打自己脸/证明夹菜），"
                "中段用自套反例即可",
            )
        # 规矩只立一次（两次即拦，避免开场后再训）
        if sum(
            1
            for sp, ln in zip(speakers, lines)
            if sp == "妈妈" and RE_PICKY_MOM_RULE.search(ln)
        ) >= 2:
            errors.append("E类挑食禁重复立同一规矩（不许挑食只说一次）")
        if RE_SNACK_BLEED.search(all_text) or re.search(
            r"尝咸淡|不算吃零食|饭前不能吃零食",
            all_text,
        ):
            errors.append(
                "E类挑食禁尝菜/零食串场，只盯青菜拨开这一条线",
            )

    if lie_t:
        if not RE_LIE_PHYSICAL.search(all_text):
            errors.append(
                "E类说谎须有可拍实物反证（空饭锅/碗还干着/外卖盒/肚子咕咕），"
                "勿只口头对质",
            )
        self_i = next(
            (
                i
                for i in range(max(0, n - 6), n)
                if speakers[i] in ("昭昭", "灿灿")
                and RE_KID_SELF_APPLY.search(lines[i])
            ),
            None,
        )
        if self_i is None:
            errors.append(
                "E类说谎末段须孩子把妈妈逻辑套自己"
                "（那我跟奶奶说我考了一百分，也算善意的吧）",
            )
        else:
            mom_reply = next(
                (
                    lines[j]
                    for j in range(self_i + 1, n)
                    if speakers[j] == "妈妈"
                ),
                "",
            )
            if not RE_MOM_FLAT_REFUSE.search(mom_reply):
                errors.append(
                    "E类说谎孩子自套逻辑后，妈妈下一句须当场否掉"
                    "（那不行/不许/你敢），勿再另编借口",
                )
        mom_excuse_n = sum(
            1
            for sp, ln in zip(speakers, lines)
            if sp == "妈妈" and RE_MOM_EXCUSE_ANY.search(ln)
        )
        if mom_excuse_n >= 5:
            errors.append(
                "E类说谎妈妈开脱句过多（宜≤3句、同一套借口加码），"
                "勿一句一个新借口",
            )
        if RE_SNACK_BLEED.search(all_text):
            errors.append(
                "E类说谎主题禁尝菜串场（那一口/咽下去/尝咸淡等）",
            )
        # 「跟你们不一样」「这个……不一样」都是同一套开脱，只认「这/那不一样」会全漏
        if sum(
            1
            for sp, ln in zip(speakers, lines)
            if sp == "妈妈" and "不一样" in ln
        ) >= 2:
            errors.append("E类说谎禁不一样开脱复读（最多一次）")
        food_hits = len(RE_LIE_FOOD_ITEM.findall(all_text))
        if food_hits >= 3:
            errors.append("E类说谎主题禁堆菜品名灌水")
        rule_i = next(
            (
                i
                for i, ln in enumerate(lines)
                if speakers[i] == "妈妈" and RE_LIE_MOM_RULE.search(ln)
            ),
            None,
        )
        if rule_i is not None:
            for i in range(min(rule_i, 6)):
                if speakers[i] == "妈妈" and RE_LIE_WAFFLE.search(lines[i]):
                    errors.append(
                        "E类说谎须先妈妈立不能说谎，再开脱敷衍",
                    )
                    break
        for i, (sp, ln) in enumerate(zip(speakers, lines)):
            if sp not in ("昭昭", "灿灿") or not RE_KID_QUOTE_EAT.search(ln):
                continue
            mom_after = "".join(
                lines[j]
                for j in range(i + 1, n)
                if speakers[j] == "妈妈"
            )
            if RE_MOM_DENY_QUOTE.search(mom_after):
                errors.append(
                    "E类说谎禁妈妈否认孩子已引用的电话内容",
                )
                break
        # 「善意/那是」等换词复读交给人读审稿按语义判并扣分：
        # 关键词硬卡与字数下限互相拉扯，会把生成逼进死循环
        side_text = "".join(
            ln for ln in lines if not RE_KID_SELF_APPLY.search(ln)
        )
        side_hits = len(RE_LIE_SIDE_PLOT.findall(side_text))
        if side_hits >= 2:
            errors.append(
                "E类说谎禁叠爸爸/作业/鱼腥等支线，只盯电话吃饭这一谎",
            )
        for i, ln in enumerate(lines):
            if RE_GARBAGE_FILLER.search(ln):
                errors.append(f"E类对白[{i}]含无意义语气垫字")
                break

    if not lie_t:
        for i, ln in enumerate(lines):
            if RE_GARBAGE_FILLER.search(ln):
                errors.append(f"E类对白[{i}]含无意义语气垫字")
                break

    tail4 = "".join(lines[-4:])
    tail3 = "".join(lines[-3:])
    body = "".join(lines[: max(0, n - 4)])

    if RE_A_WHERE_DIFF.search(tail4) and (
        "那不一样" in tail4 or RE_A_CITE_CLOSE.search(tail4)
    ):
        errors.append(
            "E类收束勿写成 A 式末四拍；应走孩子追问闭环+妈妈破功",
        )
        return

    if not RE_MOM_RULE.search(body):
        errors.append(
            "E类前段须有妈妈立论/立规矩（应该、必须、听我的等）",
        )
        return

    if not RE_KID_LOOP.search(tail3) and not RE_KID_LOOP.search(tail4):
        errors.append(
            "E类末段须孩子用妈妈原话闭环反问（自己说/你刚才等）",
        )
        return

    last = lines[-1]
    last_sp = speakers[-1] if speakers else ""
    if last_sp != "妈妈":
        errors.append("E类末句须妈妈破功收场")
        return

    if not RE_SOFT_LAST.search(last) and not re.search(
        r"唉|行了|好吧|随便|说不通|行行行",
        last,
    ):
        errors.append(
            "E类末句妈妈须破功（唉/行了/好吧/随便/说不通等）",
        )
        return

    if RE_MOM_WAFFLE.search(tail3) and not RE_KID_LOOP.search(tail3):
        errors.append(
            "E类妈妈改口后须紧跟孩子闭环反问，勿只妈妈单方面狡辩",
        )
