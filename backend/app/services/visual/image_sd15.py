"""本地 SD1.5（A1111 WebUI API）文生图 ImageProvider。"""

from __future__ import annotations

import base64
import io
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image

from app.config import get_settings
from app.services.llm.llm_mgr import llm_mgr
from app.services.llm.llm_sd15_prompt import (
    build_sd15_full_prompt,
    fallback_split_panel_prompts,
    pick_business_by_keywords,
    pick_lora_by_keywords,
    resolve_split_layout,
    science_wants_anime,
)
from app.services.visual.image_mock import MockImageProvider
from app.services.visual.visual_mgr import ImageProvider

logger = logging.getLogger(__name__)

_ANIME_CHECKPOINT = "ToonYouBeta6.safetensors"
_LIFE_CHECKPOINT = "RealisticVisionV51.safetensors"
# Deliberate v6 SFW：对科普插画/线稿/示意图 LoRA 亲和性比 DreamShaper 好，背景更干净
# 下载：hf-mirror.com/XpucT/Deliberate → Deliberate_v6 (SFW).safetensors
_SCIENCE_ILLUSTRATION_CHECKPOINT = "Deliberate_v6_SFW.safetensors"
# 分镜右半（医学截面）继续用 RealisticVision，写实解剖效果更好
_SCIENCE_MEDICAL_CHECKPOINT = "RealisticVisionV51.safetensors"

_BUSINESS_CONFIG = {
    "life": {
        "checkpoint": _LIFE_CHECKPOINT,
        "steps": 20,
        "cfg_scale": 7,
        "negative": (
            "cartoon, anime, illustration, painting, blurry, deformed, ugly, "
            "watermark, text, logo, oversaturated, "
            "jpeg artifacts, compression artifacts, duplicate, extra fingers, mutated hands"
        ),
    },
    "science": {
        "checkpoint": _SCIENCE_ILLUSTRATION_CHECKPOINT,
        "steps": 25,
        "cfg_scale": 8.5,
        "negative": (
            "anime, cartoon, manga, chibi, girl, boy, woman, man, face, portrait, "
            "hair, eyes, glowing eyes, superhero, deformed, ugly, watermark, text, "
            "logo, blurry, cluttered, busy background, cluttered background, "
            "low contrast, out of frame, cropped, bad anatomy, landscape"
        ),
    },
}

_SCIENCE_SPLIT_PANELS = {
    "left": {
        "checkpoint": _SCIENCE_ILLUSTRATION_CHECKPOINT,
        "negative": (
            "text, words, letters, lung, anatomy, organ, person, face, portrait, "
            "landscape, low quality, blurry, watermark, deformed, "
            "busy background, out of frame"
        ),
    },
    "right": {
        "checkpoint": _SCIENCE_MEDICAL_CHECKPOINT,
        "negative": (
            "text, words, letters, watermark, caption, typography, cloth, fabric, "
            "landscape, low quality, blurry, deformed, anime, cartoon, "
            "busy background, out of frame, oversaturated"
        ),
    },
}


def _resolve_checkpoint(*, business: str, prompt: str, panel: str = "single") -> str:
    if business == "science" and science_wants_anime(prompt):
        return _ANIME_CHECKPOINT
    if panel == "right":
        return _SCIENCE_SPLIT_PANELS["right"]["checkpoint"]
    if panel == "left":
        return _SCIENCE_SPLIT_PANELS["left"]["checkpoint"]
    return _BUSINESS_CONFIG[business]["checkpoint"]


def parse_image_size(size: str) -> tuple[int, int]:
    normalized = size.strip().lower().replace("x", "*")
    w_str, h_str = normalized.split("*", 1)
    return int(w_str.strip()), int(h_str.strip())


@dataclass(frozen=True)
class _Sd15PromptPrep:
    business: str
    lora: str
    layout: str
    split_axis: str = "horizontal"
    prompt_en: str = ""
    left_en: str = ""
    right_en: str = ""


def _fallback_prompt_en(prompt: str) -> str:
    cleaned = prompt.strip()
    if not cleaned:
        return "illustration, soft lighting"
    if not re.search(r"[\u3400-\u9fff]", cleaned):
        return cleaned
    return "illustration, educational scene, soft lighting, clean composition"


def _fallback_business(*, prompt: str, business_override: str | None) -> str:
    if business_override in _BUSINESS_CONFIG:
        return business_override
    return pick_business_by_keywords(prompt)


def _is_sd15_ready_prompt(text: str) -> bool:
    """判断是否为预处理过的英文短 prompt（无中文、词数 ≤ 60）。
    此类 prompt 来自 sd15_prompt_en 字段，已在脚本阶段由 LLM 生成，可跳过二次翻译。
    """
    if re.search(r"[㐀-鿿一-鿿]", text):
        return False
    word_count = len(text.split())
    return 0 < word_count <= 60


def _resolve_layout(
    *,
    result: dict[str, str] | None,
    prompt: str,
    business: str,
    width: int,
    height: int,
) -> tuple[str, str]:
    return resolve_split_layout(
        result=result,
        prompt=prompt,
        business=business,
        width=width,
        height=height,
    )


