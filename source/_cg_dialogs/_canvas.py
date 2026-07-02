from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QSpinBox,
)


class CanvasSizeDialog(QDialog):
    """画布尺寸设置（宽高 100-1000，步长 50）。"""

    def __init__(self, parent, width, height):
        super().__init__(parent)
        self.width_spin = QSpinBox(self)
        self.height_spin = QSpinBox(self)
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(100, 1000)
            spin.setSingleStep(50)
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QGridLayout()
        layout.addWidget(QLabel('宽度'), 0, 0)
        layout.addWidget(self.width_spin, 0, 1)
        layout.addWidget(QLabel('高度'), 1, 0)
        layout.addWidget(self.height_spin, 1, 1)
        layout.addWidget(buttons, 2, 0, 1, 2)
        self.setLayout(layout)
        self.setWindowTitle('重置画布')

    def values(self):
        return self.width_spin.value(), self.height_spin.value()
