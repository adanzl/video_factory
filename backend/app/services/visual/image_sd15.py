"""本地 SD1.5（A1111 WebUI API）文生图 ImageProvider。"""

from __future__ import annotations

import base64
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import requests

from app.config import get_settings
from app.services.llm.llm_mgr import llm_mgr
from app.services.llm.llm_sd15_prompt import pick_lora_by_keywords, weight_for_lora
from app.services.visual.image_mock import MockImageProvider
from app.services.visual.visual_mgr import ImageProvider

logger = logging.getLogger(__name__)

_BUSINESS_CONFIG = {
    "life": {
        "checkpoint": "RealisticVisionV51.safetensors",
        "width": 768,
        "height": 576,
        "steps": 20,
        "negative": (
            "cartoon, anime, illustration, painting, blurry, deformed, ugly, "
            "watermark, text, logo, oversaturated"
        ),
    },
    "science": {
        "checkpoint": "ToonYouBeta6.safetensors",
        "width": 576,
        "height": 768,
        "steps": 22,
        "negative": (
            "photo, realistic, 3d render, shadow, gradient background, cluttered, "
            "text, watermark, blurry"
        ),
    },
}


def parse_image_size(size: str) -> tuple[int, int]:
    normalized = size.strip().lower().replace("x", "*")
    w_str, h_str = normalized.split("*", 1)
    return int(w_str.strip()), int(h_str.strip())


def business_from_size(width: int, height: int) -> str:
    return "science" if height > width else "life"


@dataclass(frozen=True)
class _Sd15PromptPrep:
    prompt_en: str
    business: str
    lora: str


def _fallback_prompt_en(prompt: str) -> str:
    cleaned = prompt.strip()
    if not cleaned:
        return "illustration, soft lighting"
    if not re.search(r"[\u3400-\u9fff]", cleaned):
        return cleaned
    return "illustration, educational scene, soft lighting, clean composition"


def _fallback_business(*, lora: str, business_override: str | None) -> str:
    if business_override in _BUSINESS_CONFIG:
        return business_override
    from app.services.llm.llm_sd15_prompt import business_for_lora

    return business_for_lora(lora)


def _prepare_sd15_prompt(
    prompt: str,
    *,
    size_hint: str | None = None,
    business_override: str | None = None,
) -> _Sd15PromptPrep:
    cleaned = prompt.strip()
    if not cleaned:
        raise ValueError("prompt is required")

    settings = get_settings()
    if settings.deepseek_api_key:
        try:
            result = llm_mgr.prepare_sd15_image_prompt(
                cleaned,
                size_hint=size_hint,
                business_override=business_override,
            )
            logger.info(
                "sd15 prompt prep llm: business=%s lora=%s prompt_en_chars=%s",
                result["business"],
                result["lora"],
                len(result["prompt_en"]),
            )
            return _Sd15PromptPrep(
                prompt_en=result["prompt_en"],
                business=result["business"],
                lora=result["lora"],
            )
        except Exception as exc:
            logger.warning("sd15 prompt prep llm failed, using fallback: %s", exc)

    lora = pick_lora_by_keywords(cleaned)
    prompt_en = _fallback_prompt_en(cleaned)
    business = _fallback_business(lora=lora, business_override=business_override)
    logger.info(
        "sd15 prompt prep fallback: business=%s lora=%s prompt_en_chars=%s",
        business,
        lora,
        len(prompt_en),
    )
    return _Sd15PromptPrep(prompt_en=prompt_en, business=business, lora=lora)


class Sd15ImageProvider(ImageProvider):
    _checkpoint_lock = threading.Lock()

    def __init__(self) -> None:
        settings = get_settings()
        self._api_url = settings.sd_api_url.rstrip("/")
        self._business_override = settings.sd_business
        self._default_size = settings.sd_image_size
        self._timeout_sec = settings.sd_timeout_sec
        self._fallback = MockImageProvider()
        self._current_checkpoint: str | None = None

    def describe_params(self, *, size: str | None = None) -> str:
        from app.services.llm.llm_sd15_prompt import SD15_LORAS

        business = self._business_override or "auto"
        lora_hint = "llm_pick|" + "|".join(SD15_LORAS)
        cfg_life = _BUSINESS_CONFIG["life"]
        cfg_sci = _BUSINESS_CONFIG["science"]
        return (
            f"provider=sd15_t2i, api={self._api_url}, business={business}, "
            f"lora={lora_hint}, checkpoints=life:{cfg_life['checkpoint']}|"
            f"science:{cfg_sci['checkpoint']}, "
            f"size=life:{cfg_life['width']}*{cfg_life['height']}|"
            f"science:{cfg_sci['width']}*{cfg_sci['height']}"
        )

    def _cfg_for_business(self, business: str) -> dict:
        if business not in _BUSINESS_CONFIG:
            raise ValueError(f"unknown sd15 business: {business}")
        return _BUSINESS_CONFIG[business]

    def _switch_checkpoint(self, checkpoint: str) -> None:
        with self._checkpoint_lock:
            if self._current_checkpoint == checkpoint:
                return
            resp = requests.post(
                f"{self._api_url}/sdapi/v1/options",
                json={"sd_model_checkpoint": checkpoint},
                timeout=60,
            )
            resp.raise_for_status()
            self._current_checkpoint = checkpoint

    def generate(self, prompt: str, output_path: Path, *, size: str | None = None) -> Path:
        size = size or self._default_size
        prep = _prepare_sd15_prompt(
            prompt,
            size_hint=size,
            business_override=self._business_override,
        )
        business = prep.business
        cfg = self._cfg_for_business(business)
        api_width, api_height = cfg["width"], cfg["height"]
        lora = prep.lora
        weight = weight_for_lora(lora)
        full_prompt = f"<lora:{lora}:{weight}> {prep.prompt_en}"

        logger.info(
            "sd15 request: business=%s lora=%s size=%s*%s prompt_en_chars=%s",
            business,
            lora,
            api_width,
            api_height,
            len(prep.prompt_en),
        )
        try:
            self._switch_checkpoint(cfg["checkpoint"])
            payload = {
                "prompt": full_prompt,
                "negative_prompt": cfg["negative"],
                "steps": cfg["steps"],
                "cfg_scale": 7,
                "width": api_width,
                "height": api_height,
                "sampler_name": "DPM++ 2M Karras",
                "batch_size": 1,
                "n_iter": 1,
                "seed": -1,
                "enable_hr": False,
            }
            resp = requests.post(
                f"{self._api_url}/sdapi/v1/txt2img",
                json=payload,
                timeout=self._timeout_sec,
            )
            resp.raise_for_status()
            data = resp.json()
            img_bytes = base64.b64decode(data["images"][0])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(img_bytes)
            return output_path
        except Exception as exc:
            logger.error("sd15 generate failed: %s", exc)
            if get_settings().mock_mode:
                return self._fallback.generate(prompt, output_path, size=size)
            raise
