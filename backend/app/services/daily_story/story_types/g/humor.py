"""G 类好笑维：pivot 反差与暖收；权威点题旁路。"""

from __future__ import annotations

import re

RE_ESCALATE = re.compile(
    r"丢人|嘴硬|怂|没记性|充|大侠|烦|骂|错错|少来|还敢|属狗|逮着就咬|狠心|有理|装|唬",
)
RE_PIVOT = re.compile(
    r"护|撑腰|拼命|动你|心疼|认真的|我怕|重要|舍不得|在乎|"
    r"你去哪|去哪儿|你一个人|一个人走|一个人回|陪你|放心不下|怕你|"
    r"你先说|你先讲",
)
RE_STUNNED = re.compile(r"你说啥|……|\.\.\.|愣|笑出声|噗|忍不住笑")
RE_SOFT = re.compile(
    r"擦|药|说好了|行了|过来|撑腰|相视|笑|识相|饶|原谅|算了|"
    r"一起走|一起去|一起回|走吧|同路|顺路|没走成|谁也没",
)

# 与 validate 权威点题槽位对齐（抽象，禁绑单篇词）
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


def authority_punchline_slots_hit(lines: list[str]) -> bool:
    body = "".join(lines)
    tail = "".join(lines[-4:]) if lines else ""
    return bool(
        RE_AUTH_RULE.search(body)
        and RE_AUTH_REVERSE.search(body)
        and RE_AUTH_CEDE.search(body)
        and (RE_AUTH_PUNCH.search(tail) or RE_AUTH_PUNCH.search(body))
    )


def collect_g_humor_issues(
    lines: list[str],
    speakers: list[str] | None = None,
) -> list[str]:
    del speakers
    issues: list[str] = []
    body = "".join(lines)
    if authority_punchline_slots_hit(lines):
        # 旁路：不卡真情 pivot/暖收；缺槽才报
        if not RE_AUTH_RULE.search(body):
            issues.append("缺立规/约好槽")
        if not RE_AUTH_REVERSE.search(body):
            issues.append("缺反将任务槽")
        if not RE_AUTH_CEDE.search(body):
            issues.append("缺认怂让渡槽")
        tail = "".join(lines[-4:]) if lines else ""
        if not RE_AUTH_PUNCH.search(tail) and not RE_AUTH_PUNCH.search(body):
            issues.append("缺权威点题收束")
        return issues
    if not RE_ESCALATE.search(body):
        issues.append("缺数落/互损升级")
    if not RE_PIVOT.search(body):
        issues.append("缺 pivot 护短/真心")
    if not RE_STUNNED.search(body):
        issues.append("缺 pivot 后愣住 beat")
    soft_tail = "".join(lines[-3:]) if lines else ""
    if soft_tail and not RE_SOFT.search(soft_tail):
        issues.append("末段缺暖收信号")
    return issues
