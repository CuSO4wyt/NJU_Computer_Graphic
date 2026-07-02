"""命令行入口 —— 读指令文件 -> 逐行执行 -> 在 saveCanvas 处写出 BMP。

用法: python cg_cli.py <指令文件> <输出目录>
"""

import os
import sys

import numpy as np
from PIL import Image

from cg_scene import apply_command, create_state, draw_item_pixels, iter_commands


def _plot_pixels(canvas, pixels, color):
    """将像素点写入 numpy 画布数组，自动裁剪越界坐标。

    注意坐标体系：x 是列索引，y 是行索引，因此赋值时 canvas[y, x]。
    """
    height, width = canvas.shape[:2]
    for x, y in pixels:
        if 0 <= x < width and 0 <= y < height:
            canvas[y, x] = color


def _save_canvas(state, output_dir, save_name):
    """用当前 state 渲染一张完整画布并保存为 BMP。

    不需要 save_name 带 .bmp 后缀，这里统一追加。
    """
    canvas = np.full((state['height'], state['width'], 3), 255, np.uint8)
    for item in state['items'].values():
        _plot_pixels(canvas, draw_item_pixels(item), item['color'])
    Image.fromarray(canvas).save(os.path.join(output_dir, save_name + '.bmp'), 'bmp')


def main():
    if len(sys.argv) != 3:
        print('Usage: python cg_cli.py input_path output_dir')
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]
    os.makedirs(output_dir, exist_ok=True)
    state = create_state()
    try:
        for line_no, parts in enumerate(iter_commands(input_file), 1):
            event = apply_command(state, parts)
            if event and event[0] == 'saveCanvas':
                _save_canvas(state, output_dir, event[1])
    except FileNotFoundError as exc:
        print(f'错误: 找不到文件 {exc.filename}', file=sys.stderr)
        sys.exit(1)
    except (ValueError, OSError) as exc:
        print(f'错误 (第 {line_no} 行): {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()