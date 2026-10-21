"""gold_chat 终验：称谓、本地重复、展示标签。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.daily_story.quality import (
    acceptance_tags_for_quality,
    enrich_quality_acceptance_defaults,
    find_story_duplicate_matches,
    stamp_story_review_binding,
    story_production_eligibility,
    structure_score_of,
)
from app.services.daily_story.review import (
    ExportSemanticReviewResult,
    _normalize_missing_beat,
    _normalize_missing_relation,
    _validate_export_review_evidence_shape,
    _validate_export_review_raw,
    collect_escalation_chatter_signals,
    collect_export_blocking_local_issues,
    collect_sibling_address_issues,
    filter_llm_export_blocking_issues,
    format_export_blocking_issue_summary,
    partition_llm_export_blocking_issues,
    parse_review_issues,
    run_export_semantic_review,
)
from app.services.gold_story.gold_chat.convert import (
    patch_break_consecutive_keep_seed,
    patch_gold_chat_consecutive_siblings,
)
from app.services.daily_story.prompts import (
    DAILY_STORY_BODY_CHARS_MIN,
    dialogue_total_chars,
)
from app.services.gold_story.gold_chat.finalize import (
    GoldChatAcceptanceBlocked,
    GoldChatAcceptanceIncomplete,
    GoldChatLocalDuplicateBlocked,
    GoldChatSemanticBlocked,
    GoldChatValidationRepairableError,
    _is_export_repairable,
    run_gold_chat_final_acceptance,
    run_gold_chat_final_acceptance_with_semantic_repair,
)


def _story(dialogue: list[dict[str, str]]) -> dict:
    return {"dialogue": dialogue, "quality": {"structure_score": 76, "score": 76}}


def test_export_review_prompt_keeps_context_out_of_issue_lines():
    from app.services.daily_story.review import build_review_prompts

    system, _ = build_review_prompts("测试", _story([]))
    assert "只列真正需要修改的故障行" in system
    assert "lines:[11,13]" in system
    assert "不要扩大成[11,12,13,14]" in system


def test_review_prompt_scores_multi_line_situational_humor_without_requiring_one_liner():
    from app.services.daily_story.review import build_review_prompts

    system, _ = build_review_prompts("贴纸争抢", _story([]))
    assert "连续几句共同成立的情境反差" in system
    assert "不要因为找不到独立金句就把整段压到 5-9 分" in system
    assert "它只是整段笑点的代表锚点" in system
    assert "评分看完整情境" in system


def test_review_prompt_has_relation_checks_and_false_positive_guards():
    from app.services.daily_story.review import build_review_prompts

    system, _ = build_review_prompts("测试", _story([]))
    assert "多个物件同时存在完全正常" in system
    assert "允许角色明确提出加赛/改规则" in system
    assert "后文结果、损坏、分割、输赢" in system
    assert "换词反复同一态度/同一不服" in system
    assert "结尾一次引用前文规则作回旋镖不算重复" in system
    assert "剧情指令" in system


@patch("app.services.daily_story.review.run_export_semantic_review")
def test_final_acceptance_repairs_n_beat_role_drift_before_semantic_review(mock_review):
    mock_review.return_value = ExportSemanticReviewResult(
        completed=True,
        issues=[],
        humor=None,
        error=None,
    )
    beats = [
        {"beat": 1, "speaker": "妈妈", "intent": "交代旧事：昭昭掉进菜篓子还睡着了"},
        {"beat": 2, "speaker": "灿灿", "intent": "追问：你怎么会在篓子里睡着？"},
        {"beat": 3, "speaker": "昭昭", "intent": "荒诞解释：因为菜篓子软"},
        {"beat": 4, "speaker": "灿灿", "intent": "继续追问：你醒来还问吃饭了吗？"},
        {"beat": 5, "speaker": "昭昭", "intent": "荒诞自洽：我醒来当然先问吃饭"},
    ]
    row = {
        "title": "回忆旧事",
        "structure_type": "N",
        "payload": {
            "scene_contract": {
                "story_type": "N",
                "beat_chain": beats,
                "mom_lines_max": 1,
            },
        },
    }
    bad = _story(
        [
            {"speaker": "妈妈", "line": "昭昭掉进菜篓子还睡着了。"},
            {"speaker": "昭昭", "line": "你怎么会在篓子里睡着？"},
            {"speaker": "灿灿", "line": "因为菜篓子软，我睡得舒服。"},
            {"speaker": "昭昭", "line": "你醒来还问吃饭了吗？"},
            {"speaker": "灿灿", "line": "我醒来当然先问吃饭呀。"},
        ]
    )

    out = run_gold_chat_final_acceptance(bad, row, sid="BV_TEST_N_ROLE")
    expected = ["妈妈", "灿灿", "昭昭", "灿灿", "昭昭"]
    assert [item["speaker"] for item in out["dialogue"]] == expected
    reviewed_story = mock_review.call_args.args[1]
    assert [item["speaker"] for item in reviewed_story["dialogue"]] == expected


_MOM_ZHAO_MOM_OPENING_BEAT = [
    {"beat": 1, "speaker": "妈妈", "intent": "责备：作业还没写"},
    {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    {"beat": 3, "speaker": "妈妈", "intent": "愣住：接不住离谱话"},
]


def test_export_repairable_includes_opening_causality_validation_error():
    exc = GoldChatValidationRepairableError(
        "opening_causality:缺 beat=1 责备：作业还没写；对白以 beat=2 起跳",
    )
    assert _is_export_repairable(exc)


@patch("app.services.daily_story.review.run_export_semantic_review")
def test_final_acceptance_opening_causality_enters_repair(mock_review):
    mock_review.return_value = ExportSemanticReviewResult(
        completed=True,
        issues=[],
        humor=None,
        error=None,
    )
    beat = _MOM_ZHAO_MOM_OPENING_BEAT
    row = {
        "title": "测试",
        "structure_type": "N",
        "payload": {
            "scene_contract": {"beat_chain": beat, "mom_lines_max": 2},
        },
    }
    bad = _story(
        [
            {"speaker": "灿灿", "line": "我本来就要写，就是忘了嘛！"},
            {"speaker": "昭昭", "line": "姐姐你别催我嘛。"},
        ],
    )
    bad["gold_beat_chain"] = beat
    good_dialogue = [
        {"speaker": "妈妈", "line": "怎么作业还没写？别磨蹭！"},
        {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
        {"speaker": "妈妈", "line": "你……我一时接不住话。"},
        {"speaker": "灿灿", "line": "姐你别闹，我还得写作业。"},
    ]
    fix_calls: list[str] = []

    def fix_llm(chat, fb, **_kw):
        fix_calls.append(fb)
        out = dict(chat)
        out["dialogue"] = good_dialogue
        return out

    out, struct = run_gold_chat_final_acceptance_with_semantic_repair(
        bad,
        row,
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=2,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fix_llm,
        validate_chat=lambda _c: None,
        max_repairs=2,
    )
    assert struct == 80
    assert (out.get("dialogue") or [])[0].get("speaker") == "妈妈"
    assert not fix_calls
    assert mock_review.called


@patch("app.services.daily_story.review.run_export_semantic_review")
def test_final_acceptance_repairs_accountability_opening_before_review(mock_review):
    mock_review.return_value = ExportSemanticReviewResult(
        completed=True,
        issues=[],
        humor=None,
        error=None,
    )
    beat = [
        {"beat": 1, "speaker": "妈妈", "intent": "定责：灿灿作业没写，先把作业补上"},
        {"beat": 2, "speaker": "昭昭", "intent": "插嘴：离谱请求解围"},
    ]
    row = {
        "title": "测试",
        "payload": {"scene_contract": {"beat_chain": beat, "mom_lines_max": 2}},
    }
    bad = _story(
        [
            {"speaker": "灿灿", "line": "我本来就要写，就是忘带本子嘛！"},
            {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
            {"speaker": "妈妈", "line": "你说什么？手停在半空。"},
        ],
    )
    bad["conflict_core"] = "灿灿作业没写"
    bad["gold_beat_chain"] = beat

    out = run_gold_chat_final_acceptance(bad, row, sid="BV_TEST")

    assert out["dialogue"][0]["speaker"] == "妈妈"
    assert "作业" in out["dialogue"][0]["line"]
    assert mock_review.called


def test_cancan_ge_direct_address_blocks():
    issues = collect_sibling_address_issues(
        _story([{"speaker": "灿灿", "line": "哥，你别装可怜！"}]),
    )
    assert len(issues) == 1
    assert issues[0]["kind"] == "称谓"


def test_third_party_ge_not_blocked():
    issues = collect_sibling_address_issues(
        _story(
            [{"speaker": "灿灿", "line": "同学哥哥来串门，你别捣乱。"}],
        ),
    )
    assert issues == []


def test_cancan_gege_vocative_blocks():
    issues = collect_sibling_address_issues(
        _story(
            [{"speaker": "灿灿", "line": "哥哥，你的玩具还在这里。"}],
        ),
    )
    assert len(issues) == 1


def test_cancan_ge_with_nearby_third_ge_blocks_direct_only():
    issues = collect_sibling_address_issues(
        _story(
            [{"speaker": "灿灿", "line": "哥，你看隔壁哥哥都写完了。"}],
        ),
    )
    assert len(issues) == 1
    assert "哥" in issues[0]["desc"]


def test_third_party_meimei_not_blocked():
    issues = collect_sibling_address_issues(
        _story(
            [{"speaker": "灿灿", "line": "隔壁妹妹也想来玩。"}],
        ),
    )
    assert issues == []


def test_third_party_de_meimei_not_blocked():
    issues = collect_sibling_address_issues(
        _story(
            [{"speaker": "灿灿", "line": "同学的妹妹也想来玩。"}],
        ),
    )
    assert issues == []


def test_ge_at_start_blocks_even_with_gebi_later():
    issues = collect_sibling_address_issues(
        _story(
            [{"speaker": "灿灿", "line": "哥，隔壁有人找你。"}],
        ),
    )
    assert len(issues) == 1


@pytest.mark.parametrize(
    "line",
    [
        "我问同学的哥哥，他也不知道。",
        "同学哥哥，你也来玩吧。",
        "我表哥，你上次见过的。",
    ],
)
def test_gege_and_biaoge_not_blocked(line: str):
    issues = collect_sibling_address_issues(
        _story([{"speaker": "灿灿", "line": line}]),
    )
    assert issues == []


def test_gege_at_start_not_exempted_by_later_third_ge():
    issues = collect_sibling_address_issues(
        _story(
            [{"speaker": "灿灿", "line": "哥哥，你看隔壁哥哥写完了。"}],
        ),
    )
    assert len(issues) == 1
    assert "哥哥" in issues[0]["desc"]


def test_relay_quote_mom_saying_not_blocked():
    issues = collect_sibling_address_issues(
        _story(
            [{"speaker": "昭昭", "line": "妈妈说：哥哥要让着妹妹。"}],
        ),
    )
    assert issues == []


def test_quote_third_party_not_blocked():
    issues = collect_sibling_address_issues(
        _story(
            [{"speaker": "昭昭", "line": "妈妈说「哥哥的玩具别碰」。"}],
        ),
    )
    assert issues == []


def test_zhao_calls_jiejie_not_ge():
    issues = collect_sibling_address_issues(
        _story([{"speaker": "昭昭", "line": "姐姐，你让让我嘛。"}]),
    )
    assert issues == []


def test_escalation_signal_not_blocking():
    dlg = [
        {"speaker": "昭昭", "line": "谁怕谁，你来啊！"},
        {"speaker": "灿灿", "line": "不让步，我才不怕。"},
        {"speaker": "昭昭", "line": "没认输呢，继续。"},
    ]
    assert collect_escalation_chatter_signals(_story(dlg))
    assert collect_export_blocking_local_issues(_story(dlg)) == []


def test_near_duplicate_blocks_export():
    a = "你先把作业写完再说。"
    dlg = [
        {"speaker": "昭昭", "line": a},
        {"speaker": "灿灿", "line": "哼，我才不要。"},
        {"speaker": "昭昭", "line": a.replace("。", "！")},
    ]
    block = collect_export_blocking_local_issues(_story(dlg))
    assert any(it["kind"] == "重复" for it in block)


def test_dialogue_meta_label_blocks_export_if_sanitizer_did_not_remove_it():
    dlg = [
        {"speaker": "昭昭", "line": "我就是会挑地方落。"},
        {"speaker": "灿灿", "line": "你还挺会给自己找理由。"},
        {"speaker": "昭昭", "line": "一锤定音。"},
    ]
    block = collect_export_blocking_local_issues(_story(dlg))
    assert any(it["kind"] == "元标签" and it["lines"] == [3] for it in block)


def test_llm_blocking_needs_evidence():
    story = _story([{"speaker": "昭昭", "line": "冰箱里还有两根冰棍。"}])
    weak = [{"lines": [1], "kind": "矛盾", "desc": "前后矛盾", "fix": ""}]
    strong = [
        {
            "lines": [1],
            "kind": "矛盾",
            "desc": "第1句说冰箱里还有两根，下句却一起下楼买，逻辑打架",
            "fix": "",
            "evidence": [{"line": 1, "quote": "两根冰棍"}],
        },
    ]
    fabricated = [
        {
            "lines": [1],
            "kind": "矛盾",
            "desc": "第1句说已经吃完，与后文矛盾",
            "fix": "",
            "evidence": [{"line": 1, "quote": "已经吃完"}],
        },
    ]
    single_char_quote = [
        {
            "lines": [1],
            "kind": "矛盾",
            "desc": "第1句与后文冲突",
            "fix": "",
            "evidence": [{"line": 1, "quote": "无"}],
        },
    ]
    assert filter_llm_export_blocking_issues(weak, story) == []
    assert len(filter_llm_export_blocking_issues(strong, story)) == 1
    assert filter_llm_export_blocking_issues(fabricated, story) == []
    assert filter_llm_export_blocking_issues(single_char_quote, story) == []


@pytest.mark.parametrize("bad_line", [1.9, True, None])
def test_evidence_rejects_non_integer_line_numbers(bad_line):
    story = _story([{"speaker": "昭昭", "line": "冰箱里还有两根冰棍。"}])
    issues = [
        {
            "lines": [1],
            "kind": "矛盾",
            "desc": "测试",
            "fix": "",
            "evidence": [{"line": bad_line, "quote": "两根冰棍"}],
        },
    ]
    assert filter_llm_export_blocking_issues(issues, story) == []


def test_validate_rejects_float_and_bool_issue_lines():
    assert (
        _validate_export_review_raw(
            {
                "issues": [
                    {"lines": [1.9], "kind": "矛盾", "desc": "x"},
                ],
            },
            line_count=3,
        )
        is not None
    )
    assert (
        _validate_export_review_raw(
            {
                "issues": [
                    {"lines": [True], "kind": "矛盾", "desc": "x"},
                ],
            },
            line_count=3,
        )
        is not None
    )


def test_grammar_blocking_with_valid_evidence():
    story = _story(
        [
            {
                "speaker": "灿灿",
                "line": "因为作业本在书包里，所以把书包扔窗外就能交差呀。",
            },
        ],
    )
    issues = [
        {
            "lines": [1],
            "kind": "语病",
            "desc": "因果断裂，读一遍不知道在说什么",
            "fix": "改成能听懂的口语",
            "evidence": [{"line": 1, "quote": "扔窗外就能交差"}],
        },
    ]
    assert len(filter_llm_export_blocking_issues(issues, story)) == 1


def test_mismatch_blocking_needs_cross_line_evidence():
    story = _story(
        [
            {"speaker": "昭昭", "line": "你几岁开始学游泳的？"},
            {
                "speaker": "灿灿",
                "line": "上次暴雨淹了车库，我先把充气艇拖出来才吃饭。",
            },
        ],
    )
    full = [
        {
            "lines": [1, 2],
            "kind": "接不上",
            "desc": "问学游泳年龄，回答却在说暴雨车库，答非所问",
            "fix": "让回答接住年龄或改问题",
            "evidence": [
                {"line": 1, "quote": "几岁开始学游泳"},
                {"line": 2, "quote": "暴雨淹了车库"},
            ],
        },
    ]
    missing_line = [
        {
            "lines": [1, 2],
            "kind": "接不上",
            "desc": "答非所问",
            "fix": "改",
            "evidence": [{"line": 1, "quote": "几岁开始学游泳"}],
        },
    ]
    assert len(filter_llm_export_blocking_issues(full, story)) == 1
    valid, bad = partition_llm_export_blocking_issues(missing_line, story)
    assert valid == []
    assert len(bad) == 1


@patch("app.services.daily_story.review.run_export_semantic_review")
def test_final_acceptance_invalid_evidence_incomplete_not_pass(mock_review):
    mock_review.return_value = ExportSemanticReviewResult(
        completed=True,
        issues=[
            {
                "lines": [1],
                "kind": "语病",
                "desc": "读不通",
                "fix": "改",
                "evidence": [{"line": 1, "quote": "伪造片段"}],
            },
        ],
    )
    chat = _story(
        [{"speaker": "昭昭", "line": "姐姐，我把你的发卡藏进饼干了。"}],
    )
    row = {"title": "藏发卡"}
    with pytest.raises(GoldChatAcceptanceIncomplete) as exc:
        run_gold_chat_final_acceptance(chat, row, sid="BV_TEST")
    assert "审核证据无效" in str(exc.value)
    assert chat.get("quality", {}).get("semantic_pass") is not True


@patch("app.services.daily_story.review.run_export_semantic_review")
def test_final_acceptance_grammar_blocks_with_valid_evidence(mock_review):
    line = "因为作业本在书包里，所以把书包扔窗外就能交差呀。"
    mock_review.return_value = ExportSemanticReviewResult(
        completed=True,
        issues=[
            {
                "lines": [1],
                "kind": "语病",
                "desc": "因果说不通",
                "fix": "改口语",
                "evidence": [{"line": 1, "quote": "扔窗外就能交差"}],
            },
        ],
    )
    chat = _story([{"speaker": "灿灿", "line": line}])
    row = {"title": "交作业"}
    with pytest.raises(GoldChatAcceptanceBlocked) as exc:
        run_gold_chat_final_acceptance(chat, row, sid="BV_TEST")
    assert "语病" in str(exc.value)


def test_review_raw_invalid_issues_not_completed():
    assert _validate_export_review_raw({"issues": "invalid"}, line_count=1) is not None
    assert (
        _validate_export_review_raw(
            {
                "issues": [
                    {
                        "lines": [1],
                        "kind": "矛盾",
                        "desc": "x",
                    },
                ],
            },
            line_count=1,
        )
        is None
    )
    assert (
        _validate_export_review_raw(
            {"issues": [{"lines": [], "kind": "矛盾", "desc": "x"}]},
            line_count=1,
        )
        is not None
    )
    assert (
        _validate_export_review_raw(
            {"issues": [{"lines": [99], "kind": "矛盾", "desc": "x"}]},
            line_count=5,
        )
        is not None
    )
    assert (
        _validate_export_review_raw(
            {"issues": [{"lines": [1], "desc": "x"}]},
            line_count=1,
        )
        is not None
    )
    # evidence 不合规不再算「结构错」：形状校验放行，交给证据通道处理（专家裁决
    # 2026-10：证据问题不该烧掉 JSON 格式纠正预算）。
    evidence_out_of_lines = {
        "issues": [
            {
                "lines": [1],
                "kind": "矛盾",
                "desc": "x",
                "evidence": [{"line": 2, "quote": "越界"}],
            },
        ],
    }
    assert (
        _validate_export_review_raw(evidence_out_of_lines, line_count=1) is None
    )
    assert (
        _validate_export_review_evidence_shape(evidence_out_of_lines, line_count=1)
        is not None
    )
    evidence_partial_coverage = {
        "issues": [
            {
                "lines": [1, 2],
                "kind": "接不上",
                "desc": "x",
                "evidence": [{"line": 1, "quote": "a"}],
            },
        ],
    }
    assert (
        _validate_export_review_raw(evidence_partial_coverage, line_count=2) is None
    )
    assert (
        _validate_export_review_evidence_shape(
            evidence_partial_coverage, line_count=2
        )
        is not None
    )


def test_export_parse_keeps_three_written_issues():
    raw = {
        "issues": [
            {
                "lines": [1],
                "kind": "书面",
                "desc": "措辞偏书面甲",
                "fix": "改",
            },
            {
                "lines": [2],
                "kind": "书面",
                "desc": "措辞偏书面乙",
                "fix": "改",
            },
            {
                "lines": [3],
                "kind": "书面",
                "desc": "措辞偏书面丙",
                "fix": "改",
            },
        ],
    }
    story = _story(
        [
            {"speaker": "昭昭", "line": "a"},
            {"speaker": "灿灿", "line": "b"},
            {"speaker": "昭昭", "line": "c"},
        ],
    )
    normal = parse_review_issues(raw, line_count=3, for_export=False)
    export = parse_review_issues(raw, line_count=3, for_export=True)
    assert len(normal) == 2
    assert len(export) == 3


def test_export_review_bad_issue_entry_incomplete(monkeypatch):
    from app.services.llm import llm_mgr as llm_mgr_mod

    class _FakeClient:
        def __init__(self, payload):
            self._payload = payload

        def _chat_json(self, *_a, **_k):
            return self._payload, None

    story = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    monkeypatch.setattr(
        llm_mgr_mod,
        "_get_client",
        lambda: _FakeClient(
            {
                "issues": [
                    {
                        "lines": [99],
                        "kind": "矛盾",
                        "desc": "越界",
                    },
                ],
            },
        ),
    )
    assert run_export_semantic_review("主题", story).completed is False


def test_export_review_invalid_shape_incomplete(monkeypatch):
    from app.services.llm import llm_mgr as llm_mgr_mod

    class _FakeClient:
        def _chat_json(self, *_a, **_k):
            return {"issues": "invalid"}, None

    monkeypatch.setattr(llm_mgr_mod, "_get_client", lambda: _FakeClient())
    res = run_export_semantic_review("主题", _story([]))
    assert res.completed is False


def test_acceptance_tags_pending_without_semantic_pass():
    q = {"structure_score": 80, "score": 80, "humor_pending": True}
    enrich_quality_acceptance_defaults(q)
    tags = acceptance_tags_for_quality(q)
    assert "结构合格" in tags
    assert "语义待审" in tags
    assert "好笑待审" in tags
    assert q["semantic_pending"] is True


def test_acceptance_tags_after_pass():
    q = {
        "structure_score": 76,
        "score": 76,
        "semantic_pass": True,
        "semantic_pending": False,
        "humor_pending": True,
    }
    tags = acceptance_tags_for_quality(q)
    assert "语义通过" in tags
    assert structure_score_of(q) == 76


@patch("app.services.daily_story.review.run_export_semantic_review")
def test_final_acceptance_local_block(mock_review):
    mock_review.return_value = ExportSemanticReviewResult(completed=True)
    chat = _story([{"speaker": "灿灿", "line": "哥，你闭嘴。"}])
    row = {"title": "测试"}
    with pytest.raises(GoldChatAcceptanceBlocked):
        run_gold_chat_final_acceptance(chat, row, sid="BV_TEST")
    mock_review.assert_not_called()


@patch("app.services.daily_story.review.run_export_semantic_review")
def test_final_acceptance_incomplete(mock_review):
    mock_review.return_value = ExportSemanticReviewResult(
        completed=False,
        error="timeout",
    )
    chat = _story([{"speaker": "昭昭", "line": "姐姐，我来啦。"}])
    row = {"title": "测试"}
    with pytest.raises(GoldChatAcceptanceIncomplete) as exc:
        run_gold_chat_final_acceptance(chat, row, sid="BV_TEST")
    assert "timeout" in str(exc.value)


def test_body_pipeline_keeps_cancan_on_q弹_consecutive():
    from app.services.daily_story.story_types import apply_gold_chat_body_pipeline

    story = {
        "story_type": "N",
        "punchline_explain": "N类测试",
        "dialogue": [
            {"speaker": "灿灿", "line": "打我的屁股。"},
            {"speaker": "灿灿", "line": "我这么Q弹的屁股。"},
            {"speaker": "昭昭", "line": "你少来！"},
        ],
    }
    out, _notes = apply_gold_chat_body_pipeline(story, structure_type="N")
    speakers = [str(x.get("speaker") or "") for x in out.get("dialogue") or []]
    lines = " ".join(str(x.get("line") or "") for x in out.get("dialogue") or [])
    assert "灿灿" in speakers
    assert "昭昭" in speakers
    assert "Q弹" in lines
    assert not any(
        str(x.get("speaker") or "") == "昭昭"
        and "Q弹" in str(x.get("line") or "")
        for x in (out.get("dialogue") or [])
        if isinstance(x, dict)
    )


def test_n_type_patch_promotes_existing_answer_to_solemn_reason():
    from app.services.daily_story.story_types import apply_gold_chat_type_patch
    from app.services.daily_story.story_types.n.validate import append_n_body_errors

    story = {
        "story_type": "N",
        # 故意给冲突的旧标签：显式 structure_type="N" 必须覆盖 punchline 推断。
        "punchline_explain": "C类：旧标签不应覆盖本次显式类型",
        "dialogue": [
            {"speaker": "灿灿", "line": "如果只能选一个，你选姐姐还是我？"},
            {"speaker": "昭昭", "line": "我先选姐姐。"},
            {"speaker": "灿灿", "line": "为什么？"},
            {"speaker": "昭昭", "line": "她笑起来像小太阳。"},
            {"speaker": "灿灿", "line": "你这理由也太奇怪了。"},
            {"speaker": "昭昭", "line": "我说得可认真了。"},
            {"speaker": "灿灿", "line": "行吧，我服了。"},
            {"speaker": "昭昭", "line": "那就这么定。"},
        ],
    }
    before_errors: list[str] = []
    append_n_body_errors(story, before_errors)
    assert any("一本正经自洽" in error for error in before_errors)

    out, notes = apply_gold_chat_type_patch(story, structure_type="N")
    after_errors: list[str] = []
    append_n_body_errors(out, after_errors)

    assert notes == ["N追问后补自洽连接词第4句"]
    assert out["dialogue"][3]["line"] == "因为她笑起来像小太阳。"
    assert not any("一本正经自洽" in error for error in after_errors)


def test_n_type_patch_promotes_existing_question_to_challenge_without_new_plot():
    from app.services.daily_story.story_types import apply_gold_chat_type_patch
    from app.services.daily_story.story_types.n.validate import append_n_body_errors

    story = {
        "story_type": "N",
        "punchline_explain": "N类测试",
        "dialogue": [
            {"speaker": "昭昭", "line": "屁股是橡皮吗？"},
            {"speaker": "灿灿", "line": "不是，我就是认真问问。"},
            {"speaker": "昭昭", "line": "为什么你会这么想？"},
            {"speaker": "灿灿", "line": "因为它弹一下还会回来。"},
            {"speaker": "昭昭", "line": "你这也能讲得这么认真。"},
            {"speaker": "灿灿", "line": "行吧，我服了。"},
        ],
    }
    before: list[str] = []
    append_n_body_errors(story, before)
    assert any("设问/考验" in error for error in before)

    out, notes = apply_gold_chat_type_patch(story, structure_type="N")
    after: list[str] = []
    append_n_body_errors(out, after)

    assert "N已有问句补设问框架第1句" in notes
    assert out["dialogue"][0]["line"] == "你说，屁股是橡皮吗？"
    assert not any("设问/考验" in error for error in after)


def test_n_type_patch_promotes_late_existing_question_to_challenge():
    from app.services.daily_story.story_types import apply_gold_chat_type_patch
    from app.services.daily_story.story_types.n.validate import append_n_body_errors

    story = {
        "story_type": "N",
        "punchline_explain": "N类测试",
        "dialogue": [
            {"speaker": "妈妈", "line": "把作业写完再说。"},
            {"speaker": "昭昭", "line": "我就是想问一个问题。"},
            {"speaker": "灿灿", "line": "为什么非得现在写？"},
            {"speaker": "昭昭", "line": "因为早写完就能早点玩。"},
            {"speaker": "灿灿", "line": "这个理由听着还挺正经。"},
            {"speaker": "昭昭", "line": "屁股是橡皮吗？"},
            {"speaker": "灿灿", "line": "你怎么突然问这个。"},
            {"speaker": "昭昭", "line": "我就随口一问。"},
        ],
    }
    before: list[str] = []
    append_n_body_errors(story, before)
    assert any("设问/考验" in error for error in before)

    out, notes = apply_gold_chat_type_patch(story, structure_type="N")
    after: list[str] = []
    append_n_body_errors(out, after)

    assert "N已有问句补设问框架第6句" in notes
    assert out["dialogue"][5]["line"] == "你说，屁股是橡皮吗？"
    assert not any("设问/考验" in error for error in after)


def test_n_type_patch_promotes_existing_post_reason_reaction_to_stun():
    from app.services.daily_story.story_types import apply_gold_chat_type_patch
    from app.services.daily_story.story_types.n.validate import append_n_body_errors

    story = {
        "story_type": "N",
        "punchline_explain": "N类测试",
        "dialogue": [
            {"speaker": "昭昭", "line": "如果只能选一个，你选姐姐还是我？"},
            {"speaker": "灿灿", "line": "我选姐姐。"},
            {"speaker": "昭昭", "line": "为什么？"},
            {"speaker": "灿灿", "line": "因为姐姐笑起来像小太阳。"},
            {"speaker": "昭昭", "line": "你这理由我还真没想到。"},
            {"speaker": "灿灿", "line": "我可是认真想过的。"},
            {"speaker": "昭昭", "line": "那今天就先听你的。"},
            {"speaker": "灿灿", "line": "我就知道你会懂。"},
        ],
    }
    before: list[str] = []
    append_n_body_errors(story, before)
    assert any("愣住/接不住" in error for error in before)

    out, notes = apply_gold_chat_type_patch(story, structure_type="N")
    after: list[str] = []
    append_n_body_errors(out, after)

    assert "N自洽后显式化愣住反应第7句" in notes
    assert out["dialogue"][6]["line"].startswith("行吧，")
    assert not any("愣住/接不住" in error for error in after)


def test_n_type_patch_does_not_turn_stun_close_into_reason():
    from app.services.daily_story.story_types import apply_gold_chat_type_patch

    story = {
        "story_type": "N",
        "punchline_explain": "N类测试",
        "dialogue": [
            {"speaker": "灿灿", "line": "如果只能选一个，你选谁？"},
            {"speaker": "昭昭", "line": "我选姐姐。"},
            {"speaker": "灿灿", "line": "为什么？"},
            {"speaker": "昭昭", "line": "行吧，我服了。"},
            {"speaker": "灿灿", "line": "那……"},
            {"speaker": "昭昭", "line": "算了。"},
        ],
    }
    out, notes = apply_gold_chat_type_patch(story, structure_type="N")

    assert not any("补自洽连接词" in note for note in notes)
    assert out["dialogue"][3]["line"] == "行吧，我服了。"


def test_cd_protected_tail_unchanged_by_consecutive_patch():
    from app.services.gold_story.gold_chat.convert import (
        patch_gold_chat_consecutive_siblings,
    )

    tail = [
        {"speaker": "昭昭", "line": "末拍一回旋镖"},
        {"speaker": "灿灿", "line": "末拍二嘴硬"},
        {"speaker": "昭昭", "line": "末拍三引话"},
        {"speaker": "灿灿", "line": "末拍四收束"},
    ]
    head = [
        {"speaker": "灿灿", "line": "立规第一句"},
        {"speaker": "灿灿", "line": "所以续一句同人说"},
        {"speaker": "昭昭", "line": "中段反驳"},
        {"speaker": "灿灿", "line": "再顶一句"},
        {"speaker": "灿灿", "line": "所以再续"},
    ]
    story = {
        "story_type": "C",
        "punchline_explain": "C类测试",
        "dialogue": head + [dict(x) for x in tail],
    }
    out, _ = patch_gold_chat_consecutive_siblings(story)
    out_tail = out.get("dialogue") or []
    assert len(out_tail) >= 4
    assert [x.get("line") for x in out_tail[-4:]] == [x.get("line") for x in tail]


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_semantic_repair_returns_updated_structure_score(mock_acceptance):
    from app.services.daily_story.quality import structure_score_of

    calls = {"n": 0}

    def gate(_chat):
        calls["n"] += 1
        return 88 if calls["n"] >= 2 else 70

    mock_acceptance.side_effect = [
        GoldChatAcceptanceBlocked("终检语义硬伤：第[2]句·错位：测试"),
        {"dialogue": [], "quality": {"structure_score": 88, "score": 88}},
    ]

    chat = _story([{"speaker": "昭昭", "line": "姐姐，我来啦。"}])
    row = {"title": "测试", "structure_type": "N"}
    out, struct = run_gold_chat_final_acceptance_with_semantic_repair(
        chat,
        row,
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=gate,
        normalize_chat=lambda c: c,
        fix_llm=lambda c, _fb, **_kw: dict(c),
        validate_chat=lambda _c: None,
        max_repairs=2,
    )
    assert struct == 88
    assert structure_score_of(out.get("quality") or {}) == 88


def test_gold_chat_consecutive_merge_keeps_speaker_and_first_person():
    from app.services.gold_story.gold_chat.convert import (
        patch_gold_chat_consecutive_siblings,
    )

    story = {
        "story_type": "N",
        "punchline_explain": "N类测试",
        "dialogue": [
            {"speaker": "灿灿", "line": "我要打"},
            {"speaker": "灿灿", "line": "我自己的屁股练手感。"},
            {"speaker": "昭昭", "line": "你少来！"},
        ],
    }
    out, notes = patch_gold_chat_consecutive_siblings(story)
    assert any("连说合并" in n for n in notes)
    assert out["dialogue"][0]["speaker"] == "灿灿"
    assert "我自己的屁股" in out["dialogue"][0]["line"]
    assert out["dialogue"][0]["speaker"] != out["dialogue"][1]["speaker"]


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_semantic_repair_passes_after_one_revision(mock_acceptance):
    calls = {"n": 0}

    def acceptance_side_effect(chat, _row, *, sid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GoldChatAcceptanceBlocked(
                "终检语义硬伤：第[3, 4]句·错位：指代不一致",
            )
        return chat

    mock_acceptance.side_effect = acceptance_side_effect
    prompts: list[str] = []
    chat = _story(
        [
            {"speaker": "昭昭", "line": "姐姐，我来啦。"},
            {"speaker": "灿灿", "line": "别闹。"},
        ],
    )
    row = {"title": "测试", "structure_type": "N"}

    def fake_fix(_chat, fb, **_kw):
        prompts.append(fb)
        return dict(_chat)

    out, struct = run_gold_chat_final_acceptance_with_semantic_repair(
        chat,
        row,
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=lambda _c: None,
        max_repairs=2,
    )
    assert out is chat or isinstance(out, dict)
    assert struct == 80
    assert calls["n"] == 2
    assert len(prompts) == 1
    assert "错位" in prompts[0]
    assert "不得换 speaker" in prompts[0]
    assert "未点名行只作只读上下文" in prompts[0]


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_semantic_repair_blocks_after_two_failures(mock_acceptance):
    mock_acceptance.side_effect = GoldChatAcceptanceBlocked(
        "终检语义硬伤：第[2]句·语病：读不通",
    )
    fix_calls: list[int] = []

    def fake_fix(chat, _fb, **_kw):
        fix_calls.append(1)
        return dict(chat)

    chat = _story([{"speaker": "昭昭", "line": "姐姐，我来啦。"}])
    row = {"title": "测试", "structure_type": "N"}
    with pytest.raises(GoldChatAcceptanceBlocked):
        run_gold_chat_final_acceptance_with_semantic_repair(
            chat,
            row,
            sid="BV_TEST",
            st_final="N",
            banned=[],
            mom_max=1,
            source_type="field",
            attach_score=lambda c, _r: c,
            gate_score=lambda _c: 80,
            normalize_chat=lambda c: c,
            fix_llm=fake_fix,
            validate_chat=lambda _c: None,
            max_repairs=2,
        )
    assert len(fix_calls) == 2



def test_final_acceptance_semantic_block_preserves_structured_issues(monkeypatch):
    from app.services.daily_story import review

    issue = {
        "lines": [1, 2],
        "kind": "接不上",
        "desc": "上一句问带伞，下一句却回答早餐",
        "fix": "让第2句直接回应是否带伞",
        "evidence": [
            {"line": 1, "quote": "带伞"},
            {"line": 2, "quote": "早餐"},
        ],
    }
    story = _story(
        [
            {"speaker": "灿灿", "line": "你今天带伞了吗？"},
            {"speaker": "昭昭", "line": "我早餐吃了鸡蛋。"},
        ],
    )
    monkeypatch.setattr(review, "collect_export_blocking_local_issues", lambda _story: [])
    monkeypatch.setattr(
        review,
        "run_export_semantic_review",
        lambda *args, **kwargs: ExportSemanticReviewResult(completed=True, issues=[issue]),
    )

    with pytest.raises(GoldChatSemanticBlocked) as caught:
        run_gold_chat_final_acceptance(story, {"title": "测试"}, sid="TEST")

    assert caught.value.issues == [issue]
    assert "接不上" in str(caught.value)


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_duplicate_repair_uses_acceptance_patched_baseline(mock_acceptance):
    """重复定点修稿基线须与终检 patch 后稿一致，避免行号错位。"""
    issue = {
        "lines": [2, 5],
        "kind": "重复",
        "desc": "第2句与第5句同义复读",
        "fix": "只改第5句",
    }
    calls = {"n": 0}
    seen_fix_chat: list[int] = []

    def acceptance_side_effect(candidate, _row, *, sid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GoldChatLocalDuplicateBlocked(
                "终检本地硬伤：重复",
                issues=[issue],
            )
        return candidate

    mock_acceptance.side_effect = acceptance_side_effect
    original_dialogue = [
        {"speaker": "妈妈", "line": "先把作业写完。"},
        {"speaker": "昭昭", "line": "我等会儿就写。"},
        {"speaker": "灿灿", "line": "那你快点。"},
        {"speaker": "昭昭", "line": "我知道了。"},
    ]
    chat = _story(original_dialogue)

    def fake_patch(chat_in, _row):
        dlg = list(chat_in["dialogue"])
        dlg.insert(
            2,
            {"speaker": "妈妈", "line": "终检补句：先把话说清楚。"},
        )
        return {**chat_in, "dialogue": dlg}

    with patch(
        "app.services.gold_story.gold_chat.finalize.apply_final_acceptance_local_patches",
        side_effect=fake_patch,
    ):
        def fake_fix(repair_chat, feedback, **_kw):
            seen_fix_chat.append(len(repair_chat.get("dialogue") or []))
            assert "只允许改第5句" in feedback
            dlg = list(repair_chat["dialogue"])
            dlg[4] = {
                **dlg[4],
                "line": "我现在就去写，写完再玩积木。",
            }
            return {**repair_chat, "dialogue": dlg}

        result, score = run_gold_chat_final_acceptance_with_semantic_repair(
            chat,
            {"title": "测试"},
            sid="BV_TEST",
            st_final="N",
            banned=[],
            mom_max=1,
            source_type="field",
            attach_score=lambda c, _r: c,
            gate_score=lambda _c: 80,
            normalize_chat=lambda c: c,
            fix_llm=fake_fix,
            validate_chat=lambda _c: None,
            max_repairs=2,
        )

    assert score == 80
    assert seen_fix_chat == [5]
    assert len(result["dialogue"]) == 5
    assert result["dialogue"][4]["line"] == "我现在就去写，写完再玩积木。"
    assert result["dialogue"][2]["line"] == "终检补句：先把话说清楚。"


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_semantic_repair_uses_acceptance_patched_baseline(mock_acceptance):
    """定点修稿基线须与终检本地 patch 后送审稿一致（行号/speaker 对齐）。"""
    beats = [
        {"speaker": "妈妈", "intent": "交代旧事：昭昭掉进菜篓子"},
        {"speaker": "灿灿", "intent": "追问：那你怎么会在篓子里睡着？"},
        {"speaker": "昭昭", "intent": "荒诞解释：我挑的地方好"},
    ]
    row = {
        "title": "测试",
        "structure_type": "N",
        "payload": {"scene_contract": {"story_type": "N", "beat_chain": beats}},
    }
    original_dialogue = [
        {"speaker": "妈妈", "line": "昭昭小时候掉进菜篓子还睡着了。"},
        {"speaker": "灿灿", "line": "你那时候胆子也太大了吧。"},
        {"speaker": "昭昭", "line": "那叫会挑地方落。"},
        {"speaker": "昭昭", "line": "你怎么在篓子里睡着了？"},
        {"speaker": "灿灿", "line": "因为菜篓子软，我躺着舒服呀。"},
    ]
    issue = {
        "lines": [4],
        "kind": "接不上",
        "desc": "第4句追问没接住上一句",
        "fix": "只改第4句",
    }
    calls = {"n": 0}

    def acceptance_side_effect(candidate, _row, *, sid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GoldChatSemanticBlocked(
                "终检语义硬伤：第[4]句·接不上：测试",
                issues=[issue],
            )
        return candidate

    mock_acceptance.side_effect = acceptance_side_effect
    chat = _story(original_dialogue)

    def fake_fix(_chat, _feedback, **_kw):
        dlg = list(_chat["dialogue"])
        dlg[3] = {**dlg[3], "line": "那你怎么会在篓子里睡着呀？"}
        return {**_chat, "dialogue": dlg}

    result, score = run_gold_chat_final_acceptance_with_semantic_repair(
        chat,
        row,
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=lambda _c: None,
        max_repairs=2,
    )

    assert score == 80
    assert result["dialogue"][3]["speaker"] == "灿灿"
    assert result["dialogue"][3]["line"] == "那你怎么会在篓子里睡着呀？"
    assert result["dialogue"][4]["speaker"] == "昭昭"


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_semantic_repair_freezes_non_targets_and_speakers(mock_acceptance):
    issue = {
        "lines": [2],
        "kind": "接不上",
        "desc": "第2句没有接住第1句问题",
        "fix": "只改第2句，让它直接回应上一句",
    }
    calls = {"n": 0}
    seen: list[dict] = []

    def acceptance_side_effect(candidate, _row, *, sid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GoldChatSemanticBlocked(
                "终检语义硬伤：第[2]句·接不上：测试",
                issues=[issue],
            )
        seen.append(candidate)
        return candidate

    mock_acceptance.side_effect = acceptance_side_effect
    original_dialogue = [
        {"speaker": "灿灿", "line": "你今天带伞了吗？"},
        {"speaker": "昭昭", "line": "我早餐吃了鸡蛋。"},
        {"speaker": "灿灿", "line": "那我们快走吧。"},
    ]
    chat = _story(original_dialogue)
    prompts: list[str] = []

    def fake_fix(_chat, feedback, **_kw):
        prompts.append(feedback)
        return {
            **_chat,
            "dialogue": [
                {"speaker": "妈妈", "line": "第一句被模型顺手改坏了。"},
                {"speaker": "昭昭", "line": "带了，我放在书包侧袋里。"},
                {"speaker": "昭昭", "line": "第三句也被模型顺手改坏了。"},
            ],
        }

    result, score = run_gold_chat_final_acceptance_with_semantic_repair(
        chat,
        {"title": "测试", "structure_type": "N"},
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=lambda _c: None,
        max_repairs=2,
    )

    assert score == 80
    assert seen
    assert result["dialogue"] == [
        original_dialogue[0],
        {"speaker": "昭昭", "line": "带了，我放在书包侧袋里。"},
        original_dialogue[2],
    ]
    assert "只允许改第2句" in prompts[0]
    assert "只读邻句" in prompts[0]
    assert "第1句 灿灿：你今天带伞了吗？" in prompts[0]
    assert "第3句 灿灿：那我们快走吧。" in prompts[0]


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_semantic_repair_contract_gap_can_edit_preceding_line(mock_acceptance):
    issue = {
        "lines": [3],
        "kind": "缺前提",
        "desc": "第3句依赖贴纸已经被扯开，但前文没有这一拍",
        "fix": "先补贴纸被扯开的事实，再保留归属争论",
        "missing_beat": {"beat": 8, "intent": "贴纸被两人扯成两半"},
    }
    calls = {"n": 0}

    def acceptance_side_effect(candidate, _row, *, sid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GoldChatSemanticBlocked(
                "终检语义硬伤：第[3]句·缺前提：测试",
                issues=[issue],
            )
        return candidate

    mock_acceptance.side_effect = acceptance_side_effect
    original = [
        {"speaker": "灿灿", "line": "这张贴纸明明是我先拿到的。"},
        {"speaker": "昭昭", "line": "你别拽，我还没贴好呢。"},
        {"speaker": "灿灿", "line": "大半张是我的。"},
    ]
    prompts: list[str] = []

    def fake_fix(_chat, feedback, **_kw):
        prompts.append(feedback)
        dlg = [dict(x) for x in _chat["dialogue"]]
        dlg[1]["line"] = "你都把贴纸扯成两半了，还拽呀！"
        return {**_chat, "dialogue": dlg}

    result, score = run_gold_chat_final_acceptance_with_semantic_repair(
        _story(original),
        {"title": "测试", "structure_type": "N"},
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=lambda _c: None,
        max_repairs=2,
    )

    assert score == 80
    assert result["dialogue"][0] == original[0]
    assert result["dialogue"][1]["line"] == "你都把贴纸扯成两半了，还拽呀！"
    assert result["dialogue"][2] == original[2]
    assert prompts
    assert "只允许改第2句、第3句" in prompts[0]
    assert "beat=8" in prompts[0]
    assert "贴纸被两人扯成两半" in prompts[0]
    assert "前一行来补前提" in prompts[0]


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_semantic_repair_pronoun_grammar_requests_concrete_noun(mock_acceptance):
    issue = {
        "lines": [2],
        "kind": "语病",
        "desc": "‘你贴到这个吗’里的‘这个’指代不清",
        "fix": "把指代换成具体事物",
    }
    calls = {"n": 0}

    def acceptance_side_effect(candidate, _row, *, sid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GoldChatSemanticBlocked(
                "终检语义硬伤：第[2]句·语病：指代不清",
                issues=[issue],
            )
        return candidate

    mock_acceptance.side_effect = acceptance_side_effect
    original = [
        {"speaker": "昭昭", "line": "我要把星星贴纸贴在本子上。"},
        {"speaker": "灿灿", "line": "姐姐你贴到这个吗？"},
        {"speaker": "昭昭", "line": "对，就是这张星星贴纸。"},
    ]
    prompts: list[str] = []

    def fake_fix(_chat, feedback, **_kw):
        prompts.append(feedback)
        dlg = [dict(x) for x in _chat["dialogue"]]
        dlg[1]["line"] = "姐姐，你要贴这张星星贴纸吗？"
        return {**_chat, "dialogue": dlg}

    result, score = run_gold_chat_final_acceptance_with_semantic_repair(
        _story(original),
        {"title": "测试", "structure_type": "N"},
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=lambda _c: None,
        max_repairs=2,
    )

    assert score == 80
    assert result["dialogue"][0] == original[0]
    assert result["dialogue"][1]["line"] == "姐姐，你要贴这张星星贴纸吗？"
    assert result["dialogue"][2] == original[2]
    assert prompts
    assert "指代不清" in prompts[0]
    assert "具体事物名" in prompts[0]
    assert "不要靠只读邻句新增解释" in prompts[0]


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_semantic_repair_rejects_shape_change_and_keeps_original(mock_acceptance):
    issue = {
        "lines": [2],
        "kind": "语病",
        "desc": "第2句读不通",
        "fix": "只改第2句措辞",
    }
    calls = {"n": 0}

    def acceptance_side_effect(candidate, _row, *, sid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GoldChatSemanticBlocked(
                "终检语义硬伤：第[2]句·语病：测试",
                issues=[issue],
            )
        return candidate

    mock_acceptance.side_effect = acceptance_side_effect
    original_dialogue = [
        {"speaker": "灿灿", "line": "你先说清楚。"},
        {"speaker": "昭昭", "line": "这句有点乱。"},
        {"speaker": "灿灿", "line": "我听着呢。"},
    ]
    chat = _story(original_dialogue)

    def fake_fix(_chat, _feedback, **_kw):
        return {
            **_chat,
            "dialogue": [
                original_dialogue[0],
                {"speaker": "昭昭", "line": "模型擅自插了一句。"},
                {"speaker": "昭昭", "line": "现在说清楚了。"},
                original_dialogue[2],
            ],
        }

    result, score = run_gold_chat_final_acceptance_with_semantic_repair(
        chat,
        {"title": "测试", "structure_type": "N"},
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=lambda _c: None,
        max_repairs=2,
    )

    assert score == 80
    assert result["dialogue"] == original_dialogue


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_semantic_repair_applies_union_of_reported_lines_only(mock_acceptance):
    issues = [
        {"lines": [2, 3], "kind": "错位", "desc": "指代不一致", "fix": "统一说话视角"},
        {"lines": [4], "kind": "语病", "desc": "句子不通", "fix": "改顺口"},
    ]
    calls = {"n": 0}

    def acceptance_side_effect(candidate, _row, *, sid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GoldChatSemanticBlocked(
                "终检语义硬伤：多处测试",
                issues=issues,
            )
        return candidate

    mock_acceptance.side_effect = acceptance_side_effect
    original = [
        {"speaker": "灿灿", "line": "第一句保持。"},
        {"speaker": "昭昭", "line": "第二句旧。"},
        {"speaker": "灿灿", "line": "第三句旧。"},
        {"speaker": "昭昭", "line": "第四句旧。"},
        {"speaker": "灿灿", "line": "第五句保持。"},
    ]
    chat = _story(original)

    def fake_fix(_chat, _feedback, **_kw):
        return {
            **_chat,
            "dialogue": [
                {"speaker": "妈妈", "line": "第一句乱改。"},
                {"speaker": "昭昭", "line": "第二句新。"},
                {"speaker": "灿灿", "line": "第三句新。"},
                {"speaker": "昭昭", "line": "第四句新。"},
                {"speaker": "妈妈", "line": "第五句乱改。"},
            ],
        }

    result, _ = run_gold_chat_final_acceptance_with_semantic_repair(
        chat,
        {"title": "测试", "structure_type": "N"},
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=lambda _c: None,
        max_repairs=2,
    )

    assert result["dialogue"] == [
        original[0],
        {"speaker": "昭昭", "line": "第二句新。"},
        {"speaker": "灿灿", "line": "第三句新。"},
        {"speaker": "昭昭", "line": "第四句新。"},
        original[4],
    ]


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_semantic_incomplete_does_not_trigger_repair(mock_acceptance):
    mock_acceptance.side_effect = GoldChatAcceptanceIncomplete("timeout")
    fix_calls: list[int] = []

    def fake_fix(chat, _fb, **_kw):
        fix_calls.append(1)
        return dict(chat)

    chat = _story([{"speaker": "昭昭", "line": "姐姐，我来啦。"}])
    row = {"title": "测试"}
    with pytest.raises(GoldChatAcceptanceIncomplete):
        run_gold_chat_final_acceptance_with_semantic_repair(
            chat,
            row,
            sid="BV_TEST",
            st_final="N",
            banned=[],
            mom_max=1,
            source_type="field",
            attach_score=lambda c, _r: c,
            gate_score=lambda _c: 80,
            normalize_chat=lambda c: c,
            fix_llm=fake_fix,
            validate_chat=lambda _c: None,
        )
    assert fix_calls == []


def test_patch_break_consecutive_does_not_insert_fixed_bridge():
    story = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "昭昭", "line": "妈，你别打姐姐，你打我！"},
            {"speaker": "昭昭", "line": "我屁股Q弹呀，你打一下试试。"},
        ],
    }
    out, changed = patch_break_consecutive_keep_seed(story)
    assert changed is False
    assert len(out["dialogue"]) == 2
    joined = " ".join(str(x.get("line") or "") for x in out["dialogue"])
    assert "听我说完" not in joined


def test_consecutive_sibling_merge_keeps_same_speaker_explanation():
    story = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "昭昭", "line": "妈，你打我。"},
            {"speaker": "昭昭", "line": "我屁股很Q弹。"},
            {"speaker": "灿灿", "line": "你胡说什么呢。"},
        ],
    }
    out, notes = patch_gold_chat_consecutive_siblings(story)
    zhao_lines = [
        str(x.get("line") or "")
        for x in out["dialogue"]
        if x.get("speaker") == "昭昭"
    ]
    assert any("Q弹" in ln for ln in zhao_lines)
    assert any("你打我" in ln for ln in zhao_lines) or len(zhao_lines) == 1
    assert not any("听我说完" in n for n in notes)


def _sample_beat_chain() -> list[dict[str, str]]:
    return [
        {"speaker": "妈妈", "intent": "因作业未做批评灿灿"},
        {"speaker": "昭昭", "intent": "护姐姐挨打"},
    ]


def test_perbeat_key_from_object_keeps_whole_phrase():
    """逐拍 key 不许硬切 8 字切出半截括号（#138「妈妈像什么（黑面」）。"""
    from app.services.gold_story.gold_chat.expand import _perbeat_key_from_object

    assert _perbeat_key_from_object("妈妈像什么（黑面饺子）") == "妈妈像什么"
    assert _perbeat_key_from_object("（黑面）") == "黑面"
    assert _perbeat_key_from_object("黑面饺子") == "黑面饺子"
    assert _perbeat_key_from_object("") == "像什么"
    key = _perbeat_key_from_object("一二三四五六七八九十")
    assert len(key) <= 8


