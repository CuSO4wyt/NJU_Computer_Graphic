"""全局 Qt 样式表 —— 基于 Tailwind CSS 灰/蓝色系，统一所有控件的视觉风格。

通过 Qt 的 objectName 选择器（如 #railToolButton）对不同上下文中的同类控件
应用差异化样式，避免在代码中逐个设置样式。
"""

from PyQt5.QtWidgets import QApplication


APP_QSS = """
/* 全局默认：浅灰背景 + 深灰文字，中文字体优先 */
QMainWindow, QWidget {
    background: #F3F4F6;
    color: #111827;
    font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

QToolBar {
    background: #FFFFFF;
    border: 0;
    border-bottom: 1px solid #D1D5DB;
    spacing: 8px;
    padding: 8px 10px;
}

QToolButton, QPushButton {
    background: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 6px 8px;
}

QToolBar QToolButton {
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
}

QToolButton:hover, QPushButton:hover {
    background: #F9FAFB;
    border-color: #9CA3AF;
}

QToolButton:checked, QPushButton:checked {
    background: #DBEAFE;
    border-color: #2563EB;
    color: #1D4ED8;
    font-weight: 600;
}

QPushButton#dangerButton {
    color: #DC2626;
}

QToolButton#primaryButton, QPushButton#primaryButton {
    background: #2563EB;
    border-color: #2563EB;
    color: #FFFFFF;
    font-weight: 600;
}

QToolButton#primaryButton:hover, QPushButton#primaryButton:hover {
    background: #1D4ED8;
}

QToolButton#dangerButton, QPushButton#dangerButton {
    color: #DC2626;
    border-color: #FCA5A5;
}

QFrame#toolbarGroup {
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
}

QLabel#toolbarGroupLabel {
    color: #6B7280;
    font-size: 12px;
    font-weight: 600;
    padding: 0 3px 0 0;
}

QFrame#toolbarDivider {
    background: #D1D5DB;
    min-width: 1px;
    max-width: 1px;
    margin: 5px 6px;
}

QFrame#toolRail {
    background: #FFFFFF;
    border-right: 1px solid #D1D5DB;
}

QLabel#railSectionLabel {
    color: #9CA3AF;
    font-size: 10px;
    font-weight: 700;
    padding: 6px 0 2px 0;
}

QToolButton#railToolButton {
    border: 0;
    border-radius: 7px;
    padding: 4px;
    min-width: 46px;
    max-width: 46px;
    min-height: 42px;
    max-height: 42px;
}

QToolButton#railToolButton:hover {
    background: #F3F4F6;
}

QToolButton#railToolButton:checked {
    background: #DBEAFE;
    color: #1D4ED8;
    border: 2px solid #2563EB;
    font-weight: 600;
}

QToolButton#railToolButton:disabled {
    color: #9CA3AF;
    background: #F9FAFB;
}

QFrame#railDivider {
    background: #E5E7EB;
    min-height: 1px;
    max-height: 1px;
    margin: 6px 8px;
}

QLabel#panelTitle {
    color: #374151;
    font-weight: 700;
    padding-top: 4px;
}

QFrame#canvasWorkspace {
    background: #E5E7EB;
    border: 0;
}

QFrame#canvasViewBar {
    background: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
}

QLabel#workspaceZoomLabel {
    background: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #BFDBFE;
    border-radius: 6px;
    padding: 4px 8px;
    font-weight: 700;
}

QFrame#canvasPaperFrame {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
}

QWidget#sidePanel {
    background: #F8FAFC;
    border-left: 1px solid #D1D5DB;
}

QGraphicsView {
    background: #FFFFFF;
    border: 0;
}

QGraphicsView#overviewView {
    background: #F8FAFC;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
}

QListWidget, QTextEdit, QTableWidget, QLineEdit, QSpinBox {
    background: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    selection-background-color: #DBEAFE;
    selection-color: #111827;
}

QListWidget::item {
    padding: 6px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background: #DBEAFE;
    color: #1D4ED8;
}

QTabWidget::pane {
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    background: #FFFFFF;
}

QTabBar::tab {
    background: #F9FAFB;
    border: 1px solid #D1D5DB;
    border-bottom: 0;
    padding: 7px 10px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}

QTabBar::tab:selected {
    background: #FFFFFF;
    color: #1D4ED8;
    font-weight: 600;
}

QHeaderView::section {
    background: #F9FAFB;
    border: 0;
    border-bottom: 1px solid #D1D5DB;
    padding: 6px;
    font-weight: 600;
}

QStatusBar {
    background: #FFFFFF;
    border-top: 1px solid #D1D5DB;
}

QLabel#statusPill, QLabel#colorSwatch {
    background: #F9FAFB;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 3px 8px;
}

QLabel#helpPanel {
    background: #F8FAFC;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 8px;
    color: #4B5563;
}
"""


def apply_app_style():
    """应用全局 QSS 样式表，应在 QApplication 实例化后调用。"""
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(APP_QSS)