"""D 类笑点骨架：字段、校验、展开提纲。

校验红线：只卡机读结构（字段/长度/→/禁对白/禁辩定义），
禁止按主题词表判「画面够不够」——词表只认旧主题，新主题必挂。
画面要求写在 SYSTEM_APPEND 提示里，由模型兑现。
"""

from __future__ import annotations

import re

# True = 走 D1.5；A/B/C/E 空实现为 False
ENABLED = True

# 共享壳 + D 扩展
D_BLUEPRINT_KEYS = (
    "setup",
    "rule",
    "key_line",
    "twist",
    "beats",
    "persona",
    "fix",
    "boom",
)

_FIELD_MAX = {
    "setup": 16,
    "rule": 8,
    "key_line": 12,
    "twist": 20,
    "persona": 16,
    "fix": 12,
    "boom": 16,
}
_BEAT_MAX = 10
_BEAT_N_MIN = 3
_BEAT_N_MAX = 4

_RE_DIALOGUE_LEAK = re.compile(
    r"[：:]|昭昭说|灿灿说|妈妈说|你自己说.{0,12}怎么",
)
_RE_TWIST_ARROW = re.compile(r"→|->|读成|歪读")
# 歪读写成辩定义/抽象评价 = 没有可拍动作（通用，不含主题词）
_RE_DEF_TALK = re.compile(
    r"算不算|什么叫|谁对|定义|道理|懂不懂|到底[算是谁怎]",
)
# fix 写成抢夺/拦阻 = 阻止不是破规，回旋镖扣不上（通用，不含主题词）
_RE_FIX_GRAB = re.compile(r"抢|夺|拦|挡|阻止|住手|喊停|制止")


SYSTEM_APPEND = """\
【D·笑点骨架】你是喜剧结构师，只设计「字面执行」骨架，禁止写对白。
输出 JSON 对象，字段仅：
setup, rule, key_line, twist, beats, persona, fix, boom。
- setup≤16字：情境一帧（D 主戏姐弟，全卡禁出现妈妈）
- rule≤8字：规矩核（如系紧）
- key_line≤12字：可被回旋镖引用的叮嘱子串，**必须是主题叮嘱原话的逐字连续子串**
  （主题含「…轻轻放进箱子…」就写「轻轻放进箱子」，禁止自造「玩具轻轻放进箱」）
- twist≤20字：规矩词的第二种读法（须含→或「读成」），
  必须是动作/物件层面的歪，禁止「算不算/什么叫」式辩定义
- beats：3～4条，各≤10字，同一歪读可拍递进（禁第一块第二块），
  每拍写看得见的动作或物件状态，最后一拍必须是可见后果
  （东西/身体的形态位置变了）
- persona≤16字：中段性格意图（非对白原文，如「惨状当正确证明」）
- fix≤12字：叮嘱方**亲手违反 rule 本身**的动作，构成自打脸
  （说系紧的人自己解结√；说削干净的人自己随手两刀就吃√）；
  单纯抢夺/拦阻/喊住手不算破规——阻止别人不构成自相矛盾
- boom≤16字：扣法说明（key_line×她刚违反规矩的动作），禁止完整对白句
整卡宜短；不要 dialogue / 分镜。
"""

USER_FEW_SHOT = """\
【正例·鞋带】
{"setup":"玄关系鞋带出门","rule":"系紧","key_line":"鞋带要系紧","twist":"越紧越好→打死结","beats":["拉到底","花生米结","抽紧试走","脚麻焊死"],"persona":"惨状当正确证明","fix":"上手抠开死结","boom":"扣key_line×现在又解"}

【正例·收玩具】
{"setup":"客厅收玩具进箱","rule":"轻轻放","key_line":"轻轻放进箱子","twist":"轻轻放→先地上码塔再进箱","beats":["轻轻码第一层","再码高一层","塔开始晃","哗一下倒地"],"persona":"码齐才算轻轻","fix":"一把扫进箱","boom":"扣key_line×动手扫乱"}
"""


