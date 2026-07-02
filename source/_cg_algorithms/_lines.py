"""直线段扫描转换算法：Naive、DDA、Bresenham、Wu 反走样。

同时包含由线段组合而成的折线（polyline）和多边形（polygon）。
"""

import math

from _cg_algorithms._utils import _round_point


def draw_polyline(p_list, algorithm='Bresenham'):
    """将有序点列表用指定线段算法连接为连续像素列表。

    相邻相同点会被跳过（不会产生零长度线段）。
    相邻线段共享的端点会自动去重（只保留第一个），
    否则 Bresenham 等算法会在连接处重复绘制同一个像素。
    """
    result = []
    if len(p_list) < 2:
        return result
    for i in range(1, len(p_list)):
        segment = draw_line([p_list[i - 1], p_list[i]], algorithm)
        if result and segment:
            result.extend(segment[1:])
        else:
            result.extend(segment)
    return result


def draw_line(p_list, algorithm):
    """单条线段的像素级扫描转换。

    algorithm 可选 'Naive'、'DDA'、'Bresenham'。
    返回值是构成线段的像素点列表 [[x, y], ...]。
    """
    x0, y0 = p_list[0]
    x1, y1 = p_list[1]
    result = []

    if algorithm == 'Naive':
        # 朴素算法：用直线方程 y = y0 + k(x - x0) 逐 x 计算。
        # 仅处理 |k| <= 1 的情况（对竖线特殊处理），
        # 因此当线段接近垂直时效率正常但水平拉伸像素较多。
        if x0 == x1:
            y_start, y_end = sorted((y0, y1))
            for y in range(y_start, y_end + 1):
                result.append([x0, y])
        else:
            if x0 > x1:
                x0, y0, x1, y1 = x1, y1, x0, y0
            k = (y1 - y0) / (x1 - x0)
            for x in range(x0, x1 + 1):
                result.append([x, int(round(y0 + k * (x - x0)))])
    elif algorithm == 'DDA':
        # 数字微分分析器：以 max(|dx|, |dy|) 为步数，保证
        # 每一步在 x 或 y 方向恰好前进 1 单位，不会出现断点。
        dx = x1 - x0
        dy = y1 - y0
        steps = max(abs(dx), abs(dy))
        if steps == 0:
            return [[x0, y0]]
        x_increment = dx / steps
        y_increment = dy / steps
        x = x0
        y = y0
        for _ in range(steps + 1):
            result.append(_round_point(x, y))
            x += x_increment
            y += y_increment
    elif algorithm == 'Bresenham':
        # 中点 Bresenham：只用整数加减法与位移，避免浮点乘除。
        # 核心思想——每步在 x 方向前进 1，根据误差项 p
        # 决定 y 是否也前进 1，使实际像素最接近理想直线。
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        # 若斜率绝对值 > 1，交换 x 和 y 的角色逐 y 推进，
        # 保证主方向始终是 x（步进方向），避免像素稀疏。
        steep = dy > dx
        if steep:
            x0, y0 = y0, x0
            x1, y1 = y1, x1
            dx, dy = dy, dx
            sx, sy = sy, sx
        # 决策参数 p = 2*dy - dx：p >= 0 时 y 也步进
        error = 2 * dy - dx
        x = x0
        y = y0
        for _ in range(dx + 1):
            result.append([y, x] if steep else [x, y])
            if error >= 0:
                y += sy
                error -= 2 * dx
            x += sx
            error += 2 * dy
    else:
        raise ValueError(f'Unsupported line algorithm: {algorithm}')

    return result


def draw_polygon(p_list, algorithm):
    """多边形边界的像素集。

    复用 draw_polyline 后首尾相接形成闭合形状。
    闭合点（首像素==尾像素）会被剔除，不影响视觉效果。
    """
    if not p_list:
        return []
    result = draw_polyline(p_list + [p_list[0]], algorithm)
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return result


def draw_line_wu(p_list):
    """Wu 反走样线段：用亮度模拟亚像素覆盖。

    返回 [[x, y, intensity], ...]，intensity 在 0~1 之间。
    每列绘制上下两个像素，距理想直线越近亮度越高。
    两端点做特殊反走样，中间段按梯度递推。
    """
    x0, y0 = map(float, p_list[0])
    x1, y1 = map(float, p_list[1])

    def ipart(x):
        return math.floor(x)

    def round_int(x):
        return int(math.floor(x + 0.5))

    def fpart(x):
        return x - math.floor(x)

    def rfpart(x):
        return 1 - fpart(x)

    def add_point(points, steep, x, y, intensity):
        # 钳制亮度并过滤零贡献像素，减少无意义的暗点堆积
        intensity = max(0.0, min(1.0, intensity))
        if intensity <= 0:
            return
        if steep:
            points.append([int(y), int(x), intensity])
        else:
            points.append([int(x), int(y), intensity])

    result = []
    steep = abs(y1 - y0) > abs(x1 - x0)
    if steep:
        x0, y0 = y0, x0
        x1, y1 = y1, x1
    if x0 > x1:
        x0, x1 = x1, x0
        y0, y1 = y1, y0

    dx = x1 - x0
    dy = y1 - y0
    if dx == 0:
        y_start, y_end = sorted((round_int(y0), round_int(y1)))
        x = round_int(x0)
        for y in range(y_start, y_end + 1):
            add_point(result, steep, x, y, 1.0)
        return result

    gradient = dy / dx

    # 左端点反走样处理
    xend = round_int(x0)
    yend = y0 + gradient * (xend - x0)
    xgap = rfpart(x0 + 0.5)
    xpxl1 = xend
    ypxl1 = ipart(yend)
    add_point(result, steep, xpxl1, ypxl1, rfpart(yend) * xgap)
    add_point(result, steep, xpxl1, ypxl1 + 1, fpart(yend) * xgap)
    intery = yend + gradient

    # 右端点反走样处理（事先计算坐标，中间循环会跳过该列像素）
    xend = round_int(x1)
    yend = y1 + gradient * (xend - x1)
    xgap = fpart(x1 + 0.5)
    xpxl2 = xend
    ypxl2 = ipart(yend)

    # 中间段：每列绘制上下两个像素，亮度由 rfpart/fpart 分配
    for x in range(xpxl1 + 1, xpxl2):
        add_point(result, steep, x, ipart(intery), rfpart(intery))
        add_point(result, steep, x, ipart(intery) + 1, fpart(intery))
        intery += gradient

    add_point(result, steep, xpxl2, ypxl2, rfpart(yend) * xgap)
    add_point(result, steep, xpxl2, ypxl2 + 1, fpart(yend) * xgap)
    return result
