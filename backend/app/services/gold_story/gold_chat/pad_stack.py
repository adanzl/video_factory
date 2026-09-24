"""垫字叠字：review 审稿与 length 清理共用判定。"""

from __future__ import annotations

import copy
import re
from typing import Any, Literal

PadLineKind = Literal["none", "clear_pad", "keep_question", "uncertain"]

_RE_KID_TYPO_LINE = re.compile(r"听听不懂|你真是呢")

# review._RE_PARTICLE_STACK 与 length._RE_PAD_SUFFIX_STACK 并集（不含裸「好不好呀」）
RE_PARTICLE_STACK = re.compile(
    r"呢呢|啊呢|吧呢|嘛呢|呀呢|你呀呢|行了吧呢|"
    r"真的呀真的|嘛呀|了呢|不行嘛|活该了呢|"
    r"(?:真的(?:呀|呢|吧)){2,}|嘛不行嘛|"
    r"(?:不行吧|真的啊|你听着|你听着了呀|真的嘛了呀|嘛了呀){2,}|"
    r"(?:不行(?:真的|了?[啊吧呀呢嘛])?){2,}|"
    r"(?:了[啊吧呀呢]){2,}|"
    r"不行真的不行|真的了啊|真的呀不行|了吧不行|了啊不行|"
    r"活该嘛呀|不行嘛呀|"
    r"嘛呀[！。？…!?]|了呢呀|了呢了呀|"
    r"不懂你呢|你真是的呢|"
    r"了呀呢|好不好了呀|着呢了呀|"
    r"嘛真的(?:吧|呢|呀)(?=[！。？…!?]|$)|"
    r"咯(?:呢|吧|呀|啊)(?=[！。？…!?]|$)|"
    r"真的了呢|真的了吧|不行了吧真的|了吧真的了|不行了吧|吧真的了呢",
)

RE_HAOBU_TAIL = re.compile(r"(?:好不好呀|好不好)(?=[。！？…!?]|$)")

# 正常询问/邀请：保留句尾「好不好呀」
RE_GENUINE_HAOBU_QUESTION = re.compile(
    r"(?:一起|要不要|能不能|可不可以|是不是|行不行|可以吗|愿不愿意|"
    r"还来|去玩|来玩|试试|摸(?:摸)?|给你|跟我|陪(?:我|你)|咱们|我们去|你来|"
    r"再(?:说|看|试|等|考虑|商量)|明[天日]|下[次回])",
)

RE_CLEAR_STATEMENT_HAOBU = re.compile(
    r"(?:成功|完了|好了|到了|赢啦|搞定|结束|救场|搞定啦|成了)[^。！？…!?]{0,8}"
    r"(?:好不好呀|好不好)[。！？…!?]?$",
)

RE_COMPOUND_PAD = re.compile(r"(?:不行了吧|真的了呢|了吧真的)")
RE_GLUED_BU_XING = re.compile(
    r"(?<=[\u4e00-\u9fff])(?<![还就再真都也说])不行"
    r"(?=[，,！!。？?…]|$)",
)

# 与 length 原 _RE_PAD_SUFFIX_STACK 等价，供 patch 门控
RE_PAD_SUFFIX_STACK = RE_PARTICLE_STACK


def is_genuine_haobu_question(line: str) -> bool:
    """「我们一起玩好不好呀？」类保留；陈述强接尾巴不算。"""
    if not RE_HAOBU_TAIL.search(line):
        return False
    body = RE_HAOBU_TAIL.sub("", line).strip().rstrip("。！？…!?")
    if RE_GENUINE_HAOBU_QUESTION.search(body):
        return True
    if re.search(
        r"(?:你|咱|咱们|我们|姐姐|昭昭|灿灿).{0,20}(?:吗|么)[？?]?$",
        line,
    ):
        return True
    return False


def classify_pad_line(line: str) -> PadLineKind:
    if not line.strip():
        return "none"
    if _RE_KID_TYPO_LINE.search(line):
        return "uncertain"
    if RE_PARTICLE_STACK.search(line) or RE_COMPOUND_PAD.search(line):
        return "clear_pad"
    if RE_GLUED_BU_XING.search(line):
        return "clear_pad"
    if RE_HAOBU_TAIL.search(line):
        if is_genuine_haobu_question(line):
            return "keep_question"
        if RE_CLEAR_STATEMENT_HAOBU.search(line):
            return "clear_pad"
        return "uncertain"
    return "none"


def line_needs_pad_sanitize(line: str) -> bool:
    return classify_pad_line(line) == "clear_pad"


def _strip_statement_haobu_tail(line: str) -> str:
    if is_genuine_haobu_question(line):
        return line
    out = re.sub(r"(?:好不好呀|好不好)([。！？…!?]?)$", r"\1", line)
    if out == line:
        return line
    if out and out[-1] not in "。！？…!?":
        punct = line[-1] if line[-1] in "。！？…!?" else "。"
        out = out.rstrip("，, ") + punct
    return out.strip()


