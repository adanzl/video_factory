from app.quality.checkers import (
    check_image_prompts,
    skipped_image_prompts_check,
)


def _script(chars: int) -> dict:
    return {
        "segments": [{"segment_index": 1, "image_prompt": "x" * chars}],
    }


def test_check_image_prompts_pass():
    report = check_image_prompts(_script(300))
    assert report.level == "pass"
    assert report.step == "image_prompts"


def test_check_image_prompts_major_when_too_short():
    report = check_image_prompts(_script(100))
    assert report.level == "major"
    assert report.details["reason"] == "image_prompt too short"


def test_skipped_image_prompts_check():
    report = skipped_image_prompts_check()
    assert report.level == "pass"
    assert report.details["reason"] == "skipped"
