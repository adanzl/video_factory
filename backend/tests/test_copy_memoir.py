"""口播伪亲历体检测。"""

from app.quality.checkers import check_copy, detect_memoir_narration


MINER_SAMPLE = (
    "我当矿工时，老矿工教我用布蘸水捂口鼻防瓦斯。结果有一次警报响，我照做后差点晕倒。"
    "后来才知道，这个流传多年的方法，其实是致命的误区。"
)


def test_detect_memoir_narration_miner_story():
    assert detect_memoir_narration(MINER_SAMPLE) is not None


def test_detect_memoir_narration_knowledge_style_ok():
    text = (
        "很多人以为瓦斯来了用湿毛巾捂嘴就行，其实这是个致命误区。"
        "甲烷几乎不溶于水，湿布反而增加呼吸阻力。"
        "正确做法是用干燥厚布多层折叠，压低身体沿避灾路线撤离。"
    )
    assert detect_memoir_narration(text) is None


def test_check_copy_rejects_memoir_style():
    report = check_copy({"narration": MINER_SAMPLE})
    assert report.level == "major"
    assert "memoir" in report.details.get("reason", "")


def test_check_copy_accepts_short_material_narration():
    narration = "x" * 130
    report = check_copy(
        {
            "narration": narration,
            "narration_target_words": 138,
        }
    )
    assert report.level == "pass"
    assert report.details.get("word_count") == 130


def test_check_copy_rejects_below_target_accept_min():
    report = check_copy(
        {
            "narration": "x" * 50,
            "narration_target_words": 138,
        }
    )
    assert report.level == "major"
    assert report.details.get("reason") == "narration too short"
    assert report.details.get("min_expected") == 117
