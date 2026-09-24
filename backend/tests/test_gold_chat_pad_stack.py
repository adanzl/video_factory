"""垫字判定与清理：review / length 共用。"""

from __future__ import annotations

from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN
from app.services.daily_story.review import collect_pad_stack_issues
from app.services.gold_story.gold_chat import convert as gc
from app.services.gold_story.gold_chat.pad_stack import (
    apply_clear_pad_sanitize,
    is_genuine_haobu_question,
    sanitize_pad_stack_line,
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


def test_collect_errors_sanitize_then_validate():
    story = {
        "story_type": "N",
        "dialogue": [{"speaker": "昭昭", "line": "救场成功好不好呀。"}],
    }
    errors = collect_candidate_repair_errors(story, mom_lines_max=3)
    assert errors
    assert any(str(DAILY_STORY_BODY_CHARS_MIN) in e for e in errors)