def expansion_outline(bp: dict) -> str:
    """D2 Flash 用的展开提纲（非对白范文）。"""
    beats = [str(b) for b in (bp.get("beats") or [])]
    beat_txt = " → ".join(beats) if beats else "（按 twist 递进 3 拍）"
    return (
        "【D·按骨架展开·逐拍硬性】\n"
        f"1. 点到 setup，勿展开互怼。\n"
        f"2. 灿灿立规，只说一次 key_line「{bp.get('key_line') or bp.get('rule') or ''}」，\n"
        f"   只许说这句原词——twist 的歪读表述（「{bp.get('twist') or ''}」的右半）\n"
        "   绝不许从灿灿嘴里说出来，必须由昭昭自己「悟」出来才好笑。\n"
        f"3. 昭昭按 beats 顺序逐拍演：{beat_txt}。\n"
        "   每拍写 2 句：昭昭第一人称报出正在做的动作 + 灿灿看到的新惨状，\n"
        "   一拍都不许跳；其中至少一句由昭昭说出「按你说的」或\n"
        "   「你说…我就…」句式（字面执行的招牌话，不许省）；\n"
        "   两人台词都须像当场对人说话（7/10 岁孩子口语），\n"
        "   禁旁白转播腔（「啪一声XX摔碎在地」×）、禁书面比喻；\n"
        "   动作方向须与任务一致（关门=缝越来越小），前后拍勿互相打架。\n"
        f"   歪读关键拍（twist「{bp.get('twist') or ''}」落地那一拍）必须由昭昭\n"
        "   亲口亲手演出来，禁止跳过后靠灿灿一句惊呼补认。\n"
        "   每拍惨状须换新形态（东西/姿势/位置变了才算一拍），\n"
        "   禁止同一件事只换形容词原地加码；\n"
        "   一句台词只报一拍的状态：禁止用「可是/但/却」把两拍的结果\n"
        "   并进同一句（「皮削得比纸还薄，可连果肉都削下来了」×——\n"
        "   薄皮是一拍、带肉是下一拍，各自成句）；\n"
        "   惨状必须发生在昭昭对应的动作句之后，禁止灿灿先报惨状、\n"
        "   昭昭再补动作（果肉还没削怎么会先掉下来）。\n"
        f"   中段兑现 persona「{bp.get('persona') or ''}」（意图，勿整句照抄）。\n"
        f"4. 灿灿破规：{bp.get('fix') or '亲手违反自己的规矩'}。\n"
        "   破规=她亲手做出违反 key_line 的事（说系紧的人解结、\n"
        "   说削干净的人随手两刀就吃），单纯抢下来/喊住手不算——\n"
        "   阻止别人不构成自打脸，回旋镖会扣不上。\n"
        "   破规动作要先在对白里演出来（工具从哪来、手上在干什么），\n"
        "   用她自己的口语喊出来（「让开，我来关！」√，勿旁白式自述），\n"
        "   完成在昭昭点破之前，禁止只在昭昭台词里被追认。\n"
        f"5. 昭昭回旋镖（倒数第 2 句）：必须以「你自己说」或「你不是说」开头，"
        f"原样引用 key_line「{bp.get('key_line') or ''}」，再点破上手破规"
        f"（按 boom「{bp.get('boom') or ''}」现场组织口语，禁止照抄 boom 原文当台词）。\n"
        "   **禁止改引中段催促**（如把 key_line 换成「不能再塞了/别再弄了」）。\n"
        "   点破全篇只许这一句：灿灿动手破规之前，昭昭禁止说"
        "「你也破了/你这会儿也」之类的话——先点破再破规=笑点泄光。\n"
        "6. 灿灿哼/算了收束，勿再发指令。\n"
        "【动作同向·硬规】中段只许演本卡 beats/twist 那一套歪读递进；\n"
        "   禁止另开第二套无关用力线（twist 是码塔就演码/晃/倒，\n"
        "   勿写成往筐里使劲塞满；twist 是系紧就演绕/结，勿改成别的活）。\n"
        "   灿灿搞砸前禁止拆穿（「我是让你…你在地上…干什么」）。\n"
        "【物件连续性·硬规】道具在谁手里全程一条线：任务开始时物件\n"
        "   怎么到执行者手里要有台词交代（「你来试试」「给我吧」）；\n"
        "   被削掉/弄坏的部分不许凭空复原；破规动作若需要新的一份\n"
        "   （新苹果/新纸），灿灿须一句交代来源（「我再拿一个」），\n"
        "   禁止凭空多出一个。\n"
        "全程只用本骨架里的物件与动词，禁止套用其他主题的旧梗字眼"
        "（骨架没有「焊」就不许出现「焊」）。\n"
        "【字数硬卡】正文 16–17 句（默认 16）、每句必须写足 19–21 字"
        "（严禁超 24 字，超长会被截掉毁句；严禁 ~11 字短句）、"
        "合计 310–340 字（少于 300 视为不合格）；"
        "一句只报一拍时，把那一拍补足到 19–21 字"
        "（补当场动作/状态细节），勿靠加更多短句凑字。"
    )


