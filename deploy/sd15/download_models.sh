#!/bin/bash
# 底模 + LoRA 一键下载（魔搭 / hf-mirror，LoRA 全部走 HF）
set -euo pipefail

SD_HOME="${SD_HOME:-/mnt/data/stable-diffusion}"
HF="${HF_ENDPOINT:-https://hf-mirror.com}"
CKPT="$SD_HOME/models/Stable-diffusion"
LORA="$SD_HOME/models/Lora"

mkdir -p "$CKPT" "$LORA"

dl() {
  local url="$1" out="$2"
  if [[ -f "$out" && -s "$out" ]]; then
    echo "[skip] $out"
    return
  fi
  echo "[dl] $out"
  curl -fL --retry 3 --retry-delay 5 "$url" -o "$out"
}

echo "=== Checkpoints ==="

if command -v modelscope >/dev/null 2>&1; then
  modelscope download --model AI-ModelScope/realisticVisionV51_v51VAE --local_dir /tmp/rv51
  modelscope download --model ModelsLab/toonyou_beta6 --local_dir /tmp/toonyou
  find /tmp/rv51 -name "*.safetensors" -exec cp -f {} "$CKPT/RealisticVisionV51.safetensors" \;
  find /tmp/toonyou -name "*.safetensors" -exec cp -f {} "$CKPT/ToonYouBeta6.safetensors" \;
else
  dl "$HF/krnl/realisticVisionV51_v51VAE/resolve/main/realisticVisionV51_v51VAE.safetensors" \
    "$CKPT/RealisticVisionV51.safetensors"
  dl "$HF/frankjoshua/toonyou_beta6/resolve/main/toonyou_beta6.safetensors" \
    "$CKPT/ToonYouBeta6.safetensors"
fi

echo "=== LoRAs (life) ==="

dl "$HF/michecosta/food_mic/resolve/main/pytorch_lora_weights.safetensors" \
  "$LORA/Food_Photo.safetensors"
dl "$HF/minaiosu/tonade/resolve/main/room.safetensors" \
  "$LORA/Home_Interior.safetensors"
dl "$HF/phil329/face_lora_sd15/resolve/main/pytorch_lora_weights.safetensors" \
  "$LORA/Casual_Life.safetensors"
dl "$HF/casque/eddiemauroLora2_Elegant/resolve/main/eddiemauroLora2%20(Elegant).safetensors" \
  "$LORA/Product_Shot.safetensors"

echo "=== LoRAs (science) ==="

dl "$HF/whitebearhands/lineart-lora/resolve/main/pytorch_lora_weights.safetensors" \
  "$LORA/Textbook_Line_Art.safetensors"
cp -f "$LORA/Textbook_Line_Art.safetensors" "$LORA/Laboratory_Scene.safetensors"
cp -f "$LORA/Textbook_Line_Art.safetensors" "$LORA/Scientific_Equipment.safetensors"
dl "$HF/Miracle-2001/diagram-lora/resolve/main/pytorch_lora_weights.safetensors" \
  "$LORA/Simple_Diagram.safetensors"
dl "$HF/mnemic/ScienceDNAStyle-SD1.5-LoRA/resolve/main/ScienceDNAStyle.safetensors" \
  "$LORA/Science_DNA_Style.safetensors"

echo "=== Done ==="
ls -lh "$CKPT"/*.safetensors "$LORA"/*.safetensors 2>/dev/null || ls -lh "$CKPT" "$LORA"