def test_issue_evidence_may_cite_context_lines():
    """错位/重复天然引「问题句 + 对照句」：证据行不必都在 lines 里。"""
    from app.services.daily_story.review import (
        partition_llm_export_blocking_issues,
    )

    story = _story([
        {"speaker": "妈妈", "line": "这黑面饺子好不好吃？"},
        {"speaker": "昭昭", "line": "芯子又苦又涩，妈你倒是眉清目秀。"},
        {"speaker": "妈妈", "line": "你今儿嘴这么甜，是不是又想要零花钱？"},
    ])
    issue = {
        "kind": "错位",
        "lines": [2],
        "desc": "夸赞对象和后续追问对不上",
        "evidence": [
            {"line": 2, "quote": "妈你倒是眉清目秀"},
            {"line": 3, "quote": "你今儿嘴这么甜"},
        ],
    }
    valid, invalid = partition_llm_export_blocking_issues([issue], story)
    assert [it["kind"] for it in valid] == ["错位"]
    assert invalid == []


def test_issue_evidence_requires_every_issue_line_covered():
    """多引对照行可以，但 lines 里每一行都必须被逐字匹配的引文覆盖。"""
    from app.services.daily_story.review import (
        partition_llm_export_blocking_issues,
    )

    story = _story([
        {"speaker": "妈妈", "line": "这黑面饺子好不好吃？"},
        {"speaker": "昭昭", "line": "芯子又苦又涩，难吃无比。"},
        # 两句必须真有 ≥5 字逐字重复，才落进「硬伤」定义、才轮到查证据覆盖
        {"speaker": "灿灿", "line": "你嫌芯子又苦又涩还夸妈，这嘴变太快。"},
    ])
    issue = {
        "kind": "重复",
        "lines": [2, 3],
        "desc": "两句都在说嘴快",
        "evidence": [{"line": 2, "quote": "难吃无比"}],
    }
    valid, invalid = partition_llm_export_blocking_issues([issue], story)
    assert valid == []
    assert [it["kind"] for it in invalid] == ["重复"]


