"""banned_literals 过滤：仅保留 remap/真名。"""

from __future__ import annotations

from app.services.daily_story.gold_story.scene_contract import sanitize_banned_literals


def test_sanitize_drops_scene_and_humor_words():
    scene = {
        "object": "画作",
        "conflict": "灿灿：你干嘛弄坏我的画！",
        "mechanism": "谁先动手谁道歉",
        "beat_chain": [{"intent": "互毁升级"}],
    }
    banned = sanitize_banned_literals(
        ["贾西西", "贾贝贝", "画画", "碘伏", "朋友圈"],
        scene_contract=scene,
        beat=["哥哥头破涂碘伏"],
    )
    assert banned == ["贾西西", "贾贝贝"]


def test_sanitize_keeps_speaker_remap():
    banned = sanitize_banned_literals(["哥哥", "妹妹", "酱碗"])
    assert banned == ["哥哥", "妹妹"]


def test_sanitize_empty_input():
    assert sanitize_banned_literals(None) == []
    assert sanitize_banned_literals([]) == []
