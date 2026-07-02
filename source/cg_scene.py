"""
场景状态管理 —— 整个应用的数据核心。

设计思路：所有图元信息聚拢在一个 State 字典中，GUI 与 CLI 共享同一套
命令解析/应用逻辑，避免两端各自维护状态副本。

State 结构:
    {
        'width': int,        # 画布宽度（像素）
        'height': int,       # 画布高度（像素）
        'items': dict[str, Item],   # id -> 图元
        'pen_color': [r, g, b],     # 当前画笔颜色
    }

Item 结构:
    {
        'type': str,         # 'line' | 'polygon' | 'ellipse' | 'curve'
        'points': [[x, y], ...],
        'algorithm': str,    # 绘制/裁剪算法标识
        'color': [r, g, b],
    }
"""

from typing import Any

import cg_algorithms as alg
from cg_constants import CANVAS_SIZE_MIN, CANVAS_SIZE_MAX

# ── 类型别名，方便书写 ──────────────────────────────────────────────

Point = list[int]
Points = list[Point]
Color = list[int]
Item = dict[str, Any]
State = dict[str, Any]

# ── 状态初始化与工具函数 ──────────────────────────────────────────────


def create_state() -> State:
    """返回一个空白初始状态 —— 画布尺寸为 0，无图元，黑色画笔。"""
    return {
        'width': 0,
        'height': 0,
        'items': {},
        'pen_color': [0, 0, 0],
    }


def _copy_points(points: Points) -> Points:
    """深拷贝点列表，防止后续变换意外修改原始数据。"""
    return [[x, y] for x, y in points]


def _parse_points(tokens: list[str]) -> Points:
    """将扁平的字符串数值列表按序配对成 [[x1,y1], [x2,y2], ...]。
    输入 token 数必须是偶数，否则直接报错——不静默丢弃数据。
    """
    values = list(map(int, tokens))
    if len(values) % 2 != 0:
        raise ValueError(
            f'坐标参数必须成对出现，但收到奇数个数值: {len(values)} '
            f'(tokens={tokens})'
        )
    return [[values[i], values[i + 1]] for i in range(0, len(values), 2)]


def build_item(item_type: str, points: Points, algorithm: str, color: Color) -> Item:
    """构造一个图元 dict，入参 points 和 color 均做防御性拷贝。
    这样后续对该图元的变换不会污染外部持有的引用。
    """
    return {
        'type': item_type,
        'points': _copy_points(points),
        'algorithm': algorithm,
        'color': list(color),
    }


def iter_commands(input_file: str):
    """流式解析指令文件，逐行 yield tokens，避免大文件一次全部加载到内存。"""
    try:
        fp = open(input_file, 'r', encoding='utf-8')
    except FileNotFoundError:
        raise FileNotFoundError(f'指令文件不存在: {input_file}')
    with fp:
        for raw_line in fp:
            line = raw_line.strip()
            if line:
                yield line.split()


# ── 指令处理器 ────────────────────────────────────────────────────────
# 每个 handler 签名统一为 (state, parts) -> 可选返回值。
# 返回值仅 saveCanvas 使用：返回 ('saveCanvas', filename) 供上层触发写文件。

def _cmd_reset_canvas(state, parts):
    """重置画布尺寸并清空所有图元。尺寸越界直接报错。"""
    width = int(parts[1])
    height = int(parts[2])
    if not (CANVAS_SIZE_MIN <= width <= CANVAS_SIZE_MAX and CANVAS_SIZE_MIN <= height <= CANVAS_SIZE_MAX):
        raise ValueError(
            f'resetCanvas: width and height must be in [{CANVAS_SIZE_MIN}, {CANVAS_SIZE_MAX}], got {width}x{height}'
        )
    state['width'] = width
    state['height'] = height
    state['items'] = {}


def _cmd_save_canvas(_state, parts):
    """saveCanvas 不修改 state，仅向上层返回一个 event。"""
    return ('saveCanvas', parts[1])


def _cmd_set_color(state, parts):
    """设置当前画笔颜色，后续 draw* 指令使用此颜色。"""
    pen = state['pen_color']
    pen[0] = int(parts[1])
    pen[1] = int(parts[2])
    pen[2] = int(parts[3])


def _cmd_draw_line(state, parts):
    item_id = parts[1]
    x0, y0, x1, y1 = map(int, parts[2:6])
    state['items'][item_id] = build_item(
        'line', [[x0, y0], [x1, y1]], parts[6], state['pen_color'],
    )


def _cmd_draw_polygon(state, parts):
    """多边形顶点数可变，因此最后一个 token 是算法名，其余全是坐标。"""
    item_id = parts[1]
    state['items'][item_id] = build_item(
        'polygon', _parse_points(parts[2:-1]), parts[-1], state['pen_color'],
    )


def _cmd_draw_ellipse(state, parts):
    """椭圆由外接矩形定义，不需要算法参数（algorithm 置空）。"""
    item_id = parts[1]
    x0, y0, x1, y1 = map(int, parts[2:6])
    state['items'][item_id] = build_item(
        'ellipse', [[x0, y0], [x1, y1]], '', state['pen_color'],
    )


def _cmd_draw_curve(state, parts):
    """曲线由多个控制点定义，同样可变长参数。"""
    item_id = parts[1]
    state['items'][item_id] = build_item(
        'curve', _parse_points(parts[2:-1]), parts[-1], state['pen_color'],
    )


