"""Q 类正文本地修稿（角色绑定 + 口语收口 + 接话去重）。"""

from __future__ import annotations

import re

from app.services.daily_story.story_types import parse_story_type_code
from app.services.daily_story.story_types.q.validate import (
    RE_BACKFIRE,
    RE_CHEAT_OWN,
    RE_EXPOSE,
    RE_PAD_TAIL,
    resolve_q_cheat_speaker,
)

_RE_PAD_CLAUSE = re.compile(
    r"[，,。！!]+\s*(?:"
    r"马上给我挪开|我才不怕呢|不许再耍赖了?|我偏就不信|"
    r"不行好不好|好不好呀|我可记住啦"
    r")[^。！!]*"
)
# 多尾音叠加（结果导向：不像单句口语）
_RE_STACKED_PARTICLES = re.compile(
    r"(?:"
    r"嘛了呀|啦了呀|了呀不行嘛|吧真的了呢|了呢|"
    r"真的了呢|了呀真的|好不好呀|不行嘛|真的好不好呀|"
    r"了吧真的了呢|了呀真的好不好"
    r")+$"
)
_RE_TRAILING_NOISE = re.compile(
    r"(?:了?呀|了?呢|了?吧|了?嘛|真的|好不好|不行){2,}[呀呢吧嘛]*$"
)


def _dialogue_rows(story: dict) -> list[dict]:
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    return [
        d
        for d in dialogue
        if isinstance(d, dict) and str(d.get("line") or "").strip()
    ]


def patch_q_fix_punchline_prefix(story: dict) -> list[str]:
    notes: list[str] = []
    explain = str(story.get("punchline_explain") or "").strip()
    if not explain:
        story["punchline_explain"] = "Q类耍赖翻车"
        notes.append("Q补 punchline 前缀")
        return notes
    if not explain.upper().startswith("Q"):
        story["punchline_explain"] = f"Q类耍赖翻车，{explain}"
        notes.append("Q补 punchline 前缀")
    return notes


def patch_q_bind_cheat_speaker(story: dict) -> list[str]:
    """第一人称耍赖/借口句归位到耍赖方（防姐弟抢戏）。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    if not rows:
        return notes
    cheater = resolve_q_cheat_speaker(story)
    fixed = 0
    for item in rows:
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "")
        if sp not in {"昭昭", "灿灿"} or sp == cheater:
            continue
        if not RE_CHEAT_OWN.search(line):
            continue
        if RE_EXPOSE.search(line) and not RE_CHEAT_OWN.search(
            re.sub(r"看穿|拆穿|揭穿|心思|偷|别装|露馅|明明|还装", "", line)
        ):
            continue
        item["speaker"] = cheater
        fixed += 1
    if fixed:
        notes.append(f"Q耍赖句归位→{cheater}×{fixed}")
    return notes


def _strip_stacked_particles(line: str) -> str:
    cleaned = _RE_STACKED_PARTICLES.sub("", line)
    cleaned = _RE_TRAILING_NOISE.sub("", cleaned)
    return cleaned.rstrip("，, ")


def patch_q_strip_pad_tails(story: dict) -> list[str]:
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    n = 0
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "")
        if not line.strip():
            continue
        cleaned = _RE_PAD_CLAUSE.sub("", line).rstrip("，, ")
        if RE_PAD_TAIL.search(cleaned):
            cleaned = RE_PAD_TAIL.sub("", cleaned).rstrip("，, ")
        cleaned = _strip_stacked_particles(cleaned)
        cleaned = cleaned.strip("，, 。！!？?")
        if not cleaned:
            sp = str(item.get("speaker") or "").strip()
            if sp == "妈妈":
                cleaned = "别再找借口了"
            elif sp == "昭昭":
                cleaned = "你这次又想耍赖"
            elif sp == "灿灿":
                cleaned = "我才没有耍赖"
            else:
                cleaned = "真的没有"
        if cleaned[-1] not in "。！!…？?":
            cleaned += "！"
        if cleaned != line:
            item["line"] = cleaned
            n += 1
    if n:
        notes.append(f"Q剥垫字尾巴{n}句")
    return notes


def patch_q_dedupe_bridges(story: dict) -> list[str]:
    """同一拆穿短接话不得复读；后现改为推进性短句。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    if len(rows) < 3:
        return notes
    seen: dict[str, int] = {}
    alts = [
        "签都认了还改口？",
        "刚才不是挺能的？",
        "这话我怎么不信？",
        "露馅了吧？",
        "你少来这套！",
    ]
    alt_i = 0
    n = 0
    for item in rows:
        sp = str(item.get("speaker") or "").strip()
        line = str(item.get("line") or "").strip()
        core = re.sub(r"[，,。！!？?\s]+", "", line)
        if len(core) > 12:
            continue
        if sp not in {"昭昭", "灿灿"}:
            continue
        if core not in seen:
            seen[core] = 1
            continue
        seen[core] += 1
        if seen[core] < 2:
            continue
        # 复读 → 换推进短句
        while alt_i < len(alts) and re.sub(
            r"[，,。！!？?\s]+", "", alts[alt_i]
        ) in seen:
            alt_i += 1
        if alt_i >= len(alts):
            break
        item["line"] = alts[alt_i]
        seen[re.sub(r"[，,。！!？?\s]+", "", alts[alt_i])] = 1
        alt_i += 1
        n += 1
    if n:
        notes.append(f"Q接话去重{n}句")
    return notes


