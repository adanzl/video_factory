"""Q 类正文硬卡（耍赖翻车；抽象不变量，禁单篇词表）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

# 抽象：耍赖/借口加码 → 被拆穿 → 反噬；勿绑洗碗等单篇
RE_CHEAT = re.compile(
    r"耍赖|重抽|再抽|逞强|借口|推给|太少|不认|嘴硬|再来一次|换一个"
)
# 第一人称耍赖/借口功能句：须归耍赖方（抽象槽位，非单篇词表）
RE_CHEAT_OWN = re.compile(
    r"重抽|再抽|太少|胃小|剩的给你|推给你|我还能|我才不怕|"
    r"不算偷|就一根|急着吃|装不下|这次满意|才够"
)
RE_EXPOSE = re.compile(
    r"看穿|拆穿|揭穿|心思|你昨天|偷|别装|露馅|明明|还装"
)
RE_BACKFIRE = re.compile(
    r"洗碗|刷碗|洗盘子|加活|罚|活该|自己收拾|你去|翻车|自己.*吧"
)
RE_E_MOM_BREAK = re.compile(r"唉|行行行|好吧随便|说不通|被问住")
RE_P_PRANK = re.compile(r"尝尝|再试试|也给你|认输|不了不了")
RE_C_BOOMERANG = re.compile(r"你刚说|你说的|那不一样|哪里不一样|凭什么你")
RE_H_MEDIATION = re.compile(r"不打了|拉手|道歉|原谅|都有错")
RE_PAD_TAIL = re.compile(
    r"马上给我挪开|我才不怕呢|不许再耍赖|我偏就不信|不行好不好|我可记住啦"
)
RE_BOAST = re.compile(r"我还能|再来|逞强|真香|越吃|不怕辣|再抽|重抽")
RE_WEAK_EXCUSE = re.compile(r"胃小|吃不下|饱了|剩的给你|推给|装不下|嗝")
RE_STACKED_PARTICLE_HIT = re.compile(
    r"嘛了呀|啦了呀|吧真的了呢|真的了呢|了呀真的|"
    r"好不好呀|真的好不好|了呀不行嘛"
)
RE_CONCRETE_ACCUSE = re.compile(r"偷吃|偷\w+|辣条|嘴角|嘴肿")


def resolve_q_cheat_speaker(story: dict) -> str:
    """从 conflict/punch/seed 推断耍赖方；默认灿灿。"""
    core = str(story.get("conflict_core") or "")
    punch = str(story.get("punchline_explain") or "")
    m = re.search(
        r"(灿灿|昭昭).{0,24}(抽签|耍赖|重抽|逞强|借口|胃小|推食|推给)",
        core,
    )
    if m:
        return m.group(1)
    m = re.search(
        r"(灿灿|昭昭).{0,24}(抽签|耍赖|重抽|逞强|借口|胃小|推食|推给)",
        punch,
    )
    if m:
        return m.group(1)
    seed = story.get("dialogue_seed")
    if isinstance(seed, list):
        counts = {"灿灿": 0, "昭昭": 0}
        for item in seed:
            if not isinstance(item, dict):
                continue
            sp = str(item.get("speaker") or "").strip()
            intent = str(item.get("intent") or item.get("line") or "")
            if sp in counts and (
                RE_CHEAT.search(intent) or RE_CHEAT_OWN.search(intent)
            ):
                counts[sp] += 1
        if counts["昭昭"] > counts["灿灿"]:
            return "昭昭"
        if counts["灿灿"] > 0:
            return "灿灿"
    return "灿灿"


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


def append_q_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "Q":
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
    blob = f"{core}{closing}{body}"

    if not RE_CHEAT.search(blob):
        errors.append("Q类：须有耍赖/借口加码迹象")
    if not RE_EXPOSE.search(blob):
        errors.append("Q类：须有被拆穿（看穿/揭穿等）")
    # 反噬须落在对白（勿仅靠 conflict 字段冒充）
    if not RE_BACKFIRE.search(body):
        errors.append("Q类：收束须赖法反噬（加活/吃瘪等）")
    elif not RE_BACKFIRE.search(tail4):
        errors.append("Q类：反噬须落在末段对白")

    cheater = resolve_q_cheat_speaker(story)
    stolen = 0
    for sp, ln in rows:
        if sp not in {"昭昭", "灿灿"} or sp == cheater:
            continue
        if not RE_CHEAT_OWN.search(ln):
            continue
        # 纯拆穿留给拆穿方；第一人称耍赖槽位不可抢
        if RE_EXPOSE.search(ln) and not RE_CHEAT_OWN.search(
            re.sub(r"看穿|拆穿|揭穿|心思|偷|别装|露馅|明明|还装", "", ln)
        ):
            continue
        stolen += 1
    if stolen:
        errors.append(
            f"Q类：耍赖/借口句须由耍赖方（{cheater}）说，"
            f"勿由姐弟抢戏（{stolen}句）"
        )

    # 须有拆穿方：拆穿句 speaker 与主要耍赖方不宜全程同一人
    expose_idxs = [i for i, ln in enumerate(lines) if RE_EXPOSE.search(ln)]
    cheat_idxs = [
        i
        for i, (sp, ln) in enumerate(rows)
        if (RE_CHEAT.search(ln) or RE_CHEAT_OWN.search(ln)) and sp == cheater
    ]
    if not cheat_idxs:
        cheat_idxs = [i for i, ln in enumerate(lines) if RE_CHEAT.search(ln)]
    if expose_idxs and cheat_idxs:
        cheat_sp = speakers[cheat_idxs[0]]
        expose_sp = speakers[expose_idxs[-1]]
        if cheat_sp and expose_sp and cheat_sp == expose_sp:
            # 允许自嘲一句，但全文须另有他人拆穿
            other_expose = [
                i
                for i in expose_idxs
                if speakers[i] and speakers[i] != cheat_sp
            ]
            if not other_expose:
                errors.append("Q类：须有他人拆穿，禁止仅自食其果无拆穿方")
    elif RE_BACKFIRE.search(blob) and not expose_idxs:
        errors.append("Q类：禁止无拆穿方的伪反噬（仅单方自食其果）")

    if speakers and speakers[-1] == "妈妈":
        mom_ln = lines[-1]
        if (
            RE_BACKFIRE.search(mom_ln)
            and "小心思" in mom_ln
            and not re.search(r"推|剩|胃|借口", mom_ln)
        ):
            errors.append("Q类：妈妈反噬宜点明与前面借口/推食的因果")

    # 末段妈妈反噬须回指借口（胃/推/剩），勿纯指令
    for sp, ln in rows[-5:]:
        if sp != "妈妈" or not RE_BACKFIRE.search(ln):
            continue
        if re.search(r"胃小|推给|剩的给你|吃不下", body) and not re.search(
            r"推|剩|胃|借口|吃不下", ln
        ):
            errors.append("Q类：终裁反噬须回指耍赖借口（胃小/推食等）")
        break

    pad_hits = sum(1 for ln in lines if RE_PAD_TAIL.search(ln))
    if pad_hits >= 2:
        errors.append("Q类：禁堆垫字尾巴（不怕呢/不行好不好等）")

    stack_hits = sum(1 for ln in lines if RE_STACKED_PARTICLE_HIT.search(ln))
    if stack_hits >= 2:
        errors.append("Q类：禁多尾音叠堆（嘛了呀/真的了呢等）")

    # 拆穿短接话不得复读（仅极短模板句，免误伤正常短对白）
    short_cores: dict[str, int] = {}
    for sp, ln in rows:
        if sp not in {"昭昭", "灿灿"}:
            continue
        core = re.sub(r"[，,。！!？?\s]+", "", ln)
        if 2 <= len(core) <= 8:
            short_cores[core] = short_cores.get(core, 0) + 1
    if any(c >= 2 for c in short_cores.values()):
        errors.append("Q类：拆穿/接话禁复读同一短句")

    # 逞强→借口：弱化借口前须有逞强/加码
    weak_idxs = [i for i, ln in enumerate(lines) if RE_WEAK_EXCUSE.search(ln)]
    if weak_idxs:
        w0 = weak_idxs[0]
        prior = "".join(lines[:w0])
        if not RE_BOAST.search(prior) and not RE_BOAST.search(
            "".join(lines[max(0, w0 - 3) : w0 + 1])
        ):
            # 若全文有逞强类但全在借口后，仍算转折缺失
            if RE_BOAST.search(body) and not RE_BOAST.search(prior):
                errors.append("Q类：借口推食前须有逞强/加码到示弱的转折")

    # 具体指控须有前文或 seed 铺垫（句内任一关键事实有依据即可）
    seed_blob = ""
    seed = story.get("dialogue_seed")
    if isinstance(seed, list):
        for item in seed:
            if isinstance(item, dict):
                seed_blob += str(item.get("intent") or item.get("line") or "")
    prior_acc = core + seed_blob
    for i, (sp, ln) in enumerate(rows):
        if sp == cheater:
            continue
        hits = list(RE_CONCRETE_ACCUSE.finditer(ln))
        if not hits:
            continue
        prior = prior_acc + "".join(lines[:i])
        if any(
            (m.group(0) in prior) or (m.group(0)[:2] in prior) for m in hits
        ):
            continue
        errors.append("Q类：拆穿具体事实须有前文铺垫")
        break

    if RE_E_MOM_BREAK.search(tail4) and speakers[-1] == "妈妈":
        errors.append("Q类：末句勿写成 E 妈妈破功")
    if (
        len(RE_P_PRANK.findall(body)) >= 3
        and not RE_EXPOSE.search(body)
    ):
        errors.append("Q类：勿写成 P 整蛊互整链")
    if RE_C_BOOMERANG.search(tail4):
        errors.append("Q类：末段勿套 C 回旋镖收束")
    if RE_H_MEDIATION.search(tail4):
        errors.append("Q类：末段勿 H 劝和收束")
