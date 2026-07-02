"""cg_dialogs 的内部实现包。

以下划线开头表示这是实现细节，不应被外部直接 import。
外部应通过 cg_dialogs 模块访问这些对话框类。
各对话框按功能拆分到独立模块：
  - _canvas   : 画布尺寸设置
  - _transform: 裁剪窗口设置
  - _algorithm: 算法对比与演示
"""

from _cg_dialogs._canvas import CanvasSizeDialog
from _cg_dialogs._transform import ClipWindowDialog
from _cg_dialogs._algorithm import AlgorithmCompareDialog, AlgorithmDemoDialog

__all__ = [
    "CanvasSizeDialog",
    "ClipWindowDialog",
    "AlgorithmCompareDialog",
    "AlgorithmDemoDialog",
]
