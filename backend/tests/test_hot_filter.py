from app.services.topic.hot_fetcher import HotKeyword
from app.services.topic.hot_filter import (
    _parse_l1_payload,
    filter_hot_keyword_rules,
    filter_hot_keywords,
)
from app.services.topic.hot_llm import extract_items_array


def _kw(keyword: str, **kwargs) -> HotKeyword:
    return HotKeyword(
        keyword=keyword,
        show_name=kwargs.get("show_name", keyword),
        heat_score=kwargs.get("heat_score"),
        word_type=kwargs.get("word_type"),
        source=kwargs.get("source", "test"),
        pos=kwargs.get("pos"),
    )


def test_reject_sports_news():
    result = filter_hot_keyword_rules(_kw("埃及3-1战胜新西兰"))
    assert not result.accepted


def test_reject_game_promo():
    result = filter_hot_keyword_rules(_kw("崩坏因缘精灵最新实机"))
    assert not result.accepted


def test_accept_science_life_keyword():
    result = filter_hot_keyword_rules(_kw("空调怎么开最省电"))
    assert result.accepted
    assert result.mode == "direct"


def test_rules_reject_expand_candidate_without_llm():
    result = filter_hot_keyword_rules(_kw("家长眼里的不同高考分数"))
    assert not result.accepted
    assert "LLM" in result.reason


def test_llm_expand_gaokao_in_mock_mode(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "mock_mode", True)
    kept, _rejected = filter_hot_keywords([_kw("家长眼里的不同高考分数")], use_llm=True)
    assert len(kept) == 1
    assert kept[0].mode == "expand"


def test_reject_entertainment():
    result = filter_hot_keyword_rules(_kw("怎么说我不爱你神级舞台"))
    assert not result.accepted


def test_reject_esports_how_to():
    result = filter_hot_keyword_rules(_kw("猎鹰如何拿下Major冠军决胜图"))
    assert not result.accepted


def test_reject_topic_without_science_signal():
    result = filter_hot_keyword_rules(_kw("某个话题", word_type=11))
    assert not result.accepted


def test_reject_live_word_type():
    result = filter_hot_keyword_rules(_kw("某主播开播", word_type=7))
    assert not result.accepted


def test_extract_items_array_from_list():
    raw = [{"keyword": "a", "accept": True}]
    assert len(extract_items_array(raw)) == 1


def test_parse_l1_llm_payload():
    items = [_kw("端午节看龙舟拔河"), _kw("NiKo夺冠")]
    raw = {
        "items": [
            {
                "keyword": "端午节看龙舟拔河",
                "accept": True,
                "mode": "expand",
                "reason": "可扩展为端午习俗或拔河力学",
            },
            {
                "keyword": "NiKo夺冠",
                "accept": False,
                "reason": "电竞赛果",
            },
        ]
    }
    results = _parse_l1_payload(raw, items)
    by_kw = {r.item.keyword: r for r in results}
    assert by_kw["端午节看龙舟拔河"].accepted
    assert by_kw["端午节看龙舟拔河"].mode == "expand"
    assert not by_kw["NiKo夺冠"].accepted
