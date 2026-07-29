"""E 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import score_opening_cinematic

RE_SLEEP_TOPIC = re.compile(r"睡觉|九点|早睡|刷手机|卧床|被窝|挂钟")
RE_SLEEP_MOM_RULE = re.compile(r"必须睡觉|九点了|快去躺|得睡觉")
RE_SNACK_TOPIC = re.compile(r"零食|尝菜|偷吃|饭前不吃|试吃|试菜")
RE_PICKY_TOPIC = re.compile(r"挑食|青菜|拨到碗边|拨开青菜")
RE_PICKY_MOM_RULE = re.compile(
    r"不准挑食|不许挑食|不能挑食|别挑食|挑食不行|"
    r"青菜.{0,6}(?:必须|得|要)吃|饭菜都得吃",
)
RE_PICKY_EYE = re.compile(r"拨到|拨开|碗边|拨了.{0,4}青菜")
RE_LIE_TOPIC = re.compile(r"说谎|撒谎|敷衍|诚实|假话|骗")
RE_LIE_MOM_RULE = re.compile(r"不能说谎|不许说谎|要诚实|别说谎|老实")
RE_LIE_WAFFLE = re.compile(
    r"不是敷衍|善意.{0,2}谎|让奶奶放心|特殊情况|为了不让|不是骗|"
    r"不算撒谎|不算说谎",
)
RE_WEAK_TASTE_EYE = re.compile(r"汤汁|舀汤|舔勺|喝了一口汤|偷尝了汤|尝了汤")
RE_STRONG_TASTE_EYE = re.compile(
    r"勺子|勺上|尝菜|试吃|试菜|嘴角|油渍|油花|菜叶|三大勺|咽下去|腮帮|黏黏",
)
# 开场禁止妈妈已破功
E_OPENING_SPOILER_RE = re.compile(
    r"行行行|算你说得对|随便你|说不通|唉算了|"
    r"妈妈你也|你自己说",
)
# 勿像 A/B/C 开场
E_OPENING_A_RE = re.compile(
    r"那不一样|哪里不一样|检查不算|刷牙太快",
)
E_OPENING_B_RE = re.compile(
    r"嘘|别告诉|咱俩|完蛋|妈妈来了",
)
E_OPENING_C_RE = re.compile(
    r"不公平|谁先拿|你输了",
)
E_OPENING_ANCHOR_RE = re.compile(
    r"妈妈|妈|讲理|规矩|应该|不行|怎么又|我说|"
    r"挂钟|嘴角|勺子|屏幕|被窝|亮着|电话|奶奶|"
    r"青菜|挑食|碗边|拨",
)
# 孩子句旁白定格式：地点名词起句（非「刚才在…」回忆式）
RE_CHILD_NARRATOR_PREFIX = re.compile(
    r"^(?:客厅|厨房|卧室|饭桌|灶台|沙发|门口)(?:饭桌前?|里|旁|边|门口)?[，,]",
)
RE_CHILD_QUESTION = re.compile(r"[？?]|为什么|怎么|啥|吗|呢")
RE_CAMERA_NARRATION = re.compile(
    r"刚离开嘴边|勺子刚离开|还躺着刷|正靠在|正躺在",
)


def append_e_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
    setting: str = "",
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "E":
        return
    for i, item in enumerate(normalized):
        line = item["line"]
        if E_OPENING_SPOILER_RE.search(line):
            errors.append(
                f"opening[{i}] E类禁止开场妈妈已破功"
                "（行行行/算你对等），破功留给正文末句",
            )
            break
        if E_OPENING_B_RE.search(line):
            errors.append(
                f"opening[{i}] E类开场勿像B密谋（嘘/别告诉/完蛋），"
                "应是找妈妈讲理或挨训前场面",
            )
            break
        if E_OPENING_C_RE.search(line):
            errors.append(
                f"opening[{i}] E类开场勿像C争公平，应是妈妈/孩子要讲道理",
            )
            break
        if E_OPENING_A_RE.search(line):
            errors.append(
                f"opening[{i}] E类开场勿像A姐弟末四拍（那不一样等）",
            )
            break
        sp = str(item.get("speaker") or "").strip()
        if sp in ("昭昭", "灿灿"):
            narr = RE_CHILD_NARRATOR_PREFIX.search(line)
            quest = RE_CHILD_QUESTION.search(line)
            camera = RE_CAMERA_NARRATION.search(line)
            if narr and (camera or not quest):
                errors.append(
                    f"opening[{i}] E类孩子开场勿旁白定格式"
                    "（宜「刚才在客厅，妈你为什么…」）",
                )
                break
            if camera and not quest:
                errors.append(
                    f"opening[{i}] E类孩子开场勿镜头描写"
                    "（宜问妈「你为什么把勺子放嘴边」）",
                )
                break

    joined = "".join(d.get("line", "") for d in normalized)
    ctx = (conflict_core or "") + (setting or "") + joined
    if RE_SLEEP_TOPIC.search(ctx) and not RE_SLEEP_MOM_RULE.search(joined):
        errors.append(
            "E类睡觉主题开场须有妈妈立睡觉规矩"
            "（如「九点了必须睡觉」）",
        )
    snack_t = bool(RE_SNACK_TOPIC.search(ctx))
    sleep_t = bool(RE_SLEEP_TOPIC.search(ctx))
    picky_t = bool(RE_PICKY_TOPIC.search(ctx)) and not snack_t
    if picky_t:
        first = normalized[0] if normalized else {}
        first_sp = first.get("speaker", "")
        first_ln = first.get("line", "")
        rule_i = next(
            (
                i
                for i, d in enumerate(normalized)
                if d.get("speaker") == "妈妈"
                and RE_PICKY_MOM_RULE.search(d.get("line", ""))
            ),
            None,
        )
        # 孩子点名妈妈拨青菜现行
        eye_i = next(
            (
                i
                for i, d in enumerate(normalized)
                if d.get("speaker") in ("昭昭", "灿灿")
                and RE_PICKY_EYE.search(d.get("line", ""))
            ),
            None,
        )
        if first_sp != "妈妈" or not RE_PICKY_MOM_RULE.search(first_ln):
            errors.append(
                "E类挑食开场须妈妈先训孩子不能挑食"
                "（如「菜吃太少了，不能挑食」），再孩子抓拨开",
            )
        elif eye_i is not None and rule_i is not None and eye_i < rule_i:
            errors.append(
                "E类挑食开场须先立「不许挑食」，再点拨青菜；"
                "勿先问拨开再答不许挑食（因果反了）",
            )
    if snack_t and not sleep_t:
        if RE_WEAK_TASTE_EYE.search(joined) and not RE_STRONG_TASTE_EYE.search(
            joined,
        ):
            errors.append(
                "E类尝菜开场眼须可拍试吃（勺子/嘴角油），汤汁太弱",
            )
        if re.search(r"你不是说|不是说饭前|饭前不能吃零食|不能吃零食", joined):
            if not any(
                d.get("speaker") == "妈妈"
                and re.search(r"不能吃零食|不能吃零|饭前", d.get("line", ""))
                for d in normalized
            ):
                errors.append(
                    "E类零食开场勿孩子预支规矩，须妈妈亲口立「饭前不能吃零食」",
                )
    lie_t = bool(RE_LIE_TOPIC.search(ctx)) and not snack_t and not sleep_t
    if lie_t:
        # 正文已硬性要求妈妈亲口立「不能说谎」，开场只有两句、重试仅 3 次，
        # 再要求规矩必须出现在开场会把整篇逼废，这里只拦「开口先狡辩」。
        mom_lines = [
            str(d.get("line") or "")
            for d in normalized
            if d.get("speaker") == "妈妈"
        ]
        if mom_lines:
            first_mom = mom_lines[0]
            if RE_LIE_WAFFLE.search(first_mom) and not RE_LIE_MOM_RULE.search(
                first_mom,
            ):
                errors.append(
                    "E类说谎开场勿妈妈先狡辩，须先立不能说谎",
                )


def _opening_body_overlap(a: str, b: str) -> bool:
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    n = min(len(left), len(right), 8)
    return n >= 4 and left[:n] == right[:n]


def _first_body_line_after_opening(story: dict) -> str:
    opening = story.get("discovery_opening")
    dialogue = story.get("dialogue")
    if not isinstance(opening, list) or not isinstance(dialogue, list):
        return ""
    o_lines = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    d_lines = [
        str(d.get("line") or "").strip()
        for d in dialogue
        if isinstance(d, dict)
    ]
    k = 0
    while (
        k < len(o_lines)
        and k < len(d_lines)
        and _opening_body_overlap(o_lines[k], d_lines[k])
    ):
        k += 1
    return d_lines[k] if k < len(d_lines) else ""


def score_opening_quality(story: dict) -> tuple[int, list[str], list[str]]:
    pros: list[str] = []
    cons: list[str] = []
    opening = story.get("discovery_opening")
    if not isinstance(opening, list) or not opening:
        return -5, pros, ["E开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    joined = "".join(lines_o)
    pts = 0

    if E_OPENING_SPOILER_RE.search(joined):
        cons.append("E开场妈妈已破功")
        pts -= 5
    elif E_OPENING_B_RE.search(joined):
        cons.append("E开场偏B密谋")
        pts -= 4
    elif E_OPENING_C_RE.search(joined):
        cons.append("E开场偏C争公平")
        pts -= 4
    elif E_OPENING_ANCHOR_RE.search(joined):
        pts += 3
        pros.append("E开场锚定讲理场面")

    for d in opening:
        if not isinstance(d, dict):
            continue
        sp = str(d.get("speaker") or "").strip()
        ln = str(d.get("line") or "").strip()
        if sp in ("昭昭", "灿灿"):
            narr = RE_CHILD_NARRATOR_PREFIX.search(ln)
            quest = RE_CHILD_QUESTION.search(ln)
            camera = RE_CAMERA_NARRATION.search(ln)
            if narr and (camera or not quest):
                cons.append("E开场旁白定格式")
                pts -= 4
                break
            if camera and not quest:
                cons.append("E开场镜头描写")
                pts -= 3
                break

    first_body = _first_body_line_after_opening(story)
    if first_body and _opening_body_overlap(lines_o[-1], first_body):
        cons.append("E开场与正文首句重复")
        pts -= 3

    cin_pts, cin_pros, cin_cons = score_opening_cinematic(lines_o)
    pts += cin_pts
    pros.extend(cin_pros)
    cons.extend(cin_cons)

    return max(-8, min(8, pts)), pros, cons


def opening_revision_hint(issue: str) -> str | None:
    if "开场" not in issue and "E开场" not in issue:
        return None
    return (
        f"【开场·E】{issue}。"
        "挑食：妈妈开场训不能挑食，再孩子抓拨开；禁拨开→不许挑食。"
        "说谎题：孩子问电话内容→妈妈先立不能说谎→再开脱；"
        "孩子句宜口语问妈；勿旁白定格式；勿尝菜串场；勿妈妈先狡辩。"
    )