def _prepare_sd15_prompt(
    prompt: str,
    *,
    size_hint: str | None = None,
    business_override: str | None = None,
) -> _Sd15PromptPrep:
    cleaned = prompt.strip()
    if not cleaned:
        raise ValueError("prompt is required")

    width, height = parse_image_size(size_hint) if size_hint else (0, 0)
    settings = get_settings()

    # ── 快速通道：传入已是英文短 prompt（来自 sd15_prompt_en），跳过 LLM 翻译 ──
    if _is_sd15_ready_prompt(cleaned):
        business = _fallback_business(prompt=cleaned, business_override=business_override)
        lora = pick_lora_by_keywords(cleaned)
        from app.services.llm.llm_sd15_prompt import normalize_sd15_prompt_en
        prompt_en = normalize_sd15_prompt_en(cleaned, business=business, lora=lora)
        logger.info(
            "sd15 prompt prep fast-path (sd15_prompt_en): business=%s lora=%s prompt_en=%s",
            business,
            lora,
            prompt_en,
        )
        return _Sd15PromptPrep(
            business=business,
            lora=lora,
            layout="single",
            prompt_en=prompt_en,
        )

    llm_result: dict[str, str] | None = None

    if settings.deepseek_api_key:
        try:
            llm_result = llm_mgr.prepare_sd15_image_prompt(
                cleaned,
                size_hint=size_hint,
                business_override=business_override,
            )
            logger.info(
                "sd15 prompt prep llm: layout=%s business=%s lora=%s payload=%s",
                llm_result.get("layout", "single"),
                llm_result["business"],
                llm_result["lora"],
                llm_result,
            )
        except Exception as exc:
            logger.warning("sd15 prompt prep llm failed, using fallback: %s", exc)

    if llm_result:
        business = llm_result["business"]
        lora = llm_result["lora"]
        layout, split_axis = _resolve_layout(
            result=llm_result,
            prompt=cleaned,
            business=business,
            width=width,
            height=height,
        )
        if layout == "split":
            left_en = llm_result.get("left_en", "")
            right_en = llm_result.get("right_en", "")
            if not left_en or not right_en:
                left_en, right_en = fallback_split_panel_prompts(cleaned)
            return _Sd15PromptPrep(
                business=business,
                lora=lora,
                layout="split",
                split_axis=split_axis,
                left_en=left_en,
                right_en=right_en,
            )
        return _Sd15PromptPrep(
            business=business,
            lora=lora,
            layout="single",
            prompt_en=llm_result.get("prompt_en", ""),
        )

    lora = pick_lora_by_keywords(cleaned)
    business = _fallback_business(prompt=cleaned, business_override=business_override)
    layout, split_axis = _resolve_layout(
        result=None,
        prompt=cleaned,
        business=business,
        width=width,
        height=height,
    )
    if layout == "split":
        left_en, right_en = fallback_split_panel_prompts(cleaned)
        logger.info(
            "sd15 prompt prep fallback split: axis=%s business=%s lora=%s left=%s right=%s",
            split_axis,
            business,
            lora,
            left_en,
            right_en,
        )
        return _Sd15PromptPrep(
            business=business,
            lora=lora,
            layout="split",
            split_axis=split_axis,
            left_en=left_en,
            right_en=right_en,
        )

    from app.services.llm.llm_sd15_prompt import normalize_sd15_prompt_en

    prompt_en = normalize_sd15_prompt_en(
        _fallback_prompt_en(cleaned),
        business=business,
        lora=lora,
    )
    logger.info(
        "sd15 prompt prep fallback: business=%s lora=%s prompt_en=%s",
        business,
        lora,
        prompt_en,
    )
    return _Sd15PromptPrep(
        business=business,
        lora=lora,
        layout="single",
        prompt_en=prompt_en,
    )