def sanitize_pad_stack_line(line: str) -> str:
    """机械去叠语气词；陈述句「…成功好不好呀。」去强接尾巴。"""
    out = _strip_statement_haobu_tail(line)
    # 句尾混合粒子统一降成一个原始语气词，避免「嘛真的吧 / 咯呢」类机械补字。
    out = re.sub(
        r"嘛真的(?:吧|呢|呀)([！。？…!?]?)$",
        r"嘛\1",
        out,
    )
    out = re.sub(
        r"咯(?:呢|吧|呀|啊)([！。？…!?]?)$",
        r"咯\1",
        out,
    )
    out = re.sub(r"不行了呢([！。？…!?]?)$", r"不行\1", out)
    out = re.sub(r"([^不])了呢([！。？…!?])$", r"\1\2", out)
    for old, new in (
        ("呢呢", "呢"),
        ("啊呢", "啊"),
        ("吧呢", "吧"),
        ("嘛呢", "嘛"),
        ("呀呢", "呀"),
        ("你呀呢", "你呀"),
        ("行了吧呢", "行了吧"),
        ("不懂你呢", "听不懂你"),
        ("听听不懂", "听不懂"),
        ("你真是呢", "你真是的"),
        ("你真是的呢", "你真是的"),
        ("着呢了呀", "着呢"),
        ("你听着了呀", ""),
        ("你听着呀", ""),
        ("好呢了呀", "呢"),
        ("好不好了呀", ""),
        ("了呢了呀", ""),
        ("了呢呀", ""),
        ("了呀呢", ""),
        ("嘛不行嘛呀", ""),
        ("嘛不行嘛", ""),
        ("真的呀不行嘛", "真的不行"),
        ("不行嘛呀", "不行"),
        ("活该嘛呀", "活该"),
        ("活该了呢", "活该"),
    ):
        if old in out:
            out = out.replace(old, new)
    out = re.sub(r"(?:真的(?:呀|呢|吧|啊)?){2,}", "真的", out)
    out = re.sub(r"(?:不行(?:真的|了?[啊吧呀呢嘛])?){2,}", "不行", out)
    out = re.sub(r"(?:了[啊吧呀呢]){2,}", "", out)
    for junk in (
        "不行真的不行",
        "真的了啊",
        "真的呀不行",
        "了吧不行",
        "了啊不行",
    ):
        out = out.replace(junk, "")
    out = re.sub(
        r"(?:不行了吧|不行了呢|不行了啊|不行真的)+"
        r"(?:真的了?[呢啊吧呀嘛]?)+[！。？…!]?$",
        "",
        out,
    )
    out = re.sub(
        r"(?:真的了呢|了吧真的了呢|了吧真的|真的呀真的|真的了呢了呀)+"
        r"[！。？…!]?$",
        "",
        out,
    )
    out = re.sub(
        r"(?:真的(?:呀|呢|吧|了)?|不行(?:真的)?|了[呀呢吧啊嘛]){3,}",
        "",
        out,
    )
    out = re.sub(
        r"(?:不行吧|真的啊|你听着|你听着了呀|真的呀|嘛了呀){2,}"
        r"([！。！？…]?)$",
        r"\1",
        out,
    )
    out = re.sub(r"嘛呀([！。？…!?])$", r"\1", out)
    out = re.sub(r"真的(?:呀|呢|吧)?([！。？…!?])$", r"\1", out)
    out = re.sub(r"不行嘛([！。？…!?])$", r"不行\1", out)
    out = re.sub(
        r"(?<=[\u4e00-\u9fff])(?<![还就再真都也说行])不行"
        r"(?![呢])(?=[，,！!。？?…]|$)",
        "",
        out,
    )
    out = re.sub(r"[，,]{2,}", "，", out).strip("，, ")
    if out and out[-1] not in "！。？…!?" and line[-1:] in "！。？…!?":
        out += line[-1]
    return out


def pad_stack_issue_for_line(line: str, line_no: int) -> dict[str, Any] | None:
    """审稿/验收：仅报清理后仍须 LLM 定点改的垫字。"""
    line = str(line or "").strip()
    if not line:
        return None
    kind = classify_pad_line(line)
    if kind in {"none", "keep_question"}:
        return None
    if _RE_KID_TYPO_LINE.search(line):
        return {
            "lines": [line_no],
            "kind": "语病",
            "desc": f"明显语病/错字：{line}",
            "fix": "「听听不懂」→「听不懂」；「你真是呢」→「你真是的」",
        }
    if kind == "uncertain":
        return {
            "lines": [line_no],
            "kind": "垫字叠字",
            "desc": f"句尾语气/垫字需定点改写：{line}",
            "fix": "保留真实问句语气；陈述句去掉强接尾巴；"
            "用实义短语补字数，禁呢呢/啊呢/吧呢堆砌",
        }
    cleaned = sanitize_pad_stack_line(line)
    if cleaned != line and str(cleaned or "").strip():
        return None
    return {
        "lines": [line_no],
        "kind": "垫字叠字",
        "desc": f"句尾叠语气词/不通：{line}",
        "fix": "改成自然口语；禁呢呢/啊呢/吧呢/你呀呢；"
        "可用实义短句补字数（如「我改还不成吗」「我可盯着呢」）",
    }


def collect_pad_stack_issues(story: dict) -> list[dict[str, Any]]:
    """扫昭昭/灿灿台词垫字（与 daily_story.review 共用）。"""
    rows = story.get("dialogue")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        sp = str(row.get("speaker") or "").strip()
        if sp not in ("昭昭", "灿灿"):
            continue
        issue = pad_stack_issue_for_line(str(row.get("line") or ""), i)
        if issue:
            out.append(issue)
    return out


def apply_clear_pad_sanitize(
    story: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """只清明确垫字，不垫字数、不 LLM。"""
    out = copy.deepcopy(story)
    changed = False
    for item in out.get("dialogue") or []:
        if not isinstance(item, dict):
            continue
        old = str(item.get("line") or "").strip()
        if not old or not line_needs_pad_sanitize(old):
            continue
        new = sanitize_pad_stack_line(old)
        if not str(new or "").strip():
            speaker = str(item.get("speaker") or "").strip()
            new = "我……" if speaker in {"昭昭", "灿灿"} else "行了。"
        if new != old:
            item["line"] = new
            changed = True
    dialogue = out.get("dialogue")
    if isinstance(dialogue, list):
        out["dialogue"] = [
            item
            for item in dialogue
            if isinstance(item, dict) and str(item.get("line") or "").strip()
        ]
    return out, changed
