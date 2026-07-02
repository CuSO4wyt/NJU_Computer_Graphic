"""MainWindow 的 OpsMixin：绘制、变换、裁剪、图元编辑。"""

import cg_algorithms as alg
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QColorDialog, QInputDialog, QMessageBox

from cg_dialogs import (
    AlgorithmCompareDialog,
    AlgorithmDemoDialog,
    ClipWindowDialog,
)
from cg_graphic_item import GraphicItem


class OpsMixin:
    """绘图模式、交互变换、属性编辑、裁剪、图元 CRUD。"""

    # ── 绘图模式 ───────────────────────────────────────────────────

    def start_draw(self, item_type, algorithm='', shortcut=''):
        """进入绘制模式，设置 CanvasView 状态并更新 UI。"""
        if item_type in ('line', 'polygon') and algorithm:
            self._sync_rail_algorithm(item_type, algorithm)
        self.canvas_widget.begin_draw(item_type, algorithm)
        tool_key = item_type
        label = item_type
        algo_label = ''
        if item_type == 'curve':
            tool_key = 'bspline' if algorithm == 'B-spline' else 'bezier'
            label = algorithm
            if algorithm == 'Bezier':
                algo_label = 'Bezier 曲线：左键添加控制点，右键完成'
            else:
                algo_label = 'B-spline 曲线：至少 4 个控制点'
        elif item_type == 'line':
            label = f'线段 {algorithm}'
            line_subtitles = {
                'Naive': '线段绘制 - Naive：直接根据直线方程采样像素',
                'DDA': '线段绘制 - DDA：按最大坐标变化量做增量采样',
                'Bresenham': '线段绘制 - Bresenham：使用误差项递推选择像素',
            }
            algo_label = line_subtitles.get(algorithm, f'线段绘制 - {algorithm}')
        elif item_type == 'polygon':
            label = f'多边形 {algorithm}'
            if algorithm == 'DDA':
                algo_label = '多边形绘制 - DDA：左键添加顶点，右键结束并自动闭合'
            else:
                algo_label = '多边形绘制 - Bresenham：每条边使用 Bresenham 生成'
        elif item_type == 'ellipse':
            label = '椭圆'
            algo_label = '中点椭圆算法：拖拽两个对角点确定包围矩形'
        if shortcut:
            shortcut_labels = {
                'line': f'快捷键 {shortcut}：进入线段模式，当前算法 {algorithm}',
                'polygon': f'快捷键 {shortcut}：进入多边形模式，当前算法 {algorithm}',
                'ellipse': f'快捷键 {shortcut}：进入椭圆模式',
                'curve': f'快捷键 {shortcut}：进入 {algorithm} 曲线模式',
            }
            algo_label = shortcut_labels.get(item_type, f'快捷键 {shortcut}：进入绘制模式')
        self._set_active_tool(tool_key, label)
        if algo_label:
            self._flash_subtitle(algo_label)
        message = f'开始绘制 {item_type}'
        if algorithm:
            message += f' ({algorithm})'
        self.statusBar().showMessage(message)

    def cancel_draw_mode(self):
        """退出当前绘制/变换/裁剪模式，回到选择。"""
        self.canvas_widget.clear_mode()
        self.clear_transform_preview()
        self._set_active_tool('select', '选择')
        self.statusBar().showMessage('已取消当前绘制')

    # ── 变换预览 ───────────────────────────────────────────────────

    def clear_transform_preview(self):
        """移除变换预览用的临时图元。"""
        if self.transform_preview_item is not None:
            self.scene.removeItem(self.transform_preview_item)
            self.transform_preview_item = None

    def start_interactive_transform(self, transform_type):
        """进入交互式旋转/缩放模式。

        椭圆不支持旋转（题目要求）；锁定的图元不能变换。
        """
        item = self._require_selected_item()
        if item is None:
            return
        if item.locked:
            QMessageBox.information(
                self, '图元已锁定', '当前图元已锁定，不能变换'
            )
            return
        if transform_type == 'rotate' and item.item_type == 'ellipse':
            QMessageBox.information(
                self, '不支持', '题目要求中椭圆不需要旋转'
            )
            self._flash_subtitle('边界情况：课程要求椭圆不需要旋转')
            return
        label = '交互旋转' if transform_type == 'rotate' else '交互缩放'
        if transform_type == 'rotate':
            self._flash_subtitle('交互式旋转：拖拽鼠标实时预览旋转结果')
        else:
            self._flash_subtitle('交互式缩放：距离中心越远比例越大')
        self._set_active_tool(transform_type, label)
        self.canvas_widget.begin_transform(item.id, transform_type)

    def apply_interactive_transform(
        self, item, transform_type, center, value, new_points
    ):
        """CanvasView 完成变换后回调：应用结果并记录历史。"""
        if item.locked:
            QMessageBox.information(
                self, '图元已锁定', '当前图元已锁定，不能应用变换'
            )
            return
        old_points = [point[:] for point in item.points]
        self._push_undo()
        item.set_points(new_points)
        self.update_detail_panel()
        label = 'rotate' if transform_type == 'rotate' else 'scale'
        if label == 'rotate':
            self._flash_subtitle('松开鼠标：应用旋转结果，可按 Ctrl+Z 撤销')
        else:
            self._flash_subtitle('松开鼠标：应用缩放结果，可按 Ctrl+Z 撤销')
        self.record_operation(
            f'interactive{label.capitalize()} id={item.id} '
            f'center={center} value={value} from={old_points} to={new_points}'
        )

    # ── 选中辅助函数 ───────────────────────────────────────────────
    # 这些方法统一处理"无选中"和"已锁定"的边界情况，避免每个操作重复判断。

    def _require_selected_item(self):
        """获取单个选中的图元，无选中时弹出提示。"""
        if not self.selected_id or self.selected_id not in self.item_dict:
            QMessageBox.information(
                self, '未选择图元', '请先从右侧列表选择一个图元'
            )
            return None
        return self.item_dict[self.selected_id]

    def _require_selected_items(self):
        """获取所有选中的图元，无选中时回退到单选。"""
        items = self.selected_items()
        if not items:
            item = self._require_selected_item()
            return {item.id: item} if item is not None else {}
        return items

    def _filter_unlocked_items(self, items, notify=True, action='操作'):
        """过滤掉已锁定的图元，如果全部锁定则提示。"""
        editable = {
            item_id: item
            for item_id, item in items.items()
            if not item.locked
        }
        if not editable and items:
            self.statusBar().showMessage(f'所选图元均已锁定，无法{action}')
            if notify:
                QMessageBox.information(
                    self, '图元已锁定', f'所选图元均已锁定，无法{action}'
                )
        elif len(editable) < len(items):
            self.statusBar().showMessage(
                f'已跳过 {len(items) - len(editable)} 个锁定图元'
            )
        return editable

    def _require_editable_selected_items(self, action='操作'):
        """取选中图元并过滤锁定项，一步到位。"""
        return self._filter_unlocked_items(
            self._require_selected_items(), notify=True, action=action
        )

    # ── 可见 / 锁定 / 填充 ───────────────────────────────────────────

    def toggle_selected_visibility(self):
        """切换选中图元的可见性。隐藏时自动取消选中，避免误操作。"""
        items = self._require_selected_items()
        if not items:
            return
        new_value = not all(item.visible for item in items.values())
        self._push_undo()
        for item in items.values():
            item.visible = new_value
            item.setVisible(new_value)
            if not new_value:
                item.set_selected(False)
        if not new_value:
            self.clear_selection()
        self._refresh_list_widget()
        self.update_detail_panel()
        self.refresh_command_panels()
        if new_value:
            self._flash_subtitle('显示图元：恢复画布显示，并参与导出和保存')
        else:
            self._flash_subtitle('隐藏图元：画布中暂时不显示，导出时不包含它')
        self.record_operation(
            f'setVisible ids={list(items.keys())} visible={new_value}'
        )

    def toggle_selected_lock(self):
        """切换选中图元的锁定状态。混合选中时翻转全部。"""
        items = self._require_selected_items()
        if not items:
            return
        new_value = not all(item.locked for item in items.values())
        self._push_undo()
        for item in items.values():
            item.locked = new_value
        self._refresh_list_widget()
        self.update_detail_panel()
        if new_value:
            self._flash_subtitle('锁定图元：阻止误拖动、误改点和误删除')
        else:
            self._flash_subtitle('解锁图元：恢复拖动、改点和编辑操作')
        self.record_operation(
            f'setLocked ids={list(items.keys())} locked={new_value}'
        )

    def toggle_selected_fill(self):
        """切换选中多边形的填充。清空 _fill_cache 防止复用旧缓存。"""
        items = {
            item_id: item
            for item_id, item in self._require_editable_selected_items(
                '设置填充'
            ).items()
            if item.item_type == 'polygon'
        }
        if not items:
            QMessageBox.information(
                self, '无多边形', '请选择至少一个多边形图元'
            )
            return
        new_value = not all(item.fill_enabled for item in items.values())
        self._push_undo()
        for item in items.values():
            item.fill_enabled = new_value
            item._fill_cache = None
            item.update()
        self._refresh_list_widget()
        self.update_detail_panel()
        if new_value:
            self._flash_subtitle('扫描线填充：按扫描行求交点并填充内部')
        else:
            self._flash_subtitle('取消填充：保留多边形边界，隐藏内部填充')
        self.record_operation(
            f'setFill ids={list(items.keys())} fill={new_value}'
        )

    def set_selected_fill_color(self):
        """为选中的多边形设置填充色，同时自动启用填充。"""
        items = {
            item_id: item
            for item_id, item in self._require_editable_selected_items(
                '设置填充色'
            ).items()
            if item.item_type == 'polygon'
        }
        if not items:
            QMessageBox.information(
                self, '无多边形', '请选择至少一个多边形图元'
            )
            return
        first_item = next(iter(items.values()))
        color = QColorDialog.getColor(
            first_item.fill_color, self, '选择填充颜色'
        )
        if color.isValid():
            self._push_undo()
            for item in items.values():
                item.fill_color = QColor(color)
                item.fill_enabled = True
                item.update()
            self._refresh_list_widget()
            self.update_detail_panel()
            self.record_operation(
                f'setFillColor ids={list(items.keys())} '
                f'color=({color.red()}, {color.green()}, {color.blue()})'
            )
            self._flash_subtitle('填充色独立设置：边框颜色和内部颜色可以不同')

    def apply_property_flags(self):
        """属性面板的复选框变更时批量应用到选中图元。

        _updating_properties 哨兵阻断 update_detail_panel 设置复选框值
        时触发的递归调用 —— 否则会造成无限循环。
        """
        if getattr(self, '_updating_properties', False):
            return
        items = self._require_selected_items()
        if not items:
            return
        visible = self.prop_visible_checkbox.isChecked()
        locked = self.prop_locked_checkbox.isChecked()
        fill_enabled = self.prop_fill_checkbox.isChecked()
        self._push_undo()
        for item in items.values():
            item.visible = visible
            item.locked = locked
            if item.item_type == 'polygon':
                item.fill_enabled = fill_enabled
                item._fill_cache = None
            item.setVisible(visible)
            item.update()
        if not visible:
            self.clear_selection()
        self._refresh_list_widget()
        self.update_detail_panel()
        self._flash_subtitle('批量属性编辑：可见、锁定、填充状态已更新')
        self.record_operation(
            f'editProperties ids={list(items.keys())} '
            f'visible={visible} locked={locked} fill={fill_enabled}'
        )

    def apply_points_editor(self):
        """读取参数点表格，校验后应用到图元。"""
        item = self._require_selected_item()
        if item is None:
            return
        if item.locked:
            QMessageBox.information(
                self, '图元已锁定', '当前图元已锁定，不能修改参数点'
            )
            return
        try:
            points = []
            for row in range(self.points_table.rowCount()):
                x_spin = self.points_table.cellWidget(row, 0)
                y_spin = self.points_table.cellWidget(row, 1)
                if x_spin is None or y_spin is None:
                    continue
                points.append([x_spin.value(), y_spin.value()])
            if len(points) < 2:
                raise ValueError
            if item.item_type == 'line' and len(points) != 2:
                raise ValueError
            if item.item_type == 'ellipse' and len(points) != 2:
                raise ValueError
            if item.item_type == 'polygon' and len(points) < 3:
                raise ValueError
            if item.item_type == 'curve':
                min_points = 4 if item.algorithm == 'B-spline' else 2
                if len(points) < min_points:
                    raise ValueError
        except ValueError:
            QMessageBox.warning(
                self,
                '参数点格式错误',
                '请在坐标表格中填写合法点坐标，且点数满足当前图元要求。',
            )
            return
        old_points = [point[:] for point in item.points]
        self._push_undo()
        item.set_points(points)
        self.update_detail_panel()
        self._flash_subtitle('精确编辑参数点：顶点坐标已应用到图元')
        self.record_operation(
            f'editPoints id={item.id} from={old_points} to={points}'
        )

    def apply_algorithm_property(self, algorithm):
        """切换绘制算法，清空像素缓存强制重绘。"""
        if getattr(self, '_updating_properties', False):
            return
        item = self.item_dict.get(self.selected_id)
        if item is None or item.locked or not algorithm or algorithm == '默认':
            return
        if item.item_type == 'ellipse':
            return
        if item.item_type == 'curve' and algorithm == 'B-spline' and len(item.points) < 4:
            QMessageBox.warning(
                self, '控制点不足', 'B-spline 曲线至少需要 4 个控制点'
            )
            self.update_detail_panel()
            return
        if item.algorithm == algorithm:
            return
        old_algorithm = item.algorithm
        self._push_undo()
        item.algorithm = algorithm
        item._pixel_cache = None
        item._pixel_set = None
        item.update()
        self.update_detail_panel()
        self._flash_subtitle(f'算法切换：当前图元已用 {algorithm} 重新生成')
        self.record_operation(
            f'editAlgorithm id={item.id} from={old_algorithm} to={algorithm}'
        )

    # ── 画笔颜色 ───────────────────────────────────────────────────

    def set_pen_color(self):
        """设置全局画笔颜色（后续绘制的图元将使用此颜色）。"""
        color = QColorDialog.getColor(self.pen_color, self, '选择画笔颜色')
        if color.isValid():
            self.pen_color = color
            self._update_pen_color_swatch()
            self.statusBar().showMessage(
                f'当前画笔颜色: ({color.red()}, {color.green()}, {color.blue()})'
            )
            self._flash_subtitle('画笔颜色：影响之后新绘制的图元')
            self.record_operation(
                f'setPenColor '
                f'color=({color.red()}, {color.green()}, {color.blue()})'
            )

    def recolor_selected(self):
        """修改已选中图元的颜色。仅对非锁定图元生效。"""
        items = self._require_editable_selected_items('改色')
        if not items:
            return
        first_item = next(iter(items.values()))
        color = QColorDialog.getColor(
            first_item.color, self, '修改图元颜色'
        )
        if color.isValid():
            self._push_undo()
            for item in items.values():
                if not item.locked:
                    item.color = QColor(color)
                    item.update()
            self.update_detail_panel()
            self.statusBar().showMessage(
                f'已修改 {len(items)} 个图元的颜色'
            )
            self._flash_subtitle('改色：修改已有图元的边框颜色')
            self.record_operation(
                f'recolor ids={list(items.keys())} '
                f'to=({color.red()}, {color.green()}, {color.blue()})'
            )

    # ── 平移 / 图层 ────────────────────────────────────────────────

    def move_selected_by(self, dx, dy, record_history=True):
        """将选中的非锁定图元平移 (dx, dy)。

        record_history=False 用于连续拖拽：每次 mouseMove 都调此方法，
        只在 mouseRelease 时记录一次历史（由 finish_items_drag 处理）。
        """
        items = self._filter_unlocked_items(
            self._require_selected_items(), notify=False
        )
        if not items:
            return
        if record_history:
            self._push_undo()
        for item in items.values():
            if not item.locked:
                item.set_points(alg.translate(item.points, dx, dy))
        self.update_detail_panel()

    def bring_selected_forward(self):
        """当前图元上移一层（+1）。"""
        self._move_selected_layer(1)

    def send_selected_backward(self):
        """当前图元下移一层（-1）。"""
        self._move_selected_layer(-1)

    def _move_selected_layer(self, direction):
        """在 item_dict 中交换相邻两键来改变图层顺序。

        直接操作有序 dict 的键列表，比维护单独的 Z 序数据结构更简单。
        """
        if not self.selected_id or self.selected_id not in self.item_dict:
            QMessageBox.information(self, '未选择图元', '请先选择一个图元')
            return
        keys = list(self.item_dict.keys())
        index = keys.index(self.selected_id)
        new_index = index + direction
        if new_index < 0 or new_index >= len(keys):
            self.statusBar().showMessage('当前图元已经在最前或最后')
            return
        self._push_undo()
        keys[index], keys[new_index] = keys[new_index], keys[index]
        self.item_dict = {key: self.item_dict[key] for key in keys}
        self._refresh_z_order()
        self._refresh_list_widget()
        self.statusBar().showMessage(
            f'已调整图元 {self.selected_id} 的层级'
        )
        if direction > 0:
            self._flash_subtitle('上移一层：提高绘制层级，视觉上更靠前')
        else:
            self._flash_subtitle('下移一层：降低绘制层级，视觉上更靠后')
        self.record_operation(
            f'moveLayer id={self.selected_id} direction={direction}'
        )

    # ── 裁剪 ────────────────────────────────────────────────────────

    def clip_selected(self, algorithm):
        """弹对话框输入裁剪窗口，执行裁剪。无剩余时删除图元。
        多边形始终用 Sutherland-Hodgman，忽略 algorithm。"""
        item = self._require_selected_item()
        if item is None:
            return
        if item.locked:
            QMessageBox.information(
                self, '图元已锁定', '当前图元已锁定，不能裁剪'
            )
            return
        if item.item_type not in ('line', 'polygon'):
            QMessageBox.information(
                self, '不支持', '当前 GUI 支持线段裁剪和多边形矩形裁剪'
            )
            return
        if item.item_type == 'polygon':
            algorithm = 'Sutherland-Hodgman'
        dialog = ClipWindowDialog(self)
        dialog.setWindowTitle(
            f'{"多边形" if item.item_type == "polygon" else "线段"}裁剪 ({algorithm})'
        )
        if dialog.exec_() != dialog.Accepted:
            return
        x0, y0, x1, y1 = dialog.values()
        old_points = [point[:] for point in item.points]
        if item.item_type == 'polygon':
            clipped = alg.clip_polygon(item.points, x0, y0, x1, y1)
        else:
            clipped = alg.clip(item.points, x0, y0, x1, y1, algorithm)

        if clipped:
            self._push_undo()
            item.set_points(clipped)
            self.update_detail_panel()
            self._flash_subtitle(
                f'{algorithm} 裁剪：裁剪结果已写回原图元'
            )
            self.record_operation(
                f'clip algorithm={algorithm} id={item.id} '
                f'window=({x0}, {y0}, {x1}, {y1}) '
                f'from={old_points} to={clipped}'
            )
        else:
            self._push_undo()
            item_id = item.id
            self._remove_item(item)
            self._flash_subtitle(
                f'{algorithm} 裁剪：图元完全在窗口外，已删除'
            )
            self.record_operation(
                f'clip algorithm={algorithm} id={item_id} '
                f'window=({x0}, {y0}, {x1}, {y1}) '
                f'from={old_points} to=deleted'
            )
            self.statusBar().showMessage(
                '裁剪后图元完全在窗口外，已删除'
            )

    def start_interactive_clip(self, algorithm):
        """进入交互式裁剪模式：画布上拖拽矩形框指定裁剪窗口。"""
        item = self._require_selected_item()
        if item is None:
            return
        if item.item_type not in ('line', 'polygon'):
            QMessageBox.information(
                self, '不支持', '交互式裁剪支持线段和多边形'
            )
            return
        if item.locked:
            QMessageBox.information(
                self, '图元已锁定', '当前图元已锁定，不能裁剪'
            )
            return
        if item.item_type == 'polygon':
            algorithm = 'Sutherland-Hodgman'
        label = '裁剪' if algorithm == 'Sutherland-Hodgman' else f'裁剪 {algorithm}'
        if algorithm == 'Liang-Barsky':
            self._flash_subtitle('Liang-Barsky 裁剪：拖拽红色窗口，蓝色为预览结果')
        elif algorithm == 'Cohen-Sutherland':
            self._flash_subtitle('Cohen-Sutherland 裁剪：使用区域码判断端点关系')
        else:
            self._flash_subtitle('Sutherland-Hodgman：逐边裁剪多边形')
        self._set_active_tool('clip', label)
        self.canvas_widget.begin_clip(algorithm)

    def confirm_interactive_clip(self, algorithm, window, clipped):
        """弹出确认对话框，预览裁剪结果。window=None 表示已取消。"""
        if window is None:
            self.canvas_widget.cancel_clip_mode()
            return
        item = self._require_selected_item()
        if item is None:
            self.canvas_widget.cancel_clip_mode()
            return
        if item.locked:
            QMessageBox.information(
                self, '图元已锁定', '当前图元已锁定，不能应用裁剪'
            )
            self.canvas_widget.cancel_clip_mode()
            return
        is_polygon = item.item_type == 'polygon'
        item_label = '多边形' if is_polygon else '线段'
        message = (
            f'裁剪窗口: {window}\n'
            f'裁剪结果: {clipped if clipped else f"{item_label}完全在窗口外"}'
            f'\n\n是否应用裁剪结果？'
        )
        answer = QMessageBox.question(
            self,
            f'应用交互式裁剪 ({algorithm})',
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self._push_undo()
            if clipped:
                old_points = [point[:] for point in item.points]
                item.set_points(clipped)
                self.update_detail_panel()
                self._flash_subtitle(
                    f'确认裁剪：{algorithm} 结果已写回原图元'
                )
                self.record_operation(
                    f'interactiveClip algorithm={algorithm} id={item.id} '
                    f'window={window} from={old_points} to={clipped}'
                )
            else:
                item_id = item.id
                old_points = [point[:] for point in item.points]
                self._remove_item(item)
                self._flash_subtitle(
                    f'确认裁剪：{algorithm} 判断图元完全在窗口外'
                )
                self.record_operation(
                    f'interactiveClip algorithm={algorithm} id={item_id} '
                    f'window={window} from={old_points} to=deleted'
                )
        else:
            self.statusBar().showMessage('已取消应用交互式裁剪结果')
        self.canvas_widget.cancel_clip_mode()
        self._set_active_tool('select', '选择')

    # ── 复制 / 重命名 / 删除 ───────────────────────────────────────

    def duplicate_selected(self):
        """复制选中图元，新图元偏移 (20, 20) 以便肉眼区分。"""
        item = self._require_selected_item()
        if item is None:
            return
        new_item = GraphicItem(
            self.get_next_id(),
            item.item_type,
            alg.translate(item.points, 20, 20),
            item.algorithm,
            item.color,
        )
        self.add_item(new_item)
        self.statusBar().showMessage(f'已复制图元 {item.id}')
        self._flash_subtitle('Ctrl+D：复制当前图元，新副本自动偏移')
        self.record_operation(
            f'duplicate source={item.id} new={new_item.id} '
            f'points={new_item.points}'
        )

    def rename_selected(self):
        """重命名图元 ID，校验唯一性和合法性。"""
        item = self._require_selected_item()
        if item is None:
            return
        new_id, ok = QInputDialog.getText(
            self, '重命名图元', '输入新的图元 id:', text=item.id
        )
        if not ok:
            return
        new_id = new_id.strip()
        if not new_id or any(ch.isspace() for ch in new_id):
            QMessageBox.warning(
                self, '输入错误', '图元 id 不能为空，且不能包含空白字符'
            )
            return
        if new_id != item.id and new_id in self.item_dict:
            QMessageBox.warning(
                self, '输入错误', f'图元 id "{new_id}" 已存在'
            )
            return
        if new_id == item.id:
            return

        old_id = item.id
        self._push_undo()
        item.id = new_id
        self.item_dict = {
            (new_id if item_id == old_id else item_id): value
            for item_id, value in self.item_dict.items()
        }
        self.selected_id = new_id
        if old_id in self.selected_ids:
            self.selected_ids.remove(old_id)
            self.selected_ids.add(new_id)
        self._refresh_list_widget()
        self._set_selected_id(new_id)
        self.statusBar().showMessage(f'已将图元 {old_id} 重命名为 {new_id}')
        self._flash_subtitle('重命名：图元 id 已更新，导出指令会使用新 id')
        self.record_operation(f'rename old={old_id} new={new_id}')

    def delete_selected(self):
        """删除选中的非锁定图元。先拍快照再删，保证可撤销。"""
        items = self._require_editable_selected_items('删除')
        if not items:
            return
        self._push_undo()
        old_points = {
            item_id: [point[:] for point in item.points]
            for item_id, item in items.items()
        }
        for item in list(items.values()):
            self._remove_item(item)
        self.statusBar().showMessage(f'已删除 {len(items)} 个图元')
        self._flash_subtitle('Delete：删除选中的可编辑图元')
        self.record_operation(
            f'delete ids={list(items.keys())} points={old_points}'
        )

    # ── 拖拽回调 ──────────────────────────────────────────────────
    # 由 CanvasView 在用户拖拽完成后调用，记录操作日志。

    def finish_control_point_drag(
        self, item, point_index, old_points, new_points
    ):
        """单个控制点拖拽完成后的回调。"""
        self.update_detail_panel()
        self._flash_subtitle('控制点编辑：几何参数已随拖拽更新')
        self.record_operation(
            f'dragControlPoint id={item.id} index={point_index} '
            f'from={old_points} to={new_points}'
        )

    def finish_items_drag(self, old_points_by_id):
        """批量平移拖拽完成后的回调。old_points_by_id 是拖拽前的快照。"""
        new_points_by_id = {
            item_id: [p[:] for p in item.points]
            for item_id, item in self.selected_items().items()
        }
        self.update_detail_panel()
        self._flash_subtitle('拖拽平移：选中图元整体移动，可按 Ctrl+Z 撤销')
        self.record_operation(
            f'dragItems from={old_points_by_id} to={new_points_by_id}'
        )

    # ── 演示弹窗 ───────────────────────────────────────────────────

    def show_algorithm_demo(self):
        """打开算法过程演示弹窗（逐步展示扫描线等）。"""
        self._flash_subtitle('算法过程演示：把像素结果拆成可播放步骤')
        dialog = AlgorithmDemoDialog(self)
        dialog.exec_()

    def show_algorithm_compare(self):
        """对选中图元同时展示所有可用算法的绘制结果。"""
        item = self._require_selected_item()
        if item is None:
            return
        if item.item_type == 'ellipse':
            QMessageBox.information(
                self, '不支持', '椭圆当前只有一种生成算法，无需对比'
            )
            return
        if item.item_type == 'line':
            subtitle = '线段算法对比：Bresenham 与 Wu 反走样并排显示'
        elif item.item_type == 'polygon':
            subtitle = '多边形算法对比：DDA 与 Bresenham 显示像素数和耗时'
        else:
            subtitle = '曲线算法对比：Bezier 与 B-spline 展示形状差异'
        self._flash_subtitle(subtitle)
        dialog = AlgorithmCompareDialog(self, item)
        dialog.exec_()

    def show_clip_compare(self):
        """对选中线段同时展示两种裁剪算法的结果。仅支持线段。"""
        item = self._require_selected_item()
        if item is None:
            return
        if item.item_type != 'line':
            QMessageBox.information(
                self, '不支持', '裁剪算法对比仅支持线段'
            )
            return
        self._flash_subtitle('裁剪算法对比：同一线段同一窗口，对比结果和耗时')
        dialog = AlgorithmCompareDialog(self, item, compare_mode='clip')
        dialog.exec_()