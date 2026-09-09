"""H4a 金故事机审：规则硬卡 + LLM 站内适配评分。

可过：姐弟互怼，或孩子与家长的趣味冲突（家长配角）。
须卡：婴语纯可爱、无可拍冲突链、家长唯一主角且孩子无戏。
"""

from __future__ import annotations

import re
from typing import Any

from app.config import Config
from app.services.gold_story.collect import llm as llm_steps
from app.services.gold_story.scene import (
    validate_dialogue_seed_speakers,
    validate_scene,
)

_SIBLING_HINT = re.compile(
    r"姐弟|兄妹|哥哥|妹妹|二姐|弟弟|俩孩子|两个孩子|昭昭|灿灿|抢.*(?:姐姐|弟弟|哥|妹)",
    re.I,
)
_PARENT_CHILD = re.compile(r"妈妈|爸爸|母亲|父亲|宝妈|宝爸", re.I)
_STORY_RAW_TRIM_MAX = 380
_INFANT_SKEW = re.compile(r"婴语|话都说不清楚|小宝贝|人类幼崽|萌娃.*可爱", re.I)
_MOTHER_BABY_CONFLICT = re.compile(
    r"妈妈.*(?:宝宝|宝贝|睡|醒)|(?:宝宝|宝贝).*(?:妈妈|睡|醒)",
    re.I,
)