def _cmd_translate(state, parts):
    item_id = parts[1]
    dx, dy = map(int, parts[2:4])
    state['items'][item_id]['points'] = alg.translate(
        state['items'][item_id]['points'], dx, dy,
    )


def _cmd_rotate(state, parts):
    """对椭圆跳过旋转 —— 椭圆由其外接矩形定义，旋转后不再是轴对齐椭圆，
    当前算法不支持。"""
    item_id = parts[1]
    cx, cy, degree = map(int, parts[2:5])
    item = state['items'][item_id]
    if item['type'] != 'ellipse':
        item['points'] = alg.rotate(item['points'], cx, cy, degree)


def _cmd_scale(state, parts):
    item_id = parts[1]
    cx, cy = map(int, parts[2:4])
    factor = float(parts[4])
    state['items'][item_id]['points'] = alg.scale(
        state['items'][item_id]['points'], cx, cy, factor,
    )


def _cmd_clip(state, parts):
    """线段裁剪，无剩余时删除图元。"""
    item_id = parts[1]
    x0, y0, x1, y1 = map(int, parts[2:6])
    items = state['items']
    clipped = alg.clip(items[item_id]['points'], x0, y0, x1, y1, parts[6])
    if clipped:
        items[item_id]['points'] = clipped
    else:
        del items[item_id]


def _cmd_clip_polygon(state, parts):
    """多边形裁剪：仅支持 Sutherland-Hodgman 算法，且仅作用于 polygon 类型。"""
    item_id = parts[1]
    x0, y0, x1, y1 = map(int, parts[2:6])
    algorithm = parts[6] if len(parts) > 6 else 'Sutherland-Hodgman'
    if algorithm != 'Sutherland-Hodgman':
        raise ValueError(f'Unsupported polygon clip algorithm: {algorithm}')
    items = state['items']
    item = items[item_id]
    if item['type'] != 'polygon':
        raise ValueError('clipPolygon only supports polygon items')
    clipped = alg.clip_polygon(item['points'], x0, y0, x1, y1)
    if clipped:
        item['points'] = clipped
    else:
        del items[item_id]


# 指令名 -> handler 的路由表，新增指令只需在此注册。
COMMAND_DISPATCH = {
    'resetCanvas': _cmd_reset_canvas,
    'saveCanvas': _cmd_save_canvas,
    'setColor': _cmd_set_color,
    'drawLine': _cmd_draw_line,
    'drawPolygon': _cmd_draw_polygon,
    'drawEllipse': _cmd_draw_ellipse,
    'drawCurve': _cmd_draw_curve,
    'translate': _cmd_translate,
    'rotate': _cmd_rotate,
    'scale': _cmd_scale,
    'clip': _cmd_clip,
    'clipPolygon': _cmd_clip_polygon,
}


def apply_command(state: State, parts: list[str]):
    """将单条指令应用到 state。不识别的指令直接抛异常，不做静默忽略。"""
    command = parts[0]
    handler = COMMAND_DISPATCH.get(command)
    if handler is None:
        raise ValueError(f'Unsupported command: {command}')
    return handler(state, parts)


# ── 像素级渲染（调用算法模块）─────────────────────────────────────────

def draw_item_pixels(item: Item) -> Points:
    """将图元转为像素列表，按 type 分发。polyline 逐段画线，未知算法回退 Bresenham。"""
    item_type = item['type']
    points = item['points']
    algorithm = item['algorithm']

    if item_type == 'line':
        return alg.draw_line(points, algorithm)
    if item_type == 'polygon':
        return alg.draw_polygon(points, algorithm)
    if item_type == 'ellipse':
        return alg.draw_ellipse(points)
    if item_type == 'curve':
        return alg.draw_curve(points, algorithm)
    if item_type == 'polyline':
        line_algo = algorithm if algorithm in ('DDA', 'Bresenham', 'Naive') else 'Bresenham'
        return alg.draw_polyline(points, line_algo)
    raise ValueError(f'Unsupported item type: {item_type}')


# ── 序列化：State → 指令文本 ─────────────────────────────────────────

def export_commands(state: State, save_name: str | None = None) -> list[str]:
    """将当前 state 导出为可保存/重放的指令序列。

    相邻同色图元只输出一次 setColor，减少冗余。
    """
    commands = [f"resetCanvas {state['width']} {state['height']}"]
    current_color = None
    for item_id, item in state['items'].items():
        color = tuple(item['color'])
        if color != current_color:
            commands.append(f"setColor {color[0]} {color[1]} {color[2]}")
            current_color = color

        points = ' '.join(f'{x} {y}' for x, y in item['points'])
        if item['type'] == 'line':
            commands.append(f"drawLine {item_id} {points} {item['algorithm']}")
        elif item['type'] == 'polygon':
            commands.append(f"drawPolygon {item_id} {points} {item['algorithm']}")
        elif item['type'] == 'ellipse':
            commands.append(f"drawEllipse {item_id} {points}")
        elif item['type'] == 'curve':
            commands.append(f"drawCurve {item_id} {points} {item['algorithm']}")
        else:
            raise ValueError(f"Unsupported item type: {item['type']}")

    if save_name:
        commands.append(f"saveCanvas {save_name}")
    return commands


def load_final_state(input_file: str) -> State:
    """解析指令文件，重放后返回最终 state。"""
    state = create_state()
    for parts in iter_commands(input_file):
        apply_command(state, parts)
    return state