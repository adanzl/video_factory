"""金故事结构纠偏测试。"""

from __future__ import annotations

from app.services.gold_story.collect import llm as llm_steps
from app.services.gold_story.gold_chat.type_bridge import (
    resolve_gold_chat_structure_row,
)
from app.services.gold_story.structure_resolve import (
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


_STORY_39_RAW = (
    "妈妈问儿子：“如果爸爸掉水里了，你先吃苹果还是先吃香蕉？”"
    "儿子想都没想就说：“吃香蕉。”妈妈追问为什么，儿子一本正经地说："
    "“因为香蕉有籽，吃了能长成香蕉树，到时候就能把爸爸捞上来了。”"
    "妈妈愣住，哭笑不得。"
)


def test_suggests_m6_n_for_solemn_nonsense():
    from app.services.gold_story.structure_resolve import (
        should_reclassify_to_m6_n,
        suggests_m6_n_solemn_nonsense,
    )

    blob = (
        _STORY_39_RAW
        + "\n双方各执判据但未形成回旋镖"
        + "\n荒诞逻辑一本正经"
    )
    assert suggests_m6_n_solemn_nonsense(blob)
    assert should_reclassify_to_m6_n(
        mechanism="M2",
        structure_type="C",
        blob=blob,
    )
    assert not should_reclassify_m2_c_to_m8_j(
        mechanism="M2",
        structure_type="C",
        blob=blob,
    )


def test_resolve_h3_structure_story_39_to_m6_n():
    h3 = {
        "mechanism": "M2",
        "structure_type": "C",
        "conflict_core": "妈妈用假设性问题考验，儿子用荒诞逻辑回应",
        "beat": [
            "妈妈抛出二选一难题",
            "儿子秒答吃香蕉",
            "妈妈追问，儿子一本正经解释",
            "妈妈哭笑不得",
        ],
        "structure_mapping_note": "双方各执判据但未形成回旋镖",
        "structure_confidence": 0.7,
    }
    fixed, notes = resolve_h3_structure(h3, story_raw=_STORY_39_RAW)
    assert fixed["mechanism"] == "M6"
    assert fixed["structure_type"] == "N"
    assert notes
    assert "solemn-nonsense" in notes[0]


_STORY_53_RAW = (
    "灿灿和昭昭玩抢吃蜡烛的游戏，规则是剪刀石头布，赢的人才能吃一口菜。"
    "昭昭一心只想赢，每次出拳都特别认真，结果真的赢了好几次。"
    "可等她慢悠悠地夹菜时，发现桌上的菜已经被灿灿吃得差不多了。"
    "她愣愣地看着空盘子，又看看自己碗里仅剩的一小块菜，委屈地嘟囔："
    "「我光顾着赢了，菜都没了……」灿灿在一旁偷笑，妈妈也忍不住笑出声来。"
)


def test_suggests_m13_o_for_goal_tunnel():
    from app.services.gold_story.structure_resolve import (
        should_reclassify_m2_c_to_m13_o,
        suggests_m13_o_goal_tunnel,
    )

    assert suggests_m13_o_goal_tunnel(_STORY_53_RAW)
    assert should_reclassify_m2_c_to_m13_o(
        mechanism="M2",
        structure_type="C",
        blob=_STORY_53_RAW,
    )
    assert not should_reclassify_m2_c_to_m8_j(
        mechanism="M2",
        structure_type="C",
        blob=_STORY_53_RAW,
    )
    assert suggests_c_fairness_boomerang(_M2_C_FAIR_RAW)
    assert not should_reclassify_m2_c_to_m13_o(
        mechanism="M2",
        structure_type="C",
        blob=_M2_C_FAIR_RAW,
    )


def test_resolve_h3_structure_story_53_to_m13_o():
    h3 = {
        "mechanism": "M2",
        "structure_type": "C",
        "conflict_core": "昭昭光顾着赢剪刀石头布，结果菜被灿灿吃光了",
        "beat": [
            "昭昭提出剪刀石头布，赢的人才能吃菜",
            "昭昭专注出拳多次获胜",
            "夹菜时发现菜量减少",
            "昭昭点题：光顾着赢，菜都没了",
        ],
        "structure_mapping_note": "双规则体现在赢者吃菜与快速夹菜",
        "structure_confidence": 0.8,
    }
    fixed, notes = resolve_h3_structure(h3, story_raw=_STORY_53_RAW)
    assert fixed["mechanism"] == "M13"
    assert fixed["structure_type"] == "O"
    assert notes
    assert "goal-tunnel-not-fairness" in notes[0]


def test_resolve_gold_chat_structure_row_story_53_to_m13_o():
    row = {
        "id": 53,
        "mechanism": "M2",
        "structure_type": "C",
        "conflict_core": "昭昭光顾着赢剪刀石头布，结果菜被灿灿吃光了",
        "payload": {
            "story_raw": _STORY_53_RAW,
            "beat": [
                "昭昭提出剪刀石头布，赢的人才能吃菜",
                "昭昭专注出拳多次获胜",
                "夹菜时发现菜量减少",
                "昭昭点题：光顾着赢，菜都没了",
            ],
            "structure_mapping_note": "双规则体现在赢者吃菜与快速夹菜",
            "scene_contract": {"story_type": "C"},
            "closing_intent": "灿灿偷笑，妈妈笑场",
        },
    }
    fixed, notes = resolve_gold_chat_structure_row(row)
    assert fixed["mechanism"] == "M13"
    assert fixed["structure_type"] == "O"
    assert fixed["payload"]["scene_contract"]["story_type"] == "O"
    assert any("M2→M13" in n or "M13" in n for n in notes)


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
