from app.quality.checkers import (
    check_image_prompts,
    skipped_image_prompts_check,
)
from app.services.llm.llm_script_prompts import image_prompt_min_chars


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


def test_check_image_prompts_sd15_mode_accepts_short_image_prompt():
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
    report = check_image_prompts(script)
    assert report.level == "pass"


def test_check_image_prompts_sd15_mode_requires_sd15_prompt_en():
    script = {
        "include_sd15_prompt": True,
        "segments": [{"segment_index": 1, "image_prompt": "x" * 90}],
    }
    report = check_image_prompts(script)
    assert report.level == "major"
    assert report.details["reason"] == "sd15_prompt_en missing or too short"


def test_check_image_prompts_sd15_mode_image_prompt_too_short():
    script = {
        "include_sd15_prompt": True,
        "segments": [
            {
                "segment_index": 1,
                "image_prompt": "x" * 50,
                "sd15_prompt_en": "stainless steel pot on stove, close-up surface detail, kitchen counter",
            },
        ],
    }
    report = check_image_prompts(script)
    assert report.level == "major"
    assert report.details["reason"] == "image_prompt too short"
    assert report.details["segments"][0]["min_chars"] == image_prompt_min_chars(sd15_mode=True)


def test_skipped_image_prompts_check():
    report = skipped_image_prompts_check()
    assert report.level == "pass"
    assert report.details["reason"] == "skipped"
