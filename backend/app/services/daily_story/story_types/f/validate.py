"""F 类正文硬卡（互呛加码收束，非 B/G/C/A）。"""

from __future__ import annotations

import re
import hashlib
import json
from typing import Any

from app.services.daily_story.story_types import parse_story_type_code

RE_THREAT = re.compile(
    r"再说|试试|你敢|讨厌|哼|吼什么|别吵",
)
RE_ESCALATION = re.compile(
    r"还.{0,4}呢|吼|啊{2,}|更|再来| louder",
)
RE_STALE_OR_YIELD = re.compile(
    r"不跟你|不理你|谁也不|爱咋|算了|怂|不敢|露怯|"
    r"回屋|回房间|找妈妈|评理|别追|服了|认输|快走",
)
RE_EXTERNAL_PIVOT = re.compile(
    r"拍|镜头|偷拍|闭嘴|尴尬|茄子|闹着玩|丢人",
)
RE_B_ALLIANCE_TAIL = re.compile(
    r"一伙|一致对外|甩锅|露馅|瞒妈|别告诉妈|分工|你望风",
)
RE_G_SOFT = re.compile(
    r"擦药|撑腰|说好了|心疼|护姐|护短|给你擦",
)
RE_C_BOOMERANG = re.compile(
    r"你刚才说|你刚说|你说的|凭什么你|你先选|归谁",
)
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|哪里不一样")
RE_H_RECONCILE = re.compile(r"和好|和解|调解|别吵了|咱们别吵|别吵了吧")
RE_B_PERFORM_TAIL = re.compile(
    r"团结|好姐弟|说定了|多团结|永远是一伙|谁欺负你我就",
)
# seed 未落地的零食/分物（抽象高发 invent，非按单篇剧情）
RE_SNACK_INVENT = re.compile(
    r"薯片|零食|糖果|饼干|巧克力|蛋糕|酸奶|可乐|果汁|奶茶|冰棍|辣条|风车",
)
# 外部打断后「商量应对镜头」式 staging（抽象，非单篇词表）
RE_F_CAMERA_STAGING = re.compile(
    r"数三二一|一起笑|摆个笑脸|摆笑脸|一起瞪|你站我旁边|"
    r"看看谁在拍|先看看谁|他应该|希望他|满意了吧|别烦我们",
)
RE_F_BROKEN_ELLIPSIS = re.compile(
    r"^(呵呵|嘿嘿)[…\.。！!]*$|^(呵呵|嘿嘿)…你听着|^…你听着",
)
RE_F_BROKEN_EXCLAIM = re.compile(r"啊{2,}了啊|啊什么了啊")
RE_F_PAD_STACK = re.compile(
    r"了呢了呀|了呢呀|了呀呢|好不好了呀|着呢了呀|呢呢|你呀呢|啊呢",
)
RE_F_PIVOT_TRIGGER = re.compile(r"拍我们|偷拍|有人拍|镜头|录像")

F_SOURCE_ASPECTS = ("conflict", "escalation", "standoff", "closing")


