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


def test_a_not_a_question_xingbuxing_not_pad():
    """「…行不行」是正反问，不是可清理的垫字（不得报「句尾叠语气词/不通」）。"""
    line = "等等我还没准备好，你耍赖，重来一次行不行"
    assert classify_pad_line(line) == "none"
    assert sanitize_pad_stack_line(line) == line
    story = {"dialogue": [{"speaker": "昭昭", "line": line}]}
    assert collect_pad_stack_issues(story) == []


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


def test_reject_repair_that_drops_valid_body_below_240():
    baseline = {
        "dialogue": [
            {"speaker": "昭昭", "line": "甲" * 120},
            {"speaker": "灿灿", "line": "乙" * 120},
        ],
        "quality": {"structure_score": 80, "score": 80, "cons": []},
    }
    draft = {
        "dialogue": [
            {"speaker": "昭昭", "line": "甲" * 113},
            {"speaker": "灿灿", "line": "乙" * 113},
        ],
        "quality": {"structure_score": 80, "score": 80, "cons": []},
    }

    accepted, reason = evaluate_repair_candidate_acceptance(
        baseline,
        draft,
        row={"id": 102},
        mom_lines_max=2,
    )

    assert accepted is None
    assert "已达标正文压短" in reason


def test_reject_repair_that_makes_short_body_even_shorter():
    baseline = {
        "dialogue": [
            {"speaker": "昭昭", "line": "甲" * 118},
            {"speaker": "灿灿", "line": "乙" * 117},
        ],
        "quality": {"structure_score": 80, "score": 80, "cons": []},
    }
    draft = {
        "dialogue": [
            {"speaker": "昭昭", "line": "甲" * 113},
            {"speaker": "灿灿", "line": "乙" * 113},
        ],
        "quality": {"structure_score": 80, "score": 80, "cons": []},
    }

    accepted, reason = evaluate_repair_candidate_acceptance(
        baseline,
        draft,
        row={"id": 102},
        mom_lines_max=2,
    )

    assert accepted is None
    assert "继续变短" in reason


def test_collect_errors_sanitize_then_validate():
    story = {
        "story_type": "N",
        "dialogue": [{"speaker": "昭昭", "line": "救场成功好不好呀。"}],
    }
    errors = collect_candidate_repair_errors(story, mom_lines_max=3)
    assert errors
    assert any(str(DAILY_STORY_BODY_CHARS_MIN) in e for e in errors)


def test_pad_line_duplicate_three_levels():
    """垫字判重三级：逐字、去语气词后同句、以及近似句都要拦住。"""
    from app.services.gold_story.gold_chat.length import (
        _norm_pad_line,
        _pad_line_bigrams,
        _pad_line_is_duplicate,
        _pad_line_similarity,
    )

    existing = ["你再说一遍试试，我就是不服！"]
    # 1) 逐字重复
    assert _pad_line_is_duplicate("你再说一遍试试，我就是不服！", existing) is True
    # 2) 只差语气词/标点：逐字比对会漏，归一化后须判重
    assert _pad_line_is_duplicate("你再说一遍试试啊，我就是不服！", existing) is True
    assert _norm_pad_line("你再说一遍试试啊，我就是不服！") == _norm_pad_line(existing[0])
    # 3) 真正的近似句（高相似但非同一句）也要拦
    assert _pad_line_similarity("你再说一遍试试，我就是不服气！", existing[0]) >= 0.6
    assert _pad_line_is_duplicate("你再说一遍试试，我就是不服气！", existing) is True
    # 反例：不相关的句子必须放行，否则垫字补不出内容
    assert _pad_line_is_duplicate("咱们去吃西瓜吧。", existing) is False
    assert _pad_line_similarity("咱们去吃西瓜吧。", existing[0]) < 0.6
    # 空串视为重复（不可插入空行）
    assert _pad_line_is_duplicate("   ", existing) is True
    assert _pad_line_is_duplicate("不管你说啥。", []) is False
    assert _pad_line_bigrams("") == set()
    assert _pad_line_similarity("", "不管你说啥。") == 0.0


