import cg_algorithms as alg
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QSpinBox,
)


class ClipWindowDialog(QDialog):
    """裁剪窗口设置 —— 四个坐标定义矩形区域 (x0,y0)-(x1,y1)。
    默认 (100,100)-(400,300)，配合常见 500×400 画布。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.x0_spin = QSpinBox(self)
        self.y0_spin = QSpinBox(self)
        self.x1_spin = QSpinBox(self)
        self.y1_spin = QSpinBox(self)
        for spin in (
            self.x0_spin,
            self.y0_spin,
            self.x1_spin,
            self.y1_spin,
        ):
            spin.setRange(-10000, 10000)
            spin.setSingleStep(10)
        self.x0_spin.setValue(100)
        self.y0_spin.setValue(100)
        self.x1_spin.setValue(400)
        self.y1_spin.setValue(300)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QGridLayout()
        layout.addWidget(QLabel('x0'), 0, 0)
        layout.addWidget(self.x0_spin, 0, 1)
        layout.addWidget(QLabel('y0'), 1, 0)
        layout.addWidget(self.y0_spin, 1, 1)
        layout.addWidget(QLabel('x1'), 2, 0)
        layout.addWidget(self.x1_spin, 2, 1)
        layout.addWidget(QLabel('y1'), 3, 0)
        layout.addWidget(self.y1_spin, 3, 1)
        layout.addWidget(buttons, 4, 0, 1, 2)
        self.setLayout(layout)
        self.setWindowTitle('裁剪窗口')

    def values(self):
        return (
            self.x0_spin.value(),
            self.y0_spin.value(),
            self.x1_spin.value(),
            self.y1_spin.value(),
        )