def validate(bp: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(bp, dict):
        return ["骨架须为 JSON 对象"]
    for key in D_BLUEPRINT_KEYS:
        if key not in bp:
            errors.append(f"缺字段 {key}")
    if errors:
        return errors

    for key, lim in _FIELD_MAX.items():
        val = str(bp.get(key) or "").strip()
        if not val:
            errors.append(f"{key} 为空")
        elif len(val) > lim:
            errors.append(f"{key} 超过{lim}字（当前{len(val)}）")

    beats = bp.get("beats")
    if not isinstance(beats, list):
        errors.append("beats 须为数组")
    else:
        if not (_BEAT_N_MIN <= len(beats) <= _BEAT_N_MAX):
            errors.append(f"beats 须{_BEAT_N_MIN}～{_BEAT_N_MAX}条")
        for i, b in enumerate(beats):
            s = str(b or "").strip()
            if not s:
                errors.append(f"beats[{i}] 为空")
            elif len(s) > _BEAT_MAX:
                errors.append(f"beats[{i}] 超过{_BEAT_MAX}字")
            if re.search(r"第[一二三四1234]块", s):
                errors.append(f"beats[{i}] 禁止流程块序号")

    fix = str(bp.get("fix") or "")
    if fix and _RE_FIX_GRAB.search(fix):
        errors.append(
            "fix 是抢夺/拦阻不是破规：须叮嘱方亲手违反 rule 本身"
            "（说削干净的人自己随手削两刀就吃）",
        )

    twist = str(bp.get("twist") or "")
    if twist and not _RE_TWIST_ARROW.search(twist):
        errors.append("twist 须含→或读成/歪读")
    beats_text = "".join(str(b) for b in (bp.get("beats") or []))
    if _RE_DEF_TALK.search(twist + beats_text):
        errors.append("twist/beats 在辩定义，须演歪读动作")

    all_text = "".join(
        str(bp.get(k) or "") for k in D_BLUEPRINT_KEYS if k != "beats"
    ) + beats_text
    if "妈妈" in all_text:
        errors.append("骨架禁出现妈妈（D 主戏姐弟）")

    boom = str(bp.get("boom") or "")
    if _RE_DIALOGUE_LEAK.search(boom):
        errors.append("boom 禁止写成完整对白")
    key_line = str(bp.get("key_line") or "")
    if key_line and key_line not in boom and str(bp.get("rule") or "") not in boom:
        if "key_line" not in boom and "扣" not in boom:
            errors.append("boom 须扣 key_line/rule")

    return errors


def project_meta(bp: dict) -> tuple[str, str]:
    """投影 conflict_core / punchline_explain。"""
    rule = str(bp.get("rule") or "").strip()
    twist = str(bp.get("twist") or "").strip()
    key = str(bp.get("key_line") or rule).strip()
    fix = str(bp.get("fix") or "").strip()
    boom = str(bp.get("boom") or "").strip()
    if rule and twist and rule in twist:
        # twist 常自带规矩词（削干净→把果肉当皮削），勿再拼出叠字核心
        core = twist.replace("→", "被读成", 1) if "→" in twist else twist
    elif rule and twist:
        core = f"{rule}被读成{twist}"
    else:
        core = twist or rule or "字面执行"
    punch = (
        f"D类字面执行：规矩「{key}」，歪读「{twist}」，"
        f"破规「{fix}」，回旋镖「{boom}」。"
    )
    return core[:40], punch[:120]
