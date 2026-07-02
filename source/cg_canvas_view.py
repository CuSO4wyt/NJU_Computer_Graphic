"""画布视图 —— QGraphicsView 子类，管理缩放、平移、网格与交互模式切换。

模式采用状态对象委托：CanvasView 持有当前模式实例，鼠标/键盘事件
全部转发给 mode.press/move/release。切换模式时先调用旧模式的 leave()，
再调用新模式的 enter()，保证临时图元被清理。
"""

from cg_interaction_modes import _IdleMode, _DrawMode, _ClipMode, _TransformMode
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PyQt5.QtWidgets import QGraphicsView


class CanvasView(QGraphicsView):
    def __init__(self, scene, main_window):
        super().__init__(scene, main_window)
        self.main_window = main_window
        self._mode = _IdleMode(self)
        self._mode.enter()

        # ── 跨模式共享状态 ──
        self.current_mouse = None
        self.show_grid = True
        self.view_scale = 1.0

        # 平移状态 —— 中键或空格+左键触发，所有模式共享
        self._panning = False
        self._pan_last_pos = None
        self._space_pressed = False

        self.setMouseTracking(True)
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    # ── 模式切换 ─────────────────────────────────────────────────────

    def switch_mode(self, new_mode):
        """切换交互模式，先清理旧模式再初始化新模式。"""
        self._mode.leave()
        self._mode = new_mode
        new_mode.enter()

    def begin_draw(self, item_type, algorithm=''):
        """进入绘制模式，清空选中并提示操作方式。"""
        self.main_window.clear_selection()
        self.switch_mode(_DrawMode(self, item_type, algorithm))
        self.setCursor(Qt.CrossCursor)
        if item_type in ('polygon', 'curve'):
            self.main_window.statusBar().showMessage(
                '左键添加点，右键结束当前图元'
            )
        elif item_type == 'line':
            self.main_window.statusBar().showMessage('左键拖拽绘制线段')
        elif item_type == 'ellipse':
            self.main_window.statusBar().showMessage('左键拖拽绘制椭圆')

    def begin_clip(self, algorithm):
        self.switch_mode(_ClipMode(self, algorithm))
        self.setCursor(Qt.CrossCursor)
        self.main_window.statusBar().showMessage(
            f'交互式裁剪 ({algorithm}): 左键拖出裁剪窗口'
        )

    def begin_transform(self, item_id, transform_type):
        self.switch_mode(_TransformMode(self, item_id, transform_type))
        self.setCursor(Qt.CrossCursor)
        label = '旋转' if transform_type == 'rotate' else '缩放'
        self.main_window.statusBar().showMessage(
            f'交互式{label}: 拖动中心点调整中心，拖拽画布生成预览'
        )

    def clear_mode(self):
        """回到空闲模式。"""
        self.switch_mode(_IdleMode(self))
        self.unsetCursor()

    def cancel_clip_mode(self):
        if isinstance(self._mode, _ClipMode):
            self.switch_mode(_IdleMode(self))
            self.unsetCursor()

    def _reset_temp_state(self):
        """撤销/重做后清理残留的交互模式。"""
        if not isinstance(self._mode, _IdleMode):
            self.switch_mode(_IdleMode(self))
            self.unsetCursor()

    # ── 共享工具方法 ─────────────────────────────────────────────────

    def _clamp_point(self, event: QMouseEvent, snap=True):
        """将鼠标事件的视口坐标转为场景坐标，并钳制在画布范围内。

        当 snap=True 时应用主窗口的吸附逻辑，确保交互点对齐到网格。
        """
        scene_point = self.mapToScene(event.pos())
        rect = self.sceneRect()
        x = min(max(int(scene_point.x()), 0), int(rect.width()) - 1)
        y = min(max(int(scene_point.y()), 0), int(rect.height()) - 1)
        if snap:
            x, y = self.main_window.snap_point([x, y])
            x = min(max(x, 0), int(rect.width()) - 1)
            y = min(max(y, 0), int(rect.height()) - 1)
        return [x, y]

    def _clear_box_rect(self):
        if isinstance(self._mode, _IdleMode):
            self._mode._clear_box_rect()

    def _clear_clip_items(self):
        if isinstance(self._mode, _ClipMode):
            self._mode._clear_clip_items()

    def _clear_transform_items(self):
        if isinstance(self._mode, _TransformMode):
            self._mode._clear_transform_items()

    # ── 属性：暴露当前模式的临时图元引用给 MainWindow ─────────────────

    @property
    def mode(self):
        """当前交互模式的显示名称。"""
        if isinstance(self._mode, _IdleMode):
            return ''
        if isinstance(self._mode, _DrawMode):
            return self._mode.item_type
        if isinstance(self._mode, _ClipMode):
            return 'clip'
        if isinstance(self._mode, _TransformMode):
            return 'rotate' if self._mode.transform_type == 'rotate' else 'scale'
        return ''

    @property
    def preview_item(self):
        m = self._mode
        return m.preview_item if isinstance(m, _DrawMode) else None

    @property
    def draw_has_draft(self):
        m = self._mode
        return isinstance(m, _DrawMode) and bool(m.temp_points)

    @property
    def clip_rect_item(self):
        m = self._mode
        return m.clip_rect_item if isinstance(m, _ClipMode) else None

    @property
    def clip_preview_item(self):
        m = self._mode
        return m.clip_preview_item if isinstance(m, _ClipMode) else None

    @property
    def box_rect_item(self):
        m = self._mode
        return m.box_rect_item if isinstance(m, _IdleMode) else None

    @property
    def hover_rect_item(self):
        m = self._mode
        return m.hover_rect_item if isinstance(m, _IdleMode) else None

    @property
    def transform_center_item(self):
        m = self._mode
        return m.center_item if isinstance(m, _TransformMode) else None

    @property
    def transform_guide_item(self):
        m = self._mode
        return m.guide_item if isinstance(m, _TransformMode) else None

    @property
    def transform_text_item(self):
        m = self._mode
        return m.text_item if isinstance(m, _TransformMode) else None

    @property
    def transform_mode_preview_item(self):
        m = self._mode
        return m.preview_item if isinstance(m, _TransformMode) else None

    # ── 背景网格绘制 ─────────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """自适应间距网格：根据当前缩放级别动态调整网格步长。

        细线网格步长保持在 15~45 屏幕像素之间：
        - 若 step * scale < 15 则翻倍步长（避免太密）
        - 若 step * scale > 45 且 step > 10 则减半步长
        粗线（主网格线）步长为细线的 4 倍。
        """
        super().drawBackground(painter, rect)
        if not self.show_grid:
            return
        scale = max(0.01, self.view_scale)
        step = 20
        while step * scale < 15:
            step *= 2
        while step * scale > 45 and step > 10:
            step = max(10, step // 2)
        # 细网格线
        painter.setPen(QPen(QColor(229, 231, 235), 1))
        left = int(rect.left()) - int(rect.left()) % step
        top = int(rect.top()) - int(rect.top()) % step
        right = int(rect.right())
        bottom = int(rect.bottom())
        for x in range(left, right + step, step):
            painter.drawLine(x, top, x, bottom)
        for y in range(top, bottom + step, step):
            painter.drawLine(left, y, right, y)
        # 主网格线（4 倍步长）
        major_step = step * 4
        painter.setPen(QPen(QColor(203, 213, 225), 1))
        major_left = int(rect.left()) - int(rect.left()) % major_step
        major_top = int(rect.top()) - int(rect.top()) % major_step
        for x in range(major_left, right + major_step, major_step):
            painter.drawLine(x, top, x, bottom)
        for y in range(major_top, bottom + major_step, major_step):
            painter.drawLine(left, y, right, y)

    # ── 滚轮缩放 ────────────────────────────────────────────────────

    def wheelEvent(self, event):
        """滚轮缩放：每次 15%，缩放范围 0.2x ~ 8.0x。"""
        old_scale = self.view_scale
        requested = old_scale * (1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        self.view_scale = max(0.2, min(8.0, requested))
        factor = self.view_scale / old_scale
        if factor == 1.0:
            return
        self.scale(factor, factor)
        self.main_window._update_zoom_status()

    def reset_zoom(self):
        self.resetTransform()
        self.view_scale = 1.0
        self.main_window._flash_subtitle('100% 缩放：一个画布像素对应一个屏幕像素')

    def fit_to_canvas(self):
        """将整个画布缩放到当前视口内可见。"""
        self.resetTransform()
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
        self.view_scale = self.transform().m11()
        self.main_window._flash_subtitle('适配画布：自动缩放视图，使整张画布可见')

    # ── 事件分发 —— 平移由 View 层统一处理，其余转发到当前模式 ────────

    def mousePressEvent(self, event: QMouseEvent):
        # 中键或空格+左键 → 平移
        if event.button() == Qt.MiddleButton or (
            event.button() == Qt.LeftButton and self._space_pressed
        ):
            self._panning = True
            self._pan_last_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        self._mode.press(event)

    def contextMenuEvent(self, event):
        # 仅在空闲模式下弹出画布右键菜单
        if isinstance(self._mode, _IdleMode):
            point = self.mapToScene(event.pos())
            self.main_window.show_canvas_context_menu(event.globalPos(), point)
            return
        super().contextMenuEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning and self._pan_last_pos is not None:
            delta = event.pos() - self._pan_last_pos
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            self._pan_last_pos = event.pos()
            return
        self._mode.move(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._panning and event.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._panning = False
            self._pan_last_pos = None
            self.unsetCursor()
            return
        self._mode.release(event)

    def keyPressEvent(self, event: QKeyEvent):
        # 空格按下时进入"预备平移"状态，光标变为手型
        if event.key() == Qt.Key_Space:
            self._space_pressed = True
            self.setCursor(Qt.OpenHandCursor)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Space:
            self._space_pressed = False
            self.unsetCursor()
            return
        super().keyReleaseEvent(event)
