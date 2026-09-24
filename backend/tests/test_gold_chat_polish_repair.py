"""polish 候选保留与精修整体修订。"""

from __future__ import annotations

import copy

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
        "_prepare_chat_for_validate_after_local_length_close",
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
        "_prepare_chat_for_validate_after_local_length_close",
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



def test_refine_align_validate_repair_restores_rule_opening_without_second_budget(monkeypatch):
    from app.services.gold_story.gold_chat import convert as gc
    from app.services.gold_story.gold_chat import refine as grf
    from app.services.gold_story.gold_chat.validate import opening_causality_passes

    beat_chain = [
        {"beat": 1, "speaker": "妈妈", "intent": "立规：谁先动手谁先道歉"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    ]
    story = _story([
        {"speaker": "妈妈", "line": "规矩说好，谁先动手谁先道歉。"},
        {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
        {"speaker": "灿灿", "line": "我知道了。"},
    ])
    llm_bad = _story([
        {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
        {"speaker": "妈妈", "line": "你先别打岔。"},
        {"speaker": "妈妈", "line": "都听清楚。"},
        {"speaker": "妈妈", "line": "规矩说好，谁先动手谁先道歉。"},
    ])
    prepare_calls = {"n": 0}

    def prepare(chat, **kwargs):
        prepare_calls["n"] += 1
        if prepare_calls["n"] == 1:
            raise ValueError("正文总字数须≥240，当前234")
        moms = [x for x in chat.get("dialogue") or [] if x.get("speaker") == "妈妈"]
        assert len(moms) <= 3
        assert opening_causality_passes(chat, beat_chain, mom_lines_max=3)
        assert (chat.get("dialogue") or [])[0].get("speaker") == "妈妈"
        assert "谁先动手谁先道歉" in str((chat.get("dialogue") or [])[0].get("line") or "")
        return dict(chat)

    monkeypatch.setattr(grf, "collect_align_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        grf,
        "_prepare_chat_for_validate_after_local_length_close",
        prepare,
    )
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


def test_refine_n_contract_and_clean_shortage_are_local_before_budget(monkeypatch):
    from app.services.daily_story.prompts import dialogue_total_chars
    from app.services.gold_story.gold_chat import refine as grf
    from app.services.daily_story.story_types.n.validate import RE_SOLEMN_REASON

    rows = [
        {"speaker": "灿灿", "line": "如果只能选一个，你认真说选姐姐还是选我？"},
        {"speaker": "昭昭", "line": "我当然先选姐姐，这个答案不用想太久。"},
        {"speaker": "灿灿", "line": "为什么，你总得给我一个能听懂的理由吧？"},
        {"speaker": "昭昭", "line": "她笑起来像小太阳，我看见就觉得特别亮。"},
        {"speaker": "灿灿", "line": "你这个说法听着怎么越来越奇怪了？"},
        {"speaker": "昭昭", "line": "我是在认真回答你，没有故意逗你玩。"},
        {"speaker": "灿灿", "line": "那你继续说，我倒要看看还能怎么讲。"},
        {"speaker": "昭昭", "line": "我说完就是这个答案，不准备临时改口。"},
        {"speaker": "灿灿", "line": "行吧，我服了，你还真能一本正经讲下去。"},
        {"speaker": "昭昭", "line": "那就这么定，别再让我重新选一次。"},
    ]
    story = _story(rows)
    assert dialogue_total_chars(story) < DAILY_STORY_BODY_CHARS_MIN
    assert not RE_SOLEMN_REASON.search("".join(row["line"] for row in rows))

    def collect(chat, **kwargs):
        body = "".join(str(x.get("line") or "") for x in chat.get("dialogue") or [])
        if not RE_SOLEMN_REASON.search(body):
            return [{
                "kind": "对齐-类型契约",
                "desc": "N类：须有一本正经自洽（因为/所以/就能等）",
                "fix": "补齐缺槽",
            }]
        return []

    def prepare(chat, **kwargs):
        body = "".join(str(x.get("line") or "") for x in chat.get("dialogue") or [])
        assert RE_SOLEMN_REASON.search(body)
        chars = dialogue_total_chars(chat)
        if chars < DAILY_STORY_BODY_CHARS_MIN:
            raise ValueError(f"正文总字数须≥240，当前{chars}")
        return dict(chat)

    def fake_fix(*args, **kwargs):
        raise AssertionError("N 合同齐全后的纯字数缺口不应再消耗 LLM repair")

    from app.services.gold_story.gold_chat import convert as gc_convert

    monkeypatch.setattr(grf, "collect_align_issues", collect)
    monkeypatch.setattr(
        grf,
        "_prepare_chat_for_validate_after_local_length_close",
        prepare,
    )
    monkeypatch.setattr(gc_convert, "_fix_chat_with_llm", fake_fix)
    budget = GoldChatRepairBudget(max_repairs=2)

    out = grf.refine_gold_chat_align(
        story,
        structure_type="N",
        mechanism="M6",
        align_block="",
        mom_lines_max=3,
        max_rounds=2,
        bail_on_structural=False,
        repair_budget=budget,
    )

    assert budget.used == 0
    assert dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN
    assert RE_SOLEMN_REASON.search(
        "".join(str(x.get("line") or "") for x in out.get("dialogue") or [])
    )


def test_refine_post_align_local_length_close_does_not_force_dirty_margin():
    from app.services.daily_story.prompts import dialogue_total_chars
    from app.services.gold_story.gold_chat import refine as grf
    from app.services.gold_story.gold_chat.prompts import CHAT_MAX_LINE_CHARS

    rows = [
        {
            "speaker": "昭昭" if i % 2 == 0 else "灿灿",
            "line": "我把这件事情说清楚再继续争到底。",
        }
        for i in range(11)
    ]
    rows.append({"speaker": "灿灿", "line": "你" * 24 + "呀"})
    story = _story(rows)
    assert 180 <= dialogue_total_chars(story) < DAILY_STORY_BODY_CHARS_MIN
    assert max(len(x["line"]) for x in story["dialogue"]) == 25

    out = grf._stabilize_align_length_candidate(
        story,
        structure_type="N",
        mechanism="",
    )

    assert dialogue_total_chars(out) < DAILY_STORY_BODY_CHARS_MIN
    assert max(len(x["line"]) for x in out["dialogue"]) <= CHAT_MAX_LINE_CHARS
    body = "".join(str(x.get("line") or "") for x in out["dialogue"])
    assert "我偏就不信" not in body
    assert "说一不二" not in body


def test_shared_local_length_close_is_used_by_refine_wrapper(monkeypatch):
    from app.services.gold_story.gold_chat import refine as grf

    story = _story([{"speaker": "昭昭", "line": "先说清楚。"}] * 12)
    sentinel = _story([{"speaker": "灿灿", "line": "已经收口。"}] * 12)
    seen = {}

    def fake_close(candidate, **kwargs):
        seen.update(kwargs)
        assert candidate is story
        return sentinel, True

    monkeypatch.setattr(grf, "_stabilize_local_length_candidate", fake_close)
    out = grf._stabilize_align_length_candidate(
        story,
        structure_type="N",
        mechanism="M6",
    )

    assert out is sentinel
    assert seen == {
        "structure_type": "N",
        "mechanism": "M6",
        "target_chars": grf.ALIGN_POST_LOCAL_BODY_TARGET,
    }


def test_refine_polish_length_errors_use_budget_when_clean_close_is_short(monkeypatch):
    from app.services.daily_story.prompts import dialogue_total_chars
    from app.services.gold_story.gold_chat import refine as grf
    from app.services.gold_story.gold_chat.prompts import CHAT_MAX_LINE_CHARS

    old = _story([
        {"speaker": "昭昭", "line": "OLD_ALIGN_BAD"},
        {"speaker": "灿灿", "line": "先别急。"},
    ])
    rows = [
        {
            "speaker": "昭昭" if i % 2 == 0 else "灿灿",
            "line": "我把这件事情说清楚再继续争到底。",
        }
        for i in range(11)
    ]
    rows.append({"speaker": "灿灿", "line": "你" * 24 + "呀"})
    candidate = _story(rows)

    monkeypatch.setattr(grf, "_align_refine_with_llm", lambda *args, **kwargs: {"fixes": []})
    monkeypatch.setattr(
        grf,
        "_apply_gold_chat_polish_fixes",
        lambda *args, **kwargs: PolishResult(
            candidate=candidate,
            accepted={1},
            errors=[
                "正文总字数须≥240，当前200",
                f"单句过长(max=25>{CHAT_MAX_LINE_CHARS})",
            ],
        ),
    )

    def collect(chat, **kwargs):
        first = str((chat.get("dialogue") or [{}])[0].get("line") or "")
        if first == "OLD_ALIGN_BAD":
            return [{"kind": "类型-N收束", "desc": "待对齐", "fix": "改"}]
        return []

    monkeypatch.setattr(grf, "collect_align_issues", collect)

    def prepare(chat, **kwargs):
        chars = dialogue_total_chars(chat)
        if chars < DAILY_STORY_BODY_CHARS_MIN:
            raise ValueError(f"正文总字数须≥240，当前{chars}")
        assert max(len(str(x.get("line") or "")) for x in chat.get("dialogue") or []) <= CHAT_MAX_LINE_CHARS
        return dict(chat)

    def fake_fix(chat, *args, **kwargs):
        fixed = copy.deepcopy(chat)
        fixed["dialogue"].extend([
            {"speaker": "昭昭", "line": "我把刚才的话认真说完整一点。"},
            {"speaker": "灿灿", "line": "你说完整了，我这回听明白了。"},
            {"speaker": "昭昭", "line": "那我再把前因后果说清楚一点。"},
        ])
        return fixed

    from app.services.gold_story.gold_chat import convert as gc_convert

    monkeypatch.setattr(
        grf,
        "_prepare_chat_for_validate_after_local_length_close",
        prepare,
    )
    monkeypatch.setattr(gc_convert, "_fix_chat_with_llm", fake_fix)
    budget = GoldChatRepairBudget(max_repairs=2)

    out = grf.refine_gold_chat_align(
        old,
        structure_type="N",
        mechanism="",
        align_block="",
        mom_lines_max=3,
        max_rounds=1,
        bail_on_structural=False,
        repair_budget=budget,
    )

    assert dialogue_total_chars(out) >= DAILY_STORY_BODY_CHARS_MIN
    assert budget.used == 1


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
