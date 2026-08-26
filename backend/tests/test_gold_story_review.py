"""金故事 H4a 机审测试。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.daily_story.gold_story.collect import review


def test_rule_audit_rejects_mother_baby_story():
    ok, reasons = review.run_rule_audit(
        title="小宝贝话都还说不清楚，深夜和妈妈对话",
        story_raw="深夜妈妈困得不行，宝宝却精神十足和妈妈斗嘴，最后妈妈假装生气说别跟我吵了，宝宝才安静下来。" * 2,
        conflict_core="妈妈困想睡，宝宝不睡",
        transcript="妈妈：睡吧\n宝宝：不睡",
        speaker_map_note="宝宝映射昭昭，妈妈保留",
        dialogue_seed=[
            {"speaker": "妈妈", "intent": "催睡"},
            {"speaker": "宝宝", "intent": "反问"},
            {"speaker": "妈妈", "intent": "再催"},
            {"speaker": "妈妈", "intent": "假装生气"},
        ],
        beat=["a", "b", "c", "d"],
    )
    assert ok is False
    assert "infant_skew_title" in reasons or "no_sibling_signal" in reasons


def test_rule_audit_passes_sibling_story():
    ok, reasons = review.run_rule_audit(
        title="姐弟抢遥控器名场面",
        story_raw="姐姐占着遥控器不让弟弟看，弟弟说你不让我看我也不让你看，姐姐嘴硬说谁怕谁，最后弟弟真的走开，姐姐又追上去问明天还玩吗。" * 2,
        conflict_core="姐弟抢遥控器，嘴硬后露怯",
        transcript="姐姐：我的\n弟弟：给我",
        speaker_map_note="站外姐弟映射昭昭灿灿",
        dialogue_seed=[
            {"speaker": "灿灿", "intent": "占物"},
            {"speaker": "昭昭", "intent": "质疑"},
            {"speaker": "灿灿", "intent": "歪理"},
            {"speaker": "昭昭", "intent": "威胁"},
        ],
        beat=["占", "质问", "歪理", "收束"],
    )
    assert ok is True
    assert reasons == []


def test_rule_audit_passes_father_maps_to_mom():
    ok, reasons = review.run_rule_audit(
        title="玩具被抢，爸爸的4招",
        story_raw="弟弟玩具被姐姐抢走，爸爸过来调解，教弟弟四招应对，最后姐弟又和好一起玩。" * 3,
        conflict_core="玩具被抢，家长介入调解",
        transcript="爸爸：别抢\n姐姐：我先玩",
        speaker_map_note="站外爸爸→妈妈，姐姐→灿灿，弟弟→昭昭",
        dialogue_seed=[
            {"speaker": "昭昭", "intent": "被抢"},
            {"speaker": "灿灿", "intent": "占物"},
            {"speaker": "妈妈", "intent": "调解"},
            {"speaker": "昭昭", "intent": "和好"},
        ],
        beat=["抢", "介入", "调解", "和好"],
    )
    assert ok is True
    assert reasons == []


def test_rule_audit_with_scene_contract():
    contract = {
        "source_type": "field",
        "characters": ["昭昭", "灿灿"],
        "beat_chain": [
            {"speaker": "灿灿", "intent": "占物"},
            {"speaker": "昭昭", "intent": "质疑"},
            {"speaker": "灿灿", "intent": "歪理"},
            {"speaker": "昭昭", "intent": "威胁"},
        ],
        "mom_lines_max": 0,
    }
    ok, reasons = review.run_rule_audit(
        title="姐弟抢遥控器名场面",
        story_raw="姐姐占着遥控器不让弟弟看，弟弟说你不让我看我也不让你看，姐姐嘴硬说谁怕谁，最后弟弟真的走开，姐姐又追上去问明天还玩吗。" * 2,
        conflict_core="姐弟抢遥控器，嘴硬后露怯",
        transcript="姐姐：我的\n弟弟：给我",
        speaker_map_note="站外姐弟映射昭昭灿灿",
        dialogue_seed=[
            {"speaker": "灿灿", "intent": "占物"},
            {"speaker": "昭昭", "intent": "质疑"},
            {"speaker": "灿灿", "intent": "歪理"},
            {"speaker": "昭昭", "intent": "威胁"},
        ],
        beat=["占", "质问", "歪理", "收束"],
        scene_contract=contract,
    )
    assert ok is True
    assert reasons == []


def test_audit_story_skips_llm_when_rules_fail():
    out = review.audit_story(
        title="宝宝可爱日常",
        video_title="宝宝可爱日常",
        story_raw="x" * 120,
        conflict_core="可爱",
        h3={"beat": ["a", "b", "c", "d"], "mechanism": "M6", "structure_type": "A"},
        h3b={
            "dialogue_seed": [
                {"speaker": "妈妈", "intent": "1"},
                {"speaker": "妈妈", "intent": "2"},
                {"speaker": "昭昭", "intent": "3"},
                {"speaker": "灿灿", "intent": "4"},
            ],
            "speaker_map_note": "妈妈保留",
        },
        config=type(
            "Cfg",
            (),
            {
                "gold_story_audit_enabled": True,
                "gold_story_audit_min_story_raw_chars": 100,
                "gold_story_audit_min_sibling_fit": 0.55,
                "gold_story_audit_min_age_fit": 0.55,
                "gold_story_audit_min_conflict_usable": 0.55,
                "gold_story_audit_min_mapping_fit": 0.55,
            },
        )(),
    )
    assert out["pass"] is False
    assert out["stage"] == "rules"


def test_audit_story_llm_pass(monkeypatch):
    def fake_fit(**_kwargs):
        return {
            "pass": True,
            "sibling_fit": 0.8,
            "age_fit": 0.7,
            "conflict_usable": 0.75,
            "mapping_fit": 0.7,
            "reject_reasons": [],
            "audit_notes": "ok",
        }

    monkeypatch.setattr(review.llm_steps, "audit_story_fit", fake_fit)
    out = review.audit_story(
        title="姐弟抢东西",
        video_title="姐弟抢东西",
        story_raw="姐姐和弟弟抢遥控器，弟弟放狠话要回家，姐姐嘴硬后又追上去问明天还玩吗。" * 4,
        conflict_core="姐弟抢物",
        h3={
            "title": "抢遥控器",
            "beat": ["a", "b", "c", "d"],
            "mechanism": "M2",
            "structure_type": "C",
        },
        h3b={
            "dialogue_seed": [
                {"speaker": "灿灿", "intent": "1"},
                {"speaker": "昭昭", "intent": "2"},
                {"speaker": "灿灿", "intent": "3"},
                {"speaker": "昭昭", "intent": "4"},
            ],
            "speaker_map_note": "姐弟→昭昭灿灿",
        },
        config=type(
            "Cfg",
            (),
            {
                "gold_story_audit_enabled": True,
                "gold_story_audit_min_story_raw_chars": 100,
                "gold_story_audit_min_sibling_fit": 0.55,
                "gold_story_audit_min_age_fit": 0.55,
                "gold_story_audit_min_conflict_usable": 0.55,
                "gold_story_audit_min_mapping_fit": 0.55,
            },
        )(),
    )
    assert out["pass"] is True
    assert out["stage"] == "llm"
