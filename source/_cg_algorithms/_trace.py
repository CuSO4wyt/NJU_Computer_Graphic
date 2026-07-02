"""算法过程追踪，供 GUI 逐步演示。

每个 trace_* 返回中间状态描述列表，GUI 据此展示算法运行时内部变量变化。

trace 函数不是算法实现本身——它们调用 draw_* 获取结果，
再回放计算过程来收集状态。这样保持算法核心与演示逻辑解耦。
"""


def trace_line(p_list, algorithm):
    """返回线段生成每一步的中间状态字符串，用于算法过程演示。

    对 DDA 展示步序号、斜率 k、当前浮点坐标和像素；
    对 Bresenham 展示步序号、决策参数 p 和像素。
    Returns: list[str]，每项对应一个像素点的内部变量快照。
    """
    (x0, y0), (x1, y1) = p_list
    from _cg_algorithms._lines import draw_line

    pixels = draw_line(p_list, algorithm)
    states = []

    if algorithm == 'DDA':
        dx = x1 - x0
        dy = y1 - y0
        steps = max(abs(dx), abs(dy))
        k = 'inf' if dx == 0 else f'{dy / dx:.4f}'
        x_inc = 0 if steps == 0 else dx / steps
        y_inc = 0 if steps == 0 else dy / steps
        x, y = float(x0), float(y0)
        for i, pixel in enumerate(pixels):
            states.append(
                f'DDA step={i}, k={k}, x={x:.3f}, y={y:.3f}, pixel={pixel}'
            )
            x += x_inc
            y += y_inc
        return states

    # Bresenham：回放决策参数 p 的演变过程
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    steep = dy > dx
    if steep:
        x0, y0 = y0, x0
        x1, y1 = y1, x1
        dx, dy = dy, dx
    error = 2 * dy - dx
    for i, pixel in enumerate(pixels):
        states.append(
            f'Bresenham step={i}, p={error}, pixel={pixel}, steep={steep}'
        )
        if error >= 0:
            error -= 2 * dx
        error += 2 * dy
    return states


def trace_clip(p_list, x_min, y_min, x_max, y_max, algorithm):
    """返回裁剪算法每一步的中间状态字符串，用于算法过程演示。

    Cohen-Sutherland：展示区域码和判断逻辑说明。
    Liang-Barsky：展示每条边的 p、q、u 参数和 u1/u2 区间收缩。
    Returns: list[str]。
    """
    (x0, y0), (x1, y1) = p_list
    states = []

    if algorithm == 'Cohen-Sutherland':
        def _region_code(x, y):
            code = 0
            if x < x_min:
                code |= 1
            elif x > x_max:
                code |= 2
            if y < y_min:
                code |= 4
            elif y > y_max:
                code |= 8
            return code

        states.append(
            f'初始区域码: P0={_region_code(x0, y0):04b}, '
            f'P1={_region_code(x1, y1):04b}, window=({x_min},{y_min},{x_max},{y_max})'
        )
        states.append(
            '若两个区域码均为 0000 则接受；按位与非 0 则拒绝；否则按外侧端点裁剪。'
        )
        return states

    # Liang-Barsky：跟踪每条边如何收紧 u1/u2 区间
    dx = x1 - x0
    dy = y1 - y0
    p_values = [-dx, dx, -dy, dy]
    q_values = [x0 - x_min, x_max - x0, y0 - y_min, y_max - y0]
    u1, u2 = 0.0, 1.0
    for idx, (p_val, q_val) in enumerate(zip(p_values, q_values)):
        if p_val == 0:
            states.append(
                f'边界 {idx}: p={p_val}, q={q_val}, '
                f'平行, u1={u1:.3f}, u2={u2:.3f}'
            )
            continue
        u = q_val / p_val
        if p_val < 0:
            u1 = max(u1, u)
        else:
            u2 = min(u2, u)
        states.append(
            f'边界 {idx}: p={p_val}, q={q_val}, '
            f'u={u:.3f}, u1={u1:.3f}, u2={u2:.3f}'
        )
    return states


def trace_bezier(p_list, pixel_count):
    """返回 Bezier 曲线 de Casteljau 算法的分层中间状态。

    对每个采样参数 t，记录完整的递推层结构。
    GUI 利用 layers_by_step 绘制三角递推网格，展示
    曲线点如何从控制多边形逐层"收缩"得到。

    Returns:
        states: list[str] — 每步的描述文本
        layers_by_step: list[list[list[[float,float]]]] — 每步的完整分层坐标，
            最外层是步索引，第二层是递推层索引（0=原始控制点），
            最内层是该层的所有点坐标
    """
    states = []
    layers_by_step = []
    # 步数由 GUI 传入的 pixel_count 控制，但上限 120 防止演示过密
    steps = max(1, min(pixel_count - 1, 120))
    for i in range(steps + 1):
        t = i / steps
        layers = [[[float(x), float(y)] for x, y in p_list]]
        while len(layers[-1]) > 1:
            prev = layers[-1]
            current = []
            for j in range(len(prev) - 1):
                current.append([
                    (1 - t) * prev[j][0] + t * prev[j + 1][0],
                    (1 - t) * prev[j][1] + t * prev[j + 1][1],
                ])
            layers.append(current)
        states.append(
            f'de Casteljau step={i}, t={t:.3f}, '
            f'层数={len(layers)}, 曲线点={layers[-1][0]}'
        )
        layers_by_step.append(layers)
    return states, layers_by_step
