#!/bin/bash
set -e
WORKSPACE=${WORKSPACE:-/workspace}
MODEL_DIR=${MODEL_DIR:-$WORKSPACE/Wan2.2-TI2V-5B}
REPO_DIR=$WORKSPACE/Wan2.2
OUTPUT_DIR=$WORKSPACE/output
SERVER_PORT=${SERVER_PORT:-8000}
echo "=== Wan2.2 AutoDL Deployment ==="
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/5] Cloning Wan2.2..."
    git clone https://github.com/Wan-Video/Wan2.2.git "$REPO_DIR"
else
    echo "[1/5] Wan2.2 already cloned"
fi
cd "$REPO_DIR"
echo "[2/5] Installing dependencies..."
pip install -q -r requirements.txt
pip install -q fastapi uvicorn python-multipart modelscope
if [ ! -f "$MODEL_DIR/config.json" ]; then
    echo "[3/5] Downloading Wan2.2-TI2V-5B (~12GB, may take a while)..."
    mkdir -p "$MODEL_DIR"
    modelscope download Wan-AI/Wan2.2-TI2V-5B --local_dir "$MODEL_DIR"
else
    echo "[3/5] Model already downloaded"
fi
mkdir -p "$OUTPUT_DIR"
echo "[4/5] Writing server.py..."
cat > "$WORKSPACE/server.py" << 'PYEOF'
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
    logging.info(f"Loading model from {MODEL_DIR}")
    logging.info(f"Config: sample_steps={SAMPLE_STEPS}, fps={cfg.sample_fps}, frames={cfg.frame_num}")
    pipe = WanTI2V(config=cfg, checkpoint_dir=MODEL_DIR, device_id=0, rank=0,
        t5_fsdp=False, dit_fsdp=False, use_sp=False, t5_cpu=True, convert_model_dtype=True)
    logging.info("Model loaded successfully")
@app.post("/generate")
async def generate(req: GenerateRequest):
    if pipe is None:
        raise HTTPException(503, "Model not loaded yet")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_prompt = req.prompt.replace(" ", "_").replace("/", "_")[:50]
    filename = f"{timestamp}_{req.seed}_{safe_prompt}.mp4"
    output_path = os.path.join(OUTPUT_DIR, filename)
    logging.info(f"Generating: prompt='{req.prompt[:60]}...', seed={req.seed}")
    try:
        video = pipe.generate(req.prompt, size=SIZE_CONFIGS["1280*704"],
            max_area=MAX_AREA_CONFIGS["1280*704"], frame_num=cfg.frame_num,
            shift=cfg.sample_shift, sample_solver="unipc",
            sampling_steps=SAMPLE_STEPS, guide_scale=cfg.sample_guide_scale,
            seed=req.seed, offload_model=True)
        save_video(tensor=video[None], save_file=output_path,
            fps=cfg.sample_fps, nrow=1, normalize=True, value_range=(-1, 1))
        logging.info(f"Saved to {output_path}")
        return FileResponse(output_path, media_type="video/mp4")
    except Exception as e:
        logging.error(f"Generation failed: {e}")
        raise HTTPException(500, str(e))
@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": pipe is not None}
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--sample_steps", type=int, default=None)
    args = parser.parse_args()
    if args.sample_steps:
        SAMPLE_STEPS = args.sample_steps
    uvicorn.run(app, host=args.host, port=args.port)
PYEOF
echo "[5/5] Starting server on port $SERVER_PORT..."
nohup python "$WORKSPACE/server.py" --port "$SERVER_PORT" > "$WORKSPACE/server.log" 2>&1 &
SERVER_PID=$!
sleep 5
if kill -0 $SERVER_PID 2>/dev/null; then
    echo "Server started! PID: $SERVER_PID | Logs: tail -f $WORKSPACE/server.log"
else
    echo "Server failed. Check logs:"; tail -20 "$WORKSPACE/server.log"; exit 1
fi