def test_pad_safe_insert_bounds_avoid_opening_and_tail():
    """垫字不得插在开场前两句，也不得挤掉末段收束槽位。"""
    from app.services.gold_story.gold_chat.length import _pad_safe_insert_bounds

    for count in range(1, 30):
        lo, hi = _pad_safe_insert_bounds(count)
        assert 0 <= lo <= hi <= count
        assert lo <= 2, "开场前两句须避开"
        # 末段须留 4 个收束槽位；区间已被 lo 垫底时（超短稿）不强求
        if count - 4 >= lo:
            assert hi <= count - 4, "末段须留 4 个收束槽位"
    # 短稿不能因收缩区间而变成空区间
    lo, hi = _pad_safe_insert_bounds(1)
    assert lo <= hi
    lo2, hi2 = _pad_safe_insert_bounds(3)
    assert lo2 <= hi2


def _filler_dialogue(count: int) -> list[dict[str, str]]:
    """抽象占位对白：只为凑够正文字数，不含任何单篇词。"""
    return [
        {
            "speaker": "昭昭" if i % 2 == 0 else "灿灿",
            "line": f"占位对白第{i}句内容各不相同仅用于凑足正文字数",
        }
        for i in range(count)
    ]


def test_haobu_question_with_mark_is_genuine_and_kept():
    """「…到底好不好？」是真实问句：不能当垫字去尾（否则会改成「…到底？」）。"""
    line = "那你说，朋友多了到底好不好？"
    assert is_genuine_haobu_question(line)
    assert classify_pad_line(line) == "keep_question"
    assert sanitize_pad_stack_line(line) == line
    out, changed = apply_clear_pad_sanitize(
        {"dialogue": [{"speaker": "灿灿", "line": line}]},
    )
    assert not changed
    assert out["dialogue"][0]["line"] == line


def test_statement_haobu_pad_still_reported_for_llm_repair():
    """歧义垫字仍须报给 LLM 定点改：repair 路径不得本地静默剥掉。"""
    line = "这球我先拿着好不好"
    assert classify_pad_line(line) == "uncertain"
    out, changed = apply_clear_pad_sanitize(
        {"dialogue": [{"speaker": "灿灿", "line": line}]},
    )
    assert not changed


def test_pad_cleanup_runs_when_body_chars_already_meet_floor():
    """字数已达标（≥240）时机械垫字清理仍须执行。

    原实现把该清理挂在 hard_deficit 门控内，字数达标即整段跳过，句尾垫字一路
    带到终检被当成「必须 LLM 定点改」的硬伤，直接打死整轮实跑。
    """
    from app.services.gold_story.gold_chat.length import (
        _stabilize_local_length_candidate,
        dialogue_total_chars,
    )
    from app.services.daily_story.review import collect_pad_stack_issues

    pad_line = "这球我先拿着好不好"
    story = {
        "story_type": "K",
        "dialogue": [
            {"speaker": "灿灿", "line": pad_line},
            *_filler_dialogue(11),
        ],
    }
    # 前提：正文已达标，硬缺口 ≤0 —— 正是原实现提前 return 的场景
    assert dialogue_total_chars(story) >= DAILY_STORY_BODY_CHARS_MIN
    assert collect_pad_stack_issues(story), "前提：该句确实被判为垫字"

    out, changed = _stabilize_local_length_candidate(
        story,
        structure_type="K",
        mechanism="M12",
    )
    assert changed
    assert all("好不好" not in row["line"] for row in out["dialogue"])
    assert not collect_pad_stack_issues(out), "清理后不应再报垫字硬伤"


def test_pad_cleanup_leaves_normal_lines_untouched():
    """清理只动机审命中的垫字句，普通句原样保留。"""
    from app.services.gold_story.gold_chat.length import (
        _stabilize_local_length_candidate,
    )

    normal = [
        "你昨天骑了一下午，今天该我吧",
        "那是我先拿到的，你松手嘛",
    ]
    story = {
        "story_type": "K",
        "dialogue": [
            *[{"speaker": "灿灿", "line": ln} for ln in normal],
            *_filler_dialogue(12),
        ],
    }
    out, _ = _stabilize_local_length_candidate(
        story,
        structure_type="K",
        mechanism="M12",
    )
    kept = [row["line"] for row in out["dialogue"]]
    for ln in normal:
        assert ln in kept

