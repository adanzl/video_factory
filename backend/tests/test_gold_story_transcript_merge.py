"""金故事 H0b 多源逐字稿融合测试。"""

from app.config import Config
from app.services.daily_story.gold_story.transcript import ocr
from app.services.daily_story.gold_story.transcript import merge as tm


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


def test_should_skip_asr_after_ocr_when_quality_high():
    cfg = Config()
    cfg.gold_story_ocr_skip_asr_min = 0.55
    assert ocr.should_skip_asr_after_ocr(
        {"text": "我爱学习你爱吗", "quality_score": 0.89},
        cfg,
    )
    assert not ocr.should_skip_asr_after_ocr(
        {"text": "我爱学习你爱吗", "quality_score": 0.4},
        cfg,
    )
    assert not ocr.should_skip_asr_after_ocr({"text": "", "quality_score": 0.9}, cfg)


def test_ocr_models_ready(tmp_path):
    cfg = Config()
    cfg.ocr_model_dir = tmp_path
    assert not ocr.ocr_models_ready(cfg)
    (tmp_path / "ch_PP-OCRv4_det_mobile.onnx").write_text("x")
    assert not ocr.ocr_models_ready(cfg)
    (tmp_path / "ch_PP-OCRv4_rec_mobile.onnx").write_text("x")
    assert ocr.ocr_models_ready(cfg)
