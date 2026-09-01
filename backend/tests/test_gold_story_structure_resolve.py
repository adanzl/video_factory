"""金故事结构纠偏测试。"""

from __future__ import annotations

from app.services.daily_story.gold_story.collect import llm as llm_steps
from app.services.daily_story.gold_story.gold_chat.type_bridge import (
    resolve_gold_chat_structure_row,
)
from app.services.daily_story.gold_story.structure_resolve import (
    resolve_h3_structure,
    should_reclassify_m2_c_to_m8_j,
    suggests_c_fairness_boomerang,
    suggests_m8_j_domination,
)

_STORY_28_RAW = (
    "幼儿园的午休时间，两个胖乎乎的小家伙在垫子上扭打起来。"
    "弟弟先发制人，一拳打在姐姐脸上，姐姐懵了一下，随即用肉乎乎的手臂锁住弟弟的脖子，"
    "把他按倒在地。弟弟挣扎着喊：「拿出你的最强形态吧老姐！」"
    "姐姐咧嘴一笑，露出缺了门牙的牙床：「如你所愿！」"
    "然后使出绝技「草莓熊肘击」，轻轻顶在弟弟肚子上。"
    "弟弟立刻夸张地滚到一边，捂着肚子喊：「我输了！我输了！」"
    "姐姐得意地爬起来，叉着腰说：「以后幼儿园的单子都归我接！」"
    "弟弟翻个白眼，小声嘀咕：「等我长大了再跟你算账。」"
)

_M2_C_FAIR_RAW = (
    "姐弟分肉，灿灿说谁吃得多谁洗碗，昭昭说谁先夹谁赢。"
    "灿灿引用昭昭刚说的「公平」堵他，昭昭又搬出妈妈说过每人一块。"
    "最后灿灿被回旋镖：你刚说公平，凭什么你多夹两块？"
    "灿灿末句嘴硬：那不一样。"
)


def test_suggests_m8_j_for_story_28():
    assert suggests_m8_j_domination(_STORY_28_RAW)
    assert not suggests_c_fairness_boomerang(_STORY_28_RAW)
    assert should_reclassify_m2_c_to_m8_j(
        mechanism="M2",
        structure_type="C",
        blob=_STORY_28_RAW,
    )


def test_keeps_m2_c_for_dual_rule_fairness():
    assert suggests_c_fairness_boomerang(_M2_C_FAIR_RAW)
    assert not should_reclassify_m2_c_to_m8_j(
        mechanism="M2",
        structure_type="C",
        blob=_M2_C_FAIR_RAW,
    )


def test_resolve_h3_structure_story_28():
    h3 = {
        "mechanism": "M2",
        "structure_type": "C",
        "conflict_core": "姐姐用武力压制弟弟",
        "beat": [
            "弟弟先动手，姐姐反击",
            "姐姐立规谁赢了谁说了算",
            "姐姐草莓熊肘击取胜",
            "弟弟认输并嘀咕长大再算账",
        ],
        "structure_mapping_note": "保持双规则与回旋镖结构",
        "structure_confidence": 0.8,
    }
    fixed, notes = resolve_h3_structure(h3, story_raw=_STORY_28_RAW)
    assert fixed["mechanism"] == "M8"
    assert fixed["structure_type"] == "J"
    assert notes
    assert "domination-not-fairness" in notes[0]


def test_resolve_gold_chat_structure_row_m2_c_to_m8_j():
    row = {
        "id": 28,
        "mechanism": "M2",
        "structure_type": "C",
        "conflict_core": "姐姐用武力压制弟弟",
        "payload": {
            "story_raw": _STORY_28_RAW,
            "beat": [
                "弟弟先动手，姐姐反击",
                "姐姐立规谁赢了谁说了算",
                "姐姐草莓熊肘击取胜",
                "弟弟认输并嘀咕长大再算账",
            ],
            "structure_mapping_note": "保持双规则与回旋镖结构",
            "scene_contract": {"story_type": "C"},
            "closing_intent": "昭昭表面认输但内心不服，埋下回旋镖",
        },
    }
    fixed, notes = resolve_gold_chat_structure_row(row)
    assert fixed["mechanism"] == "M8"
    assert fixed["structure_type"] == "J"
    assert fixed["payload"]["scene_contract"]["story_type"] == "J"
    assert any("M2→M8" in n for n in notes)


def test_structurize_story_applies_resolve(monkeypatch):
    def fake_chat(_system: str, _user: str) -> dict:
        return {
            "title": "世子之争",
            "conflict_core": "姐姐用武力压制弟弟",
            "funny_why": "反差萌",
            "mechanism": "M2",
            "structure_type": "C",
            "theme_family": "占有",
            "beat": [
                "弟弟先动手",
                "姐姐立规谁赢了谁说了算",
                "草莓熊肘击取胜",
                "弟弟认输嘀咕长大再算账",
            ],
            "structure_confidence": 0.8,
            "structure_mapping_note": "",
        }

    monkeypatch.setattr(llm_steps, "_chat_json", fake_chat)
    out = llm_steps.structurize_story(title="世子之争", story_raw=_STORY_28_RAW)
    assert out["mechanism"] == "M8"
    assert out["structure_type"] == "J"