def source_f_binding(story: dict) -> str:
    # 表情等制作字段的归一化不改变争执结构；换词、换角色或换来源才需要重新核验。
    dialogue = [{"speaker": r.get("speaker"), "line": r.get("line")} for r in story.get("dialogue") or []]
    payload = [story.get("source_raw"), story.get("source_role_mapping"), dialogue]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def source_f_audit_error(story: dict, items: Any) -> str:
    """结构阶段的证据必须来自当前全文和原文；语义由独立审核分别判断。"""
    rows = story.get("dialogue") or []
    source = str(story.get("source_raw") or "")
    if not isinstance(items, list) or len(items) != len(F_SOURCE_ASPECTS):
        return "F来源结构审核须完整给出互呛、升级、僵持、中止收束四项"
    previous = 0
    for aspect, item in zip(F_SOURCE_ASPECTS, items):
        if not isinstance(item, dict):
            return "F来源结构审核项须为对象"
        no = item.get("line")
        if (item.get("aspect") != aspect or type(no) is not int or not previous < no <= len(rows)
                or type(item.get("pass")) is not bool):
            return "F来源结构审核须按四阶段顺序给出不同合法行号和布尔判定"
        if aspect == "closing" and no < len(rows) - 2:
            return "F中止收束须发生在末三句"
        quote, source_quote = str(item.get("quote") or ""), str(item.get("source_quote") or "")
        if len(quote) < 2 or quote not in str(rows[no - 1].get("line") or ""):
            return f"F来源结构审核 {aspect} 的 quote 不在第{no}句；须按对白标注行号逐字引用"
        if len(source_quote) < 4 or source_quote not in source:
            from difflib import get_close_matches

            fragments = [s for s in re.split(r'[：“”]|(?<=[。！？；])', source) if len(s) >= 4]
            nearest = get_close_matches(source_quote, fragments, n=1, cutoff=0.35)
            hint = f"；相近原文为{nearest[0]!r}（仅供重新核验，不能据此认定阶段成立）" if nearest else ""
            return (f"F来源结构审核 {aspect} 的 source_quote={source_quote!r}不在原始素材；"
                    "须逐字引用，不得删中间的语气词、省略号或改称谓" + hint)
        if not item.get("reason"):
            return f"F来源结构审核 {aspect} 缺少判定依据"
        previous = no
    return ""


def source_f_structure_valid(story: dict) -> bool:
    proof = story.get("gold_f_source_structure")
    return bool(story.get("source_link_review") and story.get("story_type") == "F"
                and isinstance(proof, dict) and proof.get("binding") == source_f_binding(story)
                and not source_f_audit_error(story, proof.get("items"))
                and all(item["pass"] for item in proof["items"]))


def _build_seed_haystack(
    *,
    dialogue_seed: list[Any] | None = None,
    beat_chain: list[Any] | None = None,
    beat: list[Any] | None = None,
    conflict_text: str = "",
    closing_intent: str = "",
    object_text: str = "",
    mechanism_text: str = "",
) -> str:
    parts: list[str] = [
        conflict_text,
        closing_intent,
        object_text,
        mechanism_text,
    ]
    for row in dialogue_seed or []:
        if isinstance(row, dict):
            parts.append(str(row.get("intent") or row.get("line") or ""))
        else:
            parts.append(str(row))
    for row in beat_chain or []:
        if isinstance(row, dict):
            parts.append(str(row.get("intent") or row.get("beat") or ""))
        else:
            parts.append(str(row))
    for row in beat or []:
        parts.append(str(row))
    return "".join(parts)


def _external_pivot_index(lines: list[str]) -> int | None:
    for i, ln in enumerate(lines):
        if RE_F_PIVOT_TRIGGER.search(ln):
            return i
    return None


def _story_type_f(story: dict) -> bool:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    return code == "F"


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


