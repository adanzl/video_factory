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
    _validate_export_review_raw,
    collect_escalation_chatter_signals,
    collect_export_blocking_local_issues,
    collect_sibling_address_issues,
    filter_llm_export_blocking_issues,
    parse_review_issues,
    run_export_semantic_review,
)
from app.services.gold_story.gold_chat.finalize import (
    GoldChatAcceptanceBlocked,
    GoldChatAcceptanceIncomplete,
    run_gold_chat_final_acceptance,
)


def _story(dialogue: list[dict[str, str]]) -> dict:
    return {"dialogue": dialogue, "quality": {"structure_score": 76, "score": 76}}


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
        },
    ]
    fabricated = [
        {
            "lines": [1],
            "kind": "矛盾",
            "desc": "第1句说「已经吃完」，与后文矛盾",
            "fix": "",
        },
    ]
    single_char_quote = [
        {
            "lines": [1],
            "kind": "矛盾",
            "desc": "第1句说「无」，与后文冲突",
            "fix": "",
        },
    ]
    assert filter_llm_export_blocking_issues(weak, story) == []
    assert len(filter_llm_export_blocking_issues(strong, story)) == 1
    assert filter_llm_export_blocking_issues(fabricated, story) == []
    assert filter_llm_export_blocking_issues(single_char_quote, story) == []


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
