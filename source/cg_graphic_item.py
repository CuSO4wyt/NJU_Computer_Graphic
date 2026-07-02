"""画布上的图元项 —— 继承 QGraphicsItem，负责像素渲染、命中检测与控制点交互。

像素缓存策略：边缘像素与填充像素只计算一次，坐标变更时 cache 置空。
Qt 的 QGraphicsScene 会自动剔除视口外的 item（通过 boundingRect），无需手动裁剪。
"""

from typing import Optional

import cg_algorithms as alg
from cg_scene import draw_item_pixels
from PyQt5.QtCore import QPoint, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen
from PyQt5.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget


HANDLE_RADIUS = 4  # 选中状态下控制点方形手柄的半边长


class GraphicItem(QGraphicsItem):
    """画布图元的 Qt 图形项。

    preview=True 时仅作交互预览（如拖拽过程中显示的临时形态），
    不渲染选中边框和手柄。
    """
    def __init__(
        self,
        item_id: str,
        item_type: str,
        points: list,
        algorithm: str = '',
        color: QColor = QColor(0, 0, 0),
        preview: bool = False,
        visible: bool = True,
        locked: bool = False,
        fill_enabled: bool = False,
        fill_color: QColor = QColor(220, 220, 220),
        parent: Optional[QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.id = item_id
        self.item_type = item_type
        self.points = [list(point) for point in points]
        self.algorithm = algorithm
        self.color = QColor(color)
        self.preview = preview
        self.visible = visible
        self.locked = locked
        self.fill_enabled = fill_enabled
        self.fill_color = QColor(fill_color)
        self.selected = False
        self._pixel_cache = None   # 边缘像素列表（用于绘制）
        self._pixel_set = None     # 边缘像素集合（用于命中检测 O(1)）
        self._fill_cache = None    # 填充像素列表

    def set_points(self, points):
        """更新顶点并通知 Qt 几何变更，缓存全部失效。"""
        self.prepareGeometryChange()
        self.points = [list(point) for point in points]
        self._pixel_cache = None
        self._pixel_set = None
        self._fill_cache = None
        self.update()

    def set_selected(self, selected):
        self.selected = selected
        self.update()

    def _pixels(self):
        """惰性计算边缘像素，同时维护一个 set 用于快速命中检测。"""
        if self._pixel_cache is not None:
            return self._pixel_cache
        if not self.points:
            self._pixel_cache = []
            self._pixel_set = set()
            return self._pixel_cache
        pixels = draw_item_pixels({
            'type': self.item_type,
            'points': self.points,
            'algorithm': self.algorithm,
        })
        self._pixel_cache = pixels
        self._pixel_set = {tuple(p) for p in pixels}
        return self._pixel_cache

    def _fill_pixels(self):
        """惰性计算多边形填充像素，仅对启用了填充的多边形生效。"""
        if self._fill_cache is not None:
            return self._fill_cache
        if self.item_type == 'polygon' and self.fill_enabled:
            self._fill_cache = alg.fill_polygon(self.points)
        else:
            self._fill_cache = []
        return self._fill_cache

    def control_point_at(self, point, radius=8):
        """检查点命中哪个控制顶点，返回索引；无命中返回 None。"""
        px, py = point
        for index, (x, y) in enumerate(self.points):
            if abs(px - x) <= radius and abs(py - y) <= radius:
                return index
        return None

    def contains(self, point):
        """命中检测：先查边缘像素（容差 2px），再查填充区域。

        锁定的图元不参与选中，隐藏的图元不可交互。
        """
        if not self.visible or self.locked:
            return False
        px = int(round(point.x()))
        py = int(round(point.y()))
        # 边缘像素命中 —— 5x5 邻域容差，补偿整数舍入
        self._pixels()
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if (px + dx, py + dy) in self._pixel_set:
                    return True
        # 填充多边形内部命中
        if self.item_type == 'polygon' and self.fill_enabled:
            self._fill_pixels()
            if self._fill_cache:
                fill_set = {(x, y) for x, y in self._fill_cache}
                if (px, py) in fill_set:
                    return True
        return False

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        """Qt 绘制回调：先画填充区域（确保遮挡关系正确），再画边缘像素，最后叠选中装饰。"""
        if not self.visible:
            return
        # 填充多边形 —— 以实心画刷覆盖，使下层图元被正确遮挡
        if self.fill_enabled and self.item_type == 'polygon':
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(self.fill_color))
            poly = [QPoint(x, y) for x, y in self.points]
            painter.drawPolygon(*poly)
        # 边缘像素
        pen = QPen(self.color)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        edge_px = self._pixels()
        if edge_px:
            points = [QPoint(x, y) for x, y in edge_px]
            painter.drawPoints(*points)

        # 选中状态装饰：虚线外框 + 控制点手柄
        if self.selected and not self.preview:
            painter.setPen(QPen(QColor(37, 99, 235), 1, Qt.DashLine))
            painter.drawRect(self.boundingRect())
            painter.setPen(QPen(QColor(37, 99, 235)))
            for x, y in self.points:
                painter.fillRect(
                    x - HANDLE_RADIUS,
                    y - HANDLE_RADIUS,
                    HANDLE_RADIUS * 2,
                    HANDLE_RADIUS * 2,
                    QColor(255, 255, 255),
                )
                painter.drawRect(
                    x - HANDLE_RADIUS,
                    y - HANDLE_RADIUS,
                    HANDLE_RADIUS * 2,
                    HANDLE_RADIUS * 2,
                )

    def boundingRect(self) -> QRectF:
        """返回图元的外接矩形（含 8px 边距），供 Qt 空间索引和视口裁剪使用。

        椭圆特殊处理：其外接矩形直接由两个定义点给出，无需对所有像素求最值。
        """
        if not self.points:
            return QRectF(0, 0, 1, 1)

        # 椭圆：两点定义的外接矩形即为其 bounding rect
        if self.item_type == 'ellipse' and len(self.points) == 2:
            x0, y0 = self.points[0]
            x1, y1 = self.points[1]
            left = min(x0, x1)
            top = min(y0, y1)
            width = abs(x1 - x0)
            height = abs(y1 - y0)
            return QRectF(left - 8, top - 8, width + 16, height + 16)

        xs = [point[0] for point in self.points]
        ys = [point[1] for point in self.points]
        left = min(xs)
        top = min(ys)
        width = max(xs) - left
        height = max(ys) - top
        return QRectF(left - 8, top - 8, width + 16, height + 16)