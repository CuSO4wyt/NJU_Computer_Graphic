"""线段与多边形裁剪。

- Cohen-Sutherland：区域码快速剔除
- Liang-Barsky：参数化裁剪
- Sutherland-Hodgman：逐边剪多边形
"""

from _cg_algorithms._utils import _round_point, normalize_window


def clip(p_list, x_min, y_min, x_max, y_max, algorithm):
    """线段对轴对齐矩形窗口的裁剪。

    algorithm='Cohen-Sutherland'：用 4 位区域码编码端点位置，
    码全零则线段完全在内（接受），码按位与非零则完全在外（拒绝），
    否则用外侧端点与窗口边的交点替换，迭代至接受或拒绝。

    algorithm='Liang-Barsky'：将线段参数化为 P(t)=P0+t*(P1-P0)，t∈[0,1]，
    四条窗口边各给出一个 t 的上下界，不断收缩区间 [u1, u2]。
    若最终 u1>u2 则线段完全在窗外；否则 u1,u2 就是裁剪后的端点参数。

    Returns: 裁剪后的线段端点（取整后的像素坐标），若被完全裁掉则返回 []。
    """
    x_min, y_min, x_max, y_max = normalize_window(x_min, y_min, x_max, y_max)

    if algorithm == 'Cohen-Sutherland':
        # 4 位区域码：左(1) 右(2) 上(4) 下(8)
        # 位或非零表示至少一端在外，位与非零表示两端在同侧外
        left = 1
        right = 2
        top = 4
        bottom = 8

        def region_code(x, y):
            code = 0
            if x < x_min:
                code |= left
            elif x > x_max:
                code |= right
            if y < y_min:
                code |= top
            elif y > y_max:
                code |= bottom
            return code

        x0, y0 = map(float, p_list[0])
        x1, y1 = map(float, p_list[1])
        code0 = region_code(x0, y0)
        code1 = region_code(x1, y1)

        while True:
            if code0 == 0 and code1 == 0:
                return [_round_point(x0, y0), _round_point(x1, y1)]
            if code0 & code1:
                return []

            # 选一个在外的端点，求其与最近窗口边的交点替换
            out_code = code0 if code0 else code1
            if out_code & left:
                if x1 == x0:
                    return []
                y = y0 + (y1 - y0) * (x_min - x0) / (x1 - x0)
                x = x_min
            elif out_code & right:
                if x1 == x0:
                    return []
                y = y0 + (y1 - y0) * (x_max - x0) / (x1 - x0)
                x = x_max
            elif out_code & top:
                if y1 == y0:
                    return []
                x = x0 + (x1 - x0) * (y_min - y0) / (y1 - y0)
                y = y_min
            else:
                if y1 == y0:
                    return []
                x = x0 + (x1 - x0) * (y_max - y0) / (y1 - y0)
                y = y_max

            if out_code == code0:
                x0, y0 = x, y
                code0 = region_code(x0, y0)
            else:
                x1, y1 = x, y
                code1 = region_code(x1, y1)

    if algorithm == 'Liang-Barsky':
        x0, y0 = map(float, p_list[0])
        x1, y1 = map(float, p_list[1])
        dx = x1 - x0
        dy = y1 - y0
        # 四条边的 p 和 q：每组对应一个 t 的不等式 p*t <= q
        p = [-dx, dx, -dy, dy]
        q = [x0 - x_min, x_max - x0, y0 - y_min, y_max - y0]
        u1, u2 = 0.0, 1.0

        for pi, qi in zip(p, q):
            if pi == 0:
                # p=0 表示线段与该边平行，检查 q 是否满足（即是否在边界内）
                if qi < 0:
                    return []
                continue
            u = qi / pi
            if pi < 0:
                # p<0：线段从外到内，更新下界
                u1 = max(u1, u)
            else:
                # p>0：线段从内到外，更新上界
                u2 = min(u2, u)
            if u1 > u2:
                return []

        return [
            _round_point(x0 + u1 * dx, y0 + u1 * dy),
            _round_point(x0 + u2 * dx, y0 + u2 * dy),
        ]

    raise ValueError(f'Unsupported clip algorithm: {algorithm}')


def clip_polygon(p_list, x_min, y_min, x_max, y_max):
    """Sutherland-Hodgman 多边形裁剪。

    对窗口的每条边（左、右、上、下）依次裁剪整个多边形：
    将当前边视为"内侧"，遍历多边形每条边，根据两端点是否在内侧
    决定保留还是产生交点。每次裁剪的输出作为下一次裁剪的输入。

    返回值是裁剪后的多边形顶点列表；若完全被裁掉则返回 []。
    """
    if len(p_list) < 3:
        return []
    x_min, y_min, x_max, y_max = normalize_window(x_min, y_min, x_max, y_max)

    def inside(point, edge):
        x, y = point
        if edge == 'left':
            return x >= x_min
        if edge == 'right':
            return x <= x_max
        if edge == 'top':
            return y >= y_min
        return y <= y_max

    def intersect(start, end, edge):
        # 求线段与窗口边的交点（参数化已按边方向简化）
        x0, y0 = start
        x1, y1 = end
        dx = x1 - x0
        dy = y1 - y0
        if edge == 'left':
            x = x_min
            y = y0 if dx == 0 else y0 + dy * (x_min - x0) / dx
        elif edge == 'right':
            x = x_max
            y = y0 if dx == 0 else y0 + dy * (x_max - x0) / dx
        elif edge == 'top':
            y = y_min
            x = x0 if dy == 0 else x0 + dx * (y_min - y0) / dy
        else:
            y = y_max
            x = x0 if dy == 0 else x0 + dx * (y_max - y0) / dy
        return _round_point(x, y)

    output = [point[:] for point in p_list]
    for edge in ('left', 'right', 'top', 'bottom'):
        if not output:
            return []
        source = output
        output = []
        previous = source[-1]
        for current in source:
            current_inside = inside(current, edge)
            previous_inside = inside(previous, edge)
            if current_inside:
                if not previous_inside:
                    # 从外到内：记录交点作为新顶点
                    output.append(intersect(previous, current, edge))
                output.append(current[:])
            elif previous_inside:
                # 从内到外：记录交点
                output.append(intersect(previous, current, edge))
            previous = current

    # 清理相邻重复顶点和闭合重复顶点
    cleaned = []
    for point in output:
        if not cleaned or cleaned[-1] != point:
            cleaned.append(point)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    return cleaned if len(cleaned) >= 3 else []
