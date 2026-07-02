"""仿射变换：平移、旋转、缩放。

所有变换返回取整后的像素坐标。
"""

import math

from _cg_algorithms._utils import _round_point


def translate(p_list, dx, dy):
    """平移：所有点加上偏移量 (dx, dy)。

    平移不改变点间相对位置，无需中心点。
    """
    return [[x + dx, y + dy] for x, y in p_list]


def rotate(p_list, x, y, r):
    """绕点 (x, y) 逆时针旋转 r 度。

    先将参考点平移到原点、旋转、再平移回去。
    使用 math.radians 转换角度制到弧度制，
    cos/sin 预计算避免循环内重复调用三角函数。
    """
    rad = math.radians(r)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)
    result = []
    for px, py in p_list:
        tx = px - x
        ty = py - y
        rx = tx * cos_r - ty * sin_r
        ry = tx * sin_r + ty * cos_r
        result.append(_round_point(x + rx, y + ry))
    return result


def scale(p_list, x, y, s):
    """以 (x, y) 为基准点缩放，s 为缩放因子。

    s > 1 放大，0 < s < 1 缩小。
    同样采用"平移到原点 → 缩放 → 平移回去"的套路。
    """
    result = []
    for px, py in p_list:
        sx = x + (px - x) * s
        sy = y + (py - y) * s
        result.append(_round_point(sx, sy))
    return result