def _speaker_counts(dialogue_seed: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in dialogue_seed:
        if not isinstance(row, dict):
            continue
        name = str(row.get("speaker") or "").strip()
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _has_sibling_signal(*parts: str) -> bool:
    blob = "\n".join(str(p or "") for p in parts)
    return bool(_SIBLING_HINT.search(blob))


def run_rule_audit(
    *,
    title: str,
    story_raw: str,
    conflict_core: str,
    transcript: str,
    speaker_map_note: str,
    dialogue_seed: list[Any],
    beat: list[Any],
    scene_contract: dict[str, Any] | None = None,
    min_story_raw_chars: int = 100,
) -> tuple[bool, list[str]]:
    """规则机审；False 时 reasons 非空。"""
    reasons: list[str] = []
    if isinstance(scene_contract, dict) and scene_contract:
        contract_errors = validate_scene(scene_contract)
        if contract_errors:
            reasons.extend(contract_errors[:3])
        seed_errors = validate_dialogue_seed_speakers(dialogue_seed)
        if seed_errors:
            reasons.extend(seed_errors[:3])
    raw = str(story_raw or "").strip()
    if len(raw) < min_story_raw_chars:
        reasons.append(f"story_raw_too_short:{len(raw)}<{min_story_raw_chars}")

    seed = dialogue_seed if isinstance(dialogue_seed, list) else []
    if len(seed) < 4:
        reasons.append(f"dialogue_seed_too_short:{len(seed)}<4")

    beats = beat if isinstance(beat, list) else []
    if len(beats) < 4:
        reasons.append(f"beat_too_short:{len(beats)}<4")

    title_text = str(title or "")
    counts = _speaker_counts(seed)
    mom_lines = counts.get("妈妈", 0)
    dad_lines = counts.get("爸爸", 0)
    kid_lines = counts.get("昭昭", 0) + counts.get("灿灿", 0)
    sibling = _has_sibling_signal(
        title_text,
        raw,
        conflict_core,
        transcript,
        speaker_map_note,
        " ".join(
            str(r.get("speaker") or "")
            for r in seed
            if isinstance(r, dict)
        ),
    )
    if not sibling:
        # 孩子+家长对手戏也算可拍信号，勿只认姐弟词
        parent_cast = bool(
            _PARENT_CHILD.search(raw)
            or _PARENT_CHILD.search(conflict_core)
            or mom_lines
            or dad_lines
        )
        kid_cast = kid_lines >= 1 or bool(
            re.search(r"昭昭|灿灿|女儿|儿子|妹妹|弟弟", f"{title_text}\n{raw}")
        )
        if not (parent_cast and kid_cast):
            reasons.append("no_sibling_signal")

    mom_max = 1
    if isinstance(scene_contract, dict) and scene_contract.get("mom_lines_max") is not None:
        mom_max = max(0, int(scene_contract.get("mom_lines_max") or 0))
    if mom_lines > mom_max and kid_lines < 2:
        reasons.append("dialogue_seed_mother_heavy")
    elif mom_lines >= 2 and kid_lines < 2:
        reasons.append("dialogue_seed_mother_heavy")
    # 爸爸配角：句数宜更少；孩子戏份不足才算家长过重
    if dad_lines >= 3 and kid_lines < 2:
        reasons.append("dialogue_seed_father_heavy")
    elif dad_lines >= 2 and kid_lines < 2:
        reasons.append("dialogue_seed_father_heavy")

    blob = f"{title_text}\n{raw}\n{conflict_core}"
    if _MOTHER_BABY_CONFLICT.search(blob) and not _has_sibling_signal(
        title_text, raw, speaker_map_note
    ):
        reasons.append("mother_baby_conflict_only")

    if _INFANT_SKEW.search(title_text) and not _SIBLING_HINT.search(title_text):
        reasons.append("infant_skew_title")

    map_note = str(speaker_map_note or "")
    # 映射说明写「保留家长」时须已有姐弟信号（保留爸爸配角+姐弟可过）
    if _PARENT_CHILD.search(map_note) and "保留" in map_note:
        if not _has_sibling_signal(
            title_text, raw, speaker_map_note, conflict_core,
        ):
            reasons.append("mapping_keeps_parent_role")

    return (len(reasons) == 0, reasons)


def _maybe_trim_story_raw(story_raw: str, *, max_chars: int = _STORY_RAW_TRIM_MAX) -> tuple[str, bool]:
    """过长 story_raw → LLM 精简；失败则原样返回。"""
    text = str(story_raw or "").strip()
    if len(text) <= max_chars:
        return text, False
    try:
        return llm_steps.trim_story_raw(text, max_chars=max_chars), True
    except ValueError:
        return text, False


def audit_story(
    *,
    title: str,
    story_raw: str,
    conflict_core: str,
    transcript: str = "",
    h3: dict[str, Any] | None = None,
    h3a: dict[str, Any] | None = None,
    h3b: dict[str, Any] | None = None,
    video_title: str = "",
    description: str = "",
    config: Config | None = None,
) -> dict[str, Any]:
    """H4a 机审。pass=True → 可 active；False → rejected。"""
    cfg = config or Config()
    h3 = h3 or {}
    h3a = h3a or {}
    h3b = h3b or {}
    story_raw, story_raw_trimmed = _maybe_trim_story_raw(story_raw)
    dialogue_seed = h3b.get("dialogue_seed") or []
    beat = h3.get("beat") or []
    speaker_map_note = str(h3b.get("speaker_map_note") or h3a.get("remap_note") or "")

    rule_pass, rule_reasons = run_rule_audit(
        title=title,
        story_raw=story_raw,
        conflict_core=conflict_core,
        transcript=transcript,
        speaker_map_note=speaker_map_note,
        dialogue_seed=dialogue_seed,
        beat=beat,
        scene_contract=h3a or None,
        min_story_raw_chars=cfg.gold_story_audit_min_story_raw_chars,
    )
    base: dict[str, Any] = {
        "pass": False,
        "stage": "rules",
        "rule_pass": rule_pass,
        "rule_reasons": rule_reasons,
        "story_raw_trimmed": story_raw_trimmed,
        "llm": None,
    }
    if not rule_pass:
        base["reject_reasons"] = list(rule_reasons)
        return base

    if not cfg.gold_story_audit_enabled:
        base.update({"pass": True, "stage": "disabled", "reject_reasons": []})
        return base

    try:
        llm = llm_steps.audit_story_fit(
            video_title=video_title or title,
            title=str(h3.get("title") or title),
            story_raw=story_raw,
            conflict_core=conflict_core,
            mechanism=str(h3.get("mechanism") or ""),
            structure_type=str(h3.get("structure_type") or ""),
            speaker_map_note=speaker_map_note,
            dialogue_seed=dialogue_seed,
            beat=beat,
            transcript=transcript,
            description=description,
            min_sibling_fit=cfg.gold_story_audit_min_sibling_fit,
            min_age_fit=cfg.gold_story_audit_min_age_fit,
            min_conflict_usable=cfg.gold_story_audit_min_conflict_usable,
            min_mapping_fit=cfg.gold_story_audit_min_mapping_fit,
        )
    except ValueError as exc:
        base.update(
            {
                "stage": "llm",
                "reject_reasons": [str(exc)],
            }
        )
        return base

    base["llm"] = llm
    base["stage"] = "llm"
    if llm.get("pass"):
        base["pass"] = True
        base["reject_reasons"] = []
    else:
        base["reject_reasons"] = list(llm.get("reject_reasons") or ["llm_audit_failed"])
    return base
