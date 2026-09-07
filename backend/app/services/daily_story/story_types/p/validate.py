"""P 类正文硬卡（道具整蛊互整；抽象不变量，禁单篇词表）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

# 抽象：挑战/递物 → 回敬 → 认怂；勿绑芥末/卷饼等单篇道具名
RE_OFFER = re.compile(r"尝尝|试试|给你|挑战|这[卷口块份]|递")
# 发起人识别：首发递物/怂恿，排除「再试试」回敬
RE_INIT_OFFER = re.compile(r"尝尝|给你|挑战|这[卷口块份].*香|递")
RE_BRACE_OR_HIT = re.compile(
    r"还行|没事|不辣|硬撑|呛|灌水|眼泪|脸|辣|苦"
)
RE_RETALIATE = re.compile(r"再试试|也给你|轮到你|特意|回敬|加[了料]|专门")
RE_SURRENDER = re.compile(r"认输|不了不了|不敢再|算了|我怂|服了|不试了")
RE_C_BOOMERANG = re.compile(r"你刚说|你说的|那不一样|哪里不一样|凭什么你|归谁")
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|自相矛盾")
RE_G_SOFT = re.compile(r"擦药|撑腰|说好了|心疼|护姐|护短|给你擦")
RE_F_THREAT_ONLY = re.compile(r"你敢|再说|吼什么|讨厌呢|别吵")
RE_I_SOUL = re.compile(r"爱学习|你爱吗|灵魂|拷问")
RE_C_LABEL = re.compile(r"回旋镖")
RE_PAD_TAIL = re.compile(
    r"马上给我挪开|我才不怕呢|不许再耍赖|我偏就不信|了呢了呀|着呢了呀"
)


def _rows(story: dict) -> list[tuple[str, str]]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    out: list[tuple[str, str]] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        ln = str(item.get("line") or "").strip()
        if ln:
            out.append((sp, ln))
    return out


def append_p_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "P":
        return
    rows = _rows(story)
    if len(rows) < 8:
        return

    lines = [ln for _, ln in rows]
    speakers = [sp for sp, _ in rows]
    body = "".join(lines)
    mid = "".join(lines[: max(1, len(lines) * 2 // 3)])
    tail4 = "".join(lines[-4:])
    core = str(story.get("conflict_core") or "")
    closing = str(story.get("closing_intent") or "")
    key = str(story.get("key") or "")
    blob = f"{core}{body}"

    if not RE_OFFER.search(blob):
        errors.append("P类：须有下料/挑战/递物（尝尝/试试/给你等）")
    if not RE_BRACE_OR_HIT.search(body) and not RE_RETALIATE.search(body):
        errors.append("P类：须有硬撑/中招或回敬加码迹象")
    if not RE_RETALIATE.search(mid) and not RE_RETALIATE.search(body):
        errors.append("P类：中段须有回敬加码（再试试/也给你/轮到你等）")
    if not RE_SURRENDER.search(tail4) and not RE_SURRENDER.search(body):
        errors.append("P类：收束须认怂/不敢再试（认输/不了不了等）")

    offer_idxs = [
        i for i, ln in enumerate(lines) if RE_INIT_OFFER.search(ln)
    ]
    if not offer_idxs:
        offer_idxs = [i for i, ln in enumerate(lines) if RE_OFFER.search(ln)]
    surrender_idxs = [i for i, ln in enumerate(lines) if RE_SURRENDER.search(ln)]
    if offer_idxs and surrender_idxs:
        init_sp = speakers[offer_idxs[0]]
        sur_sp = speakers[surrender_idxs[-1]]
        if init_sp and sur_sp and init_sp != sur_sp:
            errors.append(
                "P类：认怂方须为挑战发起人（首发下料方），禁止后半颠倒认怂"
            )

    for name in ("昭昭", "灿灿"):
        if f"{name}认" in closing or f"{name}认输" in closing:
            if surrender_idxs:
                sur_sp = speakers[surrender_idxs[-1]]
                if sur_sp and sur_sp != name:
                    errors.append(
                        f"P类：closing_intent 认怂人为{name}，对白须一致"
                    )

    if (
        len(RE_F_THREAT_ONLY.findall(body)) >= 3
        and not RE_RETALIATE.search(body)
        and not RE_OFFER.search(body)
    ):
        errors.append("P类：勿写成纯口头威胁链（宜道具整蛊回敬，或改标 F）")

    if RE_C_LABEL.search(f"{key}{punch}"):
        errors.append("P类：key/punchline 勿写回旋镖（易误套 C）")
    pad_n = sum(1 for ln in lines if RE_PAD_TAIL.search(ln))
    if pad_n >= 3:
        errors.append("P类：正文勿堆垫字尾巴，保持可说出口的儿童对白")

    if RE_C_BOOMERANG.search(tail4):
        errors.append("P类：末段勿套 C 回旋镖收束")
    if RE_A_BACKFIRE.search(tail4):
        errors.append("P类：末段勿 A 式反噬/破功链")
    if RE_G_SOFT.search(tail4):
        errors.append("P类：末段勿 G 式暖收（擦药/撑腰等）")
    if RE_I_SOUL.search(body):
        errors.append("P类：勿写成 I 灵魂拷问")
