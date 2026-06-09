"""外部服务层。

约定：
- 每个子模块对外只暴露 *_mgr
- 基类 / 结果类型定义在 *_mgr 内
- 具体实现（*_ali、*_mock、image_wan 等）仅被 mgr 引用
- worker/stages 只 import *_mgr
- 分镜编排在 services/segment/segment_mgr；media/ffmpeg_utils 等为底层工具
"""