def test_issue_evidence_context_line_with_wrong_quote_still_invalid():
    """对照行引错内容，或行号越界：照旧判证据无效。"""
    from app.services.daily_story.review import (
        partition_llm_export_blocking_issues,
    )

    story = _story([
        {"speaker": "妈妈", "line": "这黑面饺子好不好吃？"},
        {"speaker": "昭昭", "line": "芯子又苦又涩，妈你倒是眉清目秀。"},
    ])
    wrong_quote = {
        "kind": "错位",
        "lines": [2],
        "desc": "夸赞对象和后续追问对不上",
        "evidence": [
            {"line": 2, "quote": "妈你倒是眉清目秀"},
            {"line": 1, "quote": "原文里没有的一句"},
        ],
    }
    out_of_range = {
        "kind": "错位",
        "lines": [2],
        "desc": "夸赞对象和后续追问对不上",
        "evidence": [
            {"line": 2, "quote": "妈你倒是眉清目秀"},
            {"line": 9, "quote": "妈你倒是眉清目秀"},
        ],
    }
    valid, invalid = partition_llm_export_blocking_issues(
        [wrong_quote, out_of_range], story
    )
    assert valid == []
    assert len(invalid) == 2


def test_contract_gap_blocking_and_invalid_evidence():
    beat_chain = _sample_beat_chain()
    story = _story(
        [
            {"speaker": "昭昭", "line": "妈，你打我，别打姐姐。"},
            {"speaker": "妈妈", "line": "你又胡闹什么？"},
        ],
    )
    valid_gap = [
        {
            "lines": [1],
            "kind": "缺前提",
            "missing_beat": {"beat": 1, "intent": "因作业未做批评灿灿"},
            "desc": "解围前未交代妈妈因作业批评",
            "fix": "补触发",
            "evidence": [{"line": 1, "quote": "别打姐姐"}],
        },
    ]
    assert (
        len(
            filter_llm_export_blocking_issues(
                valid_gap,
                story,
                beat_chain=beat_chain,
            ),
        )
        == 1
    )
    fake_gap = [
        {
            "lines": [1],
            "kind": "缺前提",
            "missing_beat": {"intent": "妈妈批评作业"},
            "desc": "缺前提",
            "fix": "补",
            "evidence": [{"line": 1, "quote": "别打姐姐"}],
        },
    ]
    valid, bad = partition_llm_export_blocking_issues(
        fake_gap,
        story,
        beat_chain=beat_chain,
    )
    assert valid == []
    assert len(bad) == 1


