"""cg_algorithms 子模块共享的通用工具函数。

包含坐标取整、窗口规范化、曲线步数估算等底层 helper。
"""

import math


def _round_point(x, y):
    """浮点坐标统一取整，保证各模块输出像素坐标一致。

    所有算法模块通过此函数取整，避免各自调用 round() 时出现
    细微偏差（如 0.5 舍入方向不一致导致像素错位）。
    """
    return [int(round(x)), int(round(y))]


def normalize_window(x0, y0, x1, y1):
    """将任意对角顶点规范化为 (x_min, y_min, x_max, y_max)。

    用户可能以任意顺序给出矩形的两个对角点，
    统一为左下-右上形式后，裁剪、椭圆等算法无需自行判断顺序。
    """
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def compute_center(p_list):
    """返回点集的几何中心（取整）。

    取所有点 x/y 坐标各自的最小值与最大值的中点。
    用于变换操作（旋转、缩放）的参考中心点。

    >>> compute_center([[0, 0], [10, 10]])
    [5, 5]
    """
    xs = [point[0] for point in p_list]
    ys = [point[1] for point in p_list]
    return [int(round((min(xs) + max(xs)) / 2)), int(round((min(ys) + max(ys)) / 2))]


def _estimate_curve_steps(p_list):
    """估算曲线光栅化所需的采样步数。

    用控制多边形各段 max(|dx|, |dy|) 之和作为整条曲线的
    像素跨度估计，下限 100 步以保证光滑。这样在长曲线段
    自动提高采样密度，短曲线段不会浪费计算。

    这是一种启发式近似——实际贝塞尔/B样条弧长可能更大，
    但控制多边形的 Manhattan 长度在大多数情况下足够接近。
    """
    if len(p_list) < 2:
        return 1
    polyline = 0
    for i in range(1, len(p_list)):
        x0, y0 = p_list[i - 1]
        x1, y1 = p_list[i]
        polyline += max(abs(x1 - x0), abs(y1 - y0))
    return max(100, polyline)
