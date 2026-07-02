"""GUI 对话框模块。

实现被组织在 _cg_dialogs/ 子包中以保持代码整洁，
本文件作为单文件入口，重导出所有对话框类。
"""

from _cg_dialogs._algorithm import AlgorithmCompareDialog, AlgorithmDemoDialog
from _cg_dialogs._canvas import CanvasSizeDialog
from _cg_dialogs._transform import ClipWindowDialog

__all__ = [
    'AlgorithmCompareDialog',
    'AlgorithmDemoDialog',
    'CanvasSizeDialog',
    'ClipWindowDialog',
]