def test_contract_gap_rejects_fictional_beat_or_bad_types():
    beat_chain = _sample_beat_chain()
    story = _story(
        [
            {"speaker": "昭昭", "line": "妈，你打我，别打姐姐。"},
        ],
    )
    base = {
        "lines": [1],
        "kind": "缺前提",
        "desc": "缺前提",
        "fix": "补",
        "evidence": [{"line": 1, "quote": "别打姐姐"}],
    }
    for mb in (
        {"beat": 999, "intent": "因作业未做批评灿灿"},
        {"beat": True, "intent": "因作业未做批评灿灿"},
        {"beat": 1, "intent": "虚构事件不在契约里"},
    ):
        valid, bad = partition_llm_export_blocking_issues(
            [{**base, "missing_beat": mb}],
            story,
            beat_chain=beat_chain,
        )
        assert valid == []
        assert len(bad) == 1
    float_issue = [
        {
            **base,
            "missing_beat": {"beat": 1.9, "intent": "因作业未做批评灿灿"},
        },
    ]
    assert _normalize_missing_beat(float_issue[0]["missing_beat"]) is None


def test_missing_relation_gap_requires_string_and_valid_evidence():
    story = _story(
        [
            {"speaker": "昭昭", "line": "那我就拿走这个杯子啦。"},
            {"speaker": "灿灿", "line": "等等，你凭什么拿走？"},
        ],
    )
    base = {
        "lines": [1],
        "kind": "缺前提",
        "desc": "拿走杯子依赖前文归属规则，但前文没有建立",
        "fix": "在此前自然建立杯子归属关系",
        "evidence": [{"line": 1, "quote": "拿走这个杯子"}],
    }
    valid_issue = {
        **base,
        "missing_relation": "前文未建立昭昭拥有或赢得这个杯子的关系",
    }
    valid, bad = partition_llm_export_blocking_issues([valid_issue], story)
    assert len(valid) == 1
    assert bad == []
    assert "缺失关系：前文未建立昭昭拥有或赢得这个杯子的关系" in (
        format_export_blocking_issue_summary(valid[0])
    )

    assert _normalize_missing_relation({"relation": "错误类型"}) is None
    invalid_type, bad_type = partition_llm_export_blocking_issues(
        [{**base, "missing_relation": {"relation": "错误类型"}}],
        story,
    )
    assert invalid_type == []
    assert len(bad_type) == 1

    missing_both, bad_missing = partition_llm_export_blocking_issues([base], story)
    assert missing_both == []
    assert len(bad_missing) == 1


def test_interjection_blocking_positive_and_negative():
    story = _story(
        [
            {"speaker": "灿灿", "line": "等等，先听我说完！"},
            {"speaker": "昭昭", "line": "所以你要赔我橡皮。"},
            {"speaker": "灿灿", "line": "行，我赔。"},
        ],
    )
    good = [
        {
            "lines": [1, 2],
            "kind": "无效插话",
            "desc": "插话后未接续原解释",
            "fix": "删插话或补接续",
            "evidence": [
                {"line": 1, "quote": "先听我说完"},
                {"line": 2, "quote": "赔我橡皮"},
            ],
        },
    ]
    assert len(filter_llm_export_blocking_issues(good, story)) == 1

    hollow = [
        {
            "lines": [1, 2],
            "kind": "无效插话",
            "desc": "空插话",
            "fix": "改",
            "evidence": [{"line": 1, "quote": "先听我说完"}],
        },
    ]
    valid, bad = partition_llm_export_blocking_issues(hollow, story)
    assert valid == []
    assert len(bad) == 1


def test_contract_gap_not_downgraded_by_name_or_prop_substring():
    """人名/道具词与契约 intent 两字重合，不得把缺前提降为证据无效。"""
    beat_chain = _sample_beat_chain()
    gap_issue = {
        "lines": [2],
        "kind": "缺前提",
        "missing_beat": {"beat": 1, "intent": "因作业未做批评灿灿"},
        "desc": "解围前未交代妈妈因作业批评",
        "fix": "补触发",
        "evidence": [{"line": 2, "quote": "别骂姐姐"}],
    }
    for prior_line in (
        "灿灿，今天吃什么？",
        "作业写得真好，表扬你！",
    ):
        story = _story(
            [
                {"speaker": "妈妈", "line": prior_line},
                {"speaker": "昭昭", "line": "妈，你打我，别骂姐姐。"},
            ],
        )
        valid, bad = partition_llm_export_blocking_issues(
            [gap_issue],
            story,
            beat_chain=beat_chain,
        )
        assert len(bad) == 0, prior_line
        assert len(valid) == 1, prior_line


@pytest.mark.parametrize("recovered", [True, False])
def test_export_review_corrects_invalid_evidence_bounded(monkeypatch, recovered):
    from app.services.llm import llm_mgr

    invalid = {"issues": [{"kind": "语病", "lines": [1], "desc": "语句不通",
                           "evidence": [{"line": 1.9, "quote": "姐姐"}]}]}
    corrected = {"issues": [{"kind": "语病", "lines": [1], "desc": "语句不通",
                             "evidence": [{"line": 1, "quote": "姐姐"}]}]}
    calls = []

    class Client:
        def _chat_json(self, system, user, **kwargs):
            calls.append(user)
            return (corrected if recovered and len(calls) == 2 else invalid), None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    story = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    result = run_export_semantic_review("测试", story)
    # 证据通道只给一次定向修复（不占 JSON 格式纠正预算）：改好即停；仍不合规即降级。
    assert len(calls) == 2
    assert "issues[0].evidence" in calls[1]
    assert "姐姐好。" in calls[0] and "姐姐好。" in calls[1]
    # 专家裁决：evidence 不可核验不阻断整稿——剔除该条后继续导出
    assert result.completed, "证据不合规应剔除该条并继续，不再整稿失败"
    if recovered:
        assert len(filter_llm_export_blocking_issues(result.issues, story)) == 1
        assert result.downgraded == []
    else:
        assert result.issues == [], "不可核验的条目须被剔除"
        assert [it["kind"] for it in result.downgraded] == ["语病"]


def test_export_review_evidence_channel_survives_format_budget(monkeypatch):
    """先格式纠正、再证据纠正：证据通道仍能收尾，不因预算用尽判未完成。"""
    from app.services.llm import llm_mgr

    shape_bad = {"issues": [{"lines": [1], "desc": "x"}]}  # 缺 kind
    evidence_bad = {
        "issues": [
            {"kind": "语病", "lines": [1], "desc": "语句不通",
             "evidence": [{"line": 1.9, "quote": "姐姐"}]},
        ]
    }
    calls = []

    class Client:
        def _chat_json(self, system, user, **kwargs):
            calls.append(user)
            return (shape_bad if len(calls) == 1 else evidence_bad), None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    story = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    result = run_export_semantic_review("测试", story)
    assert len(calls) == 3
    assert result.completed
    assert result.issues == []
    assert [it["kind"] for it in result.downgraded] == ["语病"]


def test_export_review_drops_only_unverifiable_issue(monkeypatch):
    """部分条目证据不可核验时，只剔除该条，其余照常生效。"""
    from app.services.llm import llm_mgr

    payload = {
        "issues": [
            {"kind": "语病", "lines": [1], "desc": "语句不通",
             "evidence": [{"line": 1, "quote": "姐姐好"}]},
            {"kind": "重复", "lines": [2], "desc": "重复",
             "evidence": [{"line": 2.5, "quote": "再说"}]},
        ]
    }

    class Client:
        def _chat_json(self, system, user, **kwargs):
            return payload, None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    story = _story([
        {"speaker": "昭昭", "line": "姐姐好。"},
        {"speaker": "灿灿", "line": "你再说。"},
    ])
    result = run_export_semantic_review("测试", story)
    assert result.completed
    assert [it["kind"] for it in result.issues] == ["语病"]
    # 剔除不是静默放过：降级条目须随稿留档供人工抽检
    assert [it["kind"] for it in result.downgraded] == ["重复"]
    assert result.downgraded[0]["downgrade_reason"] == "invalid_evidence"
    assert result.downgraded[0]["weak_verified"] is True


def test_export_review_downgrades_mismatched_quote_style_issue(monkeypatch):
    """观感类引文对不上原文：降级并登记，不再让整稿失败。"""
    from app.services.llm import llm_mgr

    payload = {
        "issues": [
            {"kind": "重复", "lines": [2, 3], "desc": "两句都在说这事，反复说事",
             "evidence": [{"line": 2, "quote": "这句原文里没有"}]},
        ]
    }
    calls = []

    class Client:
        def _chat_json(self, system, user, **kwargs):
            calls.append(user)
            return payload, None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    story = _story([
        {"speaker": "昭昭", "line": "姐姐好。"},
        {"speaker": "灿灿", "line": "这事我说过了。"},
        {"speaker": "昭昭", "line": "这事你又说一遍。"},
    ])
    result = run_export_semantic_review("测试", story)
    assert len(calls) == 2, "证据通道只给一次定向修复"
    assert result.completed
    assert result.issues == []
    assert [it["kind"] for it in result.downgraded] == ["重复"]
    assert result.downgraded[0]["lines"] == [2, 3]
    assert result.downgraded[0]["invalid_evidence"] == [
        {"line": 2, "quote": "这句原文里没有"}
    ]


def test_export_review_keeps_high_risk_issue_with_mismatched_quote(monkeypatch):
    """高风险类（事实/称谓）引文对不上：不许降级，仍判审读未完成。"""
    from app.services.llm import llm_mgr

    payload = {
        "issues": [
            {"kind": "矛盾", "lines": [1], "desc": "前后矛盾：孩子先说去过又说没去过",
             "evidence": [{"line": 1, "quote": "原文里没有的句子"}]},
        ]
    }

    class Client:
        def _chat_json(self, system, user, **kwargs):
            return payload, None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    story = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    result = run_export_semantic_review("测试", story)
    assert not result.completed
    assert result.downgraded == []


def test_export_review_keeps_style_issue_when_weak_verify_fails(monkeypatch):
    """观感类引文对不上且 desc 方向也核不上：疑似幻觉，不许降级。"""
    from app.services.llm import llm_mgr

    payload = {
        "issues": [
            {"kind": "重复", "lines": [1], "desc": "这两句台词完全重复",
             "evidence": [{"line": 1, "quote": "原文里没有的句子"}]},
        ]
    }

    class Client:
        def _chat_json(self, system, user, **kwargs):
            return payload, None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    story = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    result = run_export_semantic_review("测试", story)
    assert not result.completed
    assert result.downgraded == []


def test_export_review_caps_downgraded_items(monkeypatch):
    """降级条目数受上限约束，超限的沿用「不可核验即不放行」。"""
    from app.services.llm import llm_mgr

    payload = {
        "issues": [
            {"kind": "重复", "lines": [1], "desc": "这两句台词来回说同一件事",
             "evidence": [{"line": 1, "quote": "原文里没有的句子A"}]},
            {"kind": "讲不通", "lines": [1], "desc": "这两句台词来回说同一件事",
             "evidence": [{"line": 1, "quote": "原文里没有的句子B"}]},
            {"kind": "接不上", "lines": [1], "desc": "这两句台词来回说同一件事",
             "evidence": [{"line": 1, "quote": "原文里没有的句子C"}]},
            {"kind": "语病", "lines": [1], "desc": "这两句台词来回说同一件事",
             "evidence": [{"line": 1, "quote": "原文里没有的句子D"}]},
        ]
    }

    class Client:
        def _chat_json(self, system, user, **kwargs):
            return payload, None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    story = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    result = run_export_semantic_review("测试", story)
    assert not result.completed, "4 条不可核验超过 1/3 上限，不得整批降级"


def test_final_acceptance_marks_spotcheck_for_downgraded(monkeypatch):
    """降级条目不再拦导出，但质量字段须标需人工抽检并留档。"""
    from app.services.gold_story.gold_chat import finalize as finalize_mod

    downgraded = [
        {
            "kind": "重复",
            "lines": [6, 7, 8, 9, 10, 11],
            "desc": "连续六句都在说同一件事",
            "downgrade_reason": "invalid_evidence",
            "weak_verified": True,
            "invalid_evidence": [{"line": 6, "quote": "对不上的引文"}],
        }
    ]
    with patch(
        "app.services.daily_story.review.run_export_semantic_review"
    ) as mock_review:
        mock_review.return_value = ExportSemanticReviewResult(
            completed=True,
            issues=[],
            downgraded=downgraded,
        )
        chat = _story([{"speaker": "昭昭", "line": "姐姐，我把发卡藏进饼干了。"}])
        row = {"title": "藏发卡"}
        accepted = finalize_mod.run_gold_chat_final_acceptance(
            chat,
            row,
            sid="BV_TEST",
        )
    quality = accepted["quality"]
    assert quality["needs_manual_spotcheck"] is True
    assert quality["review_downgraded_issues"] == downgraded
    assert quality["semantic_pass"] is True
    assert "审核证据待抽检×1" in quality["reasons"]


def test_stamp_without_downgraded_keeps_spotcheck_false():
    """无降级条目时不留下抽检标记。"""
    from app.services.daily_story.quality import (
        stamp_gold_chat_acceptance_quality,
    )

    chat = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    stamp_gold_chat_acceptance_quality(
        chat,
        review_issues=[],
        humor=None,
        chatter_signals=[],
        semantic_pass=True,
    )
    quality = chat["quality"]
    assert quality["needs_manual_spotcheck"] is False
    assert quality["review_downgraded_issues"] == []


def test_export_review_normalizes_alias_shape(monkeypatch):
    """顶层换键名时保守归一：问题内容不丢，仍走严格校验，不额外烧调用。"""
    from app.services.llm import llm_mgr

    payload = {
        "problems": [
            {
                "kind": "语病",
                "lines": [1],
                "desc": "语句不通",
                "evidence": [{"line": 1, "quote": "姐姐好"}],
            }
        ]
    }
    calls = []

    class Client:
        def _chat_json(self, system, user, **kwargs):
            calls.append(user)
            return payload, None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    story = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    result = run_export_semantic_review("测试", story)
    assert len(calls) == 1, "别名键应一次归一成功，不该再纠错"
    assert result.completed
    assert result.issues and result.issues[0]["kind"] == "语病"


def test_export_review_reports_actual_keys_for_unknown_shape(monkeypatch):
    """真无法识别时必须判未完成，并在错误里给出实际键名便于定位。"""
    from app.services.llm import llm_mgr

    class Client:
        def _chat_json(self, system, user, **kwargs):
            return {"verdict": "pass", "notes": []}, None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    story = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    result = run_export_semantic_review("测试", story)
    assert not result.completed
    assert "issues" in result.error and "verdict" in result.error


def _run_mock_reviewer(monkeypatch, story, payload):
    """独立 reviewer mock：测试专家/Qwen 给相同事实证据时，程序硬拦口径一致。"""
    from app.services.llm import llm_mgr

    class Client:
        def _chat_json(self, *_args, **_kwargs):
            return payload, None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    return run_export_semantic_review("测试", story)


def test_export_review_three_party_relation_consensus(monkeypatch):
    cases = [
        (
            _story([{"speaker": "昭昭", "line": "我轻轻推门，客厅门缝还开着。"}]),
            {
                "kind": "旁白",
                "lines": [1],
                "desc": "角色在念动作和场景说明，不是在对现场的人说话",
                "fix": "改成对现场角色可直接说的话",
                "evidence": [{"line": 1, "quote": "我轻轻推门"}],
            },
        ),
        (
            _story([
                {"speaker": "昭昭", "line": "红杯子先放你那边。"},
                {"speaker": "灿灿", "line": "那我把蓝杯子拿走啦。"},
            ]),
            {
                "kind": "缺前提",
                "lines": [2],
                "desc": "蓝杯子突然成为可拿走的对象，前文没有建立",
                "fix": "先自然建立蓝杯子的存在或归属",
                "missing_relation": "前文未建立蓝杯子的存在/归属 → 第2句直接拿走",
                "evidence": [{"line": 2, "quote": "蓝杯子拿走"}],
            },
        ),
        (
            _story([{"speaker": "昭昭", "line": "我赢了，所以蛋糕归我。"}]),
            {
                "kind": "缺前提",
                "lines": [1],
                "desc": "蛋糕奖励依赖未建立的输赢规则",
                "fix": "前文先建立赢家获得蛋糕的规则",
                "missing_relation": "前文未建立赢家获得蛋糕 → 第1句直接据此领奖",
                "evidence": [{"line": 1, "quote": "蛋糕归我"}],
            },
        ),
    ]
    for story, issue in cases:
        expert = _run_mock_reviewer(
            monkeypatch,
            story,
            {"issues": [issue], "humor": {"funny_score": 10}},
        )
        qwen = _run_mock_reviewer(
            monkeypatch,
            story,
            {"issues": [dict(issue)], "humor": {"funny_score": 10}},
        )
        assert expert.completed and qwen.completed
        # “我”：程序自己的证据校验/阻断判定，与两家 mock 的结论必须一致。
        assert len(filter_llm_export_blocking_issues(expert.issues, story)) == 1
        assert len(filter_llm_export_blocking_issues(qwen.issues, story)) == 1


def test_export_review_three_party_allows_natural_transition_and_style(monkeypatch):
    natural = _story([
        {"speaker": "昭昭", "line": "姐姐，红杯子给你，我拿蓝杯子。"},
        {"speaker": "灿灿", "line": "行，那我们就这么分。"},
    ])
    for payload in ({"issues": []}, {"issues": []}):  # expert mock / Qwen mock
        result = _run_mock_reviewer(monkeypatch, natural, payload)
        assert result.completed
        assert filter_llm_export_blocking_issues(result.issues, natural) == []

    style_story = _story([
        {"speaker": "昭昭", "line": "姐姐，我觉得这件事情有一点不太对劲。"},
    ])
    style_issue = {
        "kind": "书面",
        "lines": [1],
        "desc": "句子稍完整、偏书面，但仍是对姐姐自然可说的话",
        "fix": "可选：改得更口语",
        "evidence": [{"line": 1, "quote": "这件事情有一点不太对劲"}],
    }
    for payload in ({"issues": [style_issue]}, {"issues": [dict(style_issue)]}):
        result = _run_mock_reviewer(monkeypatch, style_story, payload)
        assert result.completed
        assert len(result.issues) == 1
        assert filter_llm_export_blocking_issues(result.issues, style_story) == []


