"""G 类正文硬卡（pivot + 暖收，非 C/F 收束）。

M4+G 权威点题旁路：``closing_mode=authority_punchline`` 时改用
立规→反将→认怂让渡→权威点题槽位，不放宽标准 G 的 pivot/暖收。
"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.quality import RE_BOOMERANG_RULE
from app.services.gold_story.structure_resolve import (
    CLOSING_MODE_AUTHORITY_PUNCHLINE,
)

# 去掉裸「管你」，避免「不用你管」假阳性；同路巧合允许「先问去向」类关心
RE_PIVOT = re.compile(
    r"护|撑腰|拼命|动你|心疼|认真的|我怕|别叫我|老弟|我弟|重要|舍不得|在乎|"
    r"你去哪|去哪儿|你一个人|一个人走|一个人回|陪你|放心不下|怕你|"
    r"你先说|你先讲",
)
RE_STUNNED = re.compile(
    r"你说啥|你说什么|……|\.\.\.|愣|啥\？|什么\？|笑出声|噗|忍不住笑",
)
RE_SOFT_CLOSE = re.compile(
    r"擦|药|说好了|行了|过来|撑腰|嗯|笑|好\s*吧|别.*欺负|识相|饶|原谅|算了|"
    r"一起走|一起去|一起回|走吧|同路|顺路|没走成|谁也没",
)
# M4+G 还允许“行动递台词”：一方先嘴硬/拒绝，看到对方示范后主动跟随，
# 用行为软化代替护短真情句；这是 H3 已允许的暖收分支，不是放宽成任意和好。
RE_BEHAVIOR_RESIST = re.compile(r"还没玩完|别动|不收|不想|不要|先歇|等会")
RE_BEHAVIOR_SOFTEN = re.compile(
    r"那我也|我也(?:来|做|收|读|看|学|帮)|我来(?:做|收|帮)|"
    r"我跟你|跟你一起|算我一个|这就(?:做|收|写|读)|一起(?:做|收|读|看|学)"
)
RE_BEHAVIOR_REACTION = re.compile(r"你(?:在)?[^，。！？?!]{0,8}(?:干嘛|做什么)|干嘛呢")
# 须双方僵持结构；裸「谁也不」会误伤「谁也没走成」
RE_F_STALE = re.compile(
    r"不跟你玩|不跟你好了|不理你|回家.*不|"
    r"谁也不理谁|谁也不跟谁说话|谁也不让谁|爱咋咋",
)

# 权威点题旁路槽位（抽象，禁绑平板/巧克力等单篇词）
RE_AUTH_RULE = re.compile(r"谁先|立规|约好|规定|规矩|定规|作业|写完")
RE_AUTH_REVERSE = re.compile(
    r"不罚|没发火|反而|反把|那今晚|那你负责|你负责|今晚你|负责哄|藏得"
)
RE_AUTH_CEDE = re.compile(
    r"立刻.*(给|塞|让)|你玩你玩|我哄|认怂|塞给|让出|你玩"
)
RE_AUTH_PUNCH = re.compile(
    r"记住|宣布|点破|并列|第[一二三]|这个家|这个班|听清楚|我说了算"
)
# 反将后抗拒/辩解（抽象：不会/不要/换/真不会，禁绑单篇词）
RE_AUTH_RESIST = re.compile(
    r"不会|不要|换件|换事|我真|凭什么|为啥|干嘛|不行吧|太难"
)


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


def _is_authority_punchline_mode(story: dict) -> bool:
    mode = str(story.get("closing_mode") or "").strip()
    return mode == CLOSING_MODE_AUTHORITY_PUNCHLINE


def _append_g_authority_punchline_errors(
    story: dict,
    errors: list[str],
    *,
    lines: list[str],
) -> None:
    body = "".join(lines)
    tail4 = "".join(lines[-4:])
    last = lines[-1] if lines else ""
    if not RE_AUTH_RULE.search(body):
        errors.append("G类(权威点题)：正文须有立规/约好槽")
    if not RE_AUTH_REVERSE.search(body):
        errors.append("G类(权威点题)：正文须有反将任务/不罚反递槽")
    if not RE_AUTH_RESIST.search(body):
        errors.append("G类(权威点题)：反将后须有抗拒/辩解槽")
    if not RE_AUTH_CEDE.search(body):
        errors.append("G类(权威点题)：正文须有认怂让渡槽")
    if not RE_AUTH_PUNCH.search(last):
        errors.append("G类(权威点题)：末句须权威点题/秩序宣布")
    elif not RE_AUTH_CEDE.search("".join(lines[:-1])):
        errors.append("G类(权威点题)：权威点题前须已有认怂让渡")
    else:
        # 让渡 → 点题：至多 1 句过渡，禁省略号空应答占行
        punch_i = len(lines) - 1
        cede_before = [
            i for i, ln in enumerate(lines[:-1]) if RE_AUTH_CEDE.search(ln)
        ]
        if cede_before:
            cede_i = cede_before[-1]
            gap = punch_i - cede_i - 1
            if gap > 1:
                errors.append("G类(权威点题)：让渡后至多1句过渡再到点题")
            for j in range(cede_i + 1, punch_i):
                mid = str(lines[j] or "").strip()
                if re.search(r"[…⋯]", mid) and len(mid) <= 10:
                    errors.append("G类(权威点题)：让渡后勿省略号空句占行")
                    break
                if re.fullmatch(r"[我你他她它]?\s*[…⋯。.！!？?\s]*", mid or ""):
                    errors.append("G类(权威点题)：让渡后勿空应答占行")
                    break
    if RE_BOOMERANG_RULE.search(tail4):
        errors.append("G类：末段勿 C 式回旋镖戳穿")
    if RE_F_STALE.search(tail4) and not RE_AUTH_PUNCH.search(tail4):
        errors.append("G类：末段勿 F 式威胁僵持")


def append_g_body_errors(story: dict, errors: list[str]) -> None:
    punch = str(story.get("punchline_explain") or "")
    if parse_story_type_code(punchline=punch) != "G":
        return
    lines, _speakers = _lines_and_speakers(story)
    if len(lines) < 10:
        return

    if _is_authority_punchline_mode(story):
        _append_g_authority_punchline_errors(story, errors, lines=lines)
        return
    if story.get("source_link_review") and "gold_g_source_structure" in story:
        if not source_g_structure_valid(story):
            errors.append("G来源结构证据缺失、失效或未通过，须重新审核")
        return

    body = "".join(lines)
    tail3 = "".join(lines[-3:])
    behavior_branch = bool(
        RE_BEHAVIOR_RESIST.search(body)
        and RE_BEHAVIOR_SOFTEN.search(body)
    )
    pivot_ok = bool(RE_PIVOT.search(body) or behavior_branch)
    stunned_ok = bool(
        RE_STUNNED.search(body)
        or (behavior_branch and RE_BEHAVIOR_REACTION.search(body))
    )
    soft_close_ok = bool(
        RE_SOFT_CLOSE.search(tail3)
        or (behavior_branch and RE_BEHAVIOR_SOFTEN.search(tail3))
    )
    if not pivot_ok:
        errors.append("G类：正文须有 pivot（护短/真心，或行动示范后主动跟随）")
    if not stunned_ok:
        errors.append("G类：pivot 后须有愣住/惊讶 beat（你说啥/你干嘛等）")
    if not soft_close_ok:
        errors.append("G类：末段须暖收或主动跟随（擦药/说好了/那我也…等）")
    if RE_BOOMERANG_RULE.search(tail3):
        errors.append("G类：末段勿 C 式回旋镖戳穿")
    # 末段已有暖收信号时，不把残余互呛词当 F 僵持
    if RE_F_STALE.search(tail3) and not soft_close_ok:
        errors.append("G类：末段勿 F 式威胁僵持")


G_SOURCE_ASPECTS = ('resistance', 'pivot', 'closing')
G_SOURCE_AUDIT_RULES = (
    '独立审核G嘴硬心软结构，不以既有分数或前序审核作证据。'
    '按resistance/pivot/closing三项核验：先数落或拒绝；同一人随后改变姿态愿意帮助；'
    '末段以具体示好或明确承诺收束。转折可由询问如何帮助表现，最终承诺才完成暖收。'
    '每项须有原文及当前成稿连续引文和语义支持，三项用不同句，按行号严格递增，closing在末三句。'
    '冷嘲贯穿、交易要挟、被迫屈服、没有前后态度反差、仅口头停止争吵均不算，pass=false。'
    '原文仅承诺时不能说已执行；不要求惊讶、护短或特定词汇。'
    '三项须分别说明语义依据，不能把同一句同一承诺重复算成转折和收束。'
    '输出g_structure_audit数组，每项含aspect、line(从1起整数)、pass(布尔)、'
    'quote(该行连续引文)、source_quote(原始素材逐字引文，不改称谓)、reason。缺阶段须明确判false。'
)


def source_g_binding(story: dict) -> str:
    import hashlib
    import json

    dialogue = [{'speaker': r.get('speaker'), 'line': r.get('line')} for r in story.get('dialogue') or []]
    payload = [story.get('source_raw'), story.get('source_role_mapping'), dialogue]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def source_g_audit_error(story: dict, items: object) -> str:
    rows = story.get('dialogue') or []
    source = str(story.get('source_raw') or '')
    if not isinstance(items, list) or len(items) != len(G_SOURCE_ASPECTS):
        return 'G来源结构审核须完整给出数落拒绝、态度转折、暖收三项'
    previous = 0
    for aspect, item in zip(G_SOURCE_ASPECTS, items):
        if not isinstance(item, dict):
            return 'G来源结构审核项须为对象'
        no = item.get('line')
        if (item.get('aspect') != aspect or type(no) is not int
                or not previous < no <= len(rows) or type(item.get('pass')) is not bool):
            return 'G来源结构审核须给出顺序递增的不同合法行号和布尔判定'
        if aspect == 'closing' and no < len(rows) - 2:
            return 'G暖收须发生在末三句'
        quote, source_quote = str(item.get('quote') or ''), str(item.get('source_quote') or '')
        if len(quote) < 2 or quote not in str(rows[no - 1].get('line') or ''):
            return f'G来源结构审核{aspect}引文不在第{no}句'
        if len(source_quote) < 4 or source_quote not in source:
            return f'G来源结构审核{aspect}的source_quote={source_quote!r}不在原文中；须逐字复制source_raw，不得用成稿台词或改写称谓'
        if not str(item.get('reason') or '').strip():
            return 'G来源结构审核缺少语义依据'
        previous = no
    if all(item['pass'] for item in items):
        speakers = [rows[item['line'] - 1].get('speaker') for item in items]
        if not speakers[0] or len(set(speakers)) != 1:
            return 'G拒绝到示好必须由同一个人完成，不能将对方屈服算成心软'
    return ''


def source_g_structure_valid(story: dict) -> bool:
    proof = story.get('gold_g_source_structure')
    return bool(story.get('source_link_review') and story.get('story_type') == 'G'
                and story.get('source_raw') and isinstance(proof, dict)
                and proof.get('binding') == source_g_binding(story)
                and not source_g_audit_error(story, proof.get('items'))
                and all(item['pass'] for item in proof['items']))
