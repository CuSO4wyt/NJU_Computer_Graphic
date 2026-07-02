"""扫描线多边形填充算法（奇偶规则）。

只依赖 math.ceil / math.floor，无外部库。
"""

import math


def fill_polygon(p_list):
    """扫描线填充（奇偶规则）。

    使用一致的下闭开规则处理边端点，避免共享顶点被重复计数：
    对于每条非水平边，以 y 坐标较小端为闭端点（包含），较大端为开端点（排除）。
    水平边直接跳过——它们不贡献交点，且被上下边界自然覆盖。

    每条扫描线得到偶数个交点后，按奇偶配对填充：
    交点 0→1 之间填充，2→3 之间填充，以此类推。

    若某行交点数为奇数则抛出 RuntimeError——说明下闭开实现有 bug。
    """
    if len(p_list) < 3:
        return []
    y_min = min(point[1] for point in p_list)
    y_max = max(point[1] for point in p_list)
    result = []
    for y in range(y_min, y_max + 1):
        intersections = []
        for i in range(len(p_list)):
            x0, y0 = p_list[i - 1]
            x1, y1 = p_list[i]
            if y0 == y1:
                continue
            # 方向无关的下闭开：以 y 较小端为包含端，较大端为排除端
            if y0 < y1:
                if y0 <= y < y1:
                    intersections.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            else:
                if y1 <= y < y0:
                    intersections.append(x1 + (y - y1) * (x0 - x1) / (y0 - y1))
        intersections.sort()
        # 下闭开规则保证偶数个交点；奇数说明有 bug，不应静默跳过
        if len(intersections) % 2 != 0:
            raise RuntimeError(
                f'fill_polygon: 扫描行 y={y} 得到奇数个交点 '
                f'({len(intersections)})，存在算法缺陷'
            )
        for i in range(0, len(intersections), 2):
            # ceil/floor 保证像素中心落在多边形内部
            x_start = int(math.ceil(intersections[i]))
            x_end = int(math.floor(intersections[i + 1]))
            for x in range(x_start, x_end + 1):
                result.append([x, y])
    return result