def test_export_review_ignores_malformed_missing_beat_on_non_gap_issue(monkeypatch):
    from app.services.llm import llm_mgr

    calls = []
    payload = {
        "issues": [
            {
                "kind": "书面",
                "lines": [1],
                "desc": "措辞偏书面",
                "missing_beat": 2,
                "evidence": [{"line": 1, "quote": "姐姐"}],
            }
        ]
    }

    class Client:
        def _chat_json(self, system, user, **kwargs):
            calls.append(user)
            return payload, None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    result = run_export_semantic_review(
        "测试",
        _story([{"speaker": "昭昭", "line": "姐姐好。"}]),
    )
    assert result.completed is True
    assert len(calls) == 1
    assert len(result.issues) == 1
    assert "missing_beat" not in result.issues[0]


def test_export_review_corrects_invalid_missing_beat_once(monkeypatch):
    from app.services.llm import llm_mgr

    intent = "因作业未做批评灿灿"
    invalid = {
        "issues": [{"kind": "缺前提", "lines": [1], "desc": "缺少批评前提",
                    "missing_beat": {"beat": 1.9, "intent": intent},
                    "evidence": [{"line": 1, "quote": "姐姐"}]}]
    }
    corrected = {
        "issues": [{"kind": "缺前提", "lines": [1], "desc": "缺少批评前提",
                    "missing_beat": {"beat": 1, "intent": intent},
                    "evidence": [{"line": 1, "quote": "姐姐"}]}]
    }
    calls = []

    class Client:
        def _chat_json(self, system, user, **kwargs):
            calls.append(user)
            return (corrected if len(calls) == 2 else invalid), None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    result = run_export_semantic_review(
        "测试",
        _story([{"speaker": "昭昭", "line": "姐姐好。"}]),
        beat_chain=[{"speaker": "妈妈", "intent": intent}],
    )
    assert result.completed is True
    assert len(calls) == 2
    assert "其他 kind 不要输出 missing_beat" in calls[1]
    assert '"beat":1' in calls[1]
    assert result.issues[0]["missing_beat"] == {"beat": 1, "intent": intent}


def test_export_review_retries_invalid_json_after_client_exhausts_internal_retry(monkeypatch):
    from app.services.llm import llm_mgr

    calls = []

    class Client:
        def _chat_json(self, system, user, **kwargs):
            calls.append(user)
            if len(calls) == 1:
                raise ValueError("LLM returned invalid JSON: Expecting ',' delimiter")
            return {"issues": []}, None

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    result = run_export_semantic_review(
        "测试",
        _story([{"speaker": "昭昭", "line": "姐姐好。"}]),
    )

    assert result.completed is True
    assert len(calls) == 2
    assert "审核格式纠正" in calls[1]
    assert "上一份审核未通过格式校验" in calls[1]


def test_export_review_timeout_does_not_retry(monkeypatch):
    from app.services.llm import llm_mgr
    calls = []

    class Client:
        def _chat_json(self, *args, **kwargs):
            calls.append(1)
            raise TimeoutError("timeout")

    monkeypatch.setattr(llm_mgr, "_get_client", lambda: Client())
    result = run_export_semantic_review("测试", _story([]))
    assert not result.completed
    assert len(calls) == 1


def test_production_eligibility_binds_review_to_current_dialogue():
    # type 字段稍后由 manager 补写时，只要与终验时可解析类型一致，不应误判正文变化。
    story = _story([
        {"speaker": "昭昭", "line": "你先说规则。"},
        {"speaker": "灿灿", "line": "谁先完成谁先用。"},
    ])
    story["quality"]["humor"] = {"funny_score": 10}
    stamp_story_review_binding(story, semantic_pass=True)

    ready = story_production_eligibility(story)
    assert ready["ok"] is True
    reviewed_hash = story["quality"]["reviewed_content_hash"]

    story["dialogue"][1]["line"] = "谁先完成就归谁。"
    stale = story_production_eligibility(story)
    assert stale["ok"] is False
    assert stale["reviewed_content_hash"] == reviewed_hash
    assert any("旧终验结果已失效" in reason for reason in stale["reasons"])


def test_direct_review_does_not_reuse_pre_repair_humor(monkeypatch):
    from app.services.daily_story import review as review_mod

    story = _story([
        {"speaker": "昭昭", "line": "姐姐你先说。"},
        {"speaker": "灿灿", "line": "这句原来不顺。"},
        {"speaker": "昭昭", "line": "那我等你。"},
    ])
    calls = {"review": 0}

    class Client:
        def review_daily_story_issues(self, _theme, _story):
            calls["review"] += 1
            if calls["review"] == 1:
                return ([{
                    "lines": [2],
                    "kind": "语病",
                    "desc": "测试修稿",
                    "fix": "改顺",
                }], {"funny_score": 14, "best_moment": "旧稿笑点", "humor_type": "natural"})
            return ([], None)

        def spot_fix_daily_story(self, *_args, **_kwargs):
            return {"fixes": [{"no": 2, "line": "这句已经改顺啦。"}]}

    def fake_apply(s, _raw, **_kwargs):
        out = {**s, "dialogue": [dict(x) for x in s["dialogue"]]}
        out["dialogue"][1]["line"] = "这句已经改顺啦。"
        return out, [2]

    monkeypatch.setattr(review_mod, "_apply_fixes_greedily", fake_apply)
    result = review_mod.run_daily_story_review(Client(), "测试", story)

    assert calls["review"] == 2
    assert result["dialogue"][1]["line"] == "这句已经改顺啦。"
    assert "humor" not in result["quality"]
    assert "好笑待审" in result["quality"].get("acceptance_tags", [])


def test_direct_review_without_llm_reviewer_stays_semantic_pending():
    from app.services.daily_story import review as review_mod

    story = _story([
        {"speaker": "昭昭", "line": "姐姐你先说规则。"},
        {"speaker": "灿灿", "line": "谁先收完谁先选。"},
        {"speaker": "昭昭", "line": "那我先收蓝色的。"},
    ])

    result = review_mod.run_daily_story_review(object(), "测试", story)

    assert result["quality"].get("semantic_pass") is None
    assert "reviewed_content_hash" not in result["quality"]
    assert "语义待审" in result["quality"].get("acceptance_tags", [])
    assert story_production_eligibility(result)["ok"] is False


def test_review_hash_uses_canonical_type_before_manager_persists_field():
    story = _story([
        {"speaker": "昭昭", "line": "谁先收完谁先选。"},
        {"speaker": "灿灿", "line": "那我先收蓝色的。"},
    ])
    story["punchline_explain"] = "A类权威翻车：姐姐立规后被弟弟拿原话反将一军"
    story["quality"]["humor"] = {"funny_score": 10}
    stamp_story_review_binding(story, semantic_pass=True)
    before = story["quality"]["reviewed_content_hash"]

    story["story_type"] = "A"
    after = story_production_eligibility(story)
    assert after["ok"] is True
    assert after["current_content_hash"] == before


def test_gold_review_contract_ignores_notes_but_binds_dialogue_seed():
    from app.services.daily_story.quality import gold_story_review_contract

    story = _story([
        {"speaker": "昭昭", "line": "姐姐先说规则。"},
        {"speaker": "灿灿", "line": "谁先收完谁先选。"},
    ])
    story["story_type"] = "A"
    story["quality"]["humor"] = {"funny_score": 10}
    row = {
        "structure_type": "A",
        "mechanism": "M6",
        "payload": {
            "dialogue_seed": [{"speaker": "昭昭", "intent": "先问规则"}],
            "scene_contract": {
                "mom_lines_max": 1,
                "beat_chain": [{"beat": 1, "speaker": "昭昭", "intent": "先问规则"}],
                "location": "客厅",
                "remap_note": "说明A",
            },
        },
    }
    stamp_story_review_binding(
        story,
        semantic_pass=True,
        review_contract=gold_story_review_contract(row, story),
    )

    row["payload"]["scene_contract"]["location"] = "餐桌旁"
    row["payload"]["scene_contract"]["remap_note"] = "说明B"
    still_ready = story_production_eligibility(
        story,
        review_contract=gold_story_review_contract(row, story),
    )
    assert still_ready["ok"] is True

    row["payload"]["dialogue_seed"][0]["intent"] = "改成另一个前提"
    stale = story_production_eligibility(
        story,
        review_contract=gold_story_review_contract(row, story),
    )
    assert stale["ok"] is False
    assert any("旧终验结果已失效" in reason for reason in stale["reasons"])


def test_full_library_dedupe_blocks_exact_cross_type_but_not_topic_only():
    candidate = {
        "story_type": "A",
        "conflict_core": "争先后顺序",
        "dialogue": [
            {"speaker": "昭昭", "line": "我先来的。"},
            {"speaker": "灿灿", "line": "明明是我先拿到。"},
            {"speaker": "昭昭", "line": "那就猜拳。"},
        ],
    }
    rows = [
        {"id": 7, "story": {**candidate, "story_type": "H"}},
        {
            "id": 8,
            "story": {
                "story_type": "A",
                "conflict_core": "同题材但冲突不同",
                "dialogue": [
                    {"speaker": "昭昭", "line": "今天轮到你收玩具。"},
                    {"speaker": "灿灿", "line": "我收蓝色的，你收红色的。"},
                    {"speaker": "昭昭", "line": "行，分开收更快。"},
                ],
            },
        },
    ]
    matches = find_story_duplicate_matches(candidate, rows)
    assert matches[0]["story_id"] == 7
    assert matches[0]["severity"] == "block"
    assert any(part["part"] == "dialogue" for part in matches[0]["matched_parts"])
    dialogue_part = next(
        part for part in matches[0]["matched_parts"] if part["part"] == "dialogue"
    )
    assert dialogue_part["candidate"] == dialogue_part["matched"]
    assert "我先来的" in dialogue_part["candidate"]
    assert all(item["story_id"] != 8 for item in matches)


def test_authority_rule_patch_refuses_narrative_disguised_as_dialogue():
    from app.services.gold_story.gold_chat.patch import _intent_to_rule_line

    assert _intent_to_rule_line("立规：谁先完成谁先用") == "谁先完成谁先用。"
    assert _intent_to_rule_line("立规：端出奖品，宣布比赛开始") == ""


def test_intent_text_is_speakable_rejects_narrative_intents():
    """叙述型 intent 不是台词：动作/神态、括号说明、纯陈述句都不算「说出口的话」。"""
    from app.services.gold_story.gold_chat.patch import _intent_text_is_speakable

    # 叙述发生了什么（第三人称事件）→ 不能当台词
    assert not _intent_text_is_speakable("端来黑面饺子，问昭昭好不好吃")
    assert not _intent_text_is_speakable("妈妈端来一盘黑面饺子，站在桌边")
    assert not _intent_text_is_speakable("他转身走了")
    # 带括号动作标记 → 观众听不见
    assert not _intent_text_is_speakable("（望窗外）今天天真好")
    # 当面说出口的话 → 放行
    assert _intent_text_is_speakable("你就不能祝我像一个公主")
    assert _intent_text_is_speakable("作业写完了吗")


def test_authority_opening_line_falls_back_instead_of_narrating_and_dialogue():
    """权威开场 intent 兜底：叙述型 intent 不再被加个问号当台词念出来。"""
    from app.services.gold_story.gold_chat.patch import (
        _intent_to_authority_opening_line,
    )

    story = {"conflict_core": "抢遥控器"}
    assert (
        _intent_to_authority_opening_line("震怒：端来黑面饺子，问昭昭好不好吃", story)
        == "别磨蹭了，先把该做的事做完！"
    )
    # 已具备口语形态的 intent 仍可原样落地
    assert (
        _intent_to_authority_opening_line("震怒：你就不能祝我像一个公主", story)
        == "你就不能祝我像一个公主？"
    )
    assert (
        _intent_to_authority_opening_line(
            "责备：大声责备昭昭弄脏衣服，并说出“傻”字",
            story,
            speaker="妈妈",
        )
        == "你怎么这么傻！"
    )


@pytest.mark.parametrize("recover", [True, False])
def test_local_duplicate_repair_rechecks_all_gates(monkeypatch, recover):
    from app.services.daily_story import review
    from app.services.gold_story.gold_chat import finalize
    events = []
    issue = {"lines": [1, 2], "kind": "重复", "desc": "同义重复", "fix": "合并"}

    def local(story):
        events.append("local")
        return [] if recover and story.get("revised") else [issue]

    def semantic(*args, **kwargs):
        events.append("semantic")
        return ExportSemanticReviewResult(completed=True)

    def fix(story, feedback, **kwargs):
        events.append("fix")
        assert "同义重复" in feedback
        return dict(story, revised=True)

    def validate(story):
        events.append("validate")

    def attach(story, row):
        events.append("score")
        return story

    def gate(story):
        events.append("gate")
        return 80

    monkeypatch.setattr(review, "collect_export_blocking_local_issues", local)
    monkeypatch.setattr(review, "run_export_semantic_review", semantic)
    kwargs = dict(sid="TEST", st_final="N", banned=[], mom_max=1,
                  source_type="field", attach_score=attach, gate_score=gate,
                  normalize_chat=lambda c: c, fix_llm=fix, validate_chat=validate)
    story = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    if recover:
        result, score = finalize.run_gold_chat_final_acceptance_with_semantic_repair(story, {}, **kwargs)
        assert result["revised"]
        assert events == [
            "validate",
            "score",
            "gate",
            "local",
            "fix",
            "validate",
            "score",
            "gate",
            "local",
            "semantic",
        ]
    else:
        with pytest.raises(finalize.GoldChatLocalDuplicateBlocked):
            finalize.run_gold_chat_final_acceptance_with_semantic_repair(story, {}, **kwargs)
        assert events.count("fix") == 2
        assert events.count("local") == 3
        assert "semantic" not in events


def test_local_duplicate_gets_one_rescue_after_shared_budget_exhausted(monkeypatch):
    from app.services.daily_story import review
    from app.services.gold_story.gold_chat import finalize
    from app.services.gold_story.gold_chat.repair import GoldChatRepairBudget

    events: list[str] = []
    issue = {
        "lines": [5, 11],
        "kind": "重复",
        "desc": "第5句与第11句说的是同一件事，换词重复",
        "fix": "改第11句推进新信息",
    }

    dialogue = [
        {"speaker": "昭昭" if no % 2 else "灿灿", "line": f"第{no}句原稿。"}
        for no in range(1, 12)
    ]

    def local(story):
        events.append("local")
        rows = story.get("dialogue") or []
        return [] if rows[10]["line"] == "写完这页我们就去拼积木。" else [issue]

    def fix(story, feedback, **kwargs):
        events.append("fix")
        assert "第5句与第11句" in feedback
        assert "只允许改第11句" in feedback
        out = dict(story)
        rows = [dict(item) for item in story.get("dialogue") or []]
        rows[10]["line"] = "写完这页我们就去拼积木。"
        out["dialogue"] = rows
        return out

    def semantic(*args, **kwargs):
        events.append("semantic")
        return ExportSemanticReviewResult(completed=True)

    monkeypatch.setattr(review, "collect_export_blocking_local_issues", local)
    monkeypatch.setattr(review, "run_export_semantic_review", semantic)
    budget = GoldChatRepairBudget(max_repairs=2)
    assert budget.consume(stage="expand_structure", reason="structure_score:65")
    assert budget.consume(stage="align", reason="align_refine_failed")
    assert budget.exhausted

    result, score = finalize.run_gold_chat_final_acceptance_with_semantic_repair(
        _story(dialogue),
        {},
        sid="TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, r: c,
        gate_score=lambda c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fix,
        validate_chat=lambda c: None,
        repair_budget=budget,
    )

    assert result["dialogue"][10]["line"] == "写完这页我们就去拼积木。"
    assert score == 80
    assert budget.used == 2
    assert events == ["local", "fix", "local", "semantic"]


def test_local_duplicate_repair_freezes_other_lines_and_all_speakers(monkeypatch):
    from app.services.daily_story import review
    from app.services.gold_story.gold_chat import finalize

    issue = {
        "lines": [1, 3],
        "kind": "重复",
        "desc": "第1句与第3句说的是同一件事，换词重复",
        "fix": "改第3句推进新信息",
    }
    original_dialogue = [
        {"speaker": "昭昭", "line": "你先把作业写完再说。"},
        {"speaker": "灿灿", "line": "我马上就写。"},
        {"speaker": "昭昭", "line": "作业先写完再玩。"},
    ]

    def local(story):
        rows = story.get("dialogue") or []
        return [] if rows[2]["line"] == "那你写完我们就去拼积木。" else [issue]

    def fix(story, feedback, **kwargs):
        assert "第1句与第3句" in feedback
        assert "只允许改第3句" in feedback
        out = dict(story)
        out["dialogue"] = [
            {"speaker": "妈妈", "line": "第一句也被模型顺手改了。"},
            {"speaker": "妈妈", "line": "第二句也被模型顺手改了。"},
            {"speaker": "灿灿", "line": "那你写完我们就去拼积木。"},
        ]
        return out

    monkeypatch.setattr(review, "collect_export_blocking_local_issues", local)
    monkeypatch.setattr(
        review,
        "run_export_semantic_review",
        lambda *args, **kwargs: ExportSemanticReviewResult(completed=True),
    )

    result, score = finalize.run_gold_chat_final_acceptance_with_semantic_repair(
        _story(original_dialogue),
        {},
        sid="TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, r: c,
        gate_score=lambda c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fix,
        validate_chat=lambda c: None,
    )

    assert score == 80
    assert result["dialogue"] == [
        original_dialogue[0],
        original_dialogue[1],
        {"speaker": "昭昭", "line": "那你写完我们就去拼积木。"},
    ]


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_export_repair_chars_239_then_passes(mock_acceptance):
    mock_acceptance.return_value = _story([{"speaker": "昭昭", "line": "姐姐好。"}])
    validate_calls = {"n": 0}
    prompts: list[str] = []

    def validate(_chat):
        validate_calls["n"] += 1
        if validate_calls["n"] == 1:
            raise ValueError(
                f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前239",
            )

    def fake_fix(_chat, fb, **_kw):
        prompts.append(fb)
        return dict(_chat)

    run_gold_chat_final_acceptance_with_semantic_repair(
        _story([{"speaker": "昭昭", "line": "姐姐好。"}]),
        {"title": "测试"},
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=3,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=validate,
        max_repairs=2,
    )
    assert validate_calls["n"] == 2
    assert len(prompts) == 1
    assert "239" in prompts[0]
    assert "240" in prompts[0] or str(DAILY_STORY_BODY_CHARS_MIN) in prompts[0]


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_export_actual_239_within_joint_floor_passes_without_local_close(mock_acceptance):
    """12 句达标时字数下限放宽一行：239 字不再触发本地补字，也不烧 LLM。"""
    from app.services.gold_story.gold_chat.length import gold_chat_effective_min_chars

    dialogue = [
        {
            "speaker": "昭昭" if i % 2 == 0 else "灿灿",
            "line": "甲" * (19 if i == 11 else 20),
        }
        for i in range(12)
    ]
    chat = _story(dialogue)
    assert dialogue_total_chars(chat) == DAILY_STORY_BODY_CHARS_MIN - 1

    validate_totals: list[int] = []
    fix_calls: list[str] = []

    def validate(candidate):
        total = dialogue_total_chars(candidate)
        validate_totals.append(total)
        rows = [
            x for x in candidate.get("dialogue") or []
            if isinstance(x, dict) and str(x.get("line") or "").strip()
        ]
        floor = gold_chat_effective_min_chars(rows)
        if total < floor:
            raise ValueError(f"正文总字数须≥{floor}，当前{total}")

    def fake_fix(candidate, feedback, **_kw):
        fix_calls.append(feedback)
        return dict(candidate)

    mock_acceptance.side_effect = lambda candidate, _row, *, sid: candidate
    result, score = run_gold_chat_final_acceptance_with_semantic_repair(
        chat,
        {"title": "测试"},
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=3,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=validate,
        max_repairs=2,
    )

    assert score == 80
    assert validate_totals == [239]
    assert not fix_calls
    assert dialogue_total_chars(result) == DAILY_STORY_BODY_CHARS_MIN - 1


