"""A 类常见主题的可核对事实（算式、时长等）。"""

from __future__ import annotations

import re

_CN_DIGIT: dict[str, int] = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _parse_cn_small_int(s: str) -> int | None:
    if not s:
        return None
    if s == "十":
        return 10
    if s.startswith("十") and len(s) == 2:
        return 10 + _CN_DIGIT.get(s[1], 0)
    if "十" in s:
        head, _, tail = s.partition("十")
        hi = _CN_DIGIT.get(head, 1) if head else 1
        lo = _CN_DIGIT.get(tail, 0) if tail else 0
        return hi * 10 + lo
    if len(s) == 1 and s in _CN_DIGIT:
        return _CN_DIGIT[s]
    return None


def parse_duration_minutes(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        n = int(token)
        return n if 0 < n <= 180 else None
    n = _parse_cn_small_int(token)
    if n is None or n <= 0 or n > 180:
        return None
    return n


def append_homework_fact_errors(story: dict, errors: list[str]) -> None:
    """教作业类：首句权责与口算事实勿自相矛盾。"""
    setting = str(story.get("setting") or "")
    core = str(story.get("conflict_core") or "")
    punch = str(story.get("punchline_explain") or "")
    blob = setting + core + punch
    if not re.search(r"作业|算术|算数|口算|竖式|算题", blob):
        return

    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return

    first = dialogue[0]
    if isinstance(first, dict):
        sp = str(first.get("speaker") or "").strip()
        line0 = str(first.get("line") or "")
        if sp == "昭昭" and re.search(r"也算错|也写错|你也错", line0):
            errors.append(
                "教作业：正文首句应由灿灿查/教，禁止昭昭无前提「也算错了」",
            )
        if sp == "昭昭" and "也" in line0[:10] and "姐" in line0:
            errors.append(
                "教作业：首句「也」缺前文，改灿灿先挑错",
            )

    lines_text = [
        str(d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict)
    ]
    full = "".join(lines_text)
    sum_m = re.search(
        r"(\d{1,3})\s*[加＋]\s*(\d{1,3})",
        full,
    )
    if not sum_m:
        return
    a, b = int(sum_m.group(1)), int(sum_m.group(2))
    correct = a + b
    correct_s = str(correct)

    # 灿灿用正确得数批弟弟错答案，却标成「姐姐算错」
    if (
        correct_s in full
        and re.search(r"算错|写错|教.*错", punch)
        and any(
            sp == "灿灿"
            and correct_s in ln
            and str(a) in ln
            and str(b) in ln
            for sp, ln in (
                (str(d.get("speaker") or "").strip(), str(d.get("line") or ""))
                for d in dialogue
                if isinstance(d, dict)
            )
        )
    ):
        wrong_claim = re.search(
            rf"{correct_s}.*错|错.*{correct_s}",
            full,
        )
        if not wrong_claim:
            errors.append(
                f"教作业事实：{a}+{b}={correct}为正确得数，"
                "灿灿若用该数批弟弟则不算姐姐算错，须改灿灿说错的得数",
            )


DURATION_TOKEN_RE = re.compile(
    r"(?:半分钟|"
    r"(?:\d+|二十[一二三四五六七八九]?|十[一二三四五六七八九]?|"
    r"[一二三四五六七八九两])分半|"
    r"(?:\d+|二十[一二三四五六七八九]?|十[一二三四五六七八九]?|"
    r"[一二三四五六七八九两])分钟)"
)

def duration_token_to_seconds(token: str) -> int | None:
    t = token.strip()
    if t == "半分钟":
        return 30
    if t.endswith("分半"):
        head = t[:-2]
        n = parse_duration_minutes(head)
        return None if n is None else n * 60 + 30
    if t.endswith("分钟"):
        n = parse_duration_minutes(t[:-2])
        return None if n is None else n * 60
    return None


def iter_duration_seconds(text: str) -> list[int]:
    out: list[int] = []
    for m in DURATION_TOKEN_RE.finditer(text or ""):
        sec = duration_token_to_seconds(m.group(0))
        if sec is not None:
            out.append(sec)
    return out


def append_brush_timer_fact_errors(story: dict, errors: list[str]) -> None:
    """刷牙/计时类：本场一锤时长全文只认一套，禁半分钟与一分半混用。"""
    setting = str(story.get("setting") or "")
    core = str(story.get("conflict_core") or "")
    punch = str(story.get("punchline_explain") or "")
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return
    lines_text = [
        str(d.get("line") or "")
        for d in dialogue
        if isinstance(d, dict)
    ]
    full = "".join(lines_text)
    blob = setting + core + punch + full
    if not re.search(r"刷牙|刷够", blob):
        return

    all_secs = set(iter_duration_seconds(full))
    if len(all_secs) >= 4:
        errors.append(
            "可核对事实：刷牙/计时出现≥4种不同时长，"
            "本场一锤只留一套数（规则+弟弟+姐姐各至多一个）",
        )

    sister_secs: set[int] = set()
    brother_secs: set[int] = set()
    for line in lines_text:
        secs = iter_duration_seconds(line)
        if not secs:
            continue
        if re.search(
            r"自己.{0,8}(?:刷|才)|上次.{0,12}(?:刷|才)|我那次|计时器上自己",
            line,
        ):
            sister_secs.update(secs)
        if re.search(
            r"你刷.{0,8}才|我(?:用了计时器|刷).{0,8}|"
            r"正好.{0,4}(?:两|二|\d)|刷干净了",
            line,
        ) or (
            "正好" in line and iter_duration_seconds(line)
        ):
            if not re.search(r"自己|我那次|上次你|上次才", line):
                brother_secs.update(secs)

    if len(sister_secs) >= 2:
        errors.append(
            "可核对事实：灿灿自己刷牙时长前后不一"
            "（如半分钟与一分半），全文只留一个数",
        )
    if len(brother_secs) >= 2:
        errors.append(
            "可核对事实：昭昭刷牙时长前后不一"
            "（如才一分钟又说正好两分钟），请统一",
        )

