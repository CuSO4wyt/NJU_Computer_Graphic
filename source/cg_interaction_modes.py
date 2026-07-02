"""交互模式 —— 状态模式实现，每种模式封装独立的鼠标/键盘处理逻辑。

模式的 enter/leave 生命周期由 CanvasView.switch_mode() 管理，
保证进入时初始化临时元素，离开时清理干净，不会泄漏到场景中。
"""

import math

import cg_algorithms as alg
from cg_algorithms import normalize_window
from cg_graphic_item import GraphicItem
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QBrush, QKeyEvent, QMouseEvent, QPainter, QPen
from PyQt5.QtWidgets import QGraphicsView


class _InteractionMode:
    """交互模式基类。每个子类封装一种交互模式的状态和事件处理。

    CanvasView 在收到鼠标/键盘事件时委托给当前 mode 对象。
    """

    def __init__(self, view):
        self.view = view

    def enter(self):
        """进入此模式时调用。"""

    def leave(self):
        """离开此模式时调用，负责清理临时图元。"""

    def press(self, event: QMouseEvent):
        """处理 mousePressEvent。"""

    def move(self, event: QMouseEvent):
        """处理 mouseMoveEvent。"""

    def release(self, event: QMouseEvent):
        """处理 mouseReleaseEvent。"""

    @property
    def mw(self):
        """快捷访问 MainWindow。"""
        return self.view.main_window