def test_export_actual_239_with_other_hard_error_still_uses_llm_repair():
    dialogue = [
        {
            "speaker": "昭昭" if i % 2 == 0 else "灿灿",
            "line": "甲" * (19 if i == 11 else 20),
        }
        for i in range(12)
    ]
    chat = _story(dialogue)
    assert dialogue_total_chars(chat) == DAILY_STORY_BODY_CHARS_MIN - 1
    fix_calls: list[str] = []

    def validate(candidate):
        total = dialogue_total_chars(candidate)
        raise ValueError(
            f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前{total};"
            "妈妈台词须≤3句，当前4",
        )

    def fake_fix(candidate, feedback, **_kw):
        fix_calls.append(feedback)
        return dict(candidate)

    with pytest.raises(GoldChatValidationRepairableError):
        run_gold_chat_final_acceptance_with_semantic_repair(
            chat,
            {"title": "测试"},
            sid="BV_TEST",
            st_final="N",
            banned=[],
            mom_max=3,
            source_type="field",
            attach_score=lambda c, _r: c,
            gate_score=lambda _c: 80,
            normalize_chat=lambda c: c,
            fix_llm=fake_fix,
            validate_chat=validate,
            max_repairs=1,
        )

    assert len(fix_calls) == 1
    assert dialogue_total_chars(chat) == DAILY_STORY_BODY_CHARS_MIN - 1


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_export_repair_mom_four_to_three(mock_acceptance):
    mock_acceptance.return_value = _story([{"speaker": "妈妈", "line": "行。"}])
    state = {"mom_ok": False}
    prompts: list[str] = []

    def validate(chat):
        mom = sum(
            1
            for x in chat.get("dialogue") or []
            if isinstance(x, dict) and x.get("speaker") == "妈妈"
        )
        if mom > 3:
            raise ValueError(f"妈妈台词须≤3句，当前{mom}")
        state["mom_ok"] = True

    def fake_fix(chat, fb, **_kw):
        prompts.append(fb)
        dlg = [dict(x) for x in chat.get("dialogue") or []]
        dlg = [x for x in dlg if x.get("speaker") != "妈妈"] + [
            {"speaker": "妈妈", "line": "行。"},
        ] * 3
        return {**chat, "dialogue": dlg[:14]}

    run_gold_chat_final_acceptance_with_semantic_repair(
        _story([{"speaker": "妈妈", "line": f"句{i}"} for i in range(4)]),
        {"title": "测试"},
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=3,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=validate,
        max_repairs=2,
    )
    assert state["mom_ok"]
    assert any("妈妈" in p and "3" in p for p in prompts)


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_export_repair_semantic_then_chars_short_second_round(mock_acceptance):
    acc_calls = {"n": 0}
    validate_calls = {"n": 0}
    fix_calls = {"n": 0}

    def acceptance_side(chat, _row, *, sid):
        acc_calls["n"] += 1
        if acc_calls["n"] == 1:
            raise GoldChatAcceptanceBlocked("终检语义硬伤：第[2]句·错位：测试")
        return chat

    mock_acceptance.side_effect = acceptance_side

    def validate(_chat):
        validate_calls["n"] += 1
        if validate_calls["n"] == 2:
            raise ValueError(
                f"正文总字数须≥{DAILY_STORY_BODY_CHARS_MIN}，当前200",
            )

    def fake_fix(chat, _fb, **_kw):
        fix_calls["n"] += 1
        return dict(chat)

    run_gold_chat_final_acceptance_with_semantic_repair(
        _story([{"speaker": "昭昭", "line": "姐姐好。"}]),
        {"title": "测试"},
        sid="BV_TEST",
        st_final="N",
        banned=[],
        mom_max=3,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fake_fix,
        validate_chat=validate,
        max_repairs=2,
    )
    assert acc_calls["n"] == 2
    assert fix_calls["n"] == 2
    assert validate_calls["n"] == 3


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_export_repair_exhausted_does_not_export(mock_acceptance):
    mock_acceptance.side_effect = GoldChatAcceptanceBlocked(
        "终检语义硬伤：第[2]句·语病：读不通",
    )
    fix_calls: list[int] = []

    def fake_fix(chat, _fb, **_kw):
        fix_calls.append(1)
        return dict(chat)

    with pytest.raises(GoldChatAcceptanceBlocked):
        run_gold_chat_final_acceptance_with_semantic_repair(
            _story([{"speaker": "昭昭", "line": "姐姐好。"}]),
            {"title": "测试"},
            sid="BV_TEST",
            st_final="N",
            banned=[],
            mom_max=3,
            source_type="field",
            attach_score=lambda c, _r: c,
            gate_score=lambda _c: 80,
            normalize_chat=lambda c: c,
            fix_llm=fake_fix,
            validate_chat=lambda _c: None,
            max_repairs=2,
        )
    assert len(fix_calls) == 2
    assert mock_acceptance.call_count == 3


@patch("app.services.gold_story.gold_chat.finalize.run_gold_chat_final_acceptance")
def test_export_repair_structure_score_in_loop(mock_acceptance):
    mock_acceptance.return_value = _story([])
    gate_calls = {"n": 0}

    def gate(_chat):
        gate_calls["n"] += 1
        if gate_calls["n"] == 1:
            raise ValueError("structure_score:70")
        return 80

    with pytest.raises(ValueError, match="structure_score:70"):
        run_gold_chat_final_acceptance_with_semantic_repair(
            _story([]),
            {"title": "测试", "structure_type": "N"},
            sid="BV_TEST",
            st_final="N",
            banned=[],
            mom_max=3,
            source_type="field",
            attach_score=lambda c, _r: c,
            gate_score=gate,
            normalize_chat=lambda c: c,
            fix_llm=lambda c, _fb, **_kw: dict(c),
            validate_chat=lambda _c: None,
            max_repairs=0,
        )

    out, struct = run_gold_chat_final_acceptance_with_semantic_repair(
        _story([]),
        {"title": "测试"},
        sid="BV2",
        st_final="N",
        banned=[],
        mom_max=3,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=gate,
        normalize_chat=lambda c: c,
        fix_llm=lambda c, _fb, **_kw: dict(c),
        validate_chat=lambda _c: None,
        max_repairs=1,
    )
    assert struct == 80
    assert gate_calls["n"] >= 2


def test_mixed_local_hard_errors_do_not_enter_duplicate_repair(monkeypatch):
    from app.services.daily_story import review
    from app.services.gold_story.gold_chat import finalize
    from unittest.mock import Mock

    issues = [
        {"lines": [1, 2], "kind": "重复", "desc": "重复对白"},
        {"lines": [1], "kind": "称谓", "desc": "称谓错误"},
    ]
    monkeypatch.setattr(review, "collect_export_blocking_local_issues", lambda c: issues)
    fix = Mock()
    semantic = Mock()
    monkeypatch.setattr(review, "run_export_semantic_review", semantic)
    with pytest.raises(GoldChatAcceptanceBlocked):
        finalize.run_gold_chat_final_acceptance_with_semantic_repair(
            _story([]), {}, sid="TEST", st_final="N", banned=[], mom_max=1,
            source_type="field", attach_score=lambda c, r: c, gate_score=lambda c: 80,
            normalize_chat=lambda c: c, fix_llm=fix, validate_chat=lambda c: None,
        )
    fix.assert_not_called()
    semantic.assert_not_called()


def _missing_beat_exc(line_no: int, beat: int, speaker: str, intent: str):
    return GoldChatSemanticBlocked(
        f"终检语义硬伤：第[{line_no}]句·缺前提：测试",
        issues=[
            {
                "lines": [line_no],
                "kind": "缺前提",
                "desc": "结果句依赖的事件前文没交代",
                "fix": "先把缺失事件说出来",
                "missing_beat": {"beat": beat, "speaker": speaker, "intent": intent},
            }
        ],
    )


def test_final_acceptance_skips_seed_premise_when_speaker_already_present(monkeypatch):
    """说话人已开过口却仍缺某拍 → 该 seed 素材不可用，禁止本地把原文硬塞回对白。

    #138 实测：ASR/OCR 乱码 seed 行因「缺前提」被本地补回对白，随即被判语病，
    修稿预算被反复烧光。判据只用「整场缺席」这一抽象事实，不看具体乱码词：
    生成端读过整条 seed 却没写这一拍，就意味着它判断这条素材不可用。
    """
    from app.services.daily_story import review
    from app.services.gold_story.gold_chat import finalize
    from app.services.gold_story.gold_chat.repair import GoldChatRepairBudget

    dialogue = [
        {"speaker": "妈妈", "line": "这盘饺子好不好吃呀？"},
        {"speaker": "灿灿", "line": "这话我可有点不信，你别蒙我。"},
        {"speaker": "昭昭", "line": "难吃无比，我没改口。"},
        {"speaker": "妈妈", "line": "那你就不能祝我像公主？"},
        {"speaker": "昭昭", "line": "她还没现出原形呢。"},
        {"speaker": "妈妈", "line": "行吧，服了。"},
    ]
    dialogue_seed = [
        {"speaker": "妈妈", "intent": "这盘饺子好不好吃呀"},
        {"speaker": "灿灿", "intent": "这话我可有点不信，你别蒙我"},
        {"speaker": "昭昭", "intent": "难吃无比，我没改口"},
        {"speaker": "灿灿", "intent": "行，那我就等着看你怎么办"},
        {"speaker": "昭昭", "intent": "她还没现出原形呢"},
        {"speaker": "妈妈", "intent": "行吧，服了"},
    ]
    calls = {"semantic": 0, "fix": 0}

    def semantic(_theme, chat, **_kwargs):
        calls["semantic"] += 1
        lines = [str(item.get("line") or "") for item in chat["dialogue"]]
        assert not any("等着看你怎么办" in ln for ln in lines), (
            "已开口说话人的 seed 拍不得被本地硬塞回对白"
        )
        if calls["semantic"] == 1:
            raise _missing_beat_exc(3, 4, "灿灿", "行，那我就等着看你怎么办")
        return ExportSemanticReviewResult(completed=True)

    def fix(story, _feedback, **_kwargs):
        calls["fix"] += 1
        return dict(story)

    monkeypatch.setattr(review, "collect_export_blocking_local_issues", lambda _s: [])
    monkeypatch.setattr(review, "run_export_semantic_review", semantic)
    budget = GoldChatRepairBudget(max_repairs=1)

    finalize.run_gold_chat_final_acceptance_with_semantic_repair(
        _story(dialogue),
        {},
        sid="TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, _r: c,
        gate_score=lambda _c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fix,
        validate_chat=lambda _c: None,
        repair_budget=budget,
        dialogue_seed=dialogue_seed,
    )

    assert calls["fix"] == 1, "该拍应进入带反馈修稿，而不是本地补回 seed 原文"


def test_semantic_repair_allows_one_missing_beat_insertion():
    """缺拍只靠改故障行补不出前提，应放行「补拍一行」并保留其余全部原行。"""
    from app.services.gold_story.gold_chat.finalize import (
        _apply_semantic_missing_beat_insertion,
        _semantic_repair_target_lines,
    )

    original = {
        "story_type": "K",
        "gold_beat_chain": [
            {"beat": 5, "speaker": "爸爸", "addressee": "灿灿", "intent": "被推趔趄"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "昭昭", "line": "你从沙发上跳下来就抢。"},
            {"speaker": "爸爸", "line": "看这招，昭昭无影脚。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
        ],
    }
    exc = _missing_beat_exc(4, 5, "爸爸", "被推趔趄")
    lifted = {
        "story_type": "K",
        "gold_beat_chain": original["gold_beat_chain"],
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "昭昭", "line": "你从沙发上跳下来就抢。"},
            {"speaker": "爸爸", "line": "看这招，昭昭无影脚。"},
            {"speaker": "灿灿", "line": "谁让你解说，我推你一下！"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
        ],
    }
    out, changed = _apply_semantic_missing_beat_insertion(
        original,
        lifted,
        exc,
        target_lines=_semantic_repair_target_lines(exc),
        st_final="K",
        normalize_chat=lambda c: c,
    )
    assert changed is True
    assert len(out["dialogue"]) == len(original["dialogue"]) + 1
    # 原行逐字保留（补行之外不动任何一行）
    assert out["dialogue"][:3] == original["dialogue"][:3]
    assert out["dialogue"][4] == original["dialogue"][3]
    # 补行落在故障行（第4句）之前
    assert out["dialogue"][3] == {
        "speaker": "灿灿",
        "line": "谁让你解说，我推你一下！",
    }


def test_semantic_repair_insert_keeps_target_edits_after_insert_point():
    """补行插在目标行之前时，目标行改写须取右移后的那一行，不得抄到补行文本。"""
    from app.services.gold_story.gold_chat.finalize import (
        _apply_semantic_missing_beat_insertion,
        _semantic_repair_target_lines,
    )

    original = {
        "story_type": "K",
        "gold_beat_chain": [
            {"beat": 5, "speaker": "爸爸", "addressee": "灿灿", "intent": "被推趔趄"},
        ],
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "昭昭", "line": "你从沙发上跳下来就抢。"},
            {"speaker": "爸爸", "line": "看这招，昭昭无影脚。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
        ],
    }
    # 最早故障行=4；补行插在下标2（第3句之前）
    exc = _missing_beat_exc(4, 5, "爸爸", "被推趔趄")
    lifted = {
        "story_type": "K",
        "gold_beat_chain": original["gold_beat_chain"],
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "昭昭", "line": "你从沙发上跳下来就抢。"},
            {"speaker": "灿灿", "line": "谁让你解说，我推你一下！"},
            {"speaker": "爸爸", "line": "看这招，昭昭无影脚。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲，屁股沾了灰呀。"},
        ],
    }
    out, changed = _apply_semantic_missing_beat_insertion(
        original,
        lifted,
        exc,
        target_lines=_semantic_repair_target_lines(exc),
        st_final="K",
        normalize_chat=lambda c: c,
    )
    assert changed is True
    assert len(out["dialogue"]) == 5
    # 补行只出现一次
    texts = [x["line"] for x in out["dialogue"]]
    assert texts.count("谁让你解说，我推你一下！") == 1
    # 未点名的第1、2句原样保留
    assert out["dialogue"][0] == original["dialogue"][0]
    assert out["dialogue"][1] == original["dialogue"][1]
    # 目标行（第4句）取到右移后的改写，且 speaker 沿用原行
    assert out["dialogue"][4] == {
        "speaker": "昭昭",
        "line": "爸爸摔了个屁股蹲，屁股沾了灰呀。",
    }
    # 第3句（原样，非目标行）仍是爸爸那句，没被补行顶掉
    assert out["dialogue"][3] == original["dialogue"][2]


def test_missing_beat_expected_speakers_include_addressee():
    """受动拍（爸爸·被推）的补前提行由施动方（addressee=灿灿）说出也应放行。"""
    from app.services.gold_story.gold_chat.finalize import (
        _missing_beat_expected_speakers,
    )

    chat = {
        "gold_beat_chain": [
            {"beat": 5, "speaker": "爸爸", "addressee": "灿灿", "intent": "被推趔趄"},
        ],
    }
    speakers = _missing_beat_expected_speakers(
        [{"beat": 5, "speaker": "爸爸", "intent": "被推趔趄"}], chat=chat
    )
    assert speakers == {"爸爸", "灿灿"}


def test_semantic_repair_rejects_speaker_not_in_dialogue():
    """契约里的说话人在本篇对白里没开口时，不得放行其补行。"""
    from app.services.gold_story.gold_chat.finalize import (
        _apply_semantic_missing_beat_insertion,
        _semantic_repair_target_lines,
    )

    original = {
        "story_type": "K",
        "gold_beat_chain": [{"beat": 5, "speaker": "妈妈", "intent": "被推趔趄"}],
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
        ],
    }
    exc = _missing_beat_exc(2, 5, "妈妈", "被推趔趄")
    lifted = {
        "story_type": "K",
        "gold_beat_chain": original["gold_beat_chain"],
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "妈妈", "line": "你推你爸爸干嘛。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
        ],
    }
    out, changed = _apply_semantic_missing_beat_insertion(
        original,
        lifted,
        exc,
        target_lines=_semantic_repair_target_lines(exc),
        st_final="K",
        normalize_chat=lambda c: c,
    )
    assert changed is False
    assert out["dialogue"] == original["dialogue"]


def test_semantic_repair_rejects_narration_insertion():
    """补拍行不得写成旁白；旁白直接拒绝，退回冻结域修稿。"""
    from app.services.gold_story.gold_chat.finalize import (
        _apply_semantic_missing_beat_insertion,
        _semantic_repair_target_lines,
    )

    original = {
        "story_type": "K",
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
        ],
    }
    exc = _missing_beat_exc(2, 5, "爸爸", "被推趔趄")
    lifted = {
        "story_type": "K",
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "灿灿", "line": "灿灿一把推得爸爸趔趄。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
        ],
    }
    out, changed = _apply_semantic_missing_beat_insertion(
        original,
        lifted,
        exc,
        target_lines=_semantic_repair_target_lines(exc),
        st_final="K",
        normalize_chat=lambda c: c,
    )
    assert changed is False
    assert out["dialogue"] == original["dialogue"]


