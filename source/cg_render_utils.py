"""渲染工具函数 —— 被算法演示对话框等组件复用，将像素数据填充到 QGraphicsScene。

pixel_bounds:         计算像素点的最小外接矩形（带边距），用于设置 scene 范围
add_pixels_to_scene:  逐点绘制纯色像素
blend_color:          将颜色向白色混合，用于反走样
add_weighted_pixels_to_scene: 逐点绘制带权重的反走样像素
"""

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPen


def pixel_bounds(pixels, points=None, margin=20):
    """像素点的最小外接矩形（带 margin 边距）。
    points 可额外追加控制点参与计算。空列表返回默认 400x300。
    """
    coords = list(pixels)
    if points:
        coords.extend(points)
    if not coords:
        return QRectF(0, 0, 400, 300)
    xs = [point[0] for point in coords]
    ys = [point[1] for point in coords]
    left = min(xs) - margin
    top = min(ys) - margin
    width = max(xs) - min(xs) + 2 * margin
    height = max(ys) - min(ys) + 2 * margin
    return QRectF(left, top, max(width, 80), max(height, 80))


def add_pixels_to_scene(scene, pixels, color):
    """逐点绘制到 scene —— 每个像素画一条零长度线段（QGraphicsScene 不支持直接画点）。"""
    pen = QPen(color)
    for x, y in pixels:
        scene.addLine(x, y, x, y, pen)


def blend_color(color, intensity):
    """将颜色向白色线性插值：intensity=0 返回原色，intensity=1 返回白色。"""
    intensity = max(0.0, min(1.0, intensity))
    return QColor(
        int(255 - (255 - color.red()) * intensity),
        int(255 - (255 - color.green()) * intensity),
        int(255 - (255 - color.blue()) * intensity),
    )


def add_weighted_pixels_to_scene(scene, pixels, color):
    """绘制反走样像素 —— 每个点携带 (x, y, intensity)，
    intensity 越大越接近白色（越"淡"），用于模拟亚像素覆盖。
    """
    for x, y, intensity in pixels:
        scene.addLine(x, y, x, y, QPen(blend_color(color, intensity)))