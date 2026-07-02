"""可复用的 PyQt 控件 —— 带行号的文本编辑器。

LineNumberArea:       行号 gutter 部件，嵌入在编辑器的 viewport 左侧
LineNumberTextEdit:   继承 QPlainTextEdit，增加行号显示、当前行高亮、错误行标记
"""

from PyQt5.QtCore import QRect, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QTextFormat
from PyQt5.QtWidgets import QPlainTextEdit, QTextEdit, QWidget


class LineNumberArea(QWidget):
    """行号区域 —— 作为编辑器的子控件嵌入，绘制委托给编辑器。"""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class LineNumberTextEdit(QPlainTextEdit):
    """带行号 gutter、当前行高亮、错误行标记的纯文本编辑器。

    通过 Qt 的 ExtraSelection 机制实现整行背景色，不影响文本内容。
    行号宽度根据文档总行数自适应计算。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def line_number_area_width(self):
        """gutter 宽度，按最大行号位数计算。"""
        digits = len(str(max(1, self.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance('9') * digits

    def update_line_number_area_width(self, _block_count):
        """行数变化时重新设置 viewport 左边距。"""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        """滚动时同步移动或重绘行号区域。"""
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        """编辑器尺寸变化时重新定位 gutter 区域。"""
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        """绘制行号 gutter —— 浅灰背景 + 灰色数字，右对齐。"""
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(248, 250, 252))
        painter.setPen(QColor(107, 114, 128))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self):
        """淡蓝色背景高亮当前行。"""
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(239, 246, 255))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    def highlight_error_line(self, line_number):
        """标记错误行 —— 当前行保持淡蓝，错误行叠淡红色背景并滚动到可见位置。"""
        selections = []
        current = QTextEdit.ExtraSelection()
        current.format.setBackground(QColor(239, 246, 255))
        current.format.setProperty(QTextFormat.FullWidthSelection, True)
        current.cursor = self.textCursor()
        current.cursor.clearSelection()
        selections.append(current)

        block = self.document().findBlockByNumber(max(0, line_number - 1))
        if block.isValid():
            error = QTextEdit.ExtraSelection()
            error.format.setBackground(QColor(254, 226, 226))
            error.format.setProperty(QTextFormat.FullWidthSelection, True)
            error.cursor = self.textCursor()
            error.cursor.setPosition(block.position())
            error.cursor.clearSelection()
            selections.append(error)
            cursor = self.textCursor()
            cursor.setPosition(block.position())
            self.setTextCursor(cursor)
            self.centerCursor()
        self.setExtraSelections(selections)