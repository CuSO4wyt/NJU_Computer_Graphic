"""曲线绘制算法：中点椭圆、de Casteljau Bezier、三次均匀 B 样条。

椭圆使用中点法避免浮点三角函数，仅用整数加减；
Bezier 与 B 样条均采用离散采样后交给 Bresenham 画线。
"""

from _cg_algorithms._lines import draw_polyline
from _cg_algorithms._utils import _estimate_curve_steps, _round_point, normalize_window


def draw_ellipse(p_list):
    """中点椭圆生成算法。

    给定对角两点确定的包围盒，绘制中心对齐的椭圆。
    将椭圆分为两个区域：斜率 |dy/dx| < 1 的区域 I 和 > 1 的区域 II。
    区域 I 用 dx 作为判别基础，区域 II 用 dy 作为判别基础，
    这样在每个区域中步进量始终为 1，不会出现像素跳跃。
    利用四对称性同时绘制四个象限，减少 3/4 的计算量。
    """
    (x0, y0), (x1, y1) = p_list
    x_min, y_min, x_max, y_max = normalize_window(x0, y0, x1, y1)
    rx = (x_max - x_min) / 2.0
    ry = (y_max - y_min) / 2.0
    xc = (x_min + x_max) / 2.0
    yc = (y_min + y_max) / 2.0

    if rx == 0 and ry == 0:
        return [[int(round(xc)), int(round(yc))]]

    def add_symmetric_points(px, py, points):
        # 四对称：将当前第一象限的点镜像到其余三个象限
        for sx in (-1, 1):
            for sy in (-1, 1):
                points.append(_round_point(xc + sx * px, yc + sy * py))

    result = []
    x = 0.0
    y = ry
    rx2 = rx * rx
    ry2 = ry * ry
    dx = 2 * ry2 * x
    dy = 2 * rx2 * y

    # 区域 I：|切线斜率| < 1，x 每次步进 1
    p1 = ry2 - rx2 * ry + 0.25 * rx2
    while dx < dy:
        add_symmetric_points(x, y, result)
        x += 1
        dx = 2 * ry2 * x
        if p1 < 0:
            p1 += dx + ry2
        else:
            y -= 1
            dy = 2 * rx2 * y
            p1 += dx - dy + ry2

    # 区域 II：|切线斜率| >= 1，y 每次步进 1（递减）
    # 决策参数初始值由区域 I 结束时的 (x, y) 计算
    p2 = ry2 * (x + 0.5) * (x + 0.5) + rx2 * (y - 1) * (y - 1) - rx2 * ry2
    while y >= 0:
        add_symmetric_points(x, y, result)
        y -= 1
        dy = 2 * rx2 * y
        if p2 > 0:
            p2 += rx2 - dy
        else:
            x += 1
            dx = 2 * ry2 * x
            p2 += dx - dy + rx2

    # 四对称会产生大量重复点（尤其是坐标轴上的点），去重
    unique = []
    seen = set()
    for point in result:
        key = (point[0], point[1])
        if key not in seen:
            unique.append(point)
            seen.add(key)
    return unique


def draw_curve(p_list, algorithm):
    """自由曲线离散采样后连接为像素集。

    algorithm='Bezier'：de Casteljau 递推求值，对每条片段采样后连线。
    algorithm='B-spline'：三次均匀 B 样条，每四个控制点生成一段曲线，
    自动保证 C2 连续性（基函数系数和为 1，落在凸包内）。
    """
    if algorithm == 'Bezier':
        sampled = []
        steps = _estimate_curve_steps(p_list)
        for i in range(steps + 1):
            t = i / steps
            # de Casteljau：对每一层相邻点做线性插值，
            # 逐层减少点数，最终只剩一个点即为 B(t)
            points = [[float(x), float(y)] for x, y in p_list]
            while len(points) > 1:
                next_points = []
                for j in range(len(points) - 1):
                    x = (1 - t) * points[j][0] + t * points[j + 1][0]
                    y = (1 - t) * points[j][1] + t * points[j + 1][1]
                    next_points.append([x, y])
                points = next_points
            sampled.append(_round_point(points[0][0], points[0][1]))
        return draw_polyline(sampled, 'Bresenham')

    if algorithm == 'B-spline':
        if len(p_list) < 4:
            return []
        sampled = []
        # 每段采样数 = max(40, 总估算步数 / 段数)，保证短曲线也不会太稀疏
        steps = max(40, _estimate_curve_steps(p_list) // max(1, len(p_list) - 3))
        for i in range(len(p_list) - 3):
            p0, p1, p2, p3 = p_list[i:i + 4]
            for j in range(steps + 1):
                u = j / steps
                # 三次均匀 B 样条基函数（推导自节点向量 [0,1,2,3,4]）
                b0 = (1 - 3 * u + 3 * u * u - u * u * u) / 6.0
                b1 = (4 - 6 * u * u + 3 * u * u * u) / 6.0
                b2 = (1 + 3 * u + 3 * u * u - 3 * u * u * u) / 6.0
                b3 = (u * u * u) / 6.0
                x = b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0]
                y = b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]
                point = _round_point(x, y)
                # 相邻段在接缝处的采样点可能完全重复，跳过
                if not sampled or sampled[-1] != point:
                    sampled.append(point)
        return draw_polyline(sampled, 'Bresenham')

    raise ValueError(f'Unsupported curve algorithm: {algorithm}')
