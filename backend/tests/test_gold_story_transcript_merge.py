"""金故事 H0b 多源逐字稿融合测试。"""

from app.config import Config
from app.services.gold_story.transcript import ocr
from app.services.gold_story.transcript import merge as tm


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


def test_score_transcript_penalizes_no_subtitle_ocr_noise():
    """无烧录字幕时误 OCR 水印/花字变体簇，不得跳过 ASR。"""
    garbled = (
        "逗乐介多网友\n逗乐个多网发\n逗乐谷多网友\n逗乐介多网方\n"
        "1.0\n"
        "一位签签左检香家网作业的时屋\n一位签签本检香家网作业购时屋\n"
        "一位签签本检查家网作业的时候\n位签签左检香家网作业的时屋\n"
        "AYK\n"
        "签签毛到后一险槽圈\n签签专到后二险槽圈\n爷签手到后一险槽圈\n"
        "签签考到后一险槽圈\n立卫往后面闪腔\n"
        "因为过却旦白户的孩子\n因为过都旦白己的孩子片之不台立点\n"
        "因为过都旦白已购孩子\n因为过都旦百户的孩子\n国为文都旦白已购孩了\n"
        "大直众了同一个出界同\n大百卖了同一个州界同飞#\n大首卖了\n大直卖了\n"
        "口奶奶都很淡定\n爸爸和奶奶都很淡定\n"
        "和拉偏架没有关系，完全是怕被误伤\n母大练练，文流Z\n"
        "1160134217@qq.com\n1160134217@qq.comYYASX\n1160134217@qq.com\n"
    )
    clean = (
        "逗乐众多网友\n"
        "一位爸爸在检查家庭作业的时候\n"
        "儿子和女儿突然在旁边打得不可开交\n"
        "爸爸看到后一脸懵圈\n"
        "立马往后面闪躲\n"
        "因为都是自己的孩子\n"
        "怕被误伤\n"
        "爸爸和奶奶都很淡定\n"
        "和拉偏架没有关系，完全是怕被误伤\n"
    )
    title = "姐弟俩在家打得不可开交，旁边的爸爸疯狂闪躲"
    garbled_score = tm.score_transcript_text(
        garbled,
        title=title,
        duration_sec=66.0,
        avg_confidence=0.85,
    )
    clean_score = tm.score_transcript_text(
        clean,
        title=title,
        duration_sec=66.0,
        avg_confidence=0.85,
    )
    assert garbled_score < 0.55, garbled_score
    assert clean_score >= 0.55, clean_score
    assert clean_score > garbled_score

    cfg = Config()
    cfg.gold_story_ocr_skip_asr_min = 0.55
    assert not ocr.should_skip_asr_after_ocr(
        {"text": garbled, "quality_score": garbled_score},
        cfg,
    )
    assert ocr.should_skip_asr_after_ocr(
        {"text": clean, "quality_score": clean_score},
        cfg,
    )


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


def test_score_transcript_penalizes_stroke_ocr_confusions():
    """描边字幕误识（育/竹/工米）不得虚高到跳过 ASR。"""
    garbled = (
        "我育不工米呀\n"
        "你为竹么不能育上米啊\n"
        "他门能育上米\n"
        "找姿\n"
        "我姿\n"
        "陶泥小猴子\n"
    )
    clean = (
        "我哭不出来呀\n"
        "你为什么不能背上来啊\n"
        "他们能背上来\n"
        "我哭\n"
        "我哭\n"
    )
    title = "我忍辱负重，只为了多年后的一句：姐，在吗？"
    garbled_score = tm.score_transcript_text(
        garbled,
        title=title,
        duration_sec=213.0,
        avg_confidence=0.88,
    )
    clean_score = tm.score_transcript_text(
        clean,
        title=title,
        duration_sec=213.0,
        avg_confidence=0.88,
    )
    assert garbled_score < 0.55, garbled_score
    assert clean_score >= 0.55, clean_score
    assert clean_score > garbled_score

    cfg = Config()
    cfg.gold_story_ocr_skip_asr_min = 0.55
    assert not ocr.should_skip_asr_after_ocr(
        {"text": garbled, "quality_score": garbled_score},
        cfg,
    )
    assert ocr.should_skip_asr_after_ocr(
        {"text": clean, "quality_score": clean_score},
        cfg,
    )
