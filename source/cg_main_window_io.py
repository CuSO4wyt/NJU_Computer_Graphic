"""MainWindow 的 IOMixin：指令面板同步、文件读写、模板加载、画布导出。"""

import os
import re
from datetime import datetime

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import (
    QFileDialog,
    QMessageBox,
)

from cg_dialogs import CanvasSizeDialog
from cg_graphic_item import GraphicItem
from cg_scene import apply_command, create_state, export_commands, load_final_state
from templates import TEMPLATES


class IOMixin:
    """指令面板同步、文件 I/O、模板管理、画布截图。"""

    # ── 指令 / 操作面板 ──────────────────────────────────────────────

    def refresh_command_panels(self):
        """根据当前场景状态刷新指令编辑器和操作日志。

        hasFocus 检查是关键：如果用户正在手动编辑指令文本，
        就不自动覆盖 —— 否则每画一笔都会打断输入。
        操作日志只保留最近 500 条，避免内存无限增长。
        """
        try:
            commands = export_commands(
                self._export_state(), save_name='exported'
            )
            if not self.command_editor.hasFocus():
                self.command_editor.setPlainText('\n'.join(commands))
        except Exception as exc:
            if not self.command_editor.hasFocus():
                self.command_editor.setPlainText(f'无法生成场景指令: {exc}')
        if self.operation_log:
            self.operation_text.setPlainText('\n'.join(self.operation_log[-500:]))
        else:
            self.operation_text.setPlainText('暂无操作日志')

    def record_operation(self, text):
        """记录一条带时间戳的操作日志，并刷新面板。

        所有 OpsMixin 中的修改操作最终都调用此方法，
        保证 GUI 操作可以导出为完整的复现脚本。
        """
        ts = datetime.now().strftime('%H:%M:%S')
        self.operation_log.append(f'[{ts}] {text}')
        self.refresh_command_panels()

    def clear_operation_log(self):
        self.operation_log = []
        self.refresh_command_panels()
        self.statusBar().showMessage('已清空操作日志')

    def refresh_command_editor_from_scene(self):
        """强制从当前场景重新生成指令文本（覆盖编辑器内容）。"""
        self.command_editor.setPlainText(
            '\n'.join(export_commands(self._export_state(), save_name='exported'))
        )
        self.statusBar().showMessage('命令编辑器已从当前场景刷新')

    def save_command_editor(self):
        """解析编辑器指令，全部合法则应用到场景。失败时高亮出错行，不修改场景。"""
        lines = self.command_editor.toPlainText().splitlines()
        try:
            state = self._parse_command_editor_state(lines)
        except ValueError as exc:
            self._highlight_command_error(exc)
            self.statusBar().showMessage('指令格式错误，保存失败')
            self._flash_subtitle('非法指令检查：错误行已高亮，原画布不会被修改')
            QMessageBox.warning(self, '指令错误', str(exc))
            return
        self._push_undo()
        self._load_state_to_scene(state)
        self.command_editor.setPlainText(
            '\n'.join(export_commands(self._export_state(), save_name='exported'))
        )
        self.record_operation('saveCommandEditor')
        self._flash_subtitle('指令已保存：GUI 场景由指令重新生成')
        self.statusBar().showMessage('指令已保存，场景已更新')
        self.command_tabs.setCurrentIndex(0)

    def _parse_command_editor_state(self, lines):
        """逐行解析指令到 state，空行跳过。"""
        state = create_state()
        for line_number, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                apply_command(state, line.split())
            except Exception as exc:
                raise ValueError(
                    f'第 {line_number} 行解析失败: {raw_line}\n{exc}'
                )
        return state

    def _highlight_command_error(self, exc):
        """解析出错时在 LineNumberTextEdit 中高亮对应行。"""
        match = re.search(r'第 (\d+) 行解析失败', str(exc))
        if match and hasattr(self.command_editor, 'highlight_error_line'):
            self.command_editor.highlight_error_line(int(match.group(1)))

    # ── 网格开关 ─────────────────────────────────────────────────

    def toggle_grid(self):
        """切换画布网格显示，触发整个 scene 重绘。"""
        self.canvas_widget.show_grid = self.grid_checkbox.isChecked()
        self.scene.update()
        if self.grid_checkbox.isChecked():
            self._flash_subtitle('显示网格：辅助背景已开启，不影响导出结果')
        else:
            self._flash_subtitle('显示网格开关：辅助背景已关闭，不影响图元')

    def toggle_snap(self):
        """切换绘图吸附网格。"""
        self.refresh_command_panels()
        if self.snap_checkbox.isChecked():
            self._flash_subtitle('吸附网格：鼠标坐标会按步长自动对齐')
        else:
            self._flash_subtitle('吸附网格已关闭：鼠标坐标不再自动对齐')

    def change_snap_step(self, value):
        """更新吸附步长。"""
        self.refresh_command_panels()
        if self.snap_checkbox.isChecked():
            self._flash_subtitle(f'吸附步长：当前按 {value} 像素对齐')

    # ── 重置画布 ────────────────────────────────────────────────────

    def reset_canvas_dialog(self):
        """弹出画布尺寸对话框，确认后清空并重设。区别于 clear_canvas 会改变画布物理尺寸。"""
        dialog = CanvasSizeDialog(self, self.canvas_width, self.canvas_height)
        if dialog.exec_() != dialog.Accepted:
            return
        width, height = dialog.values()

        self._push_undo()
        self.canvas_width = width
        self.canvas_height = height
        self.clear_canvas()
        self.scene.setSceneRect(0, 0, width, height)
        self.canvas_widget.setFixedSize(width + 2, height + 2)
        self.statusBar().showMessage(f'画布已重置为 {width} x {height}')
        self._flash_subtitle('重置画布：清空当前场景，并设置新的画布尺寸')
        self.record_operation(f'resetCanvas width={width} height={height}')

    # ── 场景 I/O ───────────────────────────────────────────────────

    def _load_state_to_scene(self, state):
        """将 state 加载到场景。item_cnt 从已有 ID 最大值 +1 推导。"""
        self.canvas_width = state['width'] or self.canvas_width
        self.canvas_height = state['height'] or self.canvas_height
        self.clear_canvas()
        self.item_cnt = 0
        self.scene.setSceneRect(0, 0, self.canvas_width, self.canvas_height)
        self.canvas_widget.setFixedSize(
            self.canvas_width + 2, self.canvas_height + 2
        )
        for item_id, item in state['items'].items():
            graphic_item = GraphicItem(
                item_id,
                item['type'],
                item['points'],
                item['algorithm'],
                QColor(*item['color']),
            )
            self.item_dict[item_id] = graphic_item
            self.scene.addItem(graphic_item)
            self._add_list_item(graphic_item)
            try:
                self.item_cnt = max(self.item_cnt, int(item_id) + 1)
            except ValueError:
                pass
        self._refresh_z_order()
        self.clear_selection()
        self.refresh_command_panels()
        self.refresh_command_editor_from_scene()

    def load_scene_file(self):
        """从 .txt 指令文件加载场景。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            '加载指令文件',
            os.getcwd(),
            'Text Files (*.txt);;All Files (*)',
        )
        if not path:
            return
        try:
            state = load_final_state(path)
        except Exception as exc:
            QMessageBox.warning(self, '加载失败', f'无法解析指令文件:\n{exc}')
            return

        self._push_undo()
        self._load_state_to_scene(state)
        self.statusBar().showMessage(
            f'已加载指令文件: {os.path.basename(path)}'
        )
        self._flash_subtitle('加载指令文件：读取课程格式文本并复现最终场景')
        self.record_operation(f'loadScene path={path}')

    def export_scene_file(self):
        """导出当前场景为 .txt 指令文件（仅可见图元）。"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            '导出指令文件',
            os.path.join(os.getcwd(), 'scene.txt'),
            'Text Files (*.txt);;All Files (*)',
        )
        if not path:
            return
        if not path.lower().endswith('.txt'):
            path += '.txt'
        with open(path, 'w', encoding='utf-8') as fp:
            fp.write(
                '\n'.join(
                    export_commands(self._export_state(), save_name='exported')
                )
                + '\n'
            )
        self.statusBar().showMessage(f'已导出指令文件: {path}')
        self._flash_subtitle('导出指令文件：当前可见图元已保存为 CLI 文本')
        self.record_operation(f'exportScene path={path}')

    def export_operation_history(self):
        """导出当前场景 CLI 指令 + 完整操作日志到文件。"""
        default_name = datetime.now().strftime(
            'operation_history_%Y%m%d_%H%M%S.txt'
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            '导出操作历史',
            os.path.join(os.getcwd(), default_name),
            'Text Files (*.txt);;All Files (*)',
        )
        if not path:
            return
        if not path.lower().endswith('.txt'):
            path += '.txt'

        commands = export_commands(self._export_state(), save_name='exported')
        lines = [
            'CG 2026 GUI 操作历史',
            f'导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            f'画布尺寸: {self.canvas_width} x {self.canvas_height}',
            '',
            '可复现 CLI 指令:',
            *commands,
            '',
            'GUI 操作日志:',
        ]
        if self.operation_log:
            lines.extend(self.operation_log)
        else:
            lines.append('(暂无操作日志)')

        with open(path, 'w', encoding='utf-8') as fp:
            fp.write('\n'.join(lines) + '\n')
        self.statusBar().showMessage(f'已导出操作历史: {path}')
        self._flash_subtitle('导出操作历史：当前指令和 GUI 操作日志已保存')
        self.record_operation(f'exportOperationHistory path={path}')

    # ── 画布截图 ─────────────────────────────────────────────────

    def save_canvas(self):
        """将当前场景渲染为位图并保存。

        关键细节：渲染前临时隐藏所有临时元素（选中框、裁剪预览、
        变换辅助线、hover 高亮等），渲染后恢复 —— 否则截图里会有
        满屏的 UI 辅助线。
        """
        path, _ = QFileDialog.getSaveFileName(
            self,
            '保存画布',
            os.path.join(os.getcwd(), 'canvas.bmp'),
            'Bitmap Files (*.bmp);;PNG Files (*.png);;JPEG Files (*.jpg *.jpeg)',
        )
        if not path:
            return
        lower_path = path.lower()
        if not lower_path.endswith(('.bmp', '.png', '.jpg', '.jpeg')):
            path += '.bmp'
            lower_path = path.lower()

        # 临时隐藏选中的高亮效果
        selected_ids = [
            item_id
            for item_id, item in self.item_dict.items()
            if item.selected
        ]
        for item_id in selected_ids:
            self.item_dict[item_id].set_selected(False)

        # 临时隐藏所有临时/预览元素
        preview_item = self.canvas_widget.preview_item
        if preview_item is not None:
            preview_item.setVisible(False)
        transient_items = [
            self.canvas_widget.clip_rect_item,
            self.canvas_widget.clip_preview_item,
            self.canvas_widget.box_rect_item,
            self.canvas_widget.hover_rect_item,
            self.canvas_widget.transform_center_item,
            self.canvas_widget.transform_guide_item,
            self.canvas_widget.transform_text_item,
            self.canvas_widget.transform_mode_preview_item,
            self.transform_preview_item,
        ]
        for transient_item in transient_items:
            if transient_item is not None:
                transient_item.setVisible(False)

        image = QImage(
            self.canvas_width, self.canvas_height, QImage.Format_RGB32
        )
        image.fill(QColor(255, 255, 255))
        painter = QPainter(image)
        self.scene.render(
            painter,
            QRectF(0, 0, self.canvas_width, self.canvas_height),
            QRectF(0, 0, self.canvas_width, self.canvas_height),
        )
        painter.end()
        if lower_path.endswith('.png'):
            image.save(path, 'PNG')
        elif lower_path.endswith(('.jpg', '.jpeg')):
            image.save(path, 'JPEG')
        else:
            image.save(path, 'BMP')

        # 恢复临时元素
        if preview_item is not None:
            preview_item.setVisible(True)
        for transient_item in transient_items:
            if transient_item is not None:
                transient_item.setVisible(True)
        for item_id in selected_ids:
            if item_id in self.item_dict:
                self.item_dict[item_id].set_selected(True)

        self.statusBar().showMessage(f'画布已保存到 {path}')
        self._flash_subtitle('保存画布：已导出位图，不包含选中框和预览线')
        self.record_operation(f'saveCanvas path={path}')

    # ── 示例 / 模板场景 ──────────────────────────────────────────────

    def load_demo_items(self, record_history=True):
        """加载示例图元（线段 x2、多边形、椭圆、Bezier 曲线）。
        record_history=False 用于启动时首次加载，不记录到撤销栈。
        """
        if record_history:
            self._push_undo()
        self.clear_canvas()
        self.item_cnt = 0

        demo_specs = [
            (
                'line', [[40, 60], [260, 170]], 'DDA',
                QColor(30, 80, 200),
            ),
            (
                'line', [[60, 280], [260, 80]], 'Bresenham',
                QColor(220, 70, 60),
            ),
            (
                'polygon',
                [[340, 70], [490, 60], [540, 170], [450, 260], [320, 190]],
                'Bresenham', QColor(20, 130, 90),
            ),
            (
                'ellipse', [[80, 360], [280, 530]], '',
                QColor(170, 100, 30),
            ),
            (
                'curve',
                [[330, 370], [390, 300], [470, 470], [550, 340]],
                'Bezier', QColor(130, 40, 170),
            ),
        ]

        for item_type, points, algorithm, color in demo_specs:
            self.add_item(
                GraphicItem(
                    self.get_next_id(), item_type, points, algorithm, color
                ),
                record_history=False,
                to_front=False,
            )

        self.statusBar().showMessage('已重新加载示例图元')
        self._flash_subtitle('加载示例：线段、多边形、椭圆和曲线已重置')
        self.record_operation('loadDemoItems')
        self.refresh_command_editor_from_scene()

    def load_template_scene(self, template_name):
        """从 TEMPLATES 字典加载预设场景，会改变画布尺寸并替换全部图元。"""
        templates = TEMPLATES
        if template_name not in templates:
            QMessageBox.warning(
                self, '模板不存在', f'未找到模板: {template_name}'
            )
            return
        template = templates[template_name]
        width, height = template['size']
        self._push_undo()
        self.canvas_width = width
        self.canvas_height = height
        self.clear_canvas()
        self.item_cnt = 0
        self.scene.setSceneRect(0, 0, width, height)
        self.canvas_widget.setFixedSize(width + 2, height + 2)
        for item_id, item_type, points, algorithm, color in template['items']:
            self.add_item(
                GraphicItem(item_id, item_type, points, algorithm, color),
                record_history=False,
                to_front=False,
            )
        self.clear_selection()
        self._refresh_z_order()
        self.statusBar().showMessage(f'已加载模板: {template_name}')
        template_subtitles = {
            '综合示例': '加载模板：综合示例，集中展示基础图元',
            '裁剪示例': '加载模板：裁剪示例，用于演示线段裁剪窗口',
            '曲线示例': '加载模板：曲线示例，展示 Bezier 和 B-spline',
            '变换示例': '加载模板：变换示例，对比旋转和缩放结果',
        }
        self._flash_subtitle(
            template_subtitles.get(template_name, f'加载模板：{template_name}')
        )
        self.record_operation(f'loadTemplate name={template_name}')
        self.refresh_command_editor_from_scene()