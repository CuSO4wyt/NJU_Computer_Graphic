"""GUI 图标 —— 内联 SVG 渲染，不依赖外部图标库。"""

from PyQt5.QtCore import QByteArray, QSize, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer


def _svg_icon(body, color='#111827', size=24):
    """将 SVG path 片段拼接为完整 SVG 文档，渲染到 QPixmap 再包装成 QIcon。

    统一使用 24x24 viewBox，stroke 风格（fill=none），颜色和尺寸可调。
    """
    svg = f'''
    <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}"
         viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round">
      {body}
    </svg>
    '''
    renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


# 图标名 → SVG path 映射，所有图标来自 Lucide 风格 24x24 网格
ICON_SVGS = {
    'open': '<path d="M4 20h16"/><path d="M4 4h7l2 3h7v11H4z"/>',
    'import': '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    'export': '<path d="M12 21V9"/><path d="m7 14 5-5 5 5"/><path d="M5 3h14"/>',
    'history': '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6"/><path d="M12 7v5l3 2"/>',
    'save': '<path d="M5 3h12l2 2v16H5z"/><path d="M8 3v6h8"/><path d="M8 17h8"/>',
    'reset': '<path d="M4 4v6h6"/><path d="M20 20v-6h-6"/><path d="M5 15a7 7 0 0 0 11 4"/><path d="M19 9A7 7 0 0 0 8 5"/>',
    'undo': '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-2"/>',
    'redo': '<path d="m15 14 5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h2"/>',
    'copy': '<rect x="9" y="9" width="11" height="11" rx="2"/><rect x="4" y="4" width="11" height="11" rx="2"/>',
    'trash': '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 15h10l1-15"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    'eye': '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    'eye-off': '<path d="M3 3l18 18"/><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M9.5 5.5A9 9 0 0 1 12 5c6 0 10 7 10 7a15 15 0 0 1-3.1 3.9"/><path d="M6.6 6.6C3.8 8.4 2 12 2 12s4 7 10 7a9.5 9.5 0 0 0 4.3-1"/>',
    'lock': '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    'unlock': '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.5-2"/>',
    'fill': '<path d="m5 11 6-6 8 8-6 6z"/><path d="M4 20h16"/><path d="M13 5v8H5"/>',
    'fit': '<path d="M4 9V4h5"/><path d="M20 9V4h-5"/><path d="M4 15v5h5"/><path d="M20 15v5h-5"/>',
    'zoom': '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/><path d="M10 7v6"/><path d="M7 10h6"/>',
    'palette': '<path d="M12 3a9 9 0 0 0 0 18h1.5a2 2 0 0 0 1.4-3.4l-.7-.7a2 2 0 0 1 1.4-3.4H17a4 4 0 0 0 0-8.2A9 9 0 0 0 12 3z"/><circle cx="7.5" cy="10" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="13.5" cy="7.5" r="1"/>',
    'template': '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 10h16"/><path d="M10 4v16"/>',
    'edit': '<path d="m4 20 4-1 11-11-3-3L5 16z"/><path d="m14 6 3 3"/>',
    'demo': '<path d="M4 5h16v12H4z"/><path d="m10 9 5 2-5 2z"/><path d="M8 21h8"/>',
    'play': '<path d="M7 4v16l13-8z"/>',
    'grid': '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 10h16"/><path d="M4 16h16"/><path d="M10 4v16"/><path d="M16 4v16"/>',
    'snap': '<path d="M6 3v5"/><path d="M18 3v5"/><path d="M6 16v5"/><path d="M18 16v5"/><path d="M3 6h5"/><path d="M16 6h5"/><path d="M3 18h5"/><path d="M16 18h5"/><path d="M9 9h6v6H9z"/>',
    'cancel': '<path d="M6 6l12 12"/><path d="M18 6 6 18"/>',
    'select': '<path d="M5 3l7 17 2-7 7-2z"/>',
    'line': '<path d="M5 19 19 5"/>',
    'polygon': '<path d="M5 8 12 3l7 5-3 11H8z"/>',
    'ellipse': '<ellipse cx="12" cy="12" rx="8" ry="5"/>',
    'bezier': '<path d="M4 17C8 4 16 20 20 7"/><circle cx="4" cy="17" r="1"/><circle cx="20" cy="7" r="1"/>',
    'bspline': '<path d="M4 16C7 8 9 8 12 14s6 5 8-4"/>',
    'clip': '<path d="M6 6h12v12H6z"/><path d="M3 12h18"/><path d="M12 3v18"/>',
    'rotate': '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v6h-6"/>',
    'scale': '<path d="M4 14v6h6"/><path d="M20 10V4h-6"/><path d="m14 10 6-6"/><path d="m4 20 6-6"/>',
}


def icon(name, color='#111827'):
    """按名称获取 QIcon，颜色可选。"""
    return _svg_icon(ICON_SVGS[name], color=color)