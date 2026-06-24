import os, json, asyncio, subprocess
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv()
AUTO_DL_URL = os.environ["AUTO_DL_URL"].rstrip("/")
SCRIPT_PATH = os.environ.get("SCRIPT_PATH", "script.json")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")


async def generate_clip(client, prompt, idx):
    resp = await client.post(
        f"{AUTO_DL_URL}/generate", json={"prompt": prompt, "seed": idx},
        timeout=600.0)
    resp.raise_for_status()
    path = Path(OUTPUT_DIR) / f"segment_{idx:03d}.mp4"
    path.write_bytes(resp.content)
    print(f"  -> {path}")
    return path


async def generate_narration(segments):
    texts = [s.get("narration") or s.get("text", "") for s in segments]
    full_text = "。".join(t for t in texts if t)
    path = Path(OUTPUT_DIR) / "narration.mp3"
    print(f"TTS ({len(full_text)} chars)...")
    proc = await yncio.create_subprocess_exec(
        "edge-tts", "--voice", "zh-CN-XiaoxiaoNeural",
        "--text", full_text, "--write-media", str(path),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()
    return path


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(SCRIPT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    segments = data["segments"]
    print(f"Loaded {len(segments)} segments")

    async with httpx.AsyncClient() as client:
        clips = []
        for i, seg in enumerate(segments):
            prompt = seg.get("visual_brief") or seg["prompt"]
            print(f"[{i+1}/{len(segments)}] {prompt[:40]}...")
            clips.append(await generate_clip(client, prompt, i))

        audio = await generate_narration(segments)

        concat = Path(OUTPUT_DIR) / "concat.txt"
        with open(concat, "w") as f:
            for p in clips:
                f.write(f"file '{p.absolute()}'\n")
        out = Path(OUTPUT_DIR) / "final.mp4"
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat), "-i", str(audio),
            "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
            str(out)], check=True, capture_output=True)
        print(f"\nDone: {out}")


if __name__ == "__main__":
    asyncio.run(main())
