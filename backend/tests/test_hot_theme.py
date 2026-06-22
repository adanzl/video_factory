from app.services.topic.hot_fetcher import HotKeyword
from app.services.topic.hot_filter import HotFilterResult
from app.services.topic.hot_theme import convert_hot_to_themes


def _kw(keyword: str) -> HotKeyword:
    return HotKeyword(
        keyword=keyword,
        show_name=keyword,
        heat_score=100,
        word_type=None,
        source="test",
    )


def test_heuristic_skips_expand_mode():
    rows = [
        HotFilterResult(
            item=_kw("端午节看龙舟拔河"),
            accepted=True,
            mode="expand",
            reason="test",
        ),
    ]
    themes = convert_hot_to_themes(rows, use_llm=False)
    assert themes == []


def test_heuristic_direct_mode():
    rows = [
        HotFilterResult(
            item=_kw("空调怎么开最省电"),
            accepted=True,
            mode="direct",
            reason="test",
        ),
    ]
    themes = convert_hot_to_themes(rows, use_llm=False)
    assert len(themes) == 1
    assert "空调" in themes[0].theme
