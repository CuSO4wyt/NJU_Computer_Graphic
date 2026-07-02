"""GUI 主入口 —— 启动 Qt 事件循环，加载 MainWindow。"""

import sys

from cg_main_window import MainWindow
from PyQt5.QtWidgets import QApplication


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())