"""垫字判定与清理：review / length 共用。"""

from __future__ import annotations

from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN
from app.services.daily_story.review import collect_pad_stack_issues
from app.services.gold_story.gold_chat import convert as gc
from app.services.gold_story.gold_chat.pad_stack import (
    apply_clear_pad_sanitize,
    classify_pad_line,
    is_genuine_haobu_question,
    sanitize_pad_stack_line,
)
from app.services.gold_story.gold_chat.repair import (
    evaluate_repair_candidate_acceptance,
    is_expand_short_only_repair,
)
from app.services.gold_story.gold_chat.repair import (
    collect_candidate_repair_errors,
    prepare_candidate_for_acceptance,
)


def test_statement_haobu_tail_stripped():
    line = "嘿嘿，我屁股Q弹，救场成功好不好呀。"
    assert not is_genuine_haobu_question(line)
    cleaned = sanitize_pad_stack_line(line)
    assert "好不好呀" not in cleaned
    assert "救场成功" in cleaned


def test_genuine_haobu_question_kept():
    line = "我们一起玩好不好呀？"
    assert is_genuine_haobu_question(line)
    out, changed = apply_clear_pad_sanitize(
        {"dialogue": [{"speaker": "昭昭", "line": line}]},
    )
    assert not changed
    assert out["dialogue"][0]["line"] == line


def test_after_pad_clean_short_chars_still_block():
    short_line = "救场成功。" * 8
    story = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "昭昭", "line": short_line},
            {"speaker": "灿灿", "line": "行。"},
        ],
    }
    cleaned, errors = prepare_candidate_for_acceptance(story, mom_lines_max=3)
    assert errors
    assert any(str(DAILY_STORY_BODY_CHARS_MIN) in e for e in errors)
    assert not collect_pad_stack_issues(cleaned)


def test_review_and_length_agree_on_statement_pad():
    line = "救场成功好不好呀。"
    story = {"dialogue": [{"speaker": "昭昭", "line": line}]}
    out, changed = gc.patch_sanitize_pad_suffix(story)
    assert changed
    assert "好不好呀" not in out["dialogue"][0]["line"]
    assert not collect_pad_stack_issues(out)


def test_buxing_le_ne_sanitized():
    line = "不行了呢！"
    cleaned = sanitize_pad_stack_line(line)
    assert cleaned == "不行！"
    assert classify_pad_line(line) == "clear_pad"


def test_mixed_sentence_final_particles_are_normalized():
    cases = {
        "铅笔找不到了嘛真的吧。": "铅笔找不到了嘛。",
        "不打我就收起来咯呢。": "不打我就收起来咯。",
    }
    for line, expected in cases.items():
        assert classify_pad_line(line) == "clear_pad"
        assert sanitize_pad_stack_line(line) == expected

    story = {
        "dialogue": [
            {"speaker": "灿灿", "line": "铅笔找不到了嘛真的吧。"},
            {"speaker": "昭昭", "line": "不打我就收起来咯呢。"},
        ],
    }
    out, changed = apply_clear_pad_sanitize(story)
    assert changed
    assert [row["line"] for row in out["dialogue"]] == list(cases.values())
    assert not collect_pad_stack_issues(out)


def test_defer_haobu_question_kept():
    line = "明天再说好不好呀？"
    assert is_genuine_haobu_question(line)
    out, changed = apply_clear_pad_sanitize(
        {"dialogue": [{"speaker": "昭昭", "line": line}]},
    )
    assert not changed
    assert out["dialogue"][0]["line"] == line


def test_ambiguous_haobu_not_auto_stripped():
    from app.services.gold_story.gold_chat.pad_stack import classify_pad_line

    line = "那就这样好不好呀。"
    assert classify_pad_line(line) == "uncertain"
    out, changed = apply_clear_pad_sanitize(
        {"dialogue": [{"speaker": "灿灿", "line": line}]},
    )
    assert not changed


def test_short_only_repair_when_structure_ok():
    errs = ["正文总字数须≥240，当前222"]
    assert is_expand_short_only_repair(errs, structure_gate_ok=True)
    assert not is_expand_short_only_repair(
        errs + ["structure_score:65"], structure_gate_ok=False,
    )
    assert not is_expand_short_only_repair(
        ["妈妈台词须≤3句，当前4"], structure_gate_ok=True,
    )


def test_short_only_requires_body_chars_alone():
    body = ["正文总字数须≥240，当前222"]
    assert is_expand_short_only_repair(body, structure_gate_ok=True)
    assert not is_expand_short_only_repair(
        body + ["单句过长(max=35>24)"],
        structure_gate_ok=True,
    )
    assert not is_expand_short_only_repair(
        ["对白句数须≥12，当前11"],
        structure_gate_ok=True,
    )
    assert not is_expand_short_only_repair(
        ["正文总字数须≥240，当前222；对白句数须≥12，当前11"],
        structure_gate_ok=True,
    )


def test_prior_repair_error_must_not_select_whole_chat_mode():
    mode_errors = ["正文总字数须≥240，当前233"]
    repair_error = "short_spot_fix: 冻结行 3 被改动"
    assert is_expand_short_only_repair(mode_errors, structure_gate_ok=True)
    assert not is_expand_short_only_repair(
        mode_errors + [repair_error],
        structure_gate_ok=True,
    )


def test_reject_repair_that_adds_mom_lines():
    baseline = {
        "dialogue": [
            {"speaker": "昭昭", "line": "a" * 120},
            {"speaker": "灿灿", "line": "b" * 120},
        ],
        "quality": {"structure_score": 80, "score": 80, "cons": []},
    }
    draft = {
        "dialogue": [
            {"speaker": "昭昭", "line": "a" * 120},
            {"speaker": "妈妈", "line": "你们别闹。"},
            {"speaker": "灿灿", "line": "b" * 120},
        ],
    }
    accepted, reason = evaluate_repair_candidate_acceptance(
        baseline,
        draft,
        row={"id": 1},
        mom_lines_max=3,
    )
    assert accepted is None
    assert "句数" in reason or "speaker" in reason


def test_collect_errors_sanitize_then_validate():
    story = {
        "story_type": "N",
        "dialogue": [{"speaker": "昭昭", "line": "救场成功好不好呀。"}],
    }
    errors = collect_candidate_repair_errors(story, mom_lines_max=3)
    assert errors
    assert any(str(DAILY_STORY_BODY_CHARS_MIN) in e for e in errors)
