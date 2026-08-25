"""金故事 H0b 多源逐字稿融合测试。"""

from app.services.daily_story.gold_story import transcript_merge as tm


def test_score_transcript_prefers_clean_dialogue():
    good = "我爱学习，你爱吗\n我不爱\n不爱学习就别跟我吵了"
    bad = "我如果忘了说少爱能不能合个礼仪再给我发一点语言"
    good_score = tm.score_transcript_text(
        good,
        title="灵魂拷问：我爱学习你爱吗",
        duration_sec=56.0,
        avg_confidence=0.9,
    )
    bad_score = tm.score_transcript_text(
        bad,
        title="灵魂拷问：我爱学习你爱吗",
        duration_sec=56.0,
        avg_confidence=0.4,
    )
    assert good_score > bad_score


def test_pick_transcript_prefers_ocr_when_higher_quality():
    picked = tm.pick_transcript_candidate(
        [
            {
                "source": "asr",
                "text": "我爱学习你爱吗。还我们俩都相红。",
                "avg_confidence": None,
                "quality_score": 0.3,
            },
            {
                "source": "ocr",
                "text": "我爱学习，你爱吗\n我不爱\n不爱学习就别跟我吵了",
                "avg_confidence": 0.88,
                "quality_score": 0.85,
            },
        ],
        title="灵魂拷问：我爱学习你爱吗",
        duration_sec=56.0,
    )
    assert picked["source"] == "ocr"


def test_texts_similar_merges_duplicate_frames():
    assert tm.texts_similar("我爱学习你爱吗", "我爱学习，你爱吗")