def patch_q_strengthen_mom_backfire(story: dict) -> list[str]:
    """妈妈/终裁反噬若缺借口回指，补与推食/胃小的因果（抽象）。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    if not rows:
        return notes
    body = "".join(str(r.get("line") or "") for r in rows)
    # 取末段含反噬的妈妈句
    target = None
    for item in reversed(rows[-5:]):
        if str(item.get("speaker") or "").strip() != "妈妈":
            continue
        if RE_BACKFIRE.search(str(item.get("line") or "")):
            target = item
            break
    if target is None:
        return notes
    line = str(target.get("line") or "")
    has_excuse_echo = bool(re.search(r"推|剩|胃|借口|吃不下", line))
    if has_excuse_echo and ("胃" in line or "推" in line):
        return notes
    # 正文若出现胃小/推食，终裁须回指
    if re.search(r"胃小|剩的给你|推给", body):
        if RE_BACKFIRE.search(line) and not has_excuse_echo:
            target["line"] = "胃小吃不下就推给我？看穿了，去洗碗。"
            notes.append("Q妈妈反噬回指胃小推食")
        elif "小心思" in line and not has_excuse_echo:
            target["line"] = re.sub(
                r"小心思", "推食的小心思", line, count=1
            )
            notes.append("Q妈妈反噬点明推食因果")
    return notes


def patch_q_ensure_backfire_close(story: dict) -> list[str]:
    """末段缺反噬对白时，补妈妈回指借口的洗碗收束（抽象模板）。"""
    notes: list[str] = []
    rows = _dialogue_rows(story)
    if len(rows) < 8:
        return notes
    body = "".join(str(r.get("line") or "") for r in rows)
    tail = "".join(str(r.get("line") or "") for r in rows[-4:])
    if RE_BACKFIRE.search(tail):
        return notes
    if not re.search(r"胃小|推给|剩的|吃不下|耍赖", body):
        return notes
    close = "胃小吃不下就推给我？看穿了，去洗碗。"
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list):
        return notes
    # 优先改写末段妈妈句；勿在已满句时追加导致超限
    for item in reversed(dialogue[-5:]):
        if not isinstance(item, dict):
            continue
        if str(item.get("speaker") or "").strip() != "妈妈":
            continue
        item["line"] = close
        notes.append("Q补妈妈反噬收束")
        return notes
    if len(dialogue) < 24:
        dialogue.append({"speaker": "妈妈", "line": close})
        notes.append("Q追加妈妈反噬收束")
    else:
        last = dialogue[-1]
        if isinstance(last, dict):
            last["speaker"] = "妈妈"
            last["line"] = close
            notes.append("Q末句改妈妈反噬收束")
    return notes


def patch_q_trim_over_lines(story: dict, *, max_lines: int = 24) -> list[str]:
    """句数超上限时优先删极短接话，保剧情句。"""
    notes: list[str] = []
    dialogue = story.get("dialogue")
    if not isinstance(dialogue, list) or len(dialogue) <= max_lines:
        return notes
    removed = 0
    while len(dialogue) > max_lines:
        drop_i = None
        for i in range(1, len(dialogue) - 1):
            item = dialogue[i]
            if not isinstance(item, dict):
                continue
            sp = str(item.get("speaker") or "").strip()
            if sp not in {"昭昭", "灿灿"}:
                continue
            core = re.sub(r"[，,。！!？?\s]+", "", str(item.get("line") or ""))
            if 2 <= len(core) <= 8:
                drop_i = i
                break
        if drop_i is None:
            # 仍超：删中段一句（非末句）
            drop_i = max(1, len(dialogue) // 2)
        dialogue.pop(drop_i)
        removed += 1
    if removed:
        notes.append(f"Q超句删接话{removed}")
    return notes


def patch_q_body(story: dict) -> list[str]:
    notes: list[str] = []
    code = parse_story_type_code(
        story_type=str(story.get("story_type") or "") or None,
        punchline=str(story.get("punchline_explain") or ""),
    )
    if code != "Q":
        return notes
    notes.extend(patch_q_fix_punchline_prefix(story))
    notes.extend(patch_q_bind_cheat_speaker(story))
    notes.extend(patch_q_strip_pad_tails(story))
    notes.extend(patch_q_dedupe_bridges(story))
    notes.extend(patch_q_strengthen_mom_backfire(story))
    notes.extend(patch_q_ensure_backfire_close(story))
    notes.extend(patch_q_trim_over_lines(story))
    return notes
