"""gold_chat 终验：称谓、本地重复、展示标签。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.daily_story.quality import (
    acceptance_tags_for_quality,
    enrich_quality_acceptance_defaults,
    structure_score_of,
)
from app.services.daily_story.review import (
    ExportSemanticReviewResult,
    _normalize_missing_beat,
    _validate_export_review_raw,
    collect_escalation_chatter_signals,
    collect_export_blocking_local_issues,
    collect_sibling_address_issues,
    filter_llm_export_blocking_issues,
    partition_llm_export_blocking_issues,
    parse_review_issues,
    run_export_semantic_review,
)
from app.services.gold_story.gold_chat.convert import (
    patch_break_consecutive_keep_seed,
    patch_gold_chat_consecutive_siblings,
)
from app.services.daily_story.prompts import DAILY_STORY_BODY_CHARS_MIN
from app.services.gold_story.gold_chat.finalize import (
    GoldChatAcceptanceBlocked,
    GoldChatAcceptanceIncomplete,
    GoldChatValidationRepairableError,
    _is_export_repairable,
    run_gold_chat_final_acceptance,
    run_gold_chat_final_acceptance_with_semantic_repair,
)


def _story(dialogue: list[dict[str, str]]) -> dict:
    return {"dialogue": dialogue, "quality": {"structure_score": 76, "score": 76}}


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
    assert (
        _validate_export_review_raw(
            {
                "issues": [
                    {
                        "lines": [1],
                        "kind": "矛盾",
                        "desc": "x",
                        "evidence": [{"line": 2, "quote": "越界"}],
                    },
                ],
            },
            line_count=1,
        )
        is not None
    )
    assert (
        _validate_export_review_raw(
            {
                "issues": [
                    {
                        "lines": [1, 2],
                        "kind": "接不上",
                        "desc": "x",
                        "evidence": [{"line": 1, "quote": "a"}],
                    },
                ],
            },
            line_count=2,
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
    assert "禁止仅为交替发言" in prompts[0]


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
def test_export_review_corrects_invalid_evidence_once(monkeypatch, recovered):
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
    assert len(calls) == 2
    assert "issues[0].evidence" in calls[1]
    assert "姐姐好。" in calls[0] and "姐姐好。" in calls[1]
    assert result.completed is recovered
    if recovered:
        assert len(filter_llm_export_blocking_issues(result.issues, story)) == 1
    else:
        assert "evidence" in result.error


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