def test_semantic_repair_rejects_insert_after_failure_line():
    """补行插在故障行之后就构不成因果，必须拒绝。"""
    from app.services.gold_story.gold_chat.finalize import (
        _apply_semantic_missing_beat_insertion,
        _semantic_repair_target_lines,
    )

    original = {
        "story_type": "K",
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
            {"speaker": "灿灿", "line": "谁让你不好好劝架。"},
        ],
    }
    exc = _missing_beat_exc(2, 5, "爸爸", "被推趔趄")
    lifted = {
        "story_type": "K",
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
            {"speaker": "灿灿", "line": "谁让你不好好劝架。"},
            {"speaker": "灿灿", "line": "谁让你解说，我推你一下！"},
        ],
    }
    out, changed = _apply_semantic_missing_beat_insertion(
        original,
        lifted,
        exc,
        target_lines=_semantic_repair_target_lines(exc),
        st_final="K",
        normalize_chat=lambda c: c,
    )
    assert changed is False
    assert out["dialogue"] == original["dialogue"]


def test_semantic_repair_rejects_insert_with_wrong_speaker():
    """补行说话人须是该缺失 beat 的说话人。"""
    from app.services.gold_story.gold_chat.finalize import (
        _apply_semantic_missing_beat_insertion,
        _semantic_repair_target_lines,
    )

    original = {
        "story_type": "K",
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
        ],
    }
    exc = _missing_beat_exc(2, 5, "爸爸", "被推趔趄")
    lifted = {
        "story_type": "K",
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "妈妈", "line": "你别推你爸爸行不行。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
        ],
    }
    out, changed = _apply_semantic_missing_beat_insertion(
        original,
        lifted,
        exc,
        target_lines=_semantic_repair_target_lines(exc),
        st_final="K",
        normalize_chat=lambda c: c,
    )
    assert changed is False
    assert out["dialogue"] == original["dialogue"]


def test_semantic_repair_prompt_states_insert_permission_only_for_missing_beat():
    """只有缺拍类硬伤才在提示词里放行插行；普通语义瑕疵仍冻结行数。"""
    from app.services.gold_story.gold_chat.finalize import (
        _build_export_repair_feedback,
    )

    chat = {
        "story_type": "K",
        "dialogue": [
            {"speaker": "灿灿", "line": "我先拿到的三轮车。"},
            {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀。"},
        ],
    }
    gap_prompt = _build_export_repair_feedback(
        _missing_beat_exc(2, 5, "爸爸", "被推趔趄"),
        chat,
        {"title": "测试"},
        st_final="K",
        mom_max=1,
    )
    assert "缺拍补行" in gap_prompt
    assert "beat=5" in gap_prompt
    assert "不得增删、合并、拆分对白" in gap_prompt

    grammar = GoldChatSemanticBlocked(
        "终检语义硬伤：第[2]句·语病：指代不清",
        issues=[{"lines": [2], "kind": "语病", "desc": "指代不清"}],
    )
    grammar_prompt = _build_export_repair_feedback(
        grammar, chat, {"title": "测试"}, st_final="K", mom_max=1
    )
    assert "缺拍补行" not in grammar_prompt
    assert "不得增删、合并、拆分对白" in grammar_prompt


def _cap_fixture(n_rows: int):
    """造一篇 n_rows 行的 K 稿，末句缺前提；缺失拍 5 的说话人已开口。"""
    filler = [
        {"speaker": "灿灿", "line": f"我先拿到的三轮车，第{i}遍问他。"}
        for i in range(n_rows - 2)
    ]
    rows = [
        *filler,
        {"speaker": "爸爸", "line": "你俩别抢了，我看着都头晕。"},
        {"speaker": "昭昭", "line": "爸爸摔了个屁股蹲呀，屁股都沾灰了。"},
    ]
    assert len(rows) == n_rows
    original = {"story_type": "K", "dialogue": rows}
    exc = _missing_beat_exc(n_rows, 5, "爸爸", "被推趔趄")
    lifted = {
        "story_type": "K",
        "dialogue": [
            *rows[:-1],
            {"speaker": "爸爸", "line": "她推我一下，我站都站不稳。"},
            rows[-1],
        ],
    }
    return original, lifted, exc


def test_semantic_insertion_cap_matches_validator_for_k():
    """乙的插入上限必须与校验层一致：K 类同样享受 +2，否则合法 K 稿不许补拍。"""
    from app.services.gold_story.gold_chat.finalize import (
        _apply_semantic_missing_beat_insertion,
        _semantic_repair_target_lines,
    )
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MAX

    # 已到普通上限 24 行的 K 稿：校验层允许到 26，故仍应允许补拍
    original, lifted, exc = _cap_fixture(CHAT_LINE_COUNT_MAX)
    out, changed = _apply_semantic_missing_beat_insertion(
        original,
        lifted,
        exc,
        target_lines=_semantic_repair_target_lines(exc),
        st_final="K",
        normalize_chat=lambda c: c,
    )
    assert changed is True
    assert len(out["dialogue"]) == CHAT_LINE_COUNT_MAX + 1


def test_semantic_insertion_rejects_over_cap_even_for_k():
    """超过 K 类上限（26）时必须拒绝补行，不得无界膨胀。"""
    from app.services.gold_story.gold_chat.finalize import (
        _apply_semantic_missing_beat_insertion,
        _semantic_repair_target_lines,
    )
    from app.services.gold_story.scene import CHAT_LINE_COUNT_MAX

    # 刚好压线 26 行：再补一行就是 27，超 K 上限，必须拒绝
    original, lifted, exc = _cap_fixture(CHAT_LINE_COUNT_MAX + 2)
    out, changed = _apply_semantic_missing_beat_insertion(
        original,
        lifted,
        exc,
        target_lines=_semantic_repair_target_lines(exc),
        st_final="K",
        normalize_chat=lambda c: c,
    )
    assert changed is False
    assert len(out["dialogue"]) == CHAT_LINE_COUNT_MAX + 2


def test_repeated_missing_beat_insertion_is_not_retried(monkeypatch):
    """同一缺拍连续两轮仍被判缺 → 属契约/生成根因，禁止反复插行。"""
    from app.services.daily_story import review as review_mod
    from app.services.gold_story.gold_chat import finalize
    from unittest.mock import Mock

    beat_exc = _missing_beat_exc(2, 5, "爸爸", "被推趔趄")
    monkeypatch.setattr(
        review_mod, "run_export_semantic_review", Mock(side_effect=beat_exc)
    )
    # 冻结域永远改不动 → 每轮都会考虑走乙
    monkeypatch.setattr(
        finalize, "_sanitize_semantic_scoped_repair",
        lambda *a, **k: (dict(a[0]), False),
    )
    insert_attempts: list[int] = []
    real_apply = finalize._apply_semantic_missing_beat_insertion

    def _spy_apply(*args, **kwargs):
        insert_attempts.append(1)
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(finalize, "_apply_semantic_missing_beat_insertion", _spy_apply)
    with pytest.raises(GoldChatAcceptanceBlocked):
        finalize.run_gold_chat_final_acceptance_with_semantic_repair(
            _story([{"speaker": "灿灿", "line": "我先拿到的三轮车。"}]),
            {"title": "测试"},
            sid="TEST",
            st_final="K",
            banned=[],
            mom_max=1,
            source_type="field",
            attach_score=lambda c, r: c,
            gate_score=lambda c: 80,
            normalize_chat=lambda c: c,
            fix_llm=Mock(side_effect=lambda *a, **k: {"dialogue": []}),
            validate_chat=lambda c: None,
        )
    # 第一轮允许尝试补拍；同拍第二轮必须被拦，不能每轮都插
    assert len(insert_attempts) == 1


def _k_b_orphan_accept_dialogue() -> list[dict[str, str]]:
    """K-B 稿：末段接住句与更早某句逐字重复（孤儿句在前、承载句在后）。"""
    lines = [
        ("灿灿", "这辆三轮车是我先拿到的，你别动！"),
        ("昭昭", "行啊！一起玩！"),
        ("灿灿", "我还没骑够呢，该轮到我骑了！"),
        ("昭昭", "你昨天明明骑了一下午呢。"),
        ("爸爸", "我不掺和，你们自己商量。"),
        ("灿灿", "那你先松手，我骑一圈就下来。"),
        ("昭昭", "你再说一遍试试，我就是不服！"),
        ("灿灿", "还玩不玩？一起吧。"),
        ("昭昭", "行啊！一起玩！"),
        ("爸爸", "那个碗还端着呢，别洒了。"),
    ]
    return [{"speaker": sp, "line": ln} for sp, ln in lines]


def test_duplicate_orphan_line_picks_line_that_keeps_k_b_tail():
    """K-B 重复组里「删掉后不变量仍成立」的孤儿句才是安全改写目标。"""
    from app.services.gold_story.gold_chat.finalize import _duplicate_orphan_line

    chat = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "dialogue": _k_b_orphan_accept_dialogue(),
    }
    # 删第 9 句（承载句）后只剩邀约 → 不成立；删第 2 句（孤儿句）不变量保持
    assert _duplicate_orphan_line([2, 9], chat) == 2


def test_duplicate_orphan_line_skips_non_k_b_and_broken_tail():
    """非 K-B、或末段本就没落位、或两个方向都成立时，不做特殊选择。"""
    from app.services.gold_story.gold_chat.finalize import _duplicate_orphan_line

    rows = _k_b_orphan_accept_dialogue()
    assert _duplicate_orphan_line([2, 9], {"k_close_mode": "K_A_PARENT_FAIL_STALEMATE", "dialogue": rows}) is None
    assert _duplicate_orphan_line([2, 9], {"k_close_mode": "K_B_CHILD_SELF_RESOLVE", "dialogue": rows[:8]}) is None
    assert _duplicate_orphan_line([2, 9], None) is None


def test_duplicate_repair_target_prefers_orphan_for_k_b():
    """重复定点范围给孤儿句：改它既消重又保住末段收束。"""
    from app.services.gold_story.gold_chat.finalize import (
        _duplicate_repair_target_lines,
    )

    chat = {
        "story_type": "K",
        "k_close_mode": "K_B_CHILD_SELF_RESOLVE",
        "dialogue": _k_b_orphan_accept_dialogue(),
    }
    exc = GoldChatLocalDuplicateBlocked(
        "终检本地硬伤：第[2, 9]句·重复",
        issues=[{"kind": "重复", "lines": [2, 9], "desc": "两句逐字重复"}],
    )
    assert _duplicate_repair_target_lines(exc, chat) == {2}
    # 非 K-B 走默认：改较后那一句
    assert _duplicate_repair_target_lines(exc, {"dialogue": chat["dialogue"]}) == {9}


def test_final_acceptance_premise_align_runs_before_semantic_budget(monkeypatch):
    """seed 里整场缺席的角色（收尾家长反应拍）在终检前确定性补回，不烧语义预算。

    终检的「缺前提」只在后文引用了该前提时才触发，无人引用的收尾拍要靠拍落地
    覆盖检查主动补回（专家裁决）；补拍发生在语义审读之前，所以预算为零时也应能过。
    """
    from app.services.daily_story import review
    from app.services.gold_story.gold_chat import finalize
    from app.services.gold_story.gold_chat.repair import GoldChatRepairBudget

    dialogue = [
        {"speaker": "灿灿", "line": "我先骑，你松手！"},
        {"speaker": "昭昭", "line": "我还没骑完呢。"},
        {"speaker": "灿灿", "line": "爸你站哪边的，倒是拉架啊！"},
        {"speaker": "昭昭", "line": "你别喊爸，他在解说呢。"},
        {"speaker": "灿灿", "line": "一起玩吧。"},
        {"speaker": "昭昭", "line": "行啊！一起玩！"},
    ]
    dialogue_seed = [
        {"speaker": "灿灿", "intent": "我先骑，你松手"},
        {"speaker": "昭昭", "intent": "我还没骑完呢"},
        {"speaker": "爸爸", "intent": "看这招，昭昭无影脚"},
        {"speaker": "灿灿", "intent": "你站哪边的"},
        {"speaker": "灿灿", "intent": "一起玩吧"},
        {"speaker": "昭昭", "intent": "行啊，一起玩"},
    ]
    seen: list[list[str]] = []

    def local(story):
        return []

    def semantic(theme, chat, **kwargs):
        seen.append([str(item.get("line") or "") for item in chat["dialogue"]])
        return ExportSemanticReviewResult(completed=True)

    def fix(story, feedback, **kwargs):  # pragma: no cover - 不应被调用
        raise AssertionError("整场缺席的拍必须先走覆盖补拍")

    monkeypatch.setattr(review, "collect_export_blocking_local_issues", local)
    monkeypatch.setattr(review, "run_export_semantic_review", semantic)
    budget = GoldChatRepairBudget(max_repairs=0)

    result, score = finalize.run_gold_chat_final_acceptance_with_semantic_repair(
        _story(dialogue),
        {},
        sid="TEST",
        st_final="N",
        banned=[],
        mom_max=1,
        source_type="field",
        attach_score=lambda c, r: c,
        gate_score=lambda c: 80,
        normalize_chat=lambda c: c,
        fix_llm=fix,
        validate_chat=lambda c: None,
        repair_budget=budget,
        dialogue_seed=dialogue_seed,
    )

    assert len(seen) == 1
    assert seen[0][2].startswith("看这招")
    assert seen[0][3].startswith("爸你站哪边的")
    assert score == 80
    assert budget.used == 0


def _n_adjacent_candidate() -> list[dict[str, str]]:
    """N 稿：两个旁观拍相邻落地 → 同一个孩子连说（#138 真实形态的抽象版）。"""
    lines = [
        ("妈妈", "昭昭，这盘饺子好不好吃呀？"),
        ("昭昭", "难吃无比，我没改口。"),
        ("灿灿", "这话我可有点不信，你别蒙我。"),
        ("灿灿", "行，那我就等着看你怎么办。"),
        ("昭昭", "妈妈像一个暴踩的老虎。"),
        ("妈妈", "你就不能祝我像一个公主？"),
        ("昭昭", "她还没现出原形呢。"),
        ("妈妈", "行吧，服了。"),
    ]
    return [{"speaker": sp, "line": ln} for sp, ln in lines]


def test_terminal_adjacency_close_runs_before_gate_and_saves_budget(monkeypatch):
    """唯一扣分项是机器可修的连说时，先拆连说再评分，不烧 LLM 修稿预算。

    #138 实测：结构闸门只剩「存在同人连说」-15 就判 65，两轮 LLM 修稿都花在
    人写的语义上，最后报「修稿预算耗尽 stage=final_acceptance；structure_score:65」。
    """
    from app.services.daily_story.quality import _has_consecutive_sibling
    from app.services.gold_story.gold_chat import finalize
    from app.services.gold_story.gold_chat.repair import GoldChatRepairBudget

    def attach(chat, _row):
        out = dict(chat)
        score = 65 if _has_consecutive_sibling(out["dialogue"]) else 80
        out["quality"] = {"structure_score": score, "score": score}
        return out

    def gate(chat):
        score = int((chat.get("quality") or {}).get("structure_score") or 0)
        if score < 75:
            raise ValueError(f"structure_score:{score}")
        return score

    def fix(*_args, **_kwargs):  # pragma: no cover - 不该被调用
        raise AssertionError("行序可机械修复，不该烧 LLM 修稿预算")

    monkeypatch.setattr(
        finalize,
        "run_gold_chat_final_acceptance",
        lambda chat, row, sid=None, **_k: chat,
    )
    budget = GoldChatRepairBudget(max_repairs=0)
    out, score = finalize.run_gold_chat_final_acceptance_with_semantic_repair(
        {"story_type": "N", "dialogue": _n_adjacent_candidate()},
        {"title": "测试"},
        sid="TEST",
        st_final="N",
        banned=[],
        mom_max=3,
        source_type="field",
        attach_score=attach,
        gate_score=gate,
        normalize_chat=lambda c: c,
        fix_llm=fix,
        validate_chat=lambda c: None,
        repair_budget=budget,
    )

    assert not _has_consecutive_sibling(out["dialogue"])
    assert score == 80
    assert budget.used == 0


def test_repair_exhaustion_stores_gate_snapshot_quality(monkeypatch):
    """预算耗尽落库的候选必须带闸门时刻的分数，而不是上一次的旧 quality。"""
    from app.services.gold_story.gold_chat import finalize
    from app.services.gold_story.gold_chat.repair import (
        GoldChatRepairBudget,
        GoldChatRepairExhausted,
    )

    def attach(chat, _row):
        out = dict(chat)
        out["quality"] = {
            "structure_score": 65,
            "score": 65,
            "structure_cons": ["存在同人连说"],
        }
        return out

    def gate(_chat):
        raise ValueError("structure_score:65")

    def fix(*_args, **_kwargs):  # pragma: no cover - 预算为 0 不该调用
        raise AssertionError("预算已耗尽，不得进入 LLM 修稿")

    chat = {
        "story_type": "K",
        "dialogue": _n_adjacent_candidate(),
        "quality": {"structure_score": 80, "score": 80, "structure_cons": []},
    }
    budget = GoldChatRepairBudget(max_repairs=0)
    with pytest.raises(GoldChatRepairExhausted) as caught:
        finalize.run_gold_chat_final_acceptance_with_semantic_repair(
            chat,
            {"title": "测试"},
            sid="TEST",
            st_final="K",
            banned=[],
            mom_max=1,
            source_type="field",
            attach_score=attach,
            gate_score=gate,
            normalize_chat=lambda c: c,
            fix_llm=fix,
            validate_chat=lambda c: None,
            repair_budget=budget,
        )

    pending = caught.value.candidate["quality"]
    assert pending["structure_score"] == 65
    assert pending["structure_cons"] == ["存在同人连说"]
    assert pending["review_status"] == "review_pending"
    assert "structure_score:65" in pending["review_failure_reason"]


def test_repair_exhaustion_rescores_candidate_that_failed_before_gate(monkeypatch):
    """校验/覆盖先失败时也要临门补算一次分，别把上一次的旧 quality 落成人审依据。"""
    from app.services.gold_story.gold_chat import finalize
    from app.services.gold_story.gold_chat.repair import (
        GoldChatRepairBudget,
        GoldChatRepairExhausted,
    )

    def attach(chat, _row):
        out = dict(chat)
        out["quality"] = {"structure_score": 72, "score": 72}
        return out

    def gate(_chat):  # pragma: no cover - 校验已失败
        raise AssertionError("校验没过就不该走到结构闸门")

    def validate(_chat):
        raise ValueError("正文总字数须≥240，当前220")

    chat = {
        "story_type": "K",
        "dialogue": _n_adjacent_candidate(),
        "quality": {"structure_score": 80, "score": 80},
    }
    budget = GoldChatRepairBudget(max_repairs=0)
    with pytest.raises(GoldChatRepairExhausted) as caught:
        finalize.run_gold_chat_final_acceptance_with_semantic_repair(
            chat,
            {"title": "测试"},
            sid="TEST",
            st_final="K",
            banned=[],
            mom_max=1,
            source_type="field",
            attach_score=attach,
            gate_score=gate,
            normalize_chat=lambda c: c,
            fix_llm=lambda *_a, **_k: {"dialogue": []},
            validate_chat=validate,
            repair_budget=budget,
        )

    assert caught.value.candidate["quality"]["structure_score"] == 72