def _stitch_vertical(top_bytes: bytes, bottom_bytes: bytes) -> bytes:
    top_img = Image.open(io.BytesIO(top_bytes)).convert("RGB")
    bottom_img = Image.open(io.BytesIO(bottom_bytes)).convert("RGB")
    width = max(top_img.width, bottom_img.width)
    total_h = top_img.height + bottom_img.height
    canvas = Image.new("RGB", (width, total_h))
    canvas.paste(top_img, (0, 0))
    canvas.paste(bottom_img, (0, top_img.height))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def _stitch_horizontal(left_bytes: bytes, right_bytes: bytes) -> bytes:
    left_img = Image.open(io.BytesIO(left_bytes)).convert("RGB")
    right_img = Image.open(io.BytesIO(right_bytes)).convert("RGB")
    total_w = left_img.width + right_img.width
    height = max(left_img.height, right_img.height)
    canvas = Image.new("RGB", (total_w, height))
    canvas.paste(left_img, (0, 0))
    canvas.paste(right_img, (left_img.width, 0))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


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

        business = self._business_override or "prompt_infer"
        lora_hint = "llm_pick|" + "|".join(SD15_LORAS)
        resolved_size = size or self._default_size
        return (
            f"provider=sd15_t2i, api={self._api_url}, business={business}, "
            f"lora={lora_hint}, checkpoints=life:{_LIFE_CHECKPOINT}|"
            f"science:{_SCIENCE_ILLUSTRATION_CHECKPOINT}|"
            f"science_medical:{_SCIENCE_MEDICAL_CHECKPOINT}|anime:{_ANIME_CHECKPOINT}, "
            f"layout=split_science, size={resolved_size}"
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

    def _txt2img(
        self,
        *,
        full_prompt: str,
        negative_prompt: str,
        checkpoint: str,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int = -1,
    ) -> bytes:
        self._switch_checkpoint(checkpoint)
        payload = {
            "prompt": full_prompt,
            "negative_prompt": negative_prompt,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "width": width,
            "height": height,
            "sampler_name": "DPM++ 2M",
            "scheduler": "Karras",
            "batch_size": 1,
            "n_iter": 1,
            "seed": seed,
            "enable_hr": False,
        }
        resp = requests.post(
            f"{self._api_url}/sdapi/v1/txt2img",
            json=payload,
            timeout=self._timeout_sec,
        )
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["images"][0])

    def _generate_split(
        self,
        prep: _Sd15PromptPrep,
        *,
        width: int,
        height: int,
        cfg: dict,
        prompt: str,
    ) -> bytes:
        first_prompt = build_sd15_full_prompt(
            subject=prep.left_en,
            business=prep.business,
            lora=prep.lora,
            layout="split",
            panel="left",
            source_prompt=prompt,
        )
        second_prompt = build_sd15_full_prompt(
            subject=prep.right_en,
            business=prep.business,
            lora=prep.lora,
            layout="split",
            panel="right",
            source_prompt=prompt,
        )
        first_cfg = _SCIENCE_SPLIT_PANELS["left"]
        second_cfg = _SCIENCE_SPLIT_PANELS["right"]
        vertical = prep.split_axis == "vertical"
        if vertical:
            panel_w, panel_h = width, height // 2
        else:
            panel_w, panel_h = width // 2, height

        logger.info(
            "sd15 split request: axis=%s lora=%s panel=%s*%s "
            "first_checkpoint=%s second_checkpoint=%s first_prompt=%s second_prompt=%s",
            prep.split_axis,
            prep.lora,
            panel_w,
            panel_h,
            first_cfg["checkpoint"],
            second_cfg["checkpoint"],
            first_prompt,
            second_prompt,
        )
        first_bytes = self._txt2img(
            full_prompt=first_prompt,
            negative_prompt=first_cfg["negative"],
            checkpoint=_resolve_checkpoint(business=prep.business, prompt=prompt, panel="left"),
            width=panel_w,
            height=panel_h,
            steps=cfg["steps"],
            cfg_scale=cfg["cfg_scale"],
            seed=42,
        )
        second_bytes = self._txt2img(
            full_prompt=second_prompt,
            negative_prompt=second_cfg["negative"],
            checkpoint=_resolve_checkpoint(business=prep.business, prompt=prompt, panel="right"),
            width=panel_w,
            height=panel_h,
            steps=cfg["steps"],
            cfg_scale=cfg["cfg_scale"],
            seed=99,
        )
        if vertical:
            return _stitch_vertical(first_bytes, second_bytes)
        return _stitch_horizontal(first_bytes, second_bytes)

    def generate(self, prompt: str, output_path: Path, *, size: str | None = None) -> Path:
        size = size or self._default_size
        prep = _prepare_sd15_prompt(
            prompt,
            size_hint=size,
            business_override=self._business_override,
        )
        business = prep.business
        cfg = self._cfg_for_business(business)
        api_width, api_height = parse_image_size(size)

        logger.info(
            "sd15 request: layout=%s axis=%s business=%s lora=%s job_size=%s api=%s*%s",
            prep.layout,
            prep.split_axis,
            business,
            prep.lora,
            size,
            api_width,
            api_height,
        )
        try:
            if prep.layout == "split":
                img_bytes = self._generate_split(
                    prep,
                    width=api_width,
                    height=api_height,
                    cfg=cfg,
                    prompt=prompt,
                )
            else:
                checkpoint = _resolve_checkpoint(business=business, prompt=prompt)
                full_prompt = build_sd15_full_prompt(
                    subject=prep.prompt_en,
                    business=business,
                    lora=prep.lora,
                    source_prompt=prompt,
                )
                logger.info(
                    "sd15 single request: checkpoint=%s prompt_en=%s full_prompt=%s",
                    checkpoint,
                    prep.prompt_en,
                    full_prompt,
                )
                img_bytes = self._txt2img(
                    full_prompt=full_prompt,
                    negative_prompt=cfg["negative"],
                    checkpoint=checkpoint,
                    width=api_width,
                    height=api_height,
                    steps=cfg["steps"],
                    cfg_scale=cfg["cfg_scale"],
                )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(img_bytes)
            return output_path
        except Exception as exc:
            logger.error("sd15 generate failed: %s", exc)
            if get_settings().mock_mode:
                return self._fallback.generate(prompt, output_path, size=size)
            raise
