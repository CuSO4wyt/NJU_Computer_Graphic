"""
cg_algorithms 实现被组织在 _cg_algorithms/ 子包中以保持代码整洁，
本文件作为单文件入口重导出所有公开函数。
"""

from _cg_algorithms._clip import clip, clip_polygon
from _cg_algorithms._curves import draw_curve, draw_ellipse
from _cg_algorithms._fill import fill_polygon
from _cg_algorithms._lines import draw_line, draw_line_wu, draw_polygon, draw_polyline
from _cg_algorithms._trace import trace_bezier, trace_clip, trace_line
from _cg_algorithms._transforms import rotate, scale, translate
from _cg_algorithms._utils import compute_center, normalize_window

__all__ = [
    # lines
    'draw_line',
    'draw_line_wu',
    'draw_polyline',
    'draw_polygon',
    # curves
    'draw_ellipse',
    'draw_curve',
    # transforms
    'translate',
    'rotate',
    'scale',
    # clip
    'clip',
    'clip_polygon',
    # fill
    'fill_polygon',
    # trace
    'trace_line',
    'trace_clip',
    'trace_bezier',
    # utils
    'compute_center',
    'normalize_window',
]