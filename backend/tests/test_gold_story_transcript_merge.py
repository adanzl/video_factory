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


def test_repeated_questions_with_high_ocr_confidence_are_not_noise():
    text = ("你下次还让我陪你去学校吗\n你下次让不让我陪你去学校\n"
            "不是你想不想让我陪你去学校\n我想自己走\n你真的不用我陪你去学校吗\n"
            "我想自己走到学校\n那你就自己走吧\n谢谢妈妈")
    garbled = "你下刺害让喔陪你句学笑吗。你下刺想想让我培泥句学校。窝想纸几奏到学笑。"
    picked = tm.pick_transcript_candidate([
        {"source": "ocr", "text": text, "avg_confidence": 0.99},
        {"source": "asr", "text": garbled},
    ], title="上学", duration_sec=60)
    assert picked["source"] == "ocr"
    # 选稿不意味着两路一致或自动通过来源审核。
    assert tm.cross_check_transcripts({"text": text}, {"text": garbled})["passed"] is False


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


def test_cross_check_flags_systematic_ocr_misrecognition():
    """两路差异过大必须判不通过：单路 OCR 会系统性地把字认错（#138 实测）。

    #138 的烧录字幕被 OCR 认成「找鸡妈像一个暴踩的老虎」，实际是
    「我妈妈像一个暴躁的老虎」——「找←我」「暴踩←暴躁」是成片的形近误认，
    整段读起来「像话」，单路质量分也不低，只有拿另一路（ASR）印证才能发现。
    """
    ocr_text = (
        "找鸡妈像一个暴踩的老虎\n"
        "你就不能祝找妈妈像一个公王\n"
        "那如米以后咱多兆了菲\n"
        "找老师让找逗可"
    )
    asr_text = (
        "我妈妈像一个暴躁的老虎\n"
        "你就不能说我妈嘛像一个公主温柔大吧漂亮\n"
        "那如果以后咱电饭的对你也是法官你会不会投入一下\n"
        "我老是有造诀就没有造谣"
    )
    res = tm.cross_check_transcripts(
        {"text": ocr_text, "source": "ocr"},
        {"text": asr_text, "source": "asr"},
    )
    assert res["available"] is True
    assert res["passed"] is False
    assert res["agreement"] < 0.55


def test_cross_check_passes_on_consistent_transcripts():
    """两路一致就是可信：完全相同与轻微措辞差异都应通过。"""
    line = "昭昭，这盘黑面饺子你尝尝，味道到底怎么样？"
    same = tm.cross_check_transcripts(
        {"text": line, "source": "ocr"}, {"text": line, "source": "asr"}
    )
    assert same["passed"] is True
    assert same["agreement"] == 1.0

    near = tm.cross_check_transcripts(
        {"text": line, "source": "ocr"},
        {"text": "昭昭，这盘黑面饺子你尝一下，味道怎么样？", "source": "asr"},
    )
    assert near["passed"] is True


def test_cross_check_unavailable_with_single_source():
    """只有一路时无从印证：标记 available=False，不能当失败也不能当通过。"""
    res = tm.cross_check_transcripts({"text": "我爱学习你爱吗", "source": "ocr"}, None)
    assert res["available"] is False
    assert res["passed"] is None
    assert res["agreement"] is None


def test_cross_check_ignores_punctuation_and_width_but_not_dialogue_changes():
    res = tm.cross_check_transcripts(
        {"source": "ocr", "text": "妈妈：给我２个！\n弟弟：好，ＡＢＣ。"},
        {"source": "asr", "text": "妈妈给我2个弟弟好abc"},
    )
    assert res["agreement"] == 1.0
    assert res["passed"] is True
    assert tm.cross_check_transcripts({"text": "？！"}, {"text": "……"})["available"] is False


def test_cross_check_does_not_discard_frequent_characters_in_long_chinese():
    from difflib import SequenceMatcher
    a = "姐姐让我洗碗弟弟说他要写作业妈妈问到底谁做家务" * 12
    b = "今天" + a.replace("洗碗", "刷碗")
    # 默认 autojunk 把超过 200 字文本里的常用字过滤，几乎整段相同却零分。
    assert SequenceMatcher(None, a, b).ratio() < 0.55
    res = tm.cross_check_transcripts({"text": a}, {"text": b})
    reverse = tm.cross_check_transcripts({"text": b}, {"text": a})
    assert res["passed"] is True
    assert res["agreement"] > 0.9
    assert res["agreement"] == reverse["agreement"]


def test_cross_check_does_not_accept_short_fragment_or_unrelated_chinese():
    short = "妈妈你什么时候回来"
    other = "姐姐和弟弟在讨论今天的作业应该怎么完成" * 20
    assert tm.cross_check_transcripts({"text": short}, {"text": short + other})["passed"] is False
    assert tm.cross_check_transcripts({"text": short * 30}, {"text": other})["passed"] is False


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
