"""A 类正文本地修稿。

加规则红线（新增前必读）：
- patch 只做**类型级**结构修补：删句/去重/改 speaker/引话接地，
  以及不含主题词的类型通用短句。
- 禁止绑定具体 theme 的规则（按「偷吃/水果/鞋带」等关键词分支
  改写台词）——主题落到分支外时会整段盖成不贴题的模板文。
  内容不合格一律交 LLM 重试，不在本地按主题造句。
"""

from __future__ import annotations

import re

from app.services.daily_story.dialogue_text import (
    DAILY_STORY_LINE_CHARS_MAX,
    dialogue_char_count,
    truncate_overlong_line,
)

RE_CLOSING_QUOTE = re.compile(
    r"(?:你刚才(?:明明|自己)?说|你自己(?:刚才)?说|你不是说|你刚说|你说的)"
    r"([^，。！？…]{3,})",
)


def quote_grounded(frag: str, hay: str) -> bool:
    clean = re.sub(r"[的话呢呀嘛吧啊…\s「」『』“”\"'‘’：:]", "", frag)
    hay2 = re.sub(r"[\s「」『』\"'‘’]", "", hay)
    if len(clean) < 3:
        return True
    run = 6 if len(clean) >= 6 else max(3, min(5, len(clean)))
    for i in range(len(clean) - run + 1):
        if clean[i : i + run] in hay2:
            return True
    return False


def _overlap_chars(a: str, b: str) -> int:
    """两句话共用的实词字符数（引话 paraphrase 与灿灿原话的重合度）。"""
    ca = set(re.sub(r"[^一-鿿]", "", a))
    cb = set(re.sub(r"[^一-鿿]", "", b))
    return len(ca & cb)


def pick_cite_chunk(cancan_line: str) -> str:
    """从灿灿原话抽可引子串（优先「XX不算YY」类免责句核；否则取首个分句）。

    非免责主题（鞋带「鞋扣朝外就对了」/刷牙「吐水也算停」）没有「不算」核，
    取逗号/自称动作前的首分句，剔掉「我系/我给你/你看着」类示范尾巴。
    """
    text = re.sub(r"^[「」\"'‘’]+|[「」\"'‘’]+$", "", cancan_line.strip())
    for m in re.finditer(r"[^，。！？…；;]{4,14}", text):
        chunk = m.group(0).strip()
        if re.search(r"不算|算停|才算", chunk):
            return chunk
    clause = re.split(r"[，。！？…；;]", text, maxsplit=1)[0].strip()
    clause = re.split(
        r"(我系|我给你|你看着|你数着|别眨眼|你学着|你尝尝|你自己|这就算|你仔细)",
        clause,
        maxsplit=1,
    )[0].strip()
    if len(clause) >= 4:
        return clause
    compact = re.sub(r"[的话呢呀嘛吧啊啦]", "", text)
    return compact[:14] if len(compact) >= 4 else text[:14]


def patch_closing_quotes(story: dict) -> list[str]:
    """引话未接地：仅当灿灿前文已有可引原话时，把昭昭引语改成其子串。

    前文没有可对齐的埋点就不硬改（交给 LLM 重试）。
    """
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return notes
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "昭昭":
            continue
        line = str(item.get("line") or "")
        m = RE_CLOSING_QUOTE.search(line)
        if not m:
            continue
        frag = m.group(1).strip()
        prior_lines = [
            str(d.get("line") or "")
            for d in dialogue[:i]
            if isinstance(d, dict)
            and str(d.get("speaker") or "").strip() == "灿灿"
            and str(d.get("line") or "").strip()
        ]
        prior = "".join(prior_lines)
        if not prior.strip():
            continue
        if quote_grounded(frag, prior):
            continue
        # 重合度优先：引语 paraphrase 与哪句灿灿前文共用字最多，就对齐到哪句
        best_donor, best_hit = "", 0
        for ln in reversed(prior_lines):
            hit = _overlap_chars(frag, ln)
            if hit > best_hit:
                best_donor, best_hit = ln, hit
        donor = best_donor if best_hit >= 2 else ""
        if not donor:
            # 兜底：找不到像的埋句时，退到旧逻辑的「不算/才算/不许/不能/别」免责核句
            for ln in reversed(prior_lines):
                if re.search(r"不算|才算|不许|不能|别", ln):
                    donor = ln
                    break
        # 没有可对齐埋点就别乱改引话
        if not donor:
            continue
        cite = pick_cite_chunk(donor)
        if not cite or (not quote_grounded(cite, donor) and cite not in donor):
            cite = donor[: min(12, len(donor))]
        head = line[: m.start(1)]
        tail = line[m.end(1) :]
        room = DAILY_STORY_LINE_CHARS_MAX - dialogue_char_count(head + tail)
        if room < 4:
            continue
        new_frag = cite if dialogue_char_count(cite) <= room else cite[:room]
        new_line = f"{head}{new_frag}{tail}"
        if dialogue_char_count(new_line) > DAILY_STORY_LINE_CHARS_MAX:
            new_line = truncate_overlong_line(new_line)
        if new_line != line:
            item["line"] = new_line
            notes.append(f"引话对齐[{i}]")
            break
    return notes


def patch_a_body(story: dict) -> list[str]:
    """只做引话接地；主题相关修稿交 LLM 重试。"""
    notes: list[str] = []
    notes.extend(patch_closing_quotes(story))
    return notes
