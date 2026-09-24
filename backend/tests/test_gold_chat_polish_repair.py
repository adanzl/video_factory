"""polish 候选保留与精修整体修订。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN
from app.services.gold_story.gold_chat.polish import (
    PolishResult,
    _apply_gold_chat_polish_fixes,
)
from app.services.gold_story.gold_chat.repair import (
    AlignRepairFailure,
    GoldChatRepairBudget,
    build_candidate_repair_feedback,
)


def _story(dialogue: list[dict[str, str]]) -> dict:
    return {"story_type": "N", "dialogue": dialogue}


def test_polish_joint_fail_keeps_applied_candidate_not_old_chat(monkeypatch):
    from app.services.gold_story.gold_chat import convert as gc

    chat = _story([{"speaker": "灿灿", "line": "行吧，我去补作业。"}])
    fixes = {"fixes": [{"no": 1, "line": "行。"}]}
    validate_calls = {"n": 0}

    def fake_validate(_story, **kwargs):
        validate_calls["n"] += 1
        raise ValueError(
            f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前223",
        )

    monkeypatch.setattr(gc, "validate_gold_chat", fake_validate)
    monkeypatch.setattr(gc, "_ensure_gold_chat_min_chars", lambda s: (s, False))
    monkeypatch.setattr(gc, "patch_sanitize_pad_suffix", lambda s: (s, False))

    result = _apply_gold_chat_polish_fixes(chat, fixes, mom_lines_max=3)
    assert result.errors
    assert result.candidate.get("dialogue")[0]["line"] == "行。"
    assert chat["dialogue"][0]["line"] == "行吧，我去补作业。"


def test_polish_batch_fail_keeps_validated_candidate(monkeypatch):
    from app.services.gold_story.gold_chat import convert as gc

    chat = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    fixes = {
        "fixes": [{"no": 1, "line": "姐姐好呀。"}],
    }
    def fake_validate(_story, **kwargs):
        raise ValueError(
            f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前223",
        )

    monkeypatch.setattr(gc, "validate_gold_chat", fake_validate)
    monkeypatch.setattr(
        gc,
        "_ensure_gold_chat_min_chars",
        lambda s: (s, False),
    )
    monkeypatch.setattr(gc, "patch_sanitize_pad_suffix", lambda s: (s, False))

    result = _apply_gold_chat_polish_fixes(
        chat,
        fixes,
        mom_lines_max=3,
    )
    assert result.candidate["dialogue"][0]["line"] == "姐姐好呀。"
    assert isinstance(result, PolishResult)
    assert result.errors
    assert "223" in result.errors[0]
    assert result.candidate is not chat
    assert result.accepted == set()


def test_build_candidate_repair_feedback_lists_metrics_and_align():
    fb = build_candidate_repair_feedback(
        _story(
            [
                {"speaker": "妈妈", "line": "a"},
                {"speaker": "妈妈", "line": "b"},
                {"speaker": "妈妈", "line": "c"},
                {"speaker": "妈妈", "line": "d"},
            ],
        ),
        validation_errors=[f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前223"],
        align_issues=[
            {"kind": "类型-N收束", "desc": "收束须愣住/接不住", "fix": "补"},
        ],
        mom_lines_max=3,
    )
    assert "223" in fb or str(DAILY_STORY_BODY_CHARS_MIN) in fb
    assert "妈妈 4 句" in fb
    assert "收束" in fb
    assert "语气词" in fb


@patch("app.services.gold_story.gold_chat.refine._align_refine_with_llm")
@patch("app.services.gold_story.gold_chat.refine._apply_gold_chat_polish_fixes")
def test_refine_repair_short_only_after_closing_fixed_on_candidate(
    mock_apply,
    mock_llm,
):
    """收束已在候选上修好、仅缺字时，反馈勿再带旧稿收束问题。"""
    from app.services.gold_story.gold_chat import refine as grf

    story = _story(
        [
            {"speaker": "灿灿", "line": "OLD_BAD"},
            {"speaker": "昭昭", "line": "姐姐别走呀。"},
        ],
    )
    mock_llm.return_value = {"fixes": [{"no": 1, "line": "GOOD_CLOSE"}]}
    candidate = _story(
        [
            {"speaker": "灿灿", "line": "GOOD_CLOSE"},
            {"speaker": "昭昭", "line": "姐姐别走呀。"},
        ],
    )
    mock_apply.return_value = PolishResult(
        candidate=candidate,
        accepted=set(),
        errors=[f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前223"],
    )
    closing_issue = [
        {"kind": "类型-N收束", "desc": "收束须愣住/接不住", "fix": "补"},
    ]

    def fake_collect(chat, **kwargs):
        first = str((chat.get("dialogue") or [{}])[0].get("line") or "")
        if first == "OLD_BAD":
            return list(closing_issue)
        return []

    fix_calls: list[str] = []
    padded = _story(
        [
            {"speaker": "灿灿", "line": "GOOD_CLOSE" + "补" * 80},
            {"speaker": "昭昭", "line": "姐姐别走呀。"},
        ],
    )

    def fake_fix(_candidate, prompt, **kwargs):
        fix_calls.append(prompt)
        return dict(padded)

    budget = GoldChatRepairBudget(max_repairs=2)
    with patch(
        "app.services.gold_story.gold_chat.convert._fix_chat_with_llm",
        side_effect=fake_fix,
    ), patch.object(grf, "collect_align_issues", side_effect=fake_collect), patch.object(
        grf,
        "_prepare_chat_for_validate",
        side_effect=lambda chat, **kwargs: dict(chat),
    ):
        out = grf.refine_gold_chat_align(
            story,
            structure_type="N",
            mechanism="",
            align_block="",
            mom_lines_max=3,
            closing_intent="",
            max_rounds=1,
            bail_on_structural=False,
            repair_budget=budget,
        )
    assert fix_calls
    assert "223" in fix_calls[0] or str(DAILY_STORY_BODY_CHARS_MIN) in fix_calls[0]
    assert "收束须愣住" not in fix_calls[0]
    assert "类型-N收束" not in fix_calls[0]
    assert out["dialogue"][0]["line"].startswith("GOOD_CLOSE")


@patch("app.services.gold_story.gold_chat.refine._align_refine_with_llm")
@patch("app.services.gold_story.gold_chat.refine._apply_gold_chat_polish_fixes")
def test_refine_whole_chat_repair_after_polish_batch_fail(
    mock_apply,
    mock_llm,
):
    from app.services.gold_story.gold_chat import refine as grf

    story = _story(
        [
            {"speaker": "灿灿", "line": "行吧，我补作业去了。"},
            {"speaker": "昭昭", "line": "姐姐别走呀。"},
        ],
    )
    mock_llm.return_value = {"fixes": []}
    candidate = dict(story)
    candidate["dialogue"] = [
        {"speaker": "灿灿", "line": "行吧。"},
        {"speaker": "昭昭", "line": "姐姐别走呀。"},
    ]
    mock_apply.return_value = PolishResult(
        candidate=candidate,
        accepted=set(),
        errors=[f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前223"],
    )
    budget = GoldChatRepairBudget(max_repairs=2)
    fix_calls: list[str] = []

    def fake_fix(_candidate, prompt, **kwargs):
        fix_calls.append(prompt)
        return dict(story)

    with patch(
        "app.services.gold_story.gold_chat.convert._fix_chat_with_llm",
        side_effect=fake_fix,
    ), patch.object(
        grf,
        "collect_align_issues",
        return_value=[
            {"kind": "类型-N收束", "desc": "收束须愣住", "fix": "补"},
        ],
    ), patch.object(
        grf,
        "_prepare_chat_for_validate",
        side_effect=ValueError("still bad"),
    ):
        with pytest.raises(AlignRepairFailure):
            grf.refine_gold_chat_align(
                story,
                structure_type="N",
                mechanism="",
                align_block="",
                mom_lines_max=3,
                closing_intent="",
                max_rounds=1,
                bail_on_structural=False,
                repair_budget=budget,
            )
    assert fix_calls
    assert "223" in fix_calls[0] or str(DAILY_STORY_BODY_CHARS_MIN) in fix_calls[0]



def test_refine_align_validate_repair_restores_opening_without_second_budget(monkeypatch):
    from app.services.gold_story.gold_chat import convert as gc
    from app.services.gold_story.gold_chat import refine as grf

    beat_chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "责备：作业还没写"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    ]
    story = _story([
        {"speaker": "妈妈", "line": "作业怎么还没写？"},
        {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
        {"speaker": "灿灿", "line": "我这就写。"},
    ])
    llm_bad = _story([
        {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
        {"speaker": "妈妈", "line": "你先别打岔。"},
        {"speaker": "妈妈", "line": "赶紧去写。"},
        {"speaker": "妈妈", "line": "别磨蹭。"},
        {"speaker": "妈妈", "line": "听见没有？"},
        {"speaker": "妈妈", "line": "快点。"},
    ])
    prepare_calls = {"n": 0}

    def prepare(chat, **kwargs):
        prepare_calls["n"] += 1
        if prepare_calls["n"] == 1:
            raise ValueError("opening_causality:对白以 beat=2 起跳")
        moms = [x for x in chat.get("dialogue") or [] if x.get("speaker") == "妈妈"]
        assert len(moms) <= 3
        assert (chat.get("dialogue") or [])[0].get("speaker") == "妈妈"
        return dict(chat)

    monkeypatch.setattr(grf, "collect_align_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr(grf, "_prepare_chat_for_validate", prepare)
    monkeypatch.setattr(gc, "_fix_chat_with_llm", lambda *args, **kwargs: llm_bad)
    budget = GoldChatRepairBudget(max_repairs=2)

    out = grf.refine_gold_chat_align(
        story,
        structure_type="N",
        mechanism="",
        align_block="",
        mom_lines_max=3,
        beat_chain=beat_chain,
        repair_budget=budget,
        max_rounds=2,
    )

    assert prepare_calls["n"] == 2
    assert budget.used == 1
    assert out["dialogue"][0]["speaker"] == "妈妈"


def test_align_repair_failure_message_not_only_short_header():
    exc = AlignRepairFailure(
        stage="align_repair",
        validation_errors=[f"正文总字数须≥240，当前223"],
        align_issues=[
            {"kind": "类型-N收束", "desc": "收束须愣住", "fix": "x"},
        ],
        candidate=_story([]),
    )
    msg = str(exc)
    assert "align_refine_failed:" in msg
    assert "223" in msg
    assert "收束" in msg

    from app.services.gold_story.gold_chat.expand import (
        _has_non_short_hard_errors,
        _short_content_reject_message,
    )

    assert _has_non_short_hard_errors(msg)
    assert "本地垫字仍不足" not in _short_content_reject_message(msg)


def test_candidate_feedback_combines_short_consecutive_and_padding():
    candidate = _story([
        {"speaker": "昭昭", "line": "你先把积木放好。"},
        {"speaker": "昭昭", "line": "我已经放好了好不好呀！"},
    ])
    candidate["quality"] = {"cons": ["存在同人连说"], "structure_score": 65}
    feedback = build_candidate_repair_feedback(
        candidate, validation_errors=[], align_issues=[], mom_lines_max=2,
    )
    assert "正文总字数" in feedback
    assert "第1、2句同人连说" in feedback
    assert "好不好呀" in feedback
    assert "存在同人连说" in feedback


def test_repair_budget_logs_stage_and_exhaustion(caplog, monkeypatch):
    import logging

    from app.services.gold_story.gold_chat import repair

    monkeypatch.setattr(repair.logger, "handlers", [caplog.handler])
    budget = GoldChatRepairBudget(max_repairs=2)
    with caplog.at_level(logging.INFO):
        assert budget.consume(stage="align", reason="字数不足")
        assert budget.consume(stage="expand_structure", reason="structure_score:65")
        assert not budget.consume(stage="final_acceptance", reason="仍有重复")
    assert budget.used == 2
    assert budget.remaining == 0
    assert "stage=align used=1 remaining=1" in caplog.text
    assert "stage=expand_structure used=2 remaining=0" in caplog.text
    assert "exhausted stage=final_acceptance" in caplog.text
    assert "仍有重复" in caplog.text


def test_consecutive_notes_do_not_become_new_hard_gate(monkeypatch):
    from app.services.gold_story.gold_chat import convert as gc
    from app.services.gold_story.gold_chat.repair import collect_candidate_repair_errors

    candidate = _story([
        {"speaker": "昭昭", "line": "积木放这里。"},
        {"speaker": "昭昭", "line": "我来收盒子。"},
    ])
    monkeypatch.setattr(gc, "validate_gold_chat", lambda *args, **kwargs: None)
    assert collect_candidate_repair_errors(candidate, mom_lines_max=2) == []
    feedback = build_candidate_repair_feedback(
        candidate, validation_errors=[], align_issues=[], mom_lines_max=2,
    )
    assert "当前硬校验与垫字问题：（无）" in feedback
    assert "连说提示（按结构分门控）：第1、2句同人连说" in feedback
