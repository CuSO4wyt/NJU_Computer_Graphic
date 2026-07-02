import os
import time

import cg_algorithms as alg
from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from cg_render_utils import (
    add_pixels_to_scene,
    add_weighted_pixels_to_scene,
    pixel_bounds,
)


class AlgorithmDemoDialog(QDialog):
    """算法过程演示 —— 逐像素播放生成过程，配合状态信息展示算法递推逻辑。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle('算法过程演示')
        self.resize(860, 660)
        self.setMinimumSize(640, 480)
        # macOS 下 QDialog 默认不继承父窗口样式，需要显式设置
        from cg_style import APP_QSS
        self.setStyleSheet(APP_QSS)

        # ── 画布视图（匹配主画布风格：白底 + 浅灰细边框） ──
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.Antialiasing, False)
        self.view.setObjectName('demoCanvasView')
        self.view.setStyleSheet(
            'QGraphicsView#demoCanvasView {'
            '  background: #FFFFFF;'
            '  border: 1px solid #CBD5E1;'
            '}'
        )

        # ── 控制栏 ──
        self.algorithm_combo = QComboBox(self)
        self.algorithm_combo.addItems([
            'DDA',
            'Bresenham',
            'Ellipse',
            'Cohen-Sutherland',
            'Liang-Barsky',
            'Bezier',
            'Scanline Fill',
            'Wu Anti-aliasing',
        ])

        self.play_button = QPushButton('▶ 播放', self)
        self.step_button = QPushButton('单步', self)
        self.reset_button = QPushButton('重置', self)
        self.speed_slider = QSlider(Qt.Horizontal, self)
        self.speed_slider.setRange(1, 100)
        self.speed_slider.setValue(50)
        self.speed_label = QLabel('速度', self)
        self.speed_label.setObjectName('toolbarGroupLabel')

        control_bar = QHBoxLayout()
        control_bar.setContentsMargins(8, 6, 8, 6)
        control_bar.setSpacing(8)
        control_bar.addWidget(QLabel('算法'))
        control_bar.addWidget(self.algorithm_combo)
        control_bar.addWidget(self.play_button)
        control_bar.addWidget(self.step_button)
        control_bar.addWidget(self.reset_button)
        control_bar.addSpacing(12)
        control_bar.addWidget(self.speed_label)
        control_bar.addWidget(self.speed_slider)

        # 浅灰背景条，和主窗口的 canvasViewBar 保持一致
        from PyQt5.QtWidgets import QFrame
        bar_frame = QFrame(self)
        bar_frame.setObjectName('canvasViewBar')
        bar_frame.setLayout(control_bar)

        # ── 信息标签 ──
        self.info_label = QLabel('', self)
        self.info_label.setObjectName('workspaceZoomLabel')
        self.state_label = QLabel('', self)
        self.state_label.setWordWrap(True)
        self.state_label.setObjectName('helpPanel')
        self.state_label.setMinimumHeight(42)

        # ── 组装布局 ──
        layout = QVBoxLayout()
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(bar_frame)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.info_label)
        layout.addWidget(self.state_label)
        self.setLayout(layout)

        # ── 定时器：控制自动播放帧率 ──
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.pixels = []
        self.weighted_pixels = []
        self.states = []
        self.casteljau_layers = []
        self.static_draw = None
        self.index = 0
        self.playing = False

        self.algorithm_combo.currentTextChanged.connect(self.reset_demo)
        self.play_button.clicked.connect(self.toggle_play)
        self.step_button.clicked.connect(self._advance)
        self.reset_button.clicked.connect(self.reset_demo)
        self.speed_slider.valueChanged.connect(self._update_timer_interval)
        self.reset_demo()

    def _selected_item(self):
        return self.main_window.item_dict.get(self.main_window.selected_id)

    def _view_bounds(self):
        """主画布尺寸，用于生成匹配比例的 fallback 图元。"""
        w = getattr(self.main_window, 'canvas_width', 600) or 600
        h = getattr(self.main_window, 'canvas_height', 600) or 600
        return w, h

    def _line_points(self):
        """获取线段端点；若选中线段几乎水平/垂直则用斜线替代。

        接近水平或垂直的线 DDA 和 Bresenham 几乎无差，
        对演示没有意义，所以用对角线替换。
        """
        item = self._selected_item()
        if item and item.item_type == 'line':
            pts = [point[:] for point in item.points]
            dx = abs(pts[1][0] - pts[0][0])
            dy = abs(pts[1][1] - pts[0][1])
            if max(dx, dy) >= 10 and min(dx, dy) >= max(dx, dy) * 0.15:
                return pts
        w, h = self._view_bounds()
        margin = min(w, h) // 8
        return [[margin, h - margin], [w - margin, margin]]

    def _ellipse_points(self):
        """椭圆参数，无选中时用默认值。"""
        item = self._selected_item()
        if item and item.item_type == 'ellipse':
            return [point[:] for point in item.points]
        w, h = self._view_bounds()
        margin = min(w, h) // 8
        return [[margin, margin], [w - margin, h - margin]]

    def _curve_points(self):
        """曲线控制点，至少 2 个；无选中时用默认 Bezier 控制多边形。"""
        item = self._selected_item()
        if item and item.item_type == 'curve' and len(item.points) >= 2:
            return [point[:] for point in item.points]
        w, h = self._view_bounds()
        margin = min(w, h) // 6
        return [
            [margin, h * 2 // 3],
            [w // 3, margin],
            [w * 2 // 3, h - margin],
            [w - margin, h // 3],
        ]

    def _polygon_points(self):
        """多边形顶点，至少 3 个；无选中时用默认五边形。"""
        item = self._selected_item()
        if item and item.item_type == 'polygon' and len(item.points) >= 3:
            return [point[:] for point in item.points]
        w, h = self._view_bounds()
        margin = min(w, h) // 8
        return [
            [w // 5, h - margin],
            [w // 2, margin],
            [w - margin, h - margin],
            [w * 3 // 4, h // 2],
            [margin, h // 3],
        ]

    def _clip_window_for_line(self, points):
        """从线段包围盒内缩 1/4 得到裁剪窗口。"""
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        left = min(xs) + (max(xs) - min(xs)) // 4
        right = max(xs) - (max(xs) - min(xs)) // 4
        top = min(ys) + (max(ys) - min(ys)) // 4
        bottom = max(ys) - (max(ys) - min(ys)) // 4
        if left == right:
            left -= 80
            right += 80
        if top == bottom:
            top -= 80
            bottom += 80
        return left, top, right, bottom

    def _build_demo(self):
        """构造当前算法演示的全部数据。
        返回 (主像素, 点集, 静态像素, 裁剪窗口, 描述, 加权像素, 状态序列, Casteljau图层)。
        """
        name = self.algorithm_combo.currentText()
        static_pixels = []
        static_rect = None
        weighted_pixels = []
        states = []
        casteljau_layers = []
        points = []
        if name in ('DDA', 'Bresenham'):
            points = self._line_points()
            pixels = alg.draw_line(points, name)
            states = alg.trace_line(points, name)
            description = f'{name} 线段生成: {points}'
        elif name == 'Ellipse':
            points = self._ellipse_points()
            pixels = alg.draw_ellipse(points)
            states = [f'椭圆对称绘制: step={i}, pixel={pixel}' for i, pixel in enumerate(pixels)]
            description = f'中点椭圆生成: {points}'
        elif name in ('Cohen-Sutherland', 'Liang-Barsky'):
            points = self._line_points()
            static_pixels = alg.draw_line(points, 'Bresenham')
            static_rect = self._clip_window_for_line(points)
            clipped = alg.clip(points, *static_rect, name)
            pixels = alg.draw_line(clipped, 'Bresenham') if clipped else []
            states = alg.trace_clip(points, *static_rect, name)
            description = f'{name} 裁剪: line={points}, window={static_rect}, result={clipped or "empty"}'
        elif name == 'Wu Anti-aliasing':
            points = self._line_points()
            weighted_pixels = alg.draw_line_wu(points)
            pixels = [[x, y] for x, y, _ in weighted_pixels]
            states = [
                f'Wu step={i}, pixel=({x}, {y}), intensity={intensity:.3f}'
                for i, (x, y, intensity) in enumerate(weighted_pixels)
            ]
            description = f'Wu 反走样线段: {points}'
        elif name == 'Scanline Fill':
            points = self._polygon_points()
            static_pixels = alg.draw_polygon(points, 'Bresenham')
            pixels = alg.fill_polygon(points)
            states = [
                f'扫描线填充 step={i}, pixel={pixel}'
                for i, pixel in enumerate(pixels)
            ]
            description = f'扫描线多边形填充: 顶点数={len(points)}'
        else:
            points = self._curve_points()
            pixels = alg.draw_curve(points, 'Bezier')
            states, casteljau_layers = alg.trace_bezier(points, len(pixels))
            description = f'Bezier 曲线生成: {points}'
        return pixels, points, static_pixels, static_rect, description, weighted_pixels, states, casteljau_layers

    def reset_demo(self):
        """重建演示数据，回到第 0 步。"""
        self.timer.stop()
        self.playing = False
        self.play_button.setText('▶ 播放')
        self.index = 0
        (
            self.pixels,
            points,
            static_pixels,
            static_rect,
            description,
            self.weighted_pixels,
            self.states,
            self.casteljau_layers,
        ) = self._build_demo()
        self.static_draw = (points, static_pixels, static_rect, description)
        self._redraw_scene()

    def _redraw_scene(self):
        """按 index 绘制画面：静态背景 → 已播放像素 → 端点标记 → 状态信息。"""
        points, static_pixels, static_rect, description = self.static_draw
        self.scene.clear()
        self.scene.setSceneRect(pixel_bounds(self.pixels + static_pixels, points))
        if static_pixels:
            add_pixels_to_scene(self.scene, static_pixels, QColor(190, 190, 190))
        if static_rect:
            x0, y0, x1, y1 = static_rect
            self.scene.addRect(QRectF(x0, y0, x1 - x0, y1 - y0), QPen(QColor(220, 80, 40), 1, Qt.DashLine))
        if self.weighted_pixels:
            add_weighted_pixels_to_scene(self.scene, self.weighted_pixels[:self.index], QColor(30, 90, 210))
        else:
            add_pixels_to_scene(self.scene, self.pixels[:self.index], QColor(30, 90, 210))
        if self.casteljau_layers and self.index > 0:
            layers = self.casteljau_layers[min(self.index - 1, len(self.casteljau_layers) - 1)]
            for layer in layers[:-1]:
                for i in range(1, len(layer)):
                    x0, y0 = layer[i - 1]
                    x1, y1 = layer[i]
                    self.scene.addLine(x0, y0, x1, y1, QPen(QColor(230, 140, 40), 1, Qt.DashLine))
        for x, y in points:
            self.scene.addRect(x - 3, y - 3, 6, 6, QPen(QColor(20, 20, 20)))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self.info_label.setText(f'{description}\n步骤: {self.index}/{len(self.pixels)}')
        if self.states:
            self.state_label.setText(self.states[min(max(self.index - 1, 0), len(self.states) - 1)])
        else:
            self.state_label.setText('')

    def _advance(self):
        """前进一帧，到末尾自动暂停。"""
        if self.index >= len(self.pixels):
            self.timer.stop()
            self.playing = False
            self.play_button.setText('▶ 播放')
            return
        self.index += 1
        self._redraw_scene()

    def _update_timer_interval(self):
        """滑块 1-100 映射到定时器间隔 208-10ms，值越大越快。"""
        if self.timer.isActive():
            self.timer.setInterval(max(5, 210 - self.speed_slider.value() * 2))

    def toggle_play(self):
        """播放 / 暂停。"""
        if self.playing:
            self.timer.stop()
            self.playing = False
            self.play_button.setText('▶ 播放')
            return
        self.playing = True
        self.play_button.setText('⏸ 暂停')
        self.timer.start(max(5, 210 - self.speed_slider.value() * 2))


class AlgorithmCompareDialog(QDialog):
    """算法对比 —— 左右并排展示两个算法对同一图元的计算结果与耗时。"""

    def __init__(self, parent, item, compare_mode='auto'):
        super().__init__(parent)
        self.item = item
        self.compare_mode = compare_mode
        self.setWindowTitle('裁剪算法对比' if compare_mode == 'clip' else '算法对比')
        if compare_mode == 'clip':
            self.resize(1180, 740)
            self.setMinimumSize(980, 620)
        else:
            self.resize(1180, 740)
            self.setMinimumSize(980, 620)
        from cg_style import APP_QSS
        self.setStyleSheet(APP_QSS)

        # ── 左右两个画布视图 ──
        self.left_scene = QGraphicsScene(self)
        self.right_scene = QGraphicsScene(self)
        self.left_view = QGraphicsView(self.left_scene, self)
        self.right_view = QGraphicsView(self.right_scene, self)
        for v in (self.left_view, self.right_view):
            v.setRenderHint(QPainter.Antialiasing, False)
            v.setMinimumSize(520, 430)
            v.setStyleSheet(
                'QGraphicsView {'
                '  background: #FFFFFF;'
                '  border: 1px solid #CBD5E1;'
                '}'
            )

        # ── 标题标签 ──
        self.left_label = QLabel('', self)
        self.left_label.setObjectName('workspaceZoomLabel')
        self.right_label = QLabel('', self)
        self.right_label.setObjectName('workspaceZoomLabel')

        # ── 汇总说明 ──
        self.summary_label = QLabel('', self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName('helpPanel')
        self.summary_label.setMinimumHeight(36)

        # ── 操作按钮 ──
        self.save_button = QPushButton('💾 保存截图', self)
        self.save_button.clicked.connect(self.save_snapshot)

        # ── 组装布局 ──
        grid = QGridLayout()
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setSpacing(10)
        grid.addWidget(self.left_label, 0, 0)
        grid.addWidget(self.right_label, 0, 1)
        grid.addWidget(self.left_view, 1, 0)
        grid.addWidget(self.right_view, 1, 1)
        grid.addWidget(self.summary_label, 2, 0, 1, 2)
        grid.addWidget(self.save_button, 3, 0, 1, 2)
        self.setLayout(grid)

        self._render()
        QTimer.singleShot(0, self._fit_views)
        QTimer.singleShot(80, self._fit_views)

    def _timed_pixels(self, callback, iterations=200):
        """多次执行取平均耗时（微秒）。"""
        start = time.perf_counter()
        pixels = None
        for _ in range(iterations):
            pixels = callback()
        elapsed_us = (time.perf_counter() - start) * 1_000_000 / iterations
        return pixels, elapsed_us

    def _line_clip_window(self, points):
        """同 _clip_window_for_line，供对比对话框使用。"""
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        x_min = min(xs) + (max(xs) - min(xs)) // 4
        x_max = max(xs) - (max(xs) - min(xs)) // 4
        y_min = min(ys) + (max(ys) - min(ys)) // 4
        y_max = max(ys) - (max(ys) - min(ys)) // 4
        if x_min == x_max:
            x_min -= 80
            x_max += 80
        if y_min == y_max:
            y_min -= 80
            y_max += 80
        return x_min, y_min, x_max, y_max

    def _clip_spec(self, points, algorithm):
        """对一条线段执行裁剪算法并返回结果规格字典。"""
        window = self._line_clip_window(points)
        clipped, elapsed_us = self._timed_pixels(lambda: alg.clip(points, *window, algorithm))
        pixels = alg.draw_line(clipped, 'Bresenham') if clipped else []
        original_pixels = alg.draw_line(points, 'Bresenham')
        if clipped:
            result_text = f'结果端点: {clipped}'
        else:
            result_text = '结果: 完全在窗口外，被拒绝'
        return {
            'title': algorithm,
            'pixels': pixels,
            'points': clipped if clipped else points,
            'original_points': points,
            'elapsed_us': elapsed_us,
            'description': result_text,
            'static_pixels': original_pixels,
            'clip_window': window,
        }

    def _comparison_specs(self):
        """返回两个算法的结果规格列表。算法对按图元类型选择。"""
        points = [point[:] for point in self.item.points]
        if self.compare_mode == 'clip':
            if self.item.item_type != 'line':
                return []
            return [
                self._clip_spec(points, 'Cohen-Sutherland'),
                self._clip_spec(points, 'Liang-Barsky'),
            ]
        if self.item.item_type == 'line':
            bresenham_pixels, bresenham_us = self._timed_pixels(lambda: alg.draw_line(points, 'Bresenham'))
            wu_pixels, wu_us = self._timed_pixels(lambda: alg.draw_line_wu(points))
            return [
                {
                    'title': 'Bresenham',
                    'pixels': bresenham_pixels,
                    'points': points,
                    'elapsed_us': bresenham_us,
                    'description': '使用整数误差项递推，适合栅格线段生成。',
                },
                {
                    'title': 'Wu Anti-aliasing',
                    'pixels': wu_pixels,
                    'points': points,
                    'elapsed_us': wu_us,
                    'description': '使用像素亮度权重降低锯齿，边缘更平滑。',
                },
            ]
        if self.item.item_type == 'polygon':
            dda_pixels, dda_us = self._timed_pixels(lambda: alg.draw_polygon(points, 'DDA'))
            bresenham_pixels, bresenham_us = self._timed_pixels(lambda: alg.draw_polygon(points, 'Bresenham'))
            return [
                {
                    'title': 'DDA',
                    'pixels': dda_pixels,
                    'points': points,
                    'elapsed_us': dda_us,
                    'description': f'多边形边数: {len(points)}，逐边使用 DDA 生成。',
                },
                {
                    'title': 'Bresenham',
                    'pixels': bresenham_pixels,
                    'points': points,
                    'elapsed_us': bresenham_us,
                    'description': f'多边形边数: {len(points)}，逐边使用 Bresenham 生成。',
                },
            ]
        if self.item.item_type == 'curve' and len(points) >= 4:
            bezier_pixels, bezier_us = self._timed_pixels(lambda: alg.draw_curve(points, 'Bezier'))
            bspline_pixels, bspline_us = self._timed_pixels(lambda: alg.draw_curve(points, 'B-spline'))
            return [
                {
                    'title': 'Bezier',
                    'pixels': bezier_pixels,
                    'points': points,
                    'elapsed_us': bezier_us,
                    'description': f'控制点数: {len(points)}，曲线经过首末控制点。',
                },
                {
                    'title': 'B-spline',
                    'pixels': bspline_pixels,
                    'points': points,
                    'elapsed_us': bspline_us,
                    'description': f'控制点数: {len(points)}，三次均匀 B 样条通常不经过首末控制点。',
                },
            ]
        return []

    def _fit_views(self):
        """窗口完成布局后按真实视口尺寸重新适配，避免内容显示过小。"""
        for view in (self.left_view, self.right_view):
            rect = view.scene().sceneRect()
            if rect.isNull():
                continue
            view.resetTransform()
            view.fitInView(rect, Qt.KeepAspectRatio)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_views)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_views)

    def _render_side(self, scene, view, label, spec):
        """在一侧画布上渲染算法结果。裁剪模式下视口聚焦裁剪窗口。"""
        scene.clear()
        title = spec['title']
        pixels = spec['pixels']
        points = spec['points']
        static_pixels = spec.get('static_pixels', [])
        clip_window = spec.get('clip_window')
        original_points = spec.get('original_points')

        # 静态背景：原始线段灰显
        if static_pixels:
            add_pixels_to_scene(scene, static_pixels, QColor(190, 190, 190))
        if clip_window and original_points and len(original_points) == 2:
            scene.addLine(
                original_points[0][0],
                original_points[0][1],
                original_points[1][0],
                original_points[1][1],
                QPen(QColor(200, 200, 200), 2),
            )
        # 裁剪窗口虚线框
        if clip_window:
            x0, y0, x1, y1 = clip_window
            scene.addRect(
                QRectF(x0, y0, x1 - x0, y1 - y0),
                QPen(QColor(220, 80, 40), 1, Qt.DashLine),
            )
        # 结果像素：Wu 用加权渲染，其余用纯色
        if pixels and len(pixels[0]) == 3:
            add_weighted_pixels_to_scene(scene, pixels, QColor(30, 90, 210))
        else:
            add_pixels_to_scene(scene, pixels, QColor(30, 90, 210))
        if clip_window and points and len(points) == 2:
            scene.addLine(
                points[0][0],
                points[0][1],
                points[1][0],
                points[1][1],
                QPen(QColor(30, 90, 210), 3),
            )
        # 端点/控制点标记
        for x, y in points:
            marker_size = 8 if clip_window else 6
            scene.addRect(
                x - marker_size / 2,
                y - marker_size / 2,
                marker_size,
                marker_size,
                QPen(QColor(210, 60, 50), 2 if clip_window else 1),
            )

        if clip_window:
            x0, y0, x1, y1 = clip_window
            margin = max(4, (x1 - x0) // 25, (y1 - y0) // 25)
            scene.setSceneRect(
                QRectF(x0 - margin, y0 - margin,
                       max(40, x1 - x0 + 2 * margin),
                       max(40, y1 - y0 + 2 * margin))
            )
        else:
            scene.setSceneRect(pixel_bounds(pixels, points))
        label.setText(f"{title}: {len(pixels)} 像素点, {spec['elapsed_us']:.1f} μs")

    def _render(self):
        """渲染两侧对比。"""
        specs = self._comparison_specs()
        if not specs:
            label = '当前图元不支持对比，或曲线控制点不足 4 个'
            self.left_label.setText(label)
            self.right_label.setText(label)
            self.summary_label.setText('')
            return
        self._render_side(self.left_scene, self.left_view, self.left_label, specs[0])
        self._render_side(self.right_scene, self.right_view, self.right_label, specs[1])
        summary = []
        for spec in specs:
            summary.append(
                f"{spec['title']}: {len(spec['pixels'])} 像素点, {spec['elapsed_us']:.1f} μs; {spec['description']}"
            )
        if self.item.item_type == 'line' and self.compare_mode != 'clip':
            summary.append('左侧展示整数栅格线段，右侧展示带亮度权重的反走样线段。')
        self.summary_label.setText('\n'.join(summary))

    def save_snapshot(self):
        """截屏保存为 PNG/BMP。"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            '保存对比截图',
            os.path.join(os.getcwd(), 'algorithm_compare.png'),
            'PNG Files (*.png);;Bitmap Files (*.bmp)',
        )
        if not path:
            return
        if not path.lower().endswith(('.png', '.bmp')):
            path += '.png'
        self.grab().save(path)
