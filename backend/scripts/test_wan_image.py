"""快速测试 wan2.6 出图效果。"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
TEST_OUTPUT_DIR = ROOT_DIR / "data/media/test"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.segment.image.image_wan import WanImageProvider

TEST_PROMPTS = [
    # 科普：人体细胞
    "电影级写实科普画面，显微视角下的人体细胞分裂过程，"
    "中心是一个正在分裂的细胞，染色体清晰可见，周围有流动的细胞质，"
    "柔和的生物荧光蓝紫色调，景深效果突出主体，细节真实可辨。",

    # 科普：地球板块
    "电影级写实科普画面，俯视地球板块俯冲带，"
    "两块大陆板块碰撞挤压，一侧板块俯冲入地幔，熔岩从缝隙中涌出，"
    "远处有海洋和云层，暖色调熔岩与冷色海洋形成对比，大气透视感强。",

    # 科普：磁铁原理（对比）
    "电影级写实科普画面，左右并排展示两块条形磁铁，"
    "左侧同极相对（N-N），用红色叉号和排斥箭头表示相斥，"
    "右侧异极相对（N-S），用绿色对勾和吸引箭头表示相吸，"
    "磁铁表面金属质感真实，背景干净柔和的浅灰色，光线均匀明亮。",
]

def main():
    settings = get_settings()
    print(f"Model: {settings.wan_model}")
    print(f"Size: {settings.wan_image_size}")
    print(f"Prompt extend: {settings.wan_prompt_extend}")
    print(f"API key set: {bool(settings.dashscope_api_key)}\n")

    provider = WanImageProvider()
    out_dir = TEST_OUTPUT_DIR
    out_dir.mkdir(exist_ok=True)

    for i, prompt in enumerate(TEST_PROMPTS, 1):
        out_path = out_dir / f"test_{i}.png"
        print(f"[{i}/3] Generating: {prompt[:60]}...")
        try:
            result = provider.generate(prompt, out_path)
            print(f"  -> Saved: {result}")
        except Exception as e:
            print(f"  -> Failed: {e}")

if __name__ == "__main__":
    main()
