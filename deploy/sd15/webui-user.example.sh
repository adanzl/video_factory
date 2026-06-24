#!/bin/bash
# 复制到 $SD_HOME/webui-user.sh（deploy.sh 会自动安装）
export HF_ENDPOINT=https://hf-mirror.com
export STABLE_DIFFUSION_REPO="https://github.com/w-e-w/stablediffusion.git"
export COMMANDLINE_ARGS="--skip-torch-cuda-test --lowvram --no-half --no-half-vae --upcast-sampling --opt-sdp-attention --nowebui --api --listen --port 9101 --disable-safe-unpickle --disable-nan-check"
