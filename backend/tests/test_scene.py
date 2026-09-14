"""H3a scene_contract 与成品对白 hard 校验测试。"""

from __future__ import annotations

import pytest

from app.services.gold_story.gold_chat.validate import (
    validate_chat_hard,
)
from app.services.gold_story.scene import (
    apply_parent_role_budget,
    format_scene_block,
    seed_from_beat_chain,
    validate_scene,
)


def _sample_contract() -> dict:
    return {
        "source_type": "field",
        "location": "客厅",
        "object": "遥控器",
        "characters": ["昭昭", "灿灿"],
        "conflict": "抢遥控器",
        "mechanism": "M2",
        "mom_lines_max": 0,
        "remap_note": "姐弟→昭昭灿灿",
        "beat_chain": [
            {"speaker": "灿灿", "intent": "占物"},
            {"speaker": "昭昭", "intent": "质疑"},
            {"speaker": "灿灿", "intent": "歪理"},
            {"speaker": "昭昭", "intent": "威胁"},
        ],
        "closing_intent": "嘴硬收束",
        "contract_confidence": 0.8,
    }


def test_validate_scene_ok():
    assert validate_scene(_sample_contract()) == []


def test_validate_scene_rejects_short_chain():
    bad = {**_sample_contract(), "beat_chain": [{"speaker": "昭昭", "intent": "a"}]}
    errs = validate_scene(bad)
    assert any("beat_chain" in e for e in errs)


def test_format_scene_block():
    block = format_scene_block(_sample_contract())
    assert "scene_contract" in block
    assert "昭昭" in block
    assert "beat_chain" in block


def test_seed_from_beat_chain():
    seed = seed_from_beat_chain(_sample_contract()["beat_chain"])
    assert len(seed) == 4
    assert seed[0]["speaker"] == "灿灿"


def test_force_age_score_remap_rewrites_adult_totals():
    from app.services.gold_story.scene import (
        age_remap_contract_errors,
        force_age_score_remap,
    )

    raw = "姐姐高考考了383分，要是683分妹妹会感谢。"
    contract = {
        "object": "383分成绩单",
        "conflict": "妹妹宣扬姐姐383分，对比683分",
        "mechanism": "宣传高分该谢",
        "beat_chain": [
            {"speaker": "妈妈", "intent": "责备宣扬383分"},
            {"speaker": "昭昭", "intent": "辩称683分会感谢"},
        ],
        "remap_note": "高考迁龄说明可保留字样",
    }
    assert age_remap_contract_errors(raw, contract)
    out, changed = force_age_score_remap(contract, story_raw=raw)
    assert changed
    assert not age_remap_contract_errors(raw, out)
    blob = f"{out['object']}{out['conflict']}{out['beat_chain']}"
    assert "383" not in blob
    assert "683" not in blob
    assert "58分" in blob and "98分" in blob


def test_scrub_h3_beat_list_remaps_sibling_and_score():
    from app.services.gold_story.scene import scrub_h3_beat_list

    beat = ["妹妹宣扬姐姐383分，妈妈责备其戳痛处"]
    out = scrub_h3_beat_list(
        beat,
        story_raw="姐姐高考考了383分，妹妹到处宣扬。",
    )
    assert out[0] == "昭昭宣扬灿灿58分，妈妈责备其戳痛处"


def test_sync_contract_exam_scores_follows_seed_mode():
    from app.services.gold_story.scene import sync_contract_exam_scores

    contract = {
        "conflict": "昭昭到处说姐姐考了58分",
        "object": "58分试卷",
        "remap_note": "58分迁为小学量级",
        "beat_chain": [{"speaker": "妈妈", "intent": "说姐姐83分？"}],
    }
    seed = [{"speaker": "妈妈", "intent": "昭昭，你满小区说姐姐83分？"}]
    out, core, changed = sync_contract_exam_scores(
        contract,
        dialogue_seed=seed,
        conflict_core=contract["conflict"],
    )
    assert changed
    assert "83分" in out["conflict"]
    assert "58分" not in out["conflict"]
    assert "83分" in core


def test_apply_parent_role_budget_keeps_mom_when_h3_beat_has_parent():
    contract = _sample_contract()
    contract["story_type"] = "I"
    contract["mom_lines_max"] = 0
    h3 = {
        "structure_type": "I",
        "beat": [
            "妹妹宣扬差分，妈妈责备戳痛处",
            "妹妹辩称宣传高分该感谢",
            "妈妈反问冰箱逻辑，妹妹语塞",
            "妈妈点出开好头，妹妹嘴硬",
        ],
    }
    out = apply_parent_role_budget(contract, h3=h3)
    assert int(out["mom_lines_max"]) >= 2
    assert "妈妈" in out["characters"]
    assert "戏核家长须保留出场" in str(out.get("remap_note") or "")


def test_apply_parent_role_budget_pure_sibling_stays_zero():
    contract = _sample_contract()
    contract["story_type"] = "C"
    h3 = {
        "structure_type": "C",
        "beat": ["占物", "质问", "歪理", "嘴硬"],
    }
    out = apply_parent_role_budget(contract, h3=h3)
    assert int(out["mom_lines_max"]) == 0
    assert "妈妈" not in out["characters"]


def _long_dialogue(n: int = 14) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for i in range(n):
        sp = "昭昭" if i % 2 else "灿灿"
        lines.append({"speaker": sp, "line": f"这是第{i + 1}句可拍对白，我们当场说清楚。"})
    return lines


def test_validate_chat_hard_ok():
    story = {"dialogue": _long_dialogue(14)}
    assert validate_chat_hard(story, mom_lines_max=0) == []


def test_validate_chat_hard_rejects_short_lines():
    story = {"dialogue": _long_dialogue(8)}
    errs = validate_chat_hard(story)
    assert any("对白句数" in e for e in errs)


def test_validate_chat_hard_allows_mom_last():
    lines = _long_dialogue(14)
    lines[-1] = {"speaker": "妈妈", "line": "好了别吵了。"}
    errs = validate_chat_hard(lines_to_story(lines), mom_lines_max=1)
    assert not any("末句" in e for e in errs)


def lines_to_story(lines: list[dict[str, str]]) -> dict:
    return {"dialogue": lines}
