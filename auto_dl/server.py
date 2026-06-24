import os, sys, argparse, logging
from datetime import datetime
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

REPO_DIR = os.environ.get("REPO_DIR", "/workspace/Wan2.2")
sys.path.insert(0, REPO_DIR)

from wan import WanTI2V
from wan.configs import WAN_CONFIGS, SIZE_CONFIGS, MAX_AREA_CONFIGS
from wan.utils.utils import save_video

MODEL_DIR = os.environ.get("CKPT_DIR", "/workspace/Wan2.2-TI2V-5B")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/workspace/output")
SAMPLE_STEPS = int(os.environ.get("SAMPLE_STEPS", "15"))
pipe = None
cfg = None
app = FastAPI(title="Wan2.2-TI2V-5B API")


class GenerateRequest(BaseModel):
    prompt: str
    seed: int = 42


@app.on_event("startup")
def load_model():
    global pipe, cfg
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
    cfg = WAN_CONFIGS["ti2v-5B"]
    logging.info(f"Loading model from {MODEL_DIR}, sample_steps={SAMPLE_STEPS}")
    pipe = WanTI2V(
        config=cfg, checkpoint_dir=MODEL_DIR, device_id=0, rank=0,
        t5_fsdp=False, dit_fsdp=False, use_sp=False, t5_cpu=True,
        convert_model_dtype=True,
    )
    logging.info("Model loaded")


@app.post("/generate")
async def generate(req: GenerateRequest):
    if pipe is None:
        raise HTTPException(503, "Not loaded yet")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{ts}_{req.seed}_{req.prompt.replace(' ','_')[:50]}.mp4"
    path = os.path.join(OUTPUT_DIR, name)
    logging.info(f"Generating: {req.prompt[:60]}...")
    try:
        video = pipe.generate(
            req.prompt, size=SIZE_CONFIGS["1280*704"],
            max_area=MAX_AREA_CONFIGS["1280*704"], frame_num=cfg.frame_num,
            shift=cfg.sample_shift, sample_solver="unipc",
            sampling_steps=SAMPLE_STEPS, guide_scale=cfg.sample_guide_scale,
            seed=req.seed, offload_model=True)
        save_video(tensor=video[None], save_file=path,
                   fps=cfg.sample_fps, nrow=1, normalize=True, value_range=(-1, 1))
        return FileResponse(path, media_type="video/mp4")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/health")
async def health():
    return {"status": "ok", "loaded": pipe is not None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--sample_steps", type=int)
    args = parser.parse_args()
    if args.sample_steps:
        SAMPLE_STEPS = args.sample_steps
    uvicorn.run(app, host=args.host, port=args.port)
