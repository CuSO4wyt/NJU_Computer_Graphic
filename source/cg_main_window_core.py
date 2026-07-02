"""Mixin for MainWindow: 选择、图元增删、撤销/重做。

所有方法假定 self 是 QMainWindow 子类，且 __init__ 已创建共享属性
（scene, item_dict, list_widget 等）。不依赖另外两个 mixin 的方法。

撤销/重做采用全量快照策略（深拷贝所有图元状态），而非命令模式。
简单粗暴但不会因漏拍某个字段而出错，适用于图元不超过几百个的场景。
"""

from PyQt5.QtCore import QSize, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QSpinBox,
    QTableWidgetItem,
    QToolButton,
    QWidget,
)

from cg_constants import UNDO_STACK_LIMIT
from cg_icons import icon
from cg_graphic_item import GraphicItem


class CoreMixin:
    """选择、图元 CRUD、撤销/重做、属性面板同步。"""

    # ── 工具函数 ─────────────────────────────────────────────────────

    def get_next_id(self):
        """自增计数器生成唯一图元 ID。永不回收，保证 undo/redo 快照中的 ID 不冲突。"""
        item_id = str(self.item_cnt)
        self.item_cnt += 1
        return item_id

    def snap_point(self, point):
        """如果吸附开关打开，将坐标吸附到最近的网格点。"""
        if not self.snap_checkbox.isChecked():
            return point[:]
        step = max(1, self.snap_step_spin.value())
        x, y = point
        return [int(round(x / step) * step), int(round(y / step) * step)]

    @staticmethod
    def _item_to_cli_dict(item):
        """序列化为 CLI 格式 —— 只含绘制必需字段，不含元数据。

        与 _item_to_snapshot_dict 的区别：CLI 格式用于导出/复现，
        不需要 id、visible 等运行状态，保持指令文件简洁。
        """
        return {
            'type': item.item_type,
            'points': [point[:] for point in item.points],
            'algorithm': item.algorithm,
            'color': [
                item.color.red(),
                item.color.green(),
                item.color.blue(),
            ],
        }

    @staticmethod
    def _item_to_snapshot_dict(item):
        """序列化为快照格式 —— 包含图元所有状态字段。

        用于撤销/重做栈，必须完整保存才能无损还原。
        """
        return {
            'type': item.item_type,
            'points': [point[:] for point in item.points],
            'algorithm': item.algorithm,
            'color': [
                item.color.red(),
                item.color.green(),
                item.color.blue(),
            ],
            'id': item.id,
            'visible': item.visible,
            'locked': item.locked,
            'fill_enabled': item.fill_enabled,
            'fill_color': [
                item.fill_color.red(),
                item.fill_color.green(),
                item.fill_color.blue(),
            ],
        }

    def _export_state(self):
        """导出当前画布状态（仅可见图元），用于生成 CLI 指令文件。"""
        return {
            'width': self.canvas_width,
            'height': self.canvas_height,
            'items': {
                item_id: self._item_to_cli_dict(item)
                for item_id, item in self.item_dict.items()
                if item.visible
            },
        }

    def _item_summary(self, item):
        """操作日志中使用的图元摘要字符串。"""
        return (
            f'id={item.id} type={item.item_type} '
            f'algorithm={item.algorithm or "default"} points={item.points}'
        )

    def _list_display_text(self, item):
        """图层列表显示文本，格式：[H][L][F] type_id。
        H=隐藏, L=锁定, F=填充。
        """
        tags = []
        if not item.visible:
            tags.append('H')
        if item.locked:
            tags.append('L')
        if item.fill_enabled:
            tags.append('F')
        prefix = f"[{''.join(tags)}] " if tags else ''
        type_prefix = {
            'line': 'line',
            'polygon': 'poly',
            'ellipse': 'ellipse',
            'curve': 'curve',
        }.get(item.item_type, item.item_type)
        return f'{prefix}{type_prefix}_{item.id}'

    def _add_list_item(self, item, to_front=True):
        """向图层列表添加一项，并在该项上嵌入自定义控件行。

        QListWidgetItem.setItemWidget 把整行替换为自定义 widget，
        从而在同一行中展示图标、名称和操作按钮。
        """
        list_item = QListWidgetItem(self._list_display_text(item))
        list_item.setIcon(icon(item.item_type if item.item_type in ('line', 'polygon', 'ellipse') else 'bezier'))
        # UserRole 存图元 ID，拖拽排序后用于重建 item_dict 顺序
        list_item.setData(Qt.UserRole, item.id)
        list_item.setSizeHint(QSize(0, 40))
        if to_front:
            self.list_widget.insertItem(0, list_item)
        else:
            self.list_widget.addItem(list_item)
        self.list_widget.setItemWidget(list_item, self._make_layer_item_widget(item))

    def _make_layer_item_widget(self, item):
        """构建图层列表中每一项的自定义行控件。

        每行包含：类型图标 + 名称 + 可见/锁定/填充三个行内操作按钮。
        lambda 中用默认参数捕获 item_id 和 callback，避免闭包延迟绑定问题。
        """
        widget = QWidget(self.list_widget)
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        type_icon = QLabel(widget)
        type_name = item.item_type if item.item_type in ('line', 'polygon', 'ellipse') else 'bezier'
        type_icon.setPixmap(icon(type_name).pixmap(20, 20))
        name = QLabel(self._list_display_text(item), widget)
        name.setObjectName('layerItemName')
        layout.addWidget(type_icon)
        layout.addWidget(name, 1)
        controls = [
            (
                'eye' if item.visible else 'eye-off',
                '隐藏' if item.visible else '显示',
                self.toggle_selected_visibility,
            ),
            (
                'lock' if item.locked else 'unlock',
                '解锁' if item.locked else '锁定',
                self.toggle_selected_lock,
            ),
            ('fill', '填充', self.toggle_selected_fill),
        ]
        for icon_name, tooltip, callback in controls:
            button = QToolButton(widget)
            button.setIcon(icon(icon_name))
            button.setIconSize(QSize(18, 18))
            button.setToolTip(tooltip)
            button.setAutoRaise(True)
            button.setFixedSize(32, 32)
            button.clicked.connect(
                lambda _checked=False, item_id=item.id, cb=callback: self._run_layer_action(item_id, cb)
            )
            layout.addWidget(button)
        widget.setLayout(layout)
        return widget

    def _run_layer_action(self, item_id, callback):
        """图层行内按钮的入口：先选中对应图元，再执行操作。"""
        if item_id in self.item_dict:
            self._set_selected_id(item_id)
            callback()

    def _list_item_id(self, list_item):
        """从 QListWidgetItem 取回图元 ID（存在 UserRole 中）。"""
        return list_item.data(Qt.UserRole) or list_item.text()

    # ── 撤销 / 重做 ─────────────────────────────────────────────────
    # 全量快照策略：每次操作前深拷贝所有图元状态。简单但不会漏字段，
    # 内存占用随图元数量线性增长，适用于图元不超过几百个的场景。

    def _state_snapshot(self):
        """拍摄当前完整状态快照（画布尺寸、画笔色、全部图元、选中状态）。"""
        return {
            'width': self.canvas_width,
            'height': self.canvas_height,
            'pen_color': [
                self.pen_color.red(),
                self.pen_color.green(),
                self.pen_color.blue(),
            ],
            'item_cnt': self.item_cnt,
            'selected_id': self.selected_id,
            'selected_ids': sorted(self.selected_ids),
            'items': [
                self._item_to_snapshot_dict(item)
                for item in self.item_dict.values()
            ],
        }

    def _restore_snapshot(self, snapshot):
        """从快照完整还原画布状态。

        _restoring 哨兵在整个还原期间为 True，防止中间步骤触发
        _push_undo、selection_changed 等副作用。
        """
        self._restoring = True
        try:
            self.clear_transform_preview()
            self.canvas_widget._reset_temp_state()
            self.canvas_widget.cancel_clip_mode()
            self._forget_subtitle_items()
            self.scene.clear()
            self.item_dict = {}
            self.list_widget.clear()
            self.canvas_width = snapshot['width']
            self.canvas_height = snapshot['height']
            self.pen_color = QColor(*snapshot['pen_color'])
            self.item_cnt = snapshot['item_cnt']
            self.selected_id = ''
            self.selected_ids = set()
            self.scene.setSceneRect(0, 0, self.canvas_width, self.canvas_height)
            self.canvas_widget.setFixedSize(
                self.canvas_width + 2, self.canvas_height + 2
            )
            for item_data in snapshot['items']:
                item = GraphicItem(
                    item_data['id'],
                    item_data['type'],
                    item_data['points'],
                    item_data['algorithm'],
                    QColor(*item_data['color']),
                    visible=item_data.get('visible', True),
                    locked=item_data.get('locked', False),
                    fill_enabled=item_data.get('fill_enabled', False),
                    fill_color=QColor(*item_data.get('fill_color', [220, 220, 220])),
                )
                self.item_dict[item.id] = item
                self.scene.addItem(item)
                self._add_list_item(item)
            self._set_selected_ids(
                snapshot.get('selected_ids', [snapshot.get('selected_id', '')]),
                primary_id=snapshot.get('selected_id', ''),
            )
            self.update_detail_panel()
            self.refresh_command_panels()
        finally:
            self._restoring = False

    def _push_undo(self):
        """在执行修改操作前调用：压入当前状态并清空 redo 栈。

        一旦有新操作，之前的 redo 历史就不可达了 —— 这是标准行为。
        _restoring 期间跳过，避免还原过程本身产生新快照。
        """
        if self._restoring:
            return
        self.undo_stack.append(self._state_snapshot())
        if len(self.undo_stack) > UNDO_STACK_LIMIT:
            self.undo_stack.pop(0)
        self.redo_stack = []

    def undo(self):
        if not self.undo_stack:
            self.statusBar().showMessage('没有可撤销的操作')
            return
        # 撤销前先保存当前状态到 redo 栈，保证 redo 能回到撤销前的样子
        self.redo_stack.append(self._state_snapshot())
        self._restore_snapshot(self.undo_stack.pop())
        self.statusBar().showMessage('已撤销')
        self._flash_subtitle('Ctrl+Z：撤销上一步编辑，场景快照恢复')
        self.record_operation('undo')

    def redo(self):
        if not self.redo_stack:
            self.statusBar().showMessage('没有可重做的操作')
            return
        self.undo_stack.append(self._state_snapshot())
        self._restore_snapshot(self.redo_stack.pop())
        self.statusBar().showMessage('已重做')
        self._flash_subtitle('Ctrl+Y：重做刚刚撤销的操作')
        self.record_operation('redo')

    # ── 图元增删 ───────────────────────────────────────────────────

    def add_item(self, item, record_history=True, to_front=True):
        """将图元加入场景和图层列表。

        record_history=False 用于初始加载（示例图元、模板），这些不应出现在撤销栈中。
        to_front 控制新图元插入图层列表的位置：顶部（最前）还是底部（最后）。
        """
        if record_history:
            self._push_undo()
        if to_front:
            # 新图元放到最前（图层列表顶部、视觉最上层）
            self.item_dict = {item.id: item, **self.item_dict}
        else:
            self.item_dict[item.id] = item
        self.scene.addItem(item)
        self._add_list_item(item, to_front=to_front)
        self._refresh_z_order()
        self._set_selected_id(item.id)
        self.refresh_command_panels()

    def _remove_item(self, item):
        """从场景和字典中移除图元，清理选中状态。"""
        self.scene.removeItem(item)
        if item.id in self.item_dict:
            del self.item_dict[item.id]
        self.selected_ids.discard(item.id)
        for row in reversed(range(self.list_widget.count())):
            list_item = self.list_widget.item(row)
            if self._list_item_id(list_item) == item.id:
                self.list_widget.takeItem(row)
        if self.selected_id == item.id:
            self.selected_id = ''
        self.update_detail_panel()

    def clear_canvas(self):
        """清空画布但不重置 undo/redo 栈。"""
        self.canvas_widget.clear_mode()
        self.clear_transform_preview()
        self._forget_subtitle_items()
        self.scene.clear()
        self.item_dict = {}
        self.selected_id = ''
        self.selected_ids = set()
        self.list_widget.clear()
        self.update_detail_panel()
        self.refresh_command_panels()

    # ── Z 序 / 图层同步 ────────────────────────────────────────

    def _refresh_z_order(self):
        """根据 item_dict 的顺序重设 Z 值。

        由于使用 Python 3.7+ 的有序 dict，item_dict 的迭代顺序即图层顺序。
        靠前的图元 Z 值更高（视觉上更靠前）。
        """
        items = list(self.item_dict.values())
        n = len(items)
        for i, item in enumerate(items):
            item.setZValue(n - i)

    def sync_layers_from_list(self, *args):
        """用户拖拽图层列表后，将新顺序同步回 item_dict。

        通过比较 keys 列表确认是重排序（非增删），
        然后重建 item_dict 以反映新顺序。
        """
        if self._restoring:
            return
        keys = [
            self._list_item_id(self.list_widget.item(row))
            for row in range(self.list_widget.count())
        ]
        if set(keys) != set(self.item_dict.keys()):
            return
        if keys == list(self.item_dict.keys()):
            return
        self._push_undo()
        self.item_dict = {key: self.item_dict[key] for key in keys}
        self._refresh_z_order()
        self._flash_subtitle('拖拽重排序：遮挡关系已按图层顺序更新')
        self.record_operation(f'reorderLayers order={keys}')

    # ── 选择逻辑 ───────────────────────────────────────────────────

    def _set_selected_id(self, item_id):
        """单选快捷入口。"""
        self._set_selected_ids([item_id] if item_id else [])

    def _set_selected_ids(self, item_ids, primary_id=None):
        """设置选中集合，同步场景图元和图层列表的高亮。

        blockSignals 防止 list_widget 的选中变化回调触发无限递归。
        """
        self.clear_selection()
        valid_ids = [
            iid for iid in item_ids if iid and iid in self.item_dict
        ]
        self.selected_ids = set(valid_ids)
        if primary_id and primary_id in self.selected_ids:
            self.selected_id = primary_id
        else:
            self.selected_id = valid_ids[-1] if valid_ids else ''
        self.list_widget.blockSignals(True)
        for item_id in valid_ids:
            self.item_dict[item_id].set_selected(True)
            for row in range(self.list_widget.count()):
                list_item = self.list_widget.item(row)
                if self._list_item_id(list_item) == item_id:
                    list_item.setText(
                        self._list_display_text(self.item_dict[item_id])
                    )
                    list_item.setSelected(True)
        if self.selected_id:
            for row in range(self.list_widget.count()):
                list_item = self.list_widget.item(row)
                if self._list_item_id(list_item) == self.selected_id:
                    self.list_widget.setCurrentItem(list_item)
                    break
            self.statusBar().showMessage(
                f'当前选择 {len(valid_ids)} 个图元，主图元: {self.selected_id}'
            )
        self.list_widget.blockSignals(False)
        self.update_detail_panel()

    def select_item_at(self, point, additive=False):
        """点选图元：从 Z 序最高的可见图元开始向下查找。

        reversed 遍历保证最前面的图元先被命中。
        additive 模式下点击已选中图元会取消选中（toggle 行为）。
        """
        for item_id in reversed(list(self.item_dict.keys())):
            item = self.item_dict[item_id]
            if item.contains(QRectF(point[0], point[1], 1, 1).center()):
                if additive:
                    selected = set(self.selected_ids)
                    if item_id in selected:
                        selected.remove(item_id)
                    else:
                        selected.add(item_id)
                    self._set_selected_ids(list(selected))
                    self._flash_subtitle('Shift 多选：追加或取消当前图元')
                else:
                    self._set_selected_id(item_id)
                    self._flash_subtitle('单击图元：选中后显示控制点和属性信息')
                return True
        return False

    def select_items_in_rect(self, rect, additive=False):
        """框选：选中所有 boundingRect 与选框相交的可见非锁定图元。"""
        found = []
        for item_id, item in self.item_dict.items():
            if (
                item.visible
                and not item.locked
                and item.boundingRect().intersects(rect)
            ):
                found.append(item_id)
        if additive:
            selected = set(self.selected_ids)
            selected.update(found)
            self._set_selected_ids(list(selected))
            self._flash_subtitle(
                f'Shift 框选：追加 {len(found)} 个相交图元到当前选择'
            )
        else:
            self._set_selected_ids(found)
            self._flash_subtitle(
                f'框选：选中 {len(found)} 个与选择框相交的图元'
            )

    def selected_items(self):
        """返回 {id: CanvasItem} 字典，仅含选中的图元。"""
        return {
            item_id: self.item_dict[item_id]
            for item_id in self.selected_ids
            if item_id in self.item_dict
        }

    def clear_selection(self):
        """清空所有选中状态。"""
        for item_id in list(self.selected_ids):
            if item_id in self.item_dict:
                self.item_dict[item_id].set_selected(False)
        self.selected_id = ''
        self.selected_ids = set()
        self.list_widget.blockSignals(True)
        self.list_widget.clearSelection()
        self.list_widget.setCurrentRow(-1)
        self.list_widget.blockSignals(False)
        self.update_detail_panel()

    def selection_changed(self):
        """图层列表选中变化 → 同步到场景图元。

        这是列表驱动的选中流程：用户在列表中点击/Shift 多选时触发。
        画布点击的选中则走 _set_selected_ids，不会经过这里。
        """
        if self._restoring:
            return
        for item in self.item_dict.values():
            item.set_selected(False)
        selected = [
            self._list_item_id(list_item)
            for list_item in self.list_widget.selectedItems()
            if self._list_item_id(list_item) in self.item_dict
        ]
        self.selected_ids = set(selected)
        current = self.list_widget.currentItem()
        current_id = self._list_item_id(current) if current else ''
        if current_id in self.selected_ids:
            self.selected_id = current_id
        else:
            self.selected_id = selected[-1] if selected else ''
        for item_id in self.selected_ids:
            self.item_dict[item_id].set_selected(True)
        self.statusBar().showMessage(
            f'当前选择 {len(self.selected_ids)} 个图元'
            if self.selected_ids
            else '空闲'
        )
        self.update_detail_panel()

    # ── UI 同步 ─────────────────────────────────────────────────────

    def _refresh_list_widget(self):
        """重建图层列表（保持选中状态）。"""
        current_ids = set(self.selected_ids)
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for item in self.item_dict.values():
            self._add_list_item(item)
        for item_id in current_ids:
            for row in range(self.list_widget.count()):
                list_item = self.list_widget.item(row)
                if self._list_item_id(list_item) == item_id:
                    list_item.setSelected(True)
        if self.selected_id in self.item_dict:
            for row in range(self.list_widget.count()):
                list_item = self.list_widget.item(row)
                if self._list_item_id(list_item) == self.selected_id:
                    self.list_widget.setCurrentItem(list_item)
                    break
        self.list_widget.blockSignals(False)

    def _set_property_rows(self, rows):
        """批量设置属性表的行数据。"""
        self.property_table.setRowCount(len(rows))
        for row, (name, value) in enumerate(rows):
            self.property_table.setItem(row, 0, QTableWidgetItem(name))
            self.property_table.setItem(row, 1, QTableWidgetItem(str(value)))

    def _populate_points_table(self, item):
        """填充参数点编辑表格：每行一个 (x, y) 配对，使用 QSpinBox 作为编辑控件。"""
        self.points_table.blockSignals(True)
        self.points_table.setRowCount(0)
        if item is None:
            self.points_table.setRowCount(1)
            self.points_table.setItem(0, 0, QTableWidgetItem('未选择'))
            self.points_table.setItem(0, 1, QTableWidgetItem(''))
            self.points_table.setEnabled(False)
            self.points_table.blockSignals(False)
            return
        self.points_table.setEnabled(not item.locked)
        self.points_table.setRowCount(len(item.points))
        for row, (x, y) in enumerate(item.points):
            self.points_table.setVerticalHeaderItem(row, QTableWidgetItem(str(row)))
            for column, value in enumerate((x, y)):
                spin = QSpinBox(self.points_table)
                spin.setRange(-10000, 10000)
                spin.setValue(int(value))
                spin.setEnabled(not item.locked)
                self.points_table.setCellWidget(row, column, spin)
        self.points_table.blockSignals(False)

    def _set_property_color_cell(self, row, color):
        """设置属性表中颜色行的背景色，并根据亮度自适应选择前景色。

        使用 ITU-R BT.601 亮度公式（0.299R + 0.587G + 0.114B），
        阈值 150 处切分深/浅色文字 —— 比固定阈值更适应人眼感知。
        """
        cell = self.property_table.item(row, 1)
        if cell is None:
            return
        cell.setBackground(QBrush(color))
        luminance = (
            0.299 * color.red()
            + 0.587 * color.green()
            + 0.114 * color.blue()
        )
        text_color = QColor(17, 24, 39) if luminance > 150 else QColor(255, 255, 255)
        cell.setForeground(QBrush(text_color))

    def update_detail_panel(self):
        """刷新属性面板所有控件。_updating_properties 哨兵防止递归更新。"""
        if not hasattr(self, 'property_table'):
            return
        item = self.item_dict.get(self.selected_id)
        self._updating_properties = True
        if item is None:
            if self.selected_ids:
                self._set_property_rows([('当前多选数量', len(self.selected_ids))])
            else:
                self._set_property_rows([('状态', '未选择图元'), ('提示', '从画布或图层中选择图元')])
            self._populate_points_table(None)
            for checkbox in (
                self.prop_visible_checkbox,
                self.prop_locked_checkbox,
                self.prop_fill_checkbox,
            ):
                checkbox.setChecked(False)
                checkbox.setEnabled(False)
            self.apply_points_button.setEnabled(False)
            self.item_color_button.setEnabled(False)
            self.fill_color_button.setEnabled(False)
            self.algorithm_combo.blockSignals(True)
            self.algorithm_combo.clear()
            self.algorithm_combo.setEnabled(False)
            self.algorithm_combo.blockSignals(False)
            self._updating_properties = False
            self.refresh_overview()
            self.refresh_command_panels()
            return
        color = item.color
        fill = item.fill_color
        self._set_property_rows([
            ('编号', item.id),
            ('类型', item.item_type),
            ('算法', item.algorithm or '默认'),
            ('颜色', f'({color.red()}, {color.green()}, {color.blue()})'),
            ('可见', item.visible),
            ('锁定', item.locked),
            ('填充', item.fill_enabled),
            ('填充色', f'({fill.red()}, {fill.green()}, {fill.blue()})'),
            ('当前多选数量', len(self.selected_ids)),
            ('参数点数', len(item.points)),
        ])
        self._set_property_color_cell(3, color)
        self._set_property_color_cell(7, fill)
        for checkbox in (
            self.prop_visible_checkbox,
            self.prop_locked_checkbox,
            self.prop_fill_checkbox,
        ):
            checkbox.setEnabled(True)
        self.prop_visible_checkbox.setChecked(item.visible)
        self.prop_locked_checkbox.setChecked(item.locked)
        self.prop_fill_checkbox.setChecked(item.fill_enabled)
        self._populate_points_table(item)
        self.apply_points_button.setEnabled(not item.locked)
        self.item_color_button.setEnabled(not item.locked)
        self.fill_color_button.setEnabled(not item.locked)
        self.algorithm_combo.blockSignals(True)
        self.algorithm_combo.clear()
        if item.item_type == 'line':
            self.algorithm_combo.addItems(['Naive', 'DDA', 'Bresenham'])
            self.algorithm_combo.setCurrentText(item.algorithm or 'DDA')
            self.algorithm_combo.setEnabled(not item.locked)
        elif item.item_type == 'polygon':
            self.algorithm_combo.addItems(['DDA', 'Bresenham'])
            self.algorithm_combo.setCurrentText(item.algorithm or 'Bresenham')
            self.algorithm_combo.setEnabled(not item.locked)
        elif item.item_type == 'curve':
            self.algorithm_combo.addItems(['Bezier', 'B-spline'])
            self.algorithm_combo.setCurrentText(item.algorithm or 'Bezier')
            self.algorithm_combo.setEnabled(not item.locked)
        else:
            self.algorithm_combo.addItem('默认')
            self.algorithm_combo.setEnabled(False)
        self.algorithm_combo.blockSignals(False)
        self._updating_properties = False
        self.refresh_overview()
        self.refresh_command_panels()

    def update_cursor_status(self, point):
        """鼠标移动时更新状态栏的模式和坐标显示。由 CanvasView 的 mouseMoveEvent 触发。"""
        mode = self._mode_display_name(self.canvas_widget.mode)
        if hasattr(self, 'mode_status_label'):
            self.mode_status_label.setText(f'模式: {mode}')
        if hasattr(self, 'coord_status_label'):
            self.coord_status_label.setText(
                f'坐标: ({point[0]}, {point[1]})'
            )
        if hasattr(self, 'zoom_status_label'):
            self._update_zoom_status()
        self.statusBar().showMessage(
            f'模式: {mode} | 坐标: ({point[0]}, {point[1]})'
        )

    def _mode_display_name(self, mode):
        """内部模式标识 → 中文显示名。"""
        if not mode:
            return '选择'
        labels = {
            'line': '线段',
            'polygon': '多边形',
            'ellipse': '椭圆',
            'curve': '曲线',
            'clip': '裁剪',
            'rotate': '旋转',
            'scale': '缩放',
        }
        return labels.get(mode, mode)