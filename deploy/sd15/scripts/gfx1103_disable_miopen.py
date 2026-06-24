# 7940HS / 780M (gfx1103)：禁用 MIOpen，改用 PyTorch 备用卷积路径
# 由 deploy/sd15/sd-webui-ctl.sh 自动同步到 $SD_HOME/scripts/
import torch

import modules.scripts as scripts

torch.backends.cudnn.enabled = False
print("[gfx1103] torch.backends.cudnn.enabled = False (MIOpen off)")


class Script(scripts.Script):
    """占位 Script，确保本文件被 WebUI 加载（模块 import 时即执行上面的禁用逻辑）"""

    def title(self):
        return "gfx1103 MIOpen fix"

    def show(self, is_img2img):
        return False
