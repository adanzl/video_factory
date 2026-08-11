"""D 类发现开场校验与开场质量分。"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import score_opening_cinematic

# 开场禁止已回旋镖/叮嘱方已破规
D_OPENING_SPOILER_RE = re.compile(
    r"你自己说|你刚才说|你也破了|你也碰了|回旋镖|"
    r"我说不许你|你不也|算你狠|谁让你",
)
# 勿像 A 管教末四拍、C 争公平
D_OPENING_A_RE = re.compile(
    r"那不一样|哪里不一样|听我的|我是姐姐你得|检查不算",
)
D_OPENING_C_RE = re.compile(
    r"不公平|谁先拿|一人一半|凭什么你拿",
)
# 正向：叮嘱/待执行场面
D_OPENING_ANCHOR_RE = re.compile(
    r"别碰|不许|轻点|慢点|慢慢|按|照|叠|鞋带|收拾|弄|叮嘱|规矩|系紧|别洒|整齐|擦|端|晃|"
    r"别浇|别多|浇|花|夹|晾|关|门|玩具|箱|收|抽屉|书桌|悠着|"
    r"挂|洗|摆|整理|扫|装|倒|铺|系|穿|搬|拿",
)
# 起因/邀约：开场须交代「为什么要做这件事」
# 含场面陈述（鞋带又松了 / 土干裂了）——不必死抠「咱俩一起」
D_OPENING_INVITE_RE = re.compile(
    r"咱俩|咱们|一起|我们俩|帮我|帮你|我来|你来|要不|走吧|吧$|好啊|好吧|行啊|"
    r"又松|又散|松了|散了|要出门|出门了|这次出门|还没出门|穿鞋|教你|"
    r"干裂|堆了一|歪着|门缝|掰不动|乱七八糟|倒了",
)
# 将要出门/去做 vs 已走完：有「走两步就」须用「还没」钉时间
_RE_OPENING_GOING = re.compile(r"出门|穿鞋|要走|快走|去上学")
_RE_OPENING_WALKED = re.compile(r"走两步就|走了两步|走过就|刚走就")
_RE_OPENING_NOT_YET = re.compile(r"还没")
# 执行者错位：D 正文永远昭昭动手，灿灿开场说「看我做」正文必穿帮
_RE_EXEC_MISMATCH = re.compile(r"看我|瞧我|给你看|我先来|我示范|我做给")
# 裸地点短语当独立小句（报幕腔）：「好啊，客厅茶几上，你手里的…」
_RE_BARE_PLACE_CLAUSE = re.compile(
    r"(?:^|[，,])(?:客厅|厨房|卧室|玄关|阳台|门口|餐厅|书房|洗手间)"
    r"[^，,。！？]{0,4}[，,]",
)

# 开场凭空新造、与 punchline 无关的障碍（不在 conflict_core/setting 里）。
def _twist_tail(conflict_core: str) -> str:
    """core「X被读成Y」的 Y——歪读做法，开场说破=剧透。"""
    core = (conflict_core or "").strip()
    if "被读成" not in core:
        return ""
    return core.split("被读成", 1)[1].strip()


def _leaks_twist(joined: str, conflict_core: str) -> bool:
    tail = _twist_tail(conflict_core)
    if len(tail) < 4:
        return False
    return any(tail[i : i + 4] in joined for i in range(len(tail) - 3))


def _shares_core_bigram(joined: str, conflict_core: str) -> bool:
    """开场与 conflict_core 共享 ≥2 字连续片段即视为点到主题。

    家务动词表只认旧主题；主题词以 core 为准，勿枚举。
    """
    compact = "".join(re.findall(r"[\u4e00-\u9fff]+", conflict_core or ""))
    for noise in ("被读成", "读成", "昭昭", "灿灿", "妈妈"):
        compact = compact.replace(noise, "")
    for i in range(len(compact) - 1):
        if compact[i : i + 2] in joined:
            return True
    return False


def append_d_opening_errors(
    normalized: list[dict],
    *,
    type_code: str | None,
    errors: list[str],
    conflict_core: str = "",
) -> None:
    code = (type_code or "").strip().upper()[:1]
    if code != "D":
        return
    for i, item in enumerate(normalized):
        if str(item.get("speaker") or "").strip() == "妈妈":
            errors.append(
                f"opening[{i}] D类主戏姐弟，开场禁止妈妈说话（留给E类）",
            )
            break
    # 末句 speaker 须昭昭：D 开场=灿灿邀约+昭昭答应报场面；
    # 末句若是灿灿，拼正文时接缝同人会把灿灿立规句当连说吞掉（key_line 丢失）
    if normalized and normalized[-1]["speaker"] == "灿灿":
        errors.append(
            "D开场末句须昭昭答应并报场面（第1句灿灿邀约、第2句昭昭答应），"
            "禁止末句仍是灿灿——否则拼正文会把灿灿立规句当连说吞掉"
        )
    for i, item in enumerate(normalized):
        if str(item.get("speaker") or "").strip() != "灿灿":
            continue
        if _RE_EXEC_MISMATCH.search(item["line"]):
            errors.append(
                f"opening[{i}] D开场执行者错位：正文由昭昭动手执行，"
                "邀约须把活交给昭昭（你来试试/帮我把…/我教你），"
                "禁止灿灿「看我做/我做给你看」",
            )
            break
    for i, item in enumerate(normalized):
        line = item["line"]
        if D_OPENING_SPOILER_RE.search(line):
            errors.append(
                f"opening[{i}] D类禁止开场已回旋镖或叮嘱方已破规"
                "（你自己说/你也碰了等），留给正文末段",
            )
            break
        if D_OPENING_A_RE.search(line):
            errors.append(
                f"opening[{i}] D类开场勿像A末四拍管教"
                "（那不一样/听我的等），应是叮嘱将执行现场",
            )
            break
        if D_OPENING_C_RE.search(line):
            errors.append(
                f"opening[{i}] D类开场勿像C争公平（不公平/谁先拿），"
                "应是「别这样弄/按我说的」类叮嘱前场面",
            )
            break
    # 须点到即将一起做的事（邀约或叮嘱均可），勿事后质问当开场；
    # 词表命不中时，与 conflict_core 共享片段同样算点到（主题勿枚举）
    if normalized:
        joined = "".join(item["line"] for item in normalized)
        if _leaks_twist(joined, conflict_core):
            errors.append(
                "opening 泄歪读（开场就把读歪的做法说破），"
                "开场只许点规矩/实物，歪读留给正文由昭昭逐步演",
            )
        if not D_OPENING_ANCHOR_RE.search(joined) and not _shares_core_bigram(
            joined, conflict_core,
        ):
            errors.append(
                "opening[0:2] D类开场须点到即将做的那件事"
                "（含主题里的实物/动词），勿事后质问（谁让你…）",
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
        return -5, pros, ["D开场缺失"]

    lines_o = [
        str(d.get("line") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    joined = "".join(lines_o)
    pts = 0

    if _leaks_twist(joined, str(story.get("conflict_core") or "")):
        cons.append("D开场泄歪读")
        pts -= 4

    speakers_o = [
        str(d.get("speaker") or "").strip()
        for d in opening
        if isinstance(d, dict)
    ]
    if any(
        sp == "灿灿" and _RE_EXEC_MISMATCH.search(ln)
        for sp, ln in zip(speakers_o, lines_o)
    ):
        cons.append("D开场执行者错位（正文昭昭动手，勿灿灿看我做）")
        pts -= 4
    if any(_RE_BARE_PLACE_CLAUSE.search(ln) for ln in lines_o):
        cons.append("D开场裸地点报幕腔（地点须嵌进物件短语）")
        pts -= 2

    if D_OPENING_SPOILER_RE.search(joined):
        cons.append("D开场已像末段回旋镖")
        pts -= 5
    elif D_OPENING_A_RE.search(joined):
        cons.append("D开场偏A管教")
        pts -= 4
    elif D_OPENING_C_RE.search(joined):
        cons.append("D开场偏C争公平")
        pts -= 4
    elif D_OPENING_ANCHOR_RE.search(joined):
        pts += 3
        pros.append("D开场锚定叮嘱物")

    if D_OPENING_INVITE_RE.search(joined):
        pts += 2
        pros.append("D开场交代起因")
    else:
        cons.append("D开场缺起因（没说为什么做这件事）")
        pts -= 2

    # 将出门 + 「走两步就…」且无「还没」→ 时间线拧着（观感扣，不硬拦）
    if len(lines_o) >= 2:
        first, second = lines_o[0], lines_o[1]
        if _RE_OPENING_GOING.search(first) and _RE_OPENING_WALKED.search(second):
            if _RE_OPENING_NOT_YET.search(second):
                pts += 1
                pros.append("D开场时间线自洽")
            else:
                cons.append("D开场时间线拧着（将出门却像已走过）")
                pts -= 3

    first_body = _first_body_line_after_opening(story)
    if first_body and _opening_body_overlap(lines_o[-1], first_body):
        cons.append("D开场与正文首句重复")
        pts -= 3

    cin_pts, cin_pros, cin_cons = score_opening_cinematic(lines_o)
    pts += cin_pts
    pros.extend(cin_pros)
    cons.extend(cin_cons)

    return max(-8, min(8, pts)), pros, cons


def opening_revision_hint(issue: str) -> str | None:
    if "开场" not in issue and "D开场" not in issue:
        return None
    return (
        f"【开场·D】{issue}。"
        "须 2 句：第1句一方**发起邀约交代起因**（这次出门再教你系/咱俩一起挂衣服吧），"
        "第2句另一方**答应+报地点与眼前场面**（地点已由第1句交代时，"
        "可直接表动作意图，如「好的，我这就去关」；此时勿硬接场景尾巴）；"
        "逻辑优先：活须交到昭昭手里（禁灿灿「看我做」）；"
        "地点嵌进物件短语，禁裸地点小句报幕；隐患须真隐患；"
        "两句同一时间线：将要做 ≠ 已经做过；隐患用「还没/又/一…就」；"
        "勿回旋镖/不公平/那不一样/事后质问。"
    )
