#!/usr/bin/env python3
"""
Optional LoRA size reduction via fp16 cast (not true INT4).
True INT4 LoRA requires kohya/sd-scripts or similar toolchain.
This script halves file size by storing weights in float16.
"""

import argparse
import shutil
from pathlib import Path

from safetensors.torch import load_file, save_file


def quantize_lora(input_path: Path, output_path: Path):
    tensors = load_file(str(input_path))
    fp16 = {k: v.to(dtype=__import__("torch").float16) for k, v in tensors.items()}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_file(fp16, str(output_path))
    orig_mb = input_path.stat().st_size / 1024 / 1024
    new_mb = output_path.stat().st_size / 1024 / 1024
    print(f"  {input_path.name}: {orig_mb:.1f}MB -> {new_mb:.1f}MB")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    inp = Path(args.input_dir)
    out = Path(args.output_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()

    files = sorted(inp.glob("*.safetensors"))
    if not files:
        print(f"No .safetensors found in {inp}")
        return

    print(f"Processing {len(files)} LoRA files...")
    for f in files:
        quantize_lora(f, out / f.name)
    print(f"Done. Output: {out}")


if __name__ == "__main__":
    main()