def append_f_body_errors(story: dict, errors: list[str]) -> None:
    if not _story_type_f(story):
        return
    lines, _speakers = _lines_and_speakers(story)
    if len(lines) < 10:
        return

    body = "".join(lines)
    mid = "".join(lines[: max(1, len(lines) * 2 // 3)])
    tail4 = "".join(lines[-4:])
    threat_hits = len(RE_THREAT.findall(mid))
    esc_hits = len(RE_ESCALATION.findall(mid))

    source_structure = source_f_structure_valid(story)
    if threat_hits < 2 and not source_structure:
        errors.append("F类：中段须至少两轮互呛/威胁（你再说/试试/还…呢等）")
    if esc_hits < 1 and not source_structure:
        errors.append("F类：中段须有加码升级（吼/还…呢/啊啊等）")
    has_close = (
        RE_STALE_OR_YIELD.search(tail4)
        or RE_EXTERNAL_PIVOT.search(tail4)
    )
    if not has_close and not source_structure:
        errors.append(
            "F类：末段须僵持/露怯或外部打断收束（不跟你玩/偷拍/尴尬等）"
        )
    if RE_B_ALLIANCE_TAIL.search(tail4) and not RE_EXTERNAL_PIVOT.search(tail4):
        errors.append("F类：末段勿 B 式结盟甩锅/一伙表演（无外部打断时）")
    if RE_B_PERFORM_TAIL.search(tail4):
        errors.append("F类：末段勿 B/G 式团结表演堆砌（好姐弟/说定了等）")
    if RE_H_RECONCILE.search(tail4):
        errors.append("F类：末段勿 H 式和好调解")
    if RE_G_SOFT.search(tail4):
        errors.append("F类：末段勿 G 式暖收（擦药/撑腰等）")
    if RE_C_BOOMERANG.search(tail4):
        errors.append("F类：末段勿 C 式回旋镖戳穿")
    if RE_A_BACKFIRE.search(tail4):
        errors.append("F类：末段勿 A 式反噬/破功链")


def append_f_align_issues(
    rows: list[dict],
    issues: list[dict],
    *,
    mechanism: str = "",
    dialogue_seed: list[Any] | None = None,
    beat_chain: list[Any] | None = None,
    beat: list[Any] | None = None,
    closing_intent: str = "",
    conflict_text: str = "",
    object_text: str = "",
    mechanism_text: str = "",
    story: dict | None = None,
) -> None:
    """gold_chat 对齐：F 类抽象 invariant（非逐篇剧情）。"""
    lines = [
        str(row.get("line") or "").strip()
        for row in rows
        if str(row.get("line") or "").strip()
    ]
    if len(lines) < 8:
        return
    n = len(lines)
    mid = "".join(lines[: max(1, n * 2 // 3)])
    tail6 = "".join(lines[-6:])
    tail4 = "".join(lines[-4:])
    mech = str(mechanism or "").strip().upper()

    source_structure = bool(story and source_f_structure_valid(story))
    if len(RE_THREAT.findall(mid)) < 2 and not source_structure:
        issues.append(
            {
                "lines": list(range(1, min(6, n) + 1)),
                "kind": "保真-F互呛",
                "desc": "中段互呛/威胁不足（须至少两轮）",
                "fix": "补你再说/试试/还…呢等互呛，再加码",
            }
        )
    if not RE_ESCALATION.search(mid) and not source_structure:
        issues.append(
            {
                "lines": list(range(2, min(8, n) + 1)),
                "kind": "保真-F加码",
                "desc": "中段缺互呛加码升级",
                "fix": "补吼叫/镜像回怼/啊啊等等势抬升",
            }
        )
    if not source_structure and not (
        RE_STALE_OR_YIELD.search(tail4) or RE_EXTERNAL_PIVOT.search(tail4)
    ):
        issues.append(
            {
                "lines": list(range(max(1, n - 3), n + 1)),
                "kind": "保真-F收束",
                "desc": "末段缺僵持/露怯或外部打断收束",
                "fix": "末段补不跟你玩/尴尬微笑/偷拍闭嘴等",
            }
        )
    if RE_B_ALLIANCE_TAIL.search(tail4) and not RE_EXTERNAL_PIVOT.search(tail4):
        issues.append(
            {
                "lines": list(range(max(1, n - 4), n + 1)),
                "kind": "保真-F边界",
                "desc": "末段似 B 结盟一伙链（无外部打断）",
                "fix": "删一伙/一致对外堆砌，改僵持或镜头尴尬收",
            }
        )
    if RE_B_PERFORM_TAIL.search(tail6):
        issues.append(
            {
                "lines": [
                    i + 1
                    for i, ln in enumerate(lines)
                    if RE_B_PERFORM_TAIL.search(ln)
                ],
                "kind": "保真-F边界",
                "desc": "末段 B 式团结/好姐弟表演堆砌",
                "fix": "删好姐弟/说定了/多团结，改尴尬微笑或短句闭嘴",
            }
        )
    if RE_H_RECONCILE.search(tail6):
        issues.append(
            {
                "lines": [
                    i + 1
                    for i, ln in enumerate(lines)
                    if RE_H_RECONCILE.search(ln)
                ],
                "kind": "保真-F边界",
                "desc": "末段 H 式和好调解（勿套 H）",
                "fix": "删和好/和解/别吵了，改尴尬收束或装闹着玩",
            }
        )

    pivot_idx = _external_pivot_index(lines)
    if pivot_idx is not None:
        post_lines = lines[pivot_idx + 1:]
        post_n = len(post_lines)
        if post_n > 5:
            issues.append(
                {
                    "lines": list(range(pivot_idx + 2, n + 1)),
                    "kind": "保真-F收束",
                    "desc": f"外部打断后对白过多（{post_n} 句，上限 5）",
                    "fix": "压至僵住/互看/干笑/闹着玩一句/茄子/快走，勿继续商量",
                }
            )
        post_text = "".join(post_lines)
        if RE_H_RECONCILE.search(post_text):
            issues.append(
                {
                    "lines": [
                        pivot_idx + 1 + i + 1
                        for i, ln in enumerate(post_lines)
                        if RE_H_RECONCILE.search(ln)
                    ],
                    "kind": "保真-F边界",
                    "desc": "打断后 H 式和好/别吵了（勿套 H）",
                    "fix": "删别吵了/和好，改小声闭嘴或干笑掩饰",
                }
            )
        if RE_F_CAMERA_STAGING.search(post_text):
            issues.append(
                {
                    "lines": [
                        pivot_idx + 1 + i + 1
                        for i, ln in enumerate(post_lines)
                        if RE_F_CAMERA_STAGING.search(ln)
                    ],
                    "kind": "保真-F边界",
                    "desc": "打断后似商量应对镜头（瞪/摆笑/数三二一/满意了吧）",
                    "fix": "删策划性应对，直接尴尬微笑或一句闹着玩后走人",
                }
            )
        ellipsis_hits = [
            pivot_idx + 1 + i + 1
            for i, ln in enumerate(post_lines)
            if RE_F_BROKEN_ELLIPSIS.search(ln.strip())
        ]
        if ellipsis_hits:
            issues.append(
                {
                    "lines": ellipsis_hits,
                    "kind": "保真-F童语",
                    "desc": "打断后半句省略号糊弄（呵呵…你听着…等）",
                    "fix": "改可拍短句：僵住/小声别吵了/干笑/闹着玩呢",
                }
            )

    exclaim_hits = [
        i + 1
        for i, ln in enumerate(lines)
        if RE_F_BROKEN_EXCLAIM.search(ln)
    ]
    if exclaim_hits:
        issues.append(
            {
                "lines": exclaim_hits,
                "kind": "保真-F童语",
                "desc": "互呛句垫字不通（啊啊啊了啊/啊什么了啊）",
                "fix": "改为啊啊啊！或啊什么啊！等自然感叹",
            }
        )

    pad_hits = [
        i + 1
        for i, ln in enumerate(lines)
        if RE_F_PAD_STACK.search(ln)
    ]
    if pad_hits:
        issues.append(
            {
                "lines": pad_hits,
                "kind": "保真-F童语",
                "desc": "句尾语气垫字叠堆（了呢了呀/了呢呀等）",
                "fix": "删叠垫字，以实词或单语气词收尾（讨厌呢/讨厌了呀）",
            }
        )

    haystack = _build_seed_haystack(
        dialogue_seed=dialogue_seed,
        beat_chain=beat_chain,
        beat=beat,
        conflict_text=conflict_text,
        closing_intent=closing_intent,
        object_text=object_text,
        mechanism_text=mechanism_text,
    )
    snack_hits: list[int] = []
    for i, ln in enumerate(lines, start=1):
        for m in RE_SNACK_INVENT.findall(ln):
            if m not in haystack:
                snack_hits.append(i)
                break
    if snack_hits:
        issues.append(
            {
                "lines": snack_hits,
                "kind": "保真-F invent",
                "desc": "正文出现 seed/beat 未落地的零食分物",
                "fix": "删薯片等 invent 物，收束止于尴尬微笑/闭嘴/茄子",
            }
        )
    del mech
