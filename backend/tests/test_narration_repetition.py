"""口播复读检测。"""

from app.quality.quality_mgr import check_narration, detect_narration_repetition

JOB25_SEG1 = (
    "哇，地震预警只有几十秒，用来逃跑吗？其实地震波还在路上跑呢！"
    "不是让你逃跑，是给你黄金时间做防护。地震就像远处摔了一跤，震波像涟漪传开，但比光慢多啦。"
)
JOB25_SEG2 = (
    "你看，地震就像在远处摔了一跤，震波像涟漪一样传开，速度比光慢多啦。"
    "光一秒钟能绕地球七圈半，而地震波一秒钟只能跑几公里，所以预警系统就是用闪电般的电波去追赶慢吞吞的地震波。"
)


def test_detect_adjacent_segment_overlap_job25_style():
    issue = detect_narration_repetition(
        JOB25_SEG1 + JOB25_SEG2,
        [
            {"segment_index": 1, "text": JOB25_SEG1},
            {"segment_index": 2, "text": JOB25_SEG2},
        ],
    )
    assert issue is not None
    assert "分镜 1" in issue


def test_detect_repeated_phrase_across_narration():
    text = "电波跑赢地震波很重要。" * 4
    issue = detect_narration_repetition(text, None)
    assert issue is not None
    assert "重复" in issue


def test_detect_narration_repetition_ok_for_varied_copy():
    narration = (
        "哇，地震预警只有几十秒！它用电波跑赢地震波，给你躲藏时间。"
        "第一步伏地，第二步遮挡，第三步抓牢，震停后再撤离。"
    )
    assert detect_narration_repetition(narration, None) is None


def test_check_narration_rejects_job25_style_overlap():
    narration = JOB25_SEG1 + JOB25_SEG2
    script = {
        "narration": narration,
        "narration_target_words": len(narration),
        "segments": [
            {"segment_index": 1, "text": JOB25_SEG1},
            {"segment_index": 2, "text": JOB25_SEG2},
        ],
    }
    report = check_narration(script)
    assert report.level == "major"
    assert "repetition" in report.details.get("reason", "")
