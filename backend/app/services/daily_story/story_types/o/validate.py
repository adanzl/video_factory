"""O 类正文硬卡（立赛规 + 死磕过程 + 资源溜走 + 点题）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code

# 抽象不变量：赛规过程执念 + 资源溜走 + 点题；禁单篇菜名/猜拳词表穷举剧情
RE_GAME_RULE = re.compile(
    r"剪刀石头布|猜拳|赢的.*(?:才)?能?吃|赢了.*吃|谁赢|规则是|吹蜡烛"
)
RE_PROCESS_FOCUS = re.compile(r"我赢了|又赢|再来|出拳|认真|光顾着赢|一心|专注")
RE_PRIZE_GONE = re.compile(
    r"少了|没了|空了|见底|只剩|吃光|吃完|吃得差不多|盘子"
)
# 须像认栽自述；禁匹配对手嘲讽「只顾着赢/你光顾着赢」
RE_GOAL_PUNCH = re.compile(
    r"我光顾着赢|我(?:也)?顾着赢|菜都没了|白赢|"
    r"赢了(?:却|都)?没|目标.*没了|过程.*输了"
)
# 点题后仅允许笑场/旁观收束（抽象，不绑单篇词）
RE_O_LAUGH_CLOSE = re.compile(r"偷笑|哈哈|嘿嘿|真逗|吃饱|笑出|笑场|逗死")
# 点题后若仍怂恿续赛/不服，不算合法笑场收束
RE_O_POST_PUNCH_CONTINUE = re.compile(
    r"慢慢赢|慢慢来|再来|再比|继续比|不服|试试看|偏就|真的不行|我偏|"
    r"下次|少废话|边赢边吃|你赔|收碗|我赢啦|我赢了|我赢呀|抢吃吹蜡烛版"
)
# 点题认栽句本身勿带申诉/翻盘情绪尾巴（抽象）
RE_O_PUNCH_SOFT_CHALLENGE = re.compile(r"不公平|太不公|不服气|我不服")
# 点题句尾垫字碎片（补字副作用）
RE_O_PUNCH_TAIL_JUNK = re.compile(
    r"[，,。！!…]*\s*(?:呜呜[，,。！!…]*)?(?:了呢|真的了呢|嘛了呀|了呀)[。！!…]*$"
)
# 资源已溜走的得意收束（点题前）若夹续赛暗示，收束不干脆
RE_O_RESULT_GLOAT = re.compile(r"嘿嘿|吃饱|吃完|吃光啦|吃光了|偷笑")
# 得意收束里「施舍最后一块」冲淡目标溜走
RE_O_GLOAT_CHARITY = re.compile(r"这块给你|给你吧|留给你|剩的给你")
# 资源溜走得意后勿再开互怼（应尽快点题）
RE_O_POST_GLOAT_QUARREL = re.compile(
    r"偷吃|少废话|耍赖|偏就|试试看|我就要赢|有本事|再闹|故意趁"
)
# 得意收束夹「慢慢来/慢慢赢」续赛暗示
RE_O_GLOAT_CONTINUE = re.compile(r"慢慢来|慢慢赢|再来|继续比")
# 死磕赢赛自述（点题须落在此类说话人）
RE_O_WIN_CLAIM = re.compile(
    r"我赢了[！!]|我赢啦|又赢[啦了！!]|我又赢|我还是赢|"
    r"哈[哈，,]?我赢"
)
# 垫字碎片过密（gold_chat 补字副作用；勿把单字「呢」当硬伤）
RE_O_PAD_JUNK = re.compile(
    r"嘛了呀|了呀不行|真的嘛了|不行好不好呀|好不好呀|再闹我恼"
)
# 对手代点题（削弱主角自悟）
RE_O_OTHER_SPOILER = re.compile(r"你(?:光)?顾着赢|你只顾着赢")
RE_C_BOOMERANG_CLOSE = re.compile(r"你刚说|你说的|那不一样|哪里不一样|八百|吃商")
RE_A_BACKFIRE = re.compile(r"那不一样|都是听|破功|自相矛盾|你刚才说")
RE_N_SOLEMN = re.compile(r"因为.*就能|一本正经|荒诞自洽")
RE_I_SOUL = re.compile(r"爱学习|你爱吗|灵魂|拷问")


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


def append_o_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=punch,
    )
    if code != "O":
        return
    lines, speakers = _lines_and_speakers(story)
    if len(lines) < 6:
        return

    body = "".join(lines)
    tail5 = "".join(lines[-5:])
    core = str(story.get("conflict_core") or "")
    blob = f"{core}{body}"
    if not RE_GAME_RULE.search(blob) and not RE_PROCESS_FOCUS.search(body):
        errors.append("O类：正文须有立赛规或死磕过程（猜拳/赢赛/再来等）")
    if not RE_PRIZE_GONE.search(blob):
        errors.append("O类：须有资源溜走（少了/没了/只剩/吃光等）")
    if not RE_GOAL_PUNCH.search(blob) and not RE_GOAL_PUNCH.search(tail5):
        errors.append("O类：收束须点题顾过程丢目标（光顾着赢/X没了等）")
    junk_n = sum(1 for ln in lines if RE_O_PAD_JUNK.search(ln))
    if junk_n >= 2:
        errors.append("O类：正文勿堆垫字碎片，保持可说出口的儿童对白")
    punch_idxs = [i for i, ln in enumerate(lines) if RE_GOAL_PUNCH.search(ln)]
    if punch_idxs:
        p_i = punch_idxs[-1]
        punch_ln = lines[p_i]
        punch_sp = speakers[p_i] if p_i < len(speakers) else ""
        prior_winners = {
            speakers[i]
            for i, ln in enumerate(lines[:p_i])
            if RE_O_WIN_CLAIM.search(ln) and i < len(speakers)
        }
        if prior_winners and punch_sp and punch_sp not in prior_winners:
            errors.append("O类：点题认栽须由死磕赢赛方自述，勿落到对手嘴上")
        win_n = sum(1 for ln in lines[:p_i] if RE_O_WIN_CLAIM.search(ln))
        if win_n >= 3:
            errors.append("O类：死磕赢赛宜约两轮见底点题，勿反复加赛拉长")
        if any(RE_O_OTHER_SPOILER.search(ln) for ln in lines[:p_i]):
            errors.append("O类：点题须主角自悟，对手勿先揭穿你光顾着赢")
        if RE_O_PUNCH_SOFT_CHALLENGE.search(punch_ln):
            errors.append("O类：点题认栽句须干脆认栽，勿带不公平/不服申诉尾巴")
        if RE_O_PUNCH_TAIL_JUNK.search(punch_ln) or re.search(
            r"(?:了呢|嘛了呀)\s*$", punch_ln
        ):
            errors.append("O类：点题句勿缀了呢/嘛了呀等垫字碎片")
        for ln in lines[:p_i]:
            if RE_O_RESULT_GLOAT.search(ln) and (
                RE_O_POST_PUNCH_CONTINUE.search(ln)
                or RE_O_GLOAT_CONTINUE.search(ln)
            ):
                errors.append("O类：资源溜走得意收束勿夹慢慢赢/再来等续赛暗示")
                break
            if RE_O_RESULT_GLOAT.search(ln) and RE_O_GLOAT_CHARITY.search(ln):
                errors.append("O类：得意收束勿施舍最后一块，资源溜走须成既成事实")
                break
        gloat_idxs = [
            i for i, ln in enumerate(lines[:p_i]) if RE_O_RESULT_GLOAT.search(ln)
        ]
        if gloat_idxs:
            g0 = gloat_idxs[0]
            mid = lines[g0 + 1 : p_i]
            if any(RE_O_POST_GLOAT_QUARREL.search(ln) for ln in mid):
                errors.append("O类：资源溜走得意后须尽快点题，勿再开偷吃互怼")
        after = lines[p_i + 1 :]
        for ln in after:
            if RE_O_POST_PUNCH_CONTINUE.search(ln):
                errors.append("O类：点题认栽后勿再开第二轮抬杠，只可留笑场/旁观")
                break
            if RE_O_LAUGH_CLOSE.search(ln) or re.search(r"哈哈|真逗", ln):
                continue
            errors.append("O类：点题认栽后勿再开第二轮抬杠，只可留笑场/旁观")
            break
    if RE_A_BACKFIRE.search(tail5):
        errors.append("O类：末段勿 A 式反噬/破功链")
    if RE_C_BOOMERANG_CLOSE.search(tail5) and not RE_GOAL_PUNCH.search(tail5):
        errors.append("O类：末段勿套 C 回旋镖收束，须落点题认栽")
    if RE_I_SOUL.search(body):
        errors.append("O类：勿写成 I 灵魂拷问（爱学习/你爱吗）")
    if RE_N_SOLEMN.search(body) and not RE_GOAL_PUNCH.search(body):
        errors.append("O类：勿写成 N 正经胡说自洽链")
