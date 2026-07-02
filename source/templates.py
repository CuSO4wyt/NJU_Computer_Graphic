"""内置模板场景。

每个模板包含 'size'（画布宽高）和 'items' 列表。
items 中每条为 (id, type, points, algorithm, QColor) 五元组。
"""

import cg_algorithms as alg
from PyQt5.QtGui import QColor

TEMPLATES = {
    '综合示例': {
        'size': (900, 650),
        'items': [
            ('axis_x', 'line', [[60, 580], [840, 580]], 'Bresenham', QColor(30, 70, 180)),
            ('axis_y', 'line', [[60, 580], [60, 60]], 'Bresenham', QColor(30, 70, 180)),
            ('house_body', 'polygon', [[180, 360], [300, 260], [420, 360], [390, 520], [210, 520]], 'Bresenham', QColor(210, 60, 50)),
            ('house_roof', 'polygon', [[180, 360], [300, 230], [420, 360]], 'Bresenham', QColor(210, 60, 50)),
            ('window_left', 'ellipse', [[230, 390], [280, 440]], '', QColor(50, 150, 90)),
            ('window_right', 'ellipse', [[320, 390], [370, 440]], '', QColor(50, 150, 90)),
            ('path_bezier', 'curve', [[430, 560], [520, 480], [620, 620], [780, 420]], 'Bezier', QColor(140, 70, 170)),
        ],
    },
    '裁剪示例': {
        'size': (900, 650),
        'items': [
            # 三条交叉线段 + 矩形裁剪窗口，直观展示裁剪效果
            ('clip_line_a', 'line', [[80, 120], [820, 520]], 'Bresenham', QColor(25, 25, 25)),
            ('clip_line_b', 'line', [[80, 520], [820, 120]], 'Bresenham', QColor(25, 25, 25)),
            ('clip_line_c', 'line', [[450, 20], [450, 630]], 'Bresenham', QColor(25, 25, 25)),
            ('clip_window', 'polygon', [[220, 160], [700, 160], [700, 520], [220, 520]], 'Bresenham', QColor(200, 80, 50)),
        ],
    },
    '曲线示例': {
        'size': (900, 650),
        'items': [
            # Bezier 和 B-spline 各一条，外加一个椭圆
            ('bezier_demo', 'curve', [[80, 420], [180, 120], [310, 550], [430, 130], [560, 420]], 'Bezier', QColor(190, 50, 60)),
            ('bspline_demo', 'curve', [[400, 560], [470, 220], [540, 520], [620, 180], [710, 480], [820, 260]], 'B-spline', QColor(40, 100, 210)),
            ('ellipse_reverse', 'ellipse', [[820, 520], [620, 320]], '', QColor(50, 150, 90)),
        ],
    },
    '变换示例': {
        'size': (900, 650),
        'items': [
            # 原始多边形 + 绕中心旋转 45° 的副本 + 缩小平移的副本
            ('base_poly', 'polygon', [[180, 160], [320, 130], [390, 250], [300, 360], [160, 300]], 'Bresenham', QColor(30, 80, 200)),
            ('rotate_poly', 'polygon', alg.rotate([[180, 160], [320, 130], [390, 250], [300, 360], [160, 300]], 280, 245, 45), 'Bresenham', QColor(210, 70, 60)),
            ('scale_poly', 'polygon', alg.translate(alg.scale([[180, 160], [320, 130], [390, 250], [300, 360], [160, 300]], 280, 245, 0.55), 360, 110), 'Bresenham', QColor(60, 150, 90)),
        ],
    },
}