def test_perbeat_final_acceptance_preserves_dialogue_without_inserting_seed_or_reassigning_roles(
    monkeypatch,
):
    import copy

    from app.services.gold_story.gold_chat import finalize

    monkeypatch.setenv("GOLD_CHAT_PERBEAT", "1")
    chat = {
        "story_type": "N",
        "dialogue": [
            {"speaker": "妈妈", "line": "今天为什么舍得夸我好看？"},
            {"speaker": "昭昭", "line": "因为你刚才瞪我那一眼，像只老虎。"},
        ],
    }
    original = copy.deepcopy(chat)
    row = {
        "payload": {
            "scene_contract": {
                "beat_chain": [
                    {"beat": 1, "speaker": "妈妈", "intent": "狐疑追问"},
                    {"beat": 2, "speaker": "昭昭", "intent": "说妈妈像老虎"},
                ],
            },
            "dialogue_seed": [
                {"speaker": "妈妈", "line": "你再盯着我看，我可就瞪你。"},
            ],
        },
    }
    with (
        patch("app.services.gold_story.gold_chat.patch.apply_opening_causality_local_patch") as opening,
        patch("app.services.gold_story.gold_chat.validate.apply_n_beat_role_speaker_align") as roles,
    ):
        result = finalize.apply_final_acceptance_local_patches(chat, row)
        repeated = finalize.apply_final_acceptance_local_patches(result, row)
    opening.assert_not_called()
    roles.assert_not_called()
    assert result == repeated == original
    assert chat == original


def test_perbeat_final_acceptance_still_rejects_missing_opening_beat(monkeypatch):
    monkeypatch.setenv("GOLD_CHAT_PERBEAT", "1")
    chat = _story([
        {"speaker": "昭昭", "line": "妈，我屁股Q弹，你打一下试试嘛！"},
        {"speaker": "妈妈", "line": "你……我一时接不住话。"},
    ])
    chat["story_type"] = "N"
    row = {
        "payload": {"scene_contract": {
            "beat_chain": _MOM_ZHAO_MOM_OPENING_BEAT, "mom_lines_max": 2,
        }},
    }
    with (
        patch("app.services.gold_story.gold_chat.patch.apply_n_contract_local_patches") as contract,
        patch("app.services.daily_story.review.run_export_semantic_review") as review,
        pytest.raises(GoldChatValidationRepairableError, match="opening_causality"),
    ):
        run_gold_chat_final_acceptance(chat, row, sid="TEST")
    contract.assert_not_called()
    review.assert_not_called()


def test_perbeat_final_acceptance_reviews_original_dialogue_and_keeps_semantic_gate(monkeypatch):
    import copy

    from app.services.daily_story import review

    monkeypatch.setenv("GOLD_CHAT_PERBEAT", "1")
    chat = _story([
        {"speaker": "灿灿", "line": "你今天带伞了吗？"},
        {"speaker": "昭昭", "line": "我早餐吃了鸡蛋。"},
    ])
    chat["story_type"] = "N"
    original = copy.deepcopy(chat["dialogue"])
    issue = {
        "lines": [1, 2], "kind": "接不上",
        "desc": "上一句问带伞，下一句却回答早餐",
        "fix": "让第2句直接回应是否带伞",
        "evidence": [{"line": 1, "quote": "带伞"}, {"line": 2, "quote": "早餐"}],
    }
    monkeypatch.setattr(review, "collect_export_blocking_local_issues", lambda _c: [])
    with (
        patch("app.services.gold_story.gold_chat.patch.apply_n_contract_local_patches") as contract,
        patch.object(review, "run_export_semantic_review", return_value=ExportSemanticReviewResult(
            completed=True, issues=[issue],
        )) as semantic,
        pytest.raises(GoldChatSemanticBlocked) as caught,
    ):
        run_gold_chat_final_acceptance(chat, {"title": "测试"}, sid="TEST")
    contract.assert_not_called()
    assert semantic.call_args.args[1]["dialogue"] == original
    assert caught.value.issues == [issue]
    assert chat["dialogue"] == original


# ---------------------------------------------------------------------------
# 逐句线路计划（line plan）：#138「黑面饺子」同型契约
# ---------------------------------------------------------------------------

_LP_CONTRACT = {
    "location": "餐桌",
    "object": "黑面饺子",
    "characters": ["妈妈", "昭昭", "灿灿"],
    "conflict": "昭昭当面嫌饺子难吃，转头夸妈妈，转头说妈妈像老虎",
    "closing_intent": "妈妈举着筷子半天没落下，认栽让昭昭以后说话先打草稿",
    "mom_lines_max": 4,
    "beat_chain": [
        {"beat": 1, "speaker": "妈妈", "intent": "端来黑面饺子问昭昭好不好吃"},
        {"beat": 2, "speaker": "昭昭", "intent": "嫌黑面芯子难吃，又补一句妈妈眉清目秀"},
        {"beat": 3, "speaker": "妈妈", "intent": "狐疑追问今天怎么舍得夸妈妈"},
        {"beat": 4, "speaker": "昭昭", "intent": "一本正经说妈妈像一只暴躁老虎"},
        {"beat": 5, "speaker": "妈妈", "intent": "气笑要求改口夸妈妈像公主"},
        {"beat": 6, "speaker": "昭昭", "intent": "不慌不忙回老虎一吼公主也得现出原形"},
        {"beat": 7, "speaker": "灿灿", "intent": "接不上话，愣住看妈妈"},
        {"beat": 8, "speaker": "妈妈", "intent": "举着筷子半天没落下，认栽让昭昭以后说话先打草稿"},
    ],
}

_LP_VALID_PLAN = [
    {"beat": 1, "speaker": "妈妈", "intent": "问昭昭黑面饺子好不好吃", "addressee": "昭昭"},
    {"beat": 2, "speaker": "昭昭", "intent": "说黑面芯子又苦又涩", "addressee": "妈妈"},
    {"beat": 2, "speaker": "灿灿", "intent": "追问昭昭那还夸妈妈干什么", "addressee": "昭昭"},
    {"beat": 2, "speaker": "昭昭", "intent": "说因为妈妈眉清目秀", "addressee": "灿灿"},
    {"beat": 3, "speaker": "妈妈", "intent": "狐疑问她今天怎么舍得夸人", "addressee": "昭昭"},
    {"beat": 4, "speaker": "昭昭", "intent": "说妈妈像只暴躁老虎", "addressee": "妈妈"},
    {"beat": 5, "speaker": "灿灿", "intent": "替妈妈不平说昭昭当面夸背后损", "addressee": "昭昭"},
    {"beat": 5, "speaker": "妈妈", "intent": "让昭昭改口夸妈妈像公主", "addressee": "昭昭"},
    {"beat": 6, "speaker": "昭昭", "intent": "说老虎一吼公主也得现原形", "addressee": "妈妈"},
    {"beat": 7, "speaker": "灿灿", "intent": "说这嘴没人管得住", "addressee": "妈妈"},
    {"beat": 7, "speaker": "昭昭", "intent": "说自己讲的是实话", "addressee": "灿灿"},
    {"beat": 8, "speaker": "妈妈", "intent": "让昭昭以后说话先打草稿", "addressee": "昭昭"},
]


def test_line_plan_capacity_accepts_canonical_contract():
    from app.services.gold_story.gold_chat.expand import _line_plan_capacity

    assert _line_plan_capacity(
        _LP_CONTRACT, _LP_CONTRACT["beat_chain"], target_lines=12
    ) == []


def test_line_plan_capacity_rejects_target_beyond_contract_capacity():
    from app.services.gold_story.gold_chat.expand import _line_plan_capacity

    # 8 拍契约的容量上界 = 家长拍 4×2 + 孩子拍 3×5 + 静场 1 = 24。
    errors = _line_plan_capacity(
        _LP_CONTRACT, _LP_CONTRACT["beat_chain"], target_lines=30
    )
    assert errors and "排不满" in errors[0]


def test_validate_line_plan_accepts_alternating_plan():
    from app.services.gold_story.gold_chat.expand import _validate_line_plan

    assert _validate_line_plan(
        _LP_VALID_PLAN,
        scene_contract=_LP_CONTRACT,
        beat_chain=_LP_CONTRACT["beat_chain"],
        target_lines=12,
    ) == []


def test_validate_line_plan_rejects_mom_over_budget():
    from app.services.gold_story.gold_chat.expand import _validate_line_plan

    # 契约只给妈妈 2 拍、2 句额度（家长额度会按拍数兜底抬额，故用拍数锁死），
    # 计划却塞了 3 句妈妈，必须被机检挡回。
    contract = {
        # 爸爸在场：否则「唯一在场家长」规则会把家长总预算让给妈妈，
        # 妈妈额度被抬到 3 句，额度卡就测不出来了。
        "characters": ["妈妈", "爸爸", "昭昭", "灿灿"],
        "mom_lines_max": 2,
        "beat_chain": [
            {"beat": 1, "speaker": "妈妈", "intent": "问昭昭要不要再吃一碗"},
            {"beat": 2, "speaker": "昭昭", "intent": "说黑面芯子苦"},
            {"beat": 3, "speaker": "妈妈", "intent": "让昭昭把话说完"},
        ],
    }
    plan = [
        {"beat": 1, "speaker": "妈妈", "intent": "问昭昭要不要再吃一碗"},
        {"beat": 2, "speaker": "昭昭", "intent": "说黑面芯子苦"},
        {"beat": 2, "speaker": "妈妈", "intent": "追问他到底想说什么"},
        {"beat": 2, "speaker": "灿灿", "intent": "说昭昭刚才还夸过妈妈"},
        {"beat": 3, "speaker": "妈妈", "intent": "让昭昭把话说完"},
    ]
    errors = _validate_line_plan(
        plan,
        scene_contract=contract,
        beat_chain=contract["beat_chain"],
        target_lines=5,
    )
    assert any("妈妈 3 句" in item for item in errors)


def test_validate_line_plan_rejects_adjacent_same_speaker():
    from app.services.gold_story.gold_chat.expand import _validate_line_plan

    plan = [dict(row) for row in _LP_VALID_PLAN]
    plan[2] = {
        "beat": 2, "speaker": "昭昭", "intent": "反过来说灿灿嘴也快",
        "addressee": "灿灿",
    }
    errors = _validate_line_plan(
        plan,
        scene_contract=_LP_CONTRACT,
        beat_chain=_LP_CONTRACT["beat_chain"],
        target_lines=12,
    )
    assert any("同一说话人" in item for item in errors)


def test_validate_line_plan_rejects_beat_without_owner_speaking():
    from app.services.gold_story.gold_chat.expand import _validate_line_plan

    plan = [dict(row) for row in _LP_VALID_PLAN]
    plan[9] = {
        "beat": 7, "speaker": "妈妈", "intent": "说灿灿别替昭昭打圆场",
        "addressee": "灿灿",
    }
    plan[10] = {
        "beat": 7, "speaker": "昭昭", "intent": "说自己讲的是实话",
        "addressee": "妈妈",
    }
    errors = _validate_line_plan(
        plan,
        scene_contract=_LP_CONTRACT,
        beat_chain=_LP_CONTRACT["beat_chain"],
        target_lines=12,
    )
    assert any("灿灿" in item and "出声" in item for item in errors)


def test_validate_line_plan_rejects_stage_action_intent():
    from app.services.gold_story.gold_chat.expand import _validate_line_plan

    plan = [dict(row) for row in _LP_VALID_PLAN]
    plan[11] = {
        "beat": 8, "speaker": "妈妈", "intent": "举着筷子气得说不出话",
        "addressee": "昭昭",
    }
    errors = _validate_line_plan(
        plan,
        scene_contract=_LP_CONTRACT,
        beat_chain=_LP_CONTRACT["beat_chain"],
        target_lines=12,
    )
    assert any("动作" in item for item in errors)


def test_build_line_plan_retries_with_structural_feedback(monkeypatch):
    from app.services.gold_story.gold_chat import expand

    calls: list[str] = []
    good = {
        "lines": [
            {"i": idx, "intent": row["intent"]}
            for idx, row in enumerate(_LP_VALID_PLAN, 1)
        ]
    }
    # 拍主行（from_beat）的 intent 由骨架写定，模型只填反应/拆句行；
    # 这里故意漏掉第 11 句（反应行）来触发一次带反馈的重试。
    bad = {"lines": [row for row in good["lines"] if row["i"] != 11]}

    def fake_chat_json(system, user, **_kwargs):
        calls.append(user)
        return bad if len(calls) == 1 else good

    monkeypatch.setattr(expand, "_chat_json", fake_chat_json)
    plan = expand._build_line_plan(
        scene_contract=_LP_CONTRACT,
        beat_chain=_LP_CONTRACT["beat_chain"],
        story_raw="妈妈端来黑面饺子，昭昭嫌苦，转头夸妈妈，又补一句像老虎。",
        target_lines=12,
        temperature=0.5,
    )
    assert len(plan) == 12
    assert "不合格" in calls[1]
    assert "第11句缺 intent" in calls[1]


def test_line_plan_slots_marks_reaction_lines_as_filler():
    from app.services.gold_story.gold_chat.expand import _line_plan_slots

    slots = _line_plan_slots(_LP_VALID_PLAN, _LP_CONTRACT["beat_chain"])
    assert slots[0]["function"] == "本拍主句"
    assert slots[0]["is_filler"] is False
    assert slots[2]["is_filler"] is True
    assert slots[2]["beat_id"] == 2


def test_line_plan_skeleton_covers_beats_without_adjacent_duplicates():
    from app.services.gold_story.gold_chat.expand import _line_plan_skeleton

    rows = _line_plan_skeleton(
        _LP_CONTRACT, _LP_CONTRACT["beat_chain"], target_lines=12
    )
    assert len(rows) == 12
    speakers = [row["speaker"] for row in rows]
    assert all(a != b for a, b in zip(speakers, speakers[1:]))
    assert speakers.count("妈妈") <= 5
    covered = {row["beat"] for row in rows}
    assert covered == {1, 2, 3, 4, 5, 6, 7, 8}
    assert rows[-1]["beat"] == 8 and rows[-1]["speaker"] == "妈妈"
    assert rows[0]["beat"] == 1


def test_perbeat_candidate_builds_slots_from_line_plan(monkeypatch):
    from app.services.gold_story.gold_chat import expand

    monkeypatch.delenv("GOLD_CHAT_PERBEAT", raising=False)
    captured: dict = {}

    def fake_plan(**_kwargs):
        return _LP_VALID_PLAN

    def fake_fill(slots, **_kwargs):
        captured["slots"] = slots
        return [
            (slot["speaker"], f"第{i}句台词内容") for i, slot in enumerate(slots, 1)
        ], []

    monkeypatch.setattr(expand, "_build_line_plan", fake_plan)
    monkeypatch.setattr(expand, "_perbeat_fill_slots", fake_fill)
    # 本用例只验「槽来自计划」，篇幅硬卡由其它用例覆盖。
    monkeypatch.setattr(expand, "_validate_expand_chat", lambda data, **_k: data)
    data = expand._generate_perbeat_candidate(
        scene_contract=_LP_CONTRACT,
        beat_chain=_LP_CONTRACT["beat_chain"],
        structure_type="N",
        mom_lines_max=4,
        row={"title": "黑面饺子", "story_raw": "妈妈端来黑面饺子问昭昭好不好吃。"},
    )
    assert [slot["speaker"] for slot in captured["slots"]] == [
        row["speaker"] for row in _LP_VALID_PLAN
    ]
    assert len(data["dialogue"]) == 12
    assert data["setting"] == "餐桌"


def test_terminal_demotes_quirk_on_verbatim_source_line():
    """终检把源故事原句判成语病时降级留档，不拦导出（2026-10）。

    同一句「老虎一吼，公主也得现出原形」在不同轮次里时过时不过：20:21 放行、
    15:04 判「公主不是老虎变的」。作者原句不该由机器判语病。
    """
    from app.services.daily_story.review import ExportSemanticReviewResult
    from app.services.gold_story.gold_chat.finalize import (
        _demote_verbatim_source_quirks,
    )

    quirk = {
        "kind": "语病",
        "lines": [10],
        "desc": "「公主也得现出原形」说不通",
        "evidence": [{"line": 10, "quote": "老虎一吼，公主也得现出原形"}],
    }
    invented = {
        "kind": "语病",
        "lines": [3],
        "desc": "「嘴变快」搭配怪",
        "evidence": [{"line": 3, "quote": "这嘴变得也太快了吧"}],
    }
    review = ExportSemanticReviewResult(
        completed=True, issues=[quirk, invented]
    )
    chat = {"source_raw": "昭昭说老虎一吼，公主也得现出原形，满桌愣住。"}
    out = _demote_verbatim_source_quirks(review, chat)
    assert out.issues == [invented]
    assert len(out.downgraded) == 1
    record = out.downgraded[0]
    assert record["kind"] == "语病"
    assert record["downgrade_reason"] == "source_verbatim"
    assert record["weak_verified"] is True
    assert out.completed is True

    # 没有源故事文本时不做任何降级（宁可拦下，也不瞎放行）。
    plain = ExportSemanticReviewResult(completed=True, issues=[quirk])
    assert _demote_verbatim_source_quirks(plain, {}).issues == [quirk]


def test_line_plan_settles_stage_intent_without_crashing():
    """静态拍的 intent 照抄拍意图时直接收口，不返工、不崩（2026-10 回归）。"""
    from app.services.gold_story.gold_chat.expand import (
        _line_plan_settle_stage_intents,
    )

    beats = [
        {"speaker": "妈妈", "intent": "举着筷子半天没落下，认栽说以后说话先打草稿"},
    ]
    plan = [{"beat": 1, "speaker": "妈妈", "intent": "气笑说两句"}]
    out = _line_plan_settle_stage_intents(plan, beats)
    assert out[0]["intent"] == beats[0]["intent"]


def test_citation_issue_without_attribution_is_demoted():
    """「眉清目秀」这种评价词不算引用；只有「你刚还夸」这类归因才算（2026-10）。

    审读模型会把「眉清目秀也压不住吼声」判成「全篇没人说过眉清目秀」，
    但那是角色自己的判断，不是引用，不该用「引用无据」拦稿。
    """
    from app.services.daily_story.review import ExportSemanticReviewResult
    from app.services.gold_story.gold_chat.finalize import (
        _demote_nonattributed_citation_issues,
    )

    chat = {
        "dialogue": [
            {"speaker": "昭昭", "line": "眉清目秀也压不住吼声，你别不信。"},
            {"speaker": "灿灿", "line": "你刚还夸她眉清目秀，转头就说吼声。"},
        ]
    }
    self_judgement = {
        "kind": "引用无据",
        "lines": [1],
        "desc": "全篇没人说过眉清目秀",
        "evidence": [{"line": 1, "quote": "眉清目秀也压不住吼声"}],
    }
    attribution = {
        "kind": "引用无据",
        "lines": [2],
        "desc": "昭昭没说过眉清目秀",
        "evidence": [{"line": 2, "quote": "你刚还夸她眉清目秀"}],
    }
    review = ExportSemanticReviewResult(
        completed=True, issues=[self_judgement, attribution]
    )
    out = _demote_nonattributed_citation_issues(review, chat)
    assert out.issues == [attribution]
    assert len(out.downgraded) == 1
    assert out.downgraded[0]["downgrade_reason"] == "no_attribution"
