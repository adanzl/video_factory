"""D 类正文硬卡（字面执行 + 回旋镖收束）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.d.humor import (
    RE_BOOM_CLOSE,
    RE_BOOM_POINT,
    RE_FIX,
    RE_MESS,
)
from app.services.daily_story.story_types.quality import (
    RE_SOFT_LAST,
)

RE_A_WHERE_DIFF = re.compile(r"哪里不一样|都是听|大人也要听小孩|大人要听小孩")
RE_A_CITE_CLOSE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)",
)
RE_LITERAL_MID = re.compile(
    r"照做|按你说的|你不是说|字面|按规矩|你说要|你让我|照你说的|"
    r"你说[^，。！？]{1,8}，?我就|我按你|你叫我|你要我|我照你",
)
# 后果场面词表与好笑侧同源（含 满/漫/泡/漂 等水类惨状），
# 勿用收玩具/叠衣专属窄表——浇花主题的惨状全是水词，窄表会把中段惨状看漏
_RE_MESS_BEAT = re.compile(
    r"倒了|掉了|全掉|掉地上|洒|滑落|滑掉|堆塌|解不开|死结|溢|"
    r"弄翻|全乱|变形了|夹变形|撑变形",
)
# 立规：须可抠字眼；裸「不能再塞」类中段催促不算
# 词表与 D prompt 的「可抠叮嘱示例（轻点/系紧/别碰/慢慢/别多/别响…）」对齐
_RE_RULE_CORE = re.compile(
    r"不许|别碰|别晃|轻点|慢点|系紧|轻轻|轻拿|别浇|别多|别夹|"
    r"别响|别堆|别乱|规矩|叮嘱|不准|只能|别太|"
    r"慢慢|慢点擦|轻擦|别毛|别用力|别猛|小心|毛手毛脚",
)
_RE_DIRECT_QUOTE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)"
    r"([^，。！？…]{3,})",
)


def _cite_grounded_in_hay(cite: str, hay: str) -> bool:
    """回旋镖引文须落前段叮嘱原话：
    1) 逐字子串即可；2) ≥4 字时允许 4 连字子串；
    3) 3–6 字短引文放宽为「同词序调整」——每个字都须在前段叮嘱里出现过
       （叠衣「叠衣服要轻点」→ 引「轻点叠」也算忠实），
       仍挡「不能再塞了」这类中段催促（催促字不落在立规句里）。"""
    if not cite:
        return False
    if cite in hay:
        return True
    if len(cite) >= 4 and any(
        cite[j : j + 4] in hay for j in range(0, len(cite) - 3)
    ):
        return True
    if 3 <= len(cite) <= 6:
        return all(hay.count(ch) >= cite.count(ch) for ch in set(cite))
    return False
# 搞砸前拆穿字面误解（结构判定，禁主题词表——词表留 humor 观感扣分）
_RE_SPOIL_LITERAL = re.compile(
    r"不是让你|我是让你|我让你.{0,8}不是|你理解错|我说的是|我是说|"
    r"你.{0,8}地上.{0,14}干(?:什么|嘛)|"
    r"你[^，。！？]{0,8}(?:码|垒|叠|堆|搭|摞|绕|缠|卷)[^，。！？]{0,10}(?:干嘛|干什么)|"
    r"你这是要",
)
# D 正文 15–17 句 + 开场 2 句 = 成片宜 17–19 句；上限对齐设计（20 含 1 句余量）
_D_MAX_DIALOGUE_LINES = 20
_RE_RULE = re.compile(r"不许|别碰|别晃|轻点|慢点|系紧|规矩|叮嘱|不准|不能")


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


def append_d_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "D":
        return

    lines, speakers = _dialogue_lines(story)
    n = len(lines)
    if n < 8:
        errors.append("D类正文过短，不足以完成字面执行收束（至少约 8 句对白）")
        return

    if n > _D_MAX_DIALOGUE_LINES:
        errors.append(
            f"D类正文过长（须≤{_D_MAX_DIALOGUE_LINES}句对白），当前{n}句",
        )
        return

    mom_n = sum(1 for sp in speakers if sp == "妈妈")
    if mom_n > 0:
        errors.append("D类主戏姐弟，禁止妈妈插话（留给E类）")

    # 唠叨门：只数灿灿前 6 句里自己立规矩的次数。
    # 昭昭「你说系紧，我就…」这类**引规复述**不算唠叨（字面执行本来就须引原话）。
    head6_cancan = "".join(
        lines[i]
        for i in range(min(6, n))
        if i < len(speakers) and speakers[i] == "灿灿"
    )
    rule_hits = len(_RE_RULE.findall(head6_cancan))
    if rule_hits >= 3:
        errors.append("D类前段勿重复唠叨同一条规矩（立规≤2次）")

    # 前段灿灿须立可抠叮嘱（邀约「收进箱子吧」不算；须轻/别/系紧等）
    early_n = min(6, max(0, n - 4))
    early_cancan = [
        lines[i]
        for i in range(early_n)
        if i < len(speakers) and speakers[i] == "灿灿"
    ]
    early_rule_text = "".join(early_cancan)
    bp = story.get("punchline_blueprint")
    key_line = ""
    if isinstance(bp, dict):
        key_line = str(bp.get("key_line") or bp.get("rule") or "").strip()
    if key_line and len(key_line) >= 2:
        if key_line not in early_rule_text and not any(
            key_line[: max(2, min(4, len(key_line)))] in ln
            for ln in early_cancan
        ):
            errors.append(
                f"D类前段须灿灿说出叮嘱原话（key_line「{key_line}」），"
                "勿只邀约不立规",
            )
            return
    elif not _RE_RULE_CORE.search(early_rule_text):
        errors.append(
            "D类前段须灿灿立可抠叮嘱（轻轻/轻点/系紧/别浇多等），"
            "裸邀约或中段「不能再…」催促不算立规",
        )
        return

    tail4 = "".join(lines[-4:])
    late8 = "".join(lines[max(0, n - 8) :])
    body_n = max(0, n - 4)
    body = "".join(lines[:body_n])
    body_lines = lines[:body_n]
    body_speakers = speakers[:body_n]

    if RE_A_WHERE_DIFF.search(tail4) and (
        "那不一样" in tail4 or RE_A_CITE_CLOSE.search(tail4)
    ):
        errors.append(
            "D类收束勿写成 A 式末四拍（引话+那不一样+哪里不一样）；"
            "应走叮嘱方破规+字面回旋镖",
        )
        return

    if not RE_LITERAL_MID.search(body):
        errors.append(
            "D类中段须有「按叮嘱/字面执行」对白（照做、按你说的、你不是说等）",
        )
        return

    # 搞砸前禁止拆穿字面误解
    mess_i = next(
        (i for i, ln in enumerate(lines) if _RE_MESS_BEAT.search(ln)),
        None,
    )
    if mess_i is None:
        mess_i = next((i for i, ln in enumerate(lines) if RE_MESS.search(ln)), None)
    if mess_i is not None:
        cancan_before = "".join(
            lines[i]
            for i in range(mess_i)
            if i < len(speakers) and speakers[i] == "灿灿"
        )
        if _RE_SPOIL_LITERAL.search(cancan_before):
            errors.append(
                "D类搞砸前禁止拆穿字面误解"
                "（不是让你…/我是让你…/你…地上…干什么/你码塔干嘛）",
            )
            return

    # 回旋镖须在近段；末句须嘴硬，禁止哼后再开第二场
    # 用 D 专口 RE_BOOM_CLOSE 而非共享 RE_BOOMERANG_RULE——
    # 后者会误中「照/按你说的」，让「我自己说」错位稿漏网
    boom_late = RE_BOOM_CLOSE.search(late8)
    if not boom_late:
        if re.search(r"我自己说|我说的[^，。！？]{0,6}(?:怎么|现在|你却|却)", late8):
            errors.append(
                "D类回旋镖须引叮嘱方原话（你自己说/你刚才说…），"
                "禁止自称立规（我自己说）",
            )
        else:
            errors.append(
                "D类末段须用叮嘱方原话回旋镖（你自己说/你刚才说/你不是说…）",
            )
        return

    # 回旋镖须在破规动作句之后：先点破再破规 = 笑点泄光。
    # 确定性硬卡：首个回旋镖行之前若无灿灿 RE_FIX 补救句 → 重试
    #（把「缺叮嘱方破规/破规未先于回旋镖」的 −7/−5 好笑扣分转成可修错误）
    boom_any_i = next(
        (i for i, ln in enumerate(lines) if RE_BOOM_CLOSE.search(ln)),
        None,
    )
    if boom_any_i is not None:
        fix_before_boom = None
        fix_start = max(0, boom_any_i - 5)
        for i in range(fix_start, len(lines)):
            if i >= boom_any_i:
                break
            ln = lines[i]
            if not RE_FIX.search(ln):
                continue
            if i < len(speakers) and speakers[i] not in ("灿灿", "妈妈"):
                continue
            fix_before_boom = i
        if fix_before_boom is None:
            errors.append(
                "D类回旋镖须在破规动作句之后：正文须有灿灿亲手补救句"
                "（我来/自己上手/一把/拢住等），回旋镖点破须在其后；"
                "禁止昭昭在破规前说「你也破了/你这会儿也破」",
            )
            return

    # 回旋镖须点破当场矛盾：只引原话不点破 = 笑点没落地（确定性硬卡）
    if boom_any_i is not None:
        boom_ln = lines[boom_any_i]
        if RE_BOOM_CLOSE.search(boom_ln) and not RE_BOOM_POINT.search(boom_ln):
            errors.append(
                "D类回旋镖须点破矛盾：引原话后须点出她此刻的破规动作"
                "（怎么现在又上手来解/自己整壶都倒进去了），"
                "禁止只写「是你自己说别浇太多的」就停",
            )
            return

    # 回旋镖引文须落在前段叮嘱，禁止改引中段催促「不能再塞了」
    boom_i = next(
        (i for i in range(max(0, n - 4), n) if RE_BOOM_CLOSE.search(lines[i])),
        None,
    )
    if boom_i is not None:
        m = _RE_DIRECT_QUOTE.search(lines[boom_i])
        if m:
            cite = m.group(1).strip()
            cite = re.split(r"[，。！？]|你现在|你却|怎么|我照", cite)[0]
            cite = re.sub(r"的$", "", cite.strip())
            hay = early_rule_text
            if key_line:
                hay = f"{key_line}{hay}"
            grounded = _cite_grounded_in_hay(cite, hay)
            if key_line and len(key_line) >= 2 and cite:
                # 引文须落在 key_line 上：boom 句含 key_line（或其≥4字前缀），
                # 或引文本体是 key_line 的逐字连续子串（放行「轻轻放」这类≥3字短原话）
                boom_has_key = key_line in lines[boom_i] or key_line[:4] in lines[boom_i]
                cite_from_key = len(cite) >= 3 and cite in key_line
                if not (boom_has_key or cite_from_key):
                    grounded = False
            if not grounded:
                key_txt = ""
                if key_line and len(key_line) >= 2:
                    key_txt = f"，key_line「{key_line}」须逐字出现在回旋镖句里"
                errors.append(
                    "D类回旋镖须原样引前段叮嘱原话"
                    "（禁改引中段催促如「不能再塞了」" + key_txt + "）",
                )
                return

    # 有骨架时：中段须演 twist/beats，禁另开第二套无关用力线
    if isinstance(bp, dict):
        twist = str(bp.get("twist") or "")
        beats_text = "".join(str(b) for b in (bp.get("beats") or []))
        plan = twist + beats_text
        zhao_mid = "".join(
            body_lines[i]
            for i in range(len(body_lines))
            if i < len(body_speakers) and body_speakers[i] == "昭昭"
        )
        # twist 含码/塔/叠/垒时，中段昭昭须出现对应演法，不能只剩塞/压
        if re.search(r"码|塔|叠|垒", plan) and zhao_mid:
            if not re.search(r"码|塔|叠|垒|晃|倒", zhao_mid) and re.search(
                r"塞|压|挤", zhao_mid,
            ):
                errors.append(
                    "D类中段须演骨架歪读（码塔/叠高等），"
                    "禁止另开「使劲塞满」第二套动作",
                )
                return

    soft_i = next(
        (i for i, ln in enumerate(lines) if re.search(r"哼|算了|行吧", ln)),
        None,
    )
    if soft_i is not None and soft_i < n - 1:
        errors.append("D类哼/算了后禁止再开第二场，末句须停在嘴硬")
        return

    last = lines[-1]
    last_sp = speakers[-1] if speakers else ""
    if last_sp == "灿灿":
        if not RE_SOFT_LAST.search(last) and not re.search(
            r"哼|算了|行吧|说不清", last,
        ):
            errors.append("D类末句须灿灿嘴硬（哼/行吧/算了），勿发新指令")
            return
    elif last_sp == "妈妈" and not RE_SOFT_LAST.search(last):
        if not re.search(r"哼|才不是|没办法|算了|行吧", last):
            errors.append(
                "D类末句叮嘱方（若由妈妈收束）须嘴硬或软破功（哼/行吧/算了等）",
            )
            return

    if RE_MESS.search(tail4) and not RE_MESS.search(body):
        errors.append(
            "D类后果跑偏宜在中段已可见（洒/掉/乱等），勿只在末句突然出现",
        )
