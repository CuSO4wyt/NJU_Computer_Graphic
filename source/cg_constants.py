"""跨模块共享的常量 —— 画布尺寸界限、撤销栈上限、吸附步长等。"""

# 画布默认尺寸及硬性边界（防止过大导致渲染卡顿或内存问题）
DEFAULT_CANVAS_WIDTH = 600
DEFAULT_CANVAS_HEIGHT = 600
CANVAS_SIZE_MIN = 100
CANVAS_SIZE_MAX = 1000

# 撤销/重做栈最大深度，超过则丢弃最旧记录
UNDO_STACK_LIMIT = 50

# 网格吸附/拖动对齐的默认步长（像素）
SNAP_DEFAULT_STEP = 10