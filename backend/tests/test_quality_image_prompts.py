from app.quality.checkers import (
    check_image_prompts,
    skipped_image_prompts_check,
)
from app.quality.image_prompt_rules import image_prompt_min_chars


def _script(chars: int) -> dict:
    return {
        "segments": [{"segment_index": 1, "image_prompt": "x" * chars}],
    }


def test_check_image_prompts_pass():
    report = check_image_prompts(_script(300))
    assert report.level == "pass"
    assert report.step == "image_prompts"


def test_check_image_prompts_major_when_too_short():
    report = check_image_prompts(_script(30))
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
    assert report.level == "minor"
    assert report.details["reason"] == "sd15_prompt_en slightly short"


def test_check_image_prompts_sd15_mode_accepts_min_sd15_words():
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
    report = check_image_prompts(script)
    assert report.level == "minor"


def test_check_image_prompts_sd15_mode_pass_when_sd15_long_enough():
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
    report = check_image_prompts(script)
    assert report.level == "pass"


def test_check_image_prompts_sd15_mode_missing_sd15_is_minor():
    script = {
        "include_sd15_prompt": True,
        "segments": [{"segment_index": 1, "image_prompt": "x" * 90}],
    }
    report = check_image_prompts(script)
    assert report.level == "minor"
    assert report.details["reason"] == "sd15_prompt_en missing, fallback at image gen"


def test_check_image_prompts_sd15_mode_bad_sd15_is_major():
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
    report = check_image_prompts(script)
    assert report.level == "major"
    assert report.details["reason"] == "sd15_prompt_en too short"


def test_check_image_prompts_sd15_mode_image_prompt_too_short():
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
    report = check_image_prompts(script)
    assert report.level == "major"
    assert report.details["reason"] == "image_prompt too short"
    assert report.details["segments"][0]["min_chars"] == image_prompt_min_chars(sd15_mode=True)


def test_check_image_prompts_scoped_to_segment_indices():
    script = {
        "segments": [
            {"segment_index": 1, "image_prompt": "x" * 50},
            {"segment_index": 2, "image_prompt": "x" * 300},
        ],
    }
    report = check_image_prompts(script, segment_indices=[2])
    assert report.level == "pass"


def test_skipped_image_prompts_check():
    report = skipped_image_prompts_check()
    assert report.level == "pass"
    assert report.details["reason"] == "skipped"