class _IdleMode(_InteractionMode):
    """空闲/选择模式 —— 单选、多选、框选、控制点拖拽、整体拖动。

    事件处理的优先级：
    1. 控制点拖拽（仅对已选中的未锁定图元）
    2. 点选图元（Shift 加选，命中后进入拖动状态）
    3. 框选（非 Shift 时先清空已有选中）
    """

    def __init__(self, view):
        super().__init__(view)
        self.dragging_selected = False
        self.dragging_control_point = False
        self.drag_last_point = None
        self.drag_changed = False
        self.drag_original_points = {}
        self.control_item_id = ''
        self.control_point_index = -1
        self.control_original_points = []
        self.box_selecting = False
        self.box_start = None
        self.box_rect_item = None
        self.hover_item_id = ''
        self.hover_rect_item = None

    def leave(self):
        self._clear_box_rect()
        self._clear_hover_rect()
        self.dragging_selected = False
        self.dragging_control_point = False
        self.drag_last_point = None
        self.drag_changed = False
        self.drag_original_points = {}
        self.control_item_id = ''
        self.control_point_index = -1
        self.control_original_points = []

    def _clear_box_rect(self):
        if self.box_rect_item is not None:
            self.view.scene().removeItem(self.box_rect_item)
            self.box_rect_item = None

    def _clear_hover_rect(self):
        if self.hover_rect_item is not None:
            self.view.scene().removeItem(self.hover_rect_item)
            self.hover_rect_item = None
        self.hover_item_id = ''

    def _update_hover_rect(self, point):
        """更新鼠标悬停高亮：从后向前遍历图元（z-order 从上到下），
        第一个命中的即显示虚线外框。
        """
        hover_id = ''
        for item_id in reversed(list(self.mw.item_dict.keys())):
            item = self.mw.item_dict[item_id]
            if item.contains(QRectF(point[0], point[1], 1, 1).center()):
                hover_id = item_id
                break
        if not hover_id:
            self._clear_hover_rect()
            return
        if hover_id == self.hover_item_id and self.hover_rect_item is not None:
            return
        self._clear_hover_rect()
        item = self.mw.item_dict[hover_id]
        self.hover_item_id = hover_id
        self.hover_rect_item = self.view.scene().addRect(
            item.boundingRect(),
            QPen(QColor(96, 165, 250), 1, Qt.DashLine),
        )
        self.hover_rect_item.setZValue(item.zValue() + 0.25)

    def press(self, event: QMouseEvent):
        """按下处理：按优先级尝试控制点、点选、框选。"""
        if event.button() != Qt.LeftButton:
            return
        point = self.view._clamp_point(event, snap=False)
        selected_item = self.mw.item_dict.get(self.mw.selected_id)

        # 1. 控制点拖拽 —— 命中已选中图元的控制顶点
        if selected_item is not None and not selected_item.locked:
            control_index = selected_item.control_point_at(point)
            if control_index is not None:
                self.dragging_control_point = True
                self.control_item_id = selected_item.id
                self.control_point_index = control_index
                self.control_original_points = [p[:] for p in selected_item.points]
                self.drag_changed = False
                return

        # 2. 点选图元（Shift 加选）
        additive = bool(event.modifiers() & Qt.ShiftModifier)
        if self.mw.select_item_at(point, additive=additive):
            self.dragging_selected = True
            self.drag_last_point = self.view._clamp_point(event)
            self.drag_changed = False
            # 记录所有被选中图元的原始坐标，用于撤销
            self.drag_original_points = {
                item_id: [p[:] for p in item.points]
                for item_id, item in self.mw.selected_items().items()
            }
            return

        # 3. 框选 —— 非 Shift 时清空选中，开始框选
        if not additive:
            self.mw.clear_selection()
        self.box_selecting = True
        self.box_start = point
        self._clear_box_rect()
        self.box_rect_item = self.view.scene().addRect(
            QRectF(point[0], point[1], 1, 1),
            QPen(QColor(80, 120, 220), 1, Qt.DashLine),
        )

    def move(self, event: QMouseEvent):
        point = self.view._clamp_point(event)
        self.mw.update_cursor_status(point)

        if self.box_selecting and self.box_start is not None:
            x0, y0, x1, y1 = normalize_window(*self.box_start, *point)
            if self.box_rect_item is not None:
                self.box_rect_item.setRect(
                    QRectF(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
                )
            return

        if self.dragging_control_point:
            item = self.mw.item_dict.get(self.control_item_id)
            if item is not None and 0 <= self.control_point_index < len(item.points):
                new_points = [p[:] for p in item.points]
                if new_points[self.control_point_index] != point:
                    # 第一次移动时才压入撤销栈（避免每次 move 都产生一条 undo）
                    if not self.drag_changed:
                        self.mw._push_undo()
                    new_points[self.control_point_index] = point
                    item.set_points(new_points)
                    self.drag_changed = True
                    self.mw.update_detail_panel()
            return

        if self.dragging_selected and self.drag_last_point is not None:
            dx = point[0] - self.drag_last_point[0]
            dy = point[1] - self.drag_last_point[1]
            if dx != 0 or dy != 0:
                self.mw.move_selected_by(
                    dx, dy, record_history=not self.drag_changed
                )
                self.drag_changed = True
                self.drag_last_point = point
            return

        self._update_hover_rect(point)

    def release(self, event: QMouseEvent):
        if self.box_selecting and event.button() == Qt.LeftButton:
            point = self.view._clamp_point(event)
            x0, y0, x1, y1 = normalize_window(*self.box_start, *point)
            additive = bool(event.modifiers() & Qt.ShiftModifier)
            self.mw.select_items_in_rect(
                QRectF(x0, y0, max(1, x1 - x0), max(1, y1 - y0)), additive
            )
            self.box_selecting = False
            self.box_start = None
            self._clear_box_rect()
            return

        if self.dragging_control_point and event.button() == Qt.LeftButton:
            item = self.mw.item_dict.get(self.control_item_id)
            if item is not None and self.drag_changed:
                # 拖拽结束后统一记录一次 undo（与 _push_undo 配对）
                self.mw.finish_control_point_drag(
                    item,
                    self.control_point_index,
                    self.control_original_points,
                    [p[:] for p in item.points],
                )
            self.dragging_control_point = False
            self.control_item_id = ''
            self.control_point_index = -1
            self.control_original_points = []
            self.drag_changed = False
            return

        if self.dragging_selected and event.button() == Qt.LeftButton:
            if self.drag_changed:
                self.mw.finish_items_drag(self.drag_original_points)
            self.dragging_selected = False
            self.drag_last_point = None
            self.drag_changed = False
            self.drag_original_points = {}
            return


class _DrawMode(_InteractionMode):
    """绘制模式 —— line/ellipse 拖拽完成，polygon/curve 逐点添加右键结束。

    polygon/curve 的实时预览使用 polyline 类型渲染（首尾不相连），
    直到用户右键确认后才切换为正式的 polygon/curve 类型。
    """

    def __init__(self, view, item_type, algorithm=''):
        super().__init__(view)
        self.item_type = item_type
        self.algorithm = algorithm
        self.temp_points = []
        self.preview_item = None
        self.dragging = False

    def leave(self):
        self._clear_preview()
        self.temp_points = []
        self.dragging = False

    def _clear_preview(self):
        if self.preview_item is not None:
            self.view.scene().removeItem(self.preview_item)
            self.preview_item = None

    def _preview_type(self):
        """预览阶段统一用 polyline（折线）渲染，避免未完成的 polygon 被填充。"""
        if self.item_type in ('polygon', 'curve'):
            return 'polyline'
        return self.item_type

    def _update_preview(self, points):
        if self.preview_item is None:
            self.preview_item = GraphicItem(
                '__preview__',
                self._preview_type(),
                points,
                self.algorithm,
                self.mw.pen_color,
                preview=True,
            )
            self.view.scene().addItem(self.preview_item)
        else:
            self.preview_item.item_type = self._preview_type()
            self.preview_item.algorithm = self.algorithm
            self.preview_item.color = QColor(self.mw.pen_color)
            self.preview_item.set_points(points)

    def _minimum_points(self):
        """各类图元的最低控制点数：多边形 3，B-spline 曲线 4，其余 2。"""
        if self.item_type == 'polygon':
            return 3
        if self.item_type == 'curve':
            return 4 if self.algorithm == 'B-spline' else 2
        return 2

    def _finish_poly_or_curve(self):
        if len(self.temp_points) < self._minimum_points():
            self.mw.statusBar().showMessage('当前点数不足，无法完成图元')
            return
        item = GraphicItem(
            self.mw.get_next_id(),
            self.item_type,
            self.temp_points,
            self.algorithm,
            self.mw.pen_color,
        )
        self.mw.add_item(item)
        self.mw.record_operation(
            f'draw {self.item_type} {self.mw._item_summary(item)}'
        )
        if self.item_type == 'curve':
            if self.algorithm == 'Bezier':
                curve_label = '完成 Bezier 曲线：de Casteljau 递推生成'
            else:
                curve_label = '完成 B-spline 曲线：三次均匀样条更平滑'
        elif self.algorithm == 'DDA':
            curve_label = '完成多边形：逐边调用 DDA 线段算法'
        else:
            curve_label = '完成多边形：逐边调用 Bresenham 线段算法'
        self.mw._flash_subtitle(curve_label)
        self.temp_points = []
        self._clear_preview()
        self.mw.statusBar().showMessage(f'已完成 {item.id}')

    def press(self, event: QMouseEvent):
        point = self.view._clamp_point(event)
        if event.button() == Qt.LeftButton:
            if self.item_type in ('line', 'ellipse'):
                # 拖拽式：起点=终点作为初始状态，后续 move 更新终点
                self.dragging = True
                self.temp_points = [point, point]
                self._update_preview(self.temp_points)
                return
            if self.item_type in ('polygon', 'curve'):
                # 逐点添加式：每次点击追加一个顶点，预览显示连线
                self.temp_points.append(point)
                self._update_preview(self.temp_points + [point])
                return
        elif event.button() == Qt.RightButton and self.item_type in ('polygon', 'curve'):
            self._finish_poly_or_curve()
            return

    def move(self, event: QMouseEvent):
        point = self.view._clamp_point(event)
        self.mw.update_cursor_status(point)
        if self.item_type in ('line', 'ellipse') and self.dragging and len(self.temp_points) == 2:
            self.temp_points[1] = point
            self._update_preview(self.temp_points)
            return
        if self.item_type in ('polygon', 'curve') and self.temp_points:
            self.view.current_mouse = point
            # 预览时把当前鼠标位置作为"虚拟末点"附加到已有顶点后
            self._update_preview(self.temp_points + [point])
            return

    def release(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        point = self.view._clamp_point(event)
        if self.item_type in ('line', 'ellipse') and self.dragging and len(self.temp_points) == 2:
            self.dragging = False
            self.temp_points[1] = point
            item = GraphicItem(
                self.mw.get_next_id(),
                self.item_type,
                self.temp_points,
                self.algorithm,
                self.mw.pen_color,
            )
            self.mw.add_item(item)
            self.mw.record_operation(
                f'draw {self.item_type} {self.mw._item_summary(item)}'
            )
            if self.item_type == 'line':
                if self.algorithm == 'Naive':
                    line_label = '完成线段：Naive 根据直线方程采样像素'
                elif self.algorithm == 'DDA':
                    line_label = '完成线段：DDA 输出离散像素序列'
                else:
                    line_label = '完成线段：Bresenham 使用整数误差递推'
            elif self.item_type == 'ellipse':
                line_label = '完成椭圆：中点算法利用对称性生成边界'
            else:
                line_label = f'绘制{self.item_type}'
            self.mw._flash_subtitle(line_label)
            self.temp_points = []
            self._clear_preview()
            self.mw.statusBar().showMessage(f'已完成 {item.id}')
            return


class _ClipMode(_InteractionMode):
    """交互式裁剪模式 —— 拖出裁剪窗口，实时预览裁剪前后对比。

    线段裁剪使用 CS/LB 算法（由 algorithm 指定），
    多边形裁剪固定用 Sutherland-Hodgman。
    预览结果用蓝色显示在原图元上方；若裁剪后无剩余则预览消失。
    """

    def __init__(self, view, algorithm):
        super().__init__(view)
        self.algorithm = algorithm
        self.clip_start = None
        self.clip_dragging = False
        self.clip_rect_item = None
        self.clip_preview_item = None
        self.clip_window = None
        self.clip_result = None

    def leave(self):
        self._clear_clip_items()
        self.clip_start = None
        self.clip_dragging = False
        self.clip_window = None
        self.clip_result = None

    def _clear_clip_items(self):
        if self.clip_rect_item is not None:
            self.view.scene().removeItem(self.clip_rect_item)
            self.clip_rect_item = None
        if self.clip_preview_item is not None:
            self.view.scene().removeItem(self.clip_preview_item)
            self.clip_preview_item = None

    def _preview_item_type(self):
        """线段裁剪预览用 line，多边形裁剪预览用 polygon。"""
        item = self.mw.item_dict.get(self.mw.selected_id)
        if item is not None and item.item_type == 'polygon':
            return 'polygon'
        return 'line'

    def _update_clip_preview(self, point):
        """实时计算裁剪结果并更新预览图元。"""
        if self.clip_start is None:
            return
        x0, y0, x1, y1 = normalize_window(*self.clip_start, *point)
        self.clip_window = (x0, y0, x1, y1)
        rect = QRectF(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
        if self.clip_rect_item is None:
            self.clip_rect_item = self.view.scene().addRect(
                rect, QPen(QColor(220, 80, 40), 1, Qt.DashLine)
            )
        else:
            self.clip_rect_item.setRect(rect)

        item = self.mw.item_dict.get(self.mw.selected_id)
        if item is None:
            return
        if item.item_type == 'polygon':
            self.clip_result = alg.clip_polygon(
                item.points, x0, y0, x1, y1,
            )
        elif item.item_type == 'line':
            self.clip_result = alg.clip(
                item.points, x0, y0, x1, y1, self.algorithm,
            )
        else:
            return
        if self.clip_result:
            preview_type = self._preview_item_type()
            if self.clip_preview_item is None:
                self.clip_preview_item = GraphicItem(
                    '__clip_preview__',
                    preview_type,
                    self.clip_result,
                    'Bresenham',
                    QColor(20, 150, 220),
                    preview=True,
                )
                self.view.scene().addItem(self.clip_preview_item)
            else:
                self.clip_preview_item.item_type = preview_type
                self.clip_preview_item.set_points(self.clip_result)
        elif self.clip_preview_item is not None:
            self.view.scene().removeItem(self.clip_preview_item)
            self.clip_preview_item = None

    def press(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            point = self.view._clamp_point(event)
            self.clip_start = point
            self.clip_dragging = True
            self._update_clip_preview(point)
        elif event.button() == Qt.RightButton:
            self.mw.statusBar().showMessage('已取消交互式裁剪')
            self.mw._flash_subtitle('右键取消：放弃当前交互式裁剪')
            self.view.switch_mode(_IdleMode(self.view))

    def move(self, event: QMouseEvent):
        point = self.view._clamp_point(event)
        self.mw.update_cursor_status(point)
        if self.clip_dragging:
            self._update_clip_preview(point)

    def release(self, event: QMouseEvent):
        if self.clip_dragging and event.button() == Qt.LeftButton:
            point = self.view._clamp_point(event)
            self.clip_dragging = False
            self._update_clip_preview(point)
            self.mw.confirm_interactive_clip(
                self.algorithm,
                self.clip_window,
                self.clip_result,
            )


class _TransformMode(_InteractionMode):
    """交互式旋转/缩放模式 —— 两步操作：先调整中心，再拖拽生成变换预览。

    旋转：以中心为原点，拖拽角度 = 当前鼠标角度 - 按下时的起始角度
    缩放：比例 = 当前鼠标到中心的距离 / 按下时的起始距离
          范围限制为 0.05x ~ 20.0x，最小距离保护（防止除零）
    """

    def __init__(self, view, item_id, transform_type):
        super().__init__(view)
        self.item_id = item_id
        self.transform_type = transform_type
        self.center = None
        self.center_item = None
        self.preview_item = None
        self.guide_item = None
        self.text_item = None
        self.dragging_center = False
        self.dragging_transform = False
        self.start_point = None
        self.start_angle = 0.0      # 拖拽起始的角度（相对于中心）
        self.start_distance = 1.0   # 拖拽起始的距离（最小保护为 1.0）
        self.preview_points = None
        self.preview_value = None

    def enter(self):
        item = self.mw.item_dict.get(self.item_id)
        if item is None:
            self.view.switch_mode(_IdleMode(self.view))
            return
        self.center = self._default_center(item)
        self._update_center_marker()
        self._update_text(
            '拖动中心点调整中心；在画布上拖拽生成预览；右键取消'
        )

    def leave(self):
        self._clear_transform_items()
        self.dragging_center = False
        self.dragging_transform = False

    def _default_center(self, item):
        return alg.compute_center(item.points)

    def _clear_transform_items(self):
        for transient_item in (
            self.center_item,
            self.preview_item,
            self.guide_item,
            self.text_item,
        ):
            if transient_item is not None:
                self.view.scene().removeItem(transient_item)
        self.center_item = None
        self.preview_item = None
        self.guide_item = None
        self.text_item = None

    def _distance_to_center(self, point):
        return math.hypot(point[0] - self.center[0], point[1] - self.center[1])

    def _angle_to_center(self, point):
        """返回点相对于中心的极角（度）。"""
        return math.degrees(
            math.atan2(point[1] - self.center[1], point[0] - self.center[0])
        )

    def _near_center(self, point):
        """判断点是否在中心标记的 9px 范围内。"""
        return abs(point[0] - self.center[0]) <= 9 and abs(point[1] - self.center[1]) <= 9

    def _update_center_marker(self):
        if self.center is None:
            return
        x, y = self.center
        rect = QRectF(x - 6, y - 6, 12, 12)
        if self.center_item is None:
            self.center_item = self.view.scene().addEllipse(
                rect,
                QPen(QColor(37, 99, 235), 2),
                QBrush(QColor(255, 255, 255)),
            )
            self.center_item.setZValue(10_000)
        else:
            self.center_item.setRect(rect)

    def _update_guide(self, point):
        """从中心到当前鼠标的引导线。"""
        if self.center is None:
            return
        if self.guide_item is None:
            self.guide_item = self.view.scene().addLine(
                self.center[0],
                self.center[1],
                point[0],
                point[1],
                QPen(QColor(37, 99, 235), 1, Qt.DashLine),
            )
            self.guide_item.setZValue(9_999)
        else:
            self.guide_item.setLine(
                self.center[0], self.center[1], point[0], point[1]
            )

    def _update_text(self, text, point=None):
        if self.text_item is None:
            self.text_item = self.view.scene().addText(text)
            self.text_item.setDefaultTextColor(QColor(29, 78, 216))
            self.text_item.setZValue(10_001)
        else:
            self.text_item.setPlainText(text)
        anchor = point or self.center or [12, 12]
        self.text_item.setPos(anchor[0] + 12, anchor[1] + 12)

    def _update_preview(self, point):
        """根据当前鼠标位置更新变换预览图元。"""
        item = self.mw.item_dict.get(self.item_id)
        if item is None or self.center is None:
            return
        cx, cy = self.center
        if self.transform_type == 'rotate':
            # 旋转量 = 当前角度 - 按下时角度（取整）
            degree = int(round(self._angle_to_center(point) - self.start_angle))
            points = alg.rotate(item.points, cx, cy, degree)
            text = f'旋转: {degree}°  中心: ({cx}, {cy})'
            self.preview_value = degree
        else:
            # 缩放比例 = 当前距离 / 起始距离，夹在 [0.05, 20.0]
            distance = max(1.0, self._distance_to_center(point))
            factor = max(0.05, min(20.0, distance / self.start_distance))
            points = alg.scale(item.points, cx, cy, factor)
            text = f'缩放: {factor:.3f}  中心: ({cx}, {cy})'
            self.preview_value = factor
        self.preview_points = points
        if self.preview_item is None:
            self.preview_item = GraphicItem(
                '__interactive_transform_preview__',
                item.item_type,
                points,
                item.algorithm,
                QColor(37, 99, 235),
                preview=True,
            )
            self.preview_item.setZValue(item.zValue() + 0.75)
            self.view.scene().addItem(self.preview_item)
        else:
            self.preview_item.set_points(points)
        self._update_guide(point)
        self._update_text(text, point)
        self.mw.statusBar().showMessage(text)

    def press(self, event: QMouseEvent):
        if event.button() == Qt.RightButton:
            self.mw.statusBar().showMessage('已取消交互式变换')
            self.mw._flash_subtitle('右键取消：放弃当前交互式变换并返回选择')
            self.view.switch_mode(_IdleMode(self.view))
            self.view.unsetCursor()
            self.mw._set_active_tool('select', '选择')
            return
        if event.button() != Qt.LeftButton:
            return
        point = self.view._clamp_point(event)
        # 点击靠近中心 → 拖动中心
        if self._near_center(point):
            self.dragging_center = True
            self.view.setCursor(Qt.SizeAllCursor)
            return
        # 远离中心 → 拖拽变换
        self.dragging_transform = True
        self.start_point = point
        self.start_angle = self._angle_to_center(point)
        self.start_distance = max(1.0, self._distance_to_center(point))
        self._update_preview(point)

    def move(self, event: QMouseEvent):
        point = self.view._clamp_point(event)
        self.mw.update_cursor_status(point)
        if self.dragging_center:
            # 拖动中心时清除旧预览/引导线，仅更新中心标记和文字
            self.center = point
            self.preview_points = None
            if self.preview_item is not None:
                self.view.scene().removeItem(self.preview_item)
                self.preview_item = None
            if self.guide_item is not None:
                self.view.scene().removeItem(self.guide_item)
                self.guide_item = None
            self._update_center_marker()
            self._update_text(f'中心: ({point[0]}, {point[1]})', point)
            return
        if self.dragging_transform:
            self._update_preview(point)
            return
        # 悬停反馈：靠近中心时改变光标
        if self._near_center(point):
            self.view.setCursor(Qt.SizeAllCursor)
        else:
            self.view.setCursor(Qt.CrossCursor)

    def release(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        if self.dragging_center:
            self.dragging_center = False
            self.view.setCursor(Qt.CrossCursor)
            return
        if self.dragging_transform:
            self.dragging_transform = False
            item = self.mw.item_dict.get(self.item_id)
            if item is not None and self.preview_points is not None:
                self.mw.apply_interactive_transform(
                    item,
                    self.transform_type,
                    self.center,
                    self.preview_value,
                    self.preview_points,
                )
            # 变换完成后回到空闲模式
            self.view.switch_mode(_IdleMode(self.view))
            self.view.unsetCursor()
            self.mw._set_active_tool('select', '选择')