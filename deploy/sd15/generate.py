#!/usr/bin/env python3
"""SD1.5 dual-business txt2img client for A1111 API."""

import argparse
import base64
import json
import os
import time
from pathlib import Path

import httpx

SD_API_URL = os.environ.get("SD_API_URL", "http://127.0.0.1:7860").rstrip("/")
OUTPUT_DIR = os.environ.get("SD_OUTPUT_DIR", "output")

BUSINESS_CONFIG = {
    "life": {
        "checkpoint": "RealisticVisionV51.safetensors",
        "width": 768,
        "height": 576,
        "steps": 20,
        "negative": "cartoon, anime, illustration, painting, blurry, deformed, ugly, watermark, text, logo, oversaturated",
    },
    "science": {
        "checkpoint": "ToonYouBeta6.safetensors",
        "width": 576,
        "height": 768,
        "steps": 22,
        "negative": "photo, realistic, 3d render, shadow, gradient background, cluttered, text, watermark, blurry",
    },
}

LORA_WEIGHTS = {
    "Food_Photo": 0.6,
    "Home_Interior": 0.65,
    "Casual_Life": 0.6,
    "Product_Shot": 0.7,
    "Laboratory_Scene": 0.65,
    "Scientific_Equipment": 0.7,
    "Textbook_Line_Art": 0.7,
    "Simple_Diagram": 0.65,
}


def switch_checkpoint(client: httpx.Client, checkpoint: str):
    resp = client.post(f"{SD_API_URL}/sdapi/v1/options", json={"sd_model_checkpoint": checkpoint})
    resp.raise_for_status()


def generate_one(
    client: httpx.Client,
    business: str,
    lora: str,
    prompt: str,
    output: str,
    seed: int = -1,
):
    cfg = BUSINESS_CONFIG[business]
    weight = LORA_WEIGHTS.get(lora, 0.65)
    full_prompt = f"<lora:{lora}:{weight}> {prompt}"

    switch_checkpoint(client, cfg["checkpoint"])

    payload = {
        "prompt": full_prompt,
        "negative_prompt": cfg["negative"],
        "steps": cfg["steps"],
        "cfg_scale": 7,
        "width": cfg["width"],
        "height": cfg["height"],
        "sampler_name": "DPM++ 2M Karras",
        "batch_size": 1,
        "n_iter": 1,
        "seed": seed,
        "enable_hr": False,
    }

    print(f"[{business}] {lora} @ {cfg['width']}x{cfg['height']} — {prompt[:50]}...")
    t0 = time.time()
    resp = client.post(f"{SD_API_URL}/sdapi/v1/txt2img", json=payload, timeout=600.0)
    resp.raise_for_status()
    elapsed = time.time() - t0

    data = resp.json()
    img_bytes = base64.b64decode(data["images"][0])
    out_path = Path(OUTPUT_DIR) / output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(img_bytes)
    print(f"  -> {out_path} ({elapsed:.1f}s)")
    return out_path


def run_batch(tasks_file: str):
    with open(tasks_file, encoding="utf-8") as f:
        tasks = json.load(f)

    with httpx.Client() as client:
        for i, task in enumerate(tasks):
            print(f"--- [{i + 1}/{len(tasks)}] ---")
            generate_one(
                client,
                business=task["business"],
                lora=task["lora"],
                prompt=task["prompt"],
                output=task["output"],
                seed=task.get("seed", -1),
            )


def main():
    parser = argparse.ArgumentParser(description="SD1.5 dual-business image generator")
    parser.add_argument("--business", choices=["life", "science"], help="Business pipeline")
    parser.add_argument("--lora", help="LoRA filename without extension")
    parser.add_argument("--prompt", help="Prompt text (without lora tag)")
    parser.add_argument("--output", help="Output filename")
    parser.add_argument("--seed", type=int, default=-1)
    parser.add_argument("--batch", help="JSON file with task list")
    args = parser.parse_args()

    if args.batch:
        run_batch(args.batch)
        return

    if not all([args.business, args.lora, args.prompt, args.output]):
        parser.error("--business, --lora, --prompt, --output are required (or use --batch)")

    with httpx.Client() as client:
        generate_one(client, args.business, args.lora, args.prompt, args.output, args.seed)


if __name__ == "__main__":
    main()
