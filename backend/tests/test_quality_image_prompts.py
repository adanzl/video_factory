from app.quality.quality_mgr import (
    check_image_prompt,
    skip_image_prompt_check,
)
from app.quality.image_prompt import (
    audit_image_prompt_slots,
    collect_motion_prompt_issues,
    generic_motion_prompt_issue,
    image_prompt_min_chars,
)


def _script(chars: int) -> dict:
    return {
        "segments": [{"segment_index": 1, "image_prompt": "x" * chars}],
    }


def test_check_image_prompt_pass():
    report = check_image_prompt(_script(300))
    assert report.level == "pass"
    assert report.step == "image_prompts"


def test_check_image_prompt_pass_at_pass_threshold():
    report = check_image_prompt(_script(150))
    assert report.level == "pass"


def test_check_image_prompt_minor_when_below_pass_threshold():
    report = check_image_prompt(_script(120))
    assert report.level == "minor"
    assert report.details["reason"] == "image_prompt slightly short"


def test_check_image_prompt_major_when_too_short():
    report = check_image_prompt(_script(30))
    assert report.level == "major"
    assert report.details["reason"] == "image_prompt too short"


def test_check_image_prompt_sd15_mode_accepts_short_image_prompt():
    script = {
        "include_sd15_prompt": True,
        "segments": [
            {
                "segment_index": 1,
                "image_prompt": "x" * 90,
                "sd15_prompt_en": "stainless steel pot on stove, close-up surface detail, kitchen counter",
            },
        ],
    }
    report = check_image_prompt(script)
    assert report.level == "minor"
    assert report.details["reason"] == "sd15_prompt_en slightly short"


def test_check_image_prompt_sd15_mode_accepts_min_sd15_words():
    script = {
        "include_sd15_prompt": True,
        "segments": [
            {
                "segment_index": 1,
                "image_prompt": "x" * 90,
                "sd15_prompt_en": "one two three four five six seven eight",
            },
        ],
    }
    report = check_image_prompt(script)
    assert report.level == "minor"


def test_check_image_prompt_sd15_mode_pass_when_sd15_long_enough():
    script = {
        "include_sd15_prompt": True,
        "segments": [
            {
                "segment_index": 1,
                "image_prompt": "x" * 120,
                "sd15_prompt_en": (
                    "stainless steel pot on stove boiling water steam rising warm kitchen light"
                ),
            },
        ],
    }
    report = check_image_prompt(script)
    assert report.level == "pass"


def test_check_image_prompt_sd15_mode_missing_sd15_is_minor():
    script = {
        "include_sd15_prompt": True,
        "segments": [{"segment_index": 1, "image_prompt": "x" * 90}],
    }
    report = check_image_prompt(script)
    assert report.level == "minor"
    assert report.details["reason"] == "sd15_prompt_en missing, fallback at image gen"


def test_check_image_prompt_sd15_mode_bad_sd15_is_major():
    script = {
        "include_sd15_prompt": True,
        "segments": [
            {
                "segment_index": 1,
                "image_prompt": "x" * 120,
                "sd15_prompt_en": "too few words",
            },
        ],
    }
    report = check_image_prompt(script)
    assert report.level == "major"
    assert report.details["reason"] == "sd15_prompt_en too short"


def test_check_image_prompt_sd15_mode_image_prompt_too_short():
    script = {
        "include_sd15_prompt": True,
        "segments": [
            {
                "segment_index": 1,
                "image_prompt": "x" * 15,
                "sd15_prompt_en": "stainless steel pot on stove, close-up surface detail, kitchen counter",
            },
        ],
    }
    report = check_image_prompt(script)
    assert report.level == "major"
    assert report.details["reason"] == "image_prompt too short"
    assert report.details["segments"][0]["min_chars"] == image_prompt_min_chars(sd15_mode=True)


def test_check_image_prompt_scoped_to_segment_indices():
    script = {
        "segments": [
            {"segment_index": 1, "image_prompt": "x" * 50},
            {"segment_index": 2, "image_prompt": "x" * 300},
        ],
    }
    report = check_image_prompt(script, segment_indices=[2])
    assert report.level == "pass"


def test_skip_image_prompt_check():
    report = skip_image_prompt_check()
    assert report.level == "pass"
    assert report.details["reason"] == "skipped"


def test_generic_motion_prompt_issue_rejects_filler():
    assert generic_motion_prompt_issue("镜头固定，主体稳定，画面平滑") is not None
    assert generic_motion_prompt_issue("炉口青烟缓缓上升，镜头极缓推进") is None


def test_audit_does_not_block_negation_words():
    issues = audit_image_prompt_slots(
        "昭昭坐在餐桌左边，右手扶额，无奈。不要画出字幕。"
    )
    assert not any(i.get("kind") == "negation" for i in issues)


def test_check_image_prompt_allows_wunai_in_assembled_slot():
    prompt = (
        "儿童情绪涂鸦风，彩铅蜡笔混合笔触，高饱和色彩，涂色出界，手工感；"
        "餐桌旁；餐桌、椅子清晰可见。"
        "画面左边是昭昭，右手扶额，无奈。画面右边是灿灿，右手拿着筷子，眯眼笑。"
        "昭昭：7岁男孩，黑色超短发露耳露后颈，圆脸，蓝色短袖T恤。"
        "灿灿：10岁女孩，黑色单侧高马尾，粉色卫衣蓝色长裤。"
        "窗光从一侧斜照，在墙面和地面投下柔和光影。"
        "画面左边是昭昭，右边是灿灿。中近景特写，全身可见"
    )
    report = check_image_prompt(
        {"segments": [{"segment_index": 11, "image_prompt": prompt}]}
    )
    assert report.level != "major"


def test_collect_motion_prompt_issues_flags_duplicates():
    segments = [
        {"segment_index": 1, "motion_prompt": "炉口青烟缓缓上升，镜头极缓推进"},
        {"segment_index": 2, "motion_prompt": "炉口青烟缓缓上升，镜头极缓推进"},
        {"segment_index": 3, "motion_prompt": "炉口青烟缓缓上升，镜头极缓推进"},
    ]
    issues = collect_motion_prompt_issues(segments)
    assert any("完全相同" in item for item in issues)
