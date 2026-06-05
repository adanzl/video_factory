"""外部服务层。

约定：
- 每个子模块对外只暴露 *_mgr
- 基类 / 结果类型定义在 *_mgr 内
- 具体实现（*_ali、*_mock、image_wan 等）仅被 mgr 引用
- worker/stages 只 import *_mgr
- ffmpeg 底层工具在 media/ffmpeg_utils，成片编排在 media_mgr
"""
