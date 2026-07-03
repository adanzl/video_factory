"""选题标题打分测试。"""

from app.services.topic.topic_mgr import score_title, status_from_score


def test_conversational_ac_title_scores_above_threshold():
    """生活向对话反转标题应能过线（空调/热等须计入画面可生成度）。"""
    result = score_title(
        "欧洲人不装空调就这？明明热到掉渣",
        category="生活避坑实用常识",
        template="误区反问式",
        hook="欧洲人夏天很少装空调的真实原因",
    )
    assert result.visual >= 82
    assert result.total >= 85
    assert status_from_score(result) == "queued"


def test_science_conversational_title_still_scores_well():
    result = score_title(
        "日本断供光刻胶？明明仓库都堆成山了",
        category="日常科学原理",
        template="误区反问式",
    )
    assert result.total >= 85
    assert status_from_score(result) == "queued"


def test_conversational_title_rejects_attitude_only_response():
    result = score_title(
        "地震云预报地震？就这",
        category="日常科学原理",
        template="误区反问式",
    )
    assert result.total == 0
    assert result.rejected_reason is not None
    assert "语气词" in result.rejected_reason
    assert status_from_score(result) == "rejected"


def test_conversational_title_accepts_substantive_rebuttal():
    result = score_title(
        "看云就能报地震？明明气象局早就辟谣了",
        category="日常科学原理",
        template="误区反问式",
    )
    assert result.total >= 85
    assert status_from_score(result) == "queued"


def test_conversational_title_witty_rebuttal_scores_above_bland():
    witty = score_title(
        "地震预警只有几十秒？明明够你跑路的",
        category="日常科学原理",
        template="误区反问式",
    )
    bland = score_title(
        "地震预警只有几十秒？明明足够你躲桌下",
        category="日常科学原理",
        template="误区反问式",
    )
    assert witty.total >= 85
    assert status_from_score(witty) == "queued"
    assert bland.total < witty.total
    assert status_from_score(bland) == "rejected"
