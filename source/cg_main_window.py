"""MainWindow —— 顶层应用窗口。

UI 构建集中在此文件（__init__、菜单、工具栏），领域逻辑拆分到三个 mixin：
  cg_main_window_core.py   CoreMixin   —— 选择、图元、撤销/重做
  cg_main_window_ops.py    OpsMixin    —— 绘制、变换、裁剪
  cg_main_window_io.py     IOMixin     —— 文件读写、模板、指令面板

用 mixin 而非单文件堆砌，是为了在 ~900 行的规模下还能定位到具体逻辑。
"""

from PyQt5 import sip
from PyQt5.QtCore import QSize, Qt, QTimer
from PyQt5.QtGui import QColor, QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QShortcut,
    qApp,
)

from cg_canvas_view import CanvasView
from cg_constants import DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT, SNAP_DEFAULT_STEP
from cg_icons import icon
from cg_main_window_core import CoreMixin
from cg_main_window_io import IOMixin
from cg_main_window_ops import OpsMixin
from cg_style import apply_app_style
from cg_widgets import LineNumberTextEdit


class MainWindow(QMainWindow, CoreMixin, OpsMixin, IOMixin):
    """Python 的 MRO 决定查找顺序为 MainWindow → IOMixin → OpsMixin → CoreMixin。
    QMainWindow 始终在最后，保证 Qt 的基类方法不被 mixin 意外覆盖。"""

    def __init__(self):
        super().__init__()
        apply_app_style()
        # ── 画布尺寸 + 默认画笔色 ──
        self.canvas_width = DEFAULT_CANVAS_WIDTH
        self.canvas_height = DEFAULT_CANVAS_HEIGHT
        self.pen_color = QColor(0, 0, 0)
        # ── 图元注册表：id → CanvasItem ──
        self.item_cnt = 0
        self.item_dict = {}
        self.selected_id = ''
        self.selected_ids = set()
        # ── 撤销/重做栈（深拷贝快照） ──
        self.undo_stack = []
        self.redo_stack = []
        # ── GUI 操作日志，用于导出可复现的指令序列 ──
        self.operation_log = []
        # ── 变换预览：操作过程中临时覆盖的图元 ──
        self.transform_preview_item = None
        # ── 防止递归更新的哨兵 ──
        self._restoring = False
        self._updating_properties = False
        # ── 左侧工具条的按钮字典 ──
        self.tool_buttons = {}
        self.current_tool_key = 'select'
        # ── rail 按钮当前使用的绘制算法，右键可切换 ──
        self._rail_algorithms = {'line': 'DDA', 'polygon': 'Bresenham'}

        # ── QGraphicsScene/View：所有图元的渲染容器 ──
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, self.canvas_width, self.canvas_height)

        self.canvas_widget = CanvasView(self.scene, self)
        self.canvas_widget.setFocusPolicy(Qt.StrongFocus)
        # +2 是为了容纳 1px 的 sceneRect 边框线
        self.canvas_widget.setFixedSize(
            self.canvas_width + 2, self.canvas_height + 2,
        )

        # ── 图元列表：支持拖拽排序（改变绘制顺序/图层） ──
        self.list_widget = QListWidget(self)
        self.list_widget.setMinimumWidth(200)
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.itemSelectionChanged.connect(self.selection_changed)
        self.list_widget.model().rowsMoved.connect(self.sync_layers_from_list)

        # ── 属性表：只读展示，通过下方控件修改 ──
        self.property_table = QTableWidget(0, 2, self)
        self.property_table.setHorizontalHeaderLabels(['字段', '值'])
        self.property_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.property_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.property_table.verticalHeader().setVisible(False)
        self.property_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.property_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.property_table.setMinimumHeight(190)

        # ── 三个属性开关：可见、锁定、填充 ──
        self.prop_visible_checkbox = QCheckBox('可见')
        self.prop_locked_checkbox = QCheckBox('锁定')
        self.prop_fill_checkbox = QCheckBox('填充')
        for checkbox in (
            self.prop_visible_checkbox,
            self.prop_locked_checkbox,
            self.prop_fill_checkbox,
        ):
            checkbox.stateChanged.connect(self.apply_property_flags)

        # ── 算法选择：仅当选中图元支持多种算法时生效 ──
        self.algorithm_combo = QComboBox(self)
        self.algorithm_combo.currentTextChanged.connect(
            self.apply_algorithm_property
        )

        # ── 颜色控件 ──
        self.pen_color_button = QPushButton('画笔色')
        self.pen_color_button.clicked.connect(self.set_pen_color)
        self.pen_color_swatch = QLabel()
        self.pen_color_swatch.setObjectName('colorSwatch')
        self.pen_color_swatch.setFixedWidth(52)

        self.item_color_button = QPushButton('图元颜色')
        self.item_color_button.clicked.connect(self.recolor_selected)
        self.fill_color_button = QPushButton('填充色')
        self.fill_color_button.clicked.connect(self.set_selected_fill_color)

        # ── 参数点编辑器：可批量修改图元的控制点坐标 ──
        self.points_table = QTableWidget(0, 2, self)
        self.points_table.setHorizontalHeaderLabels(['x', 'y'])
        self.points_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.points_table.verticalHeader().setVisible(True)
        self.points_table.setMaximumHeight(150)
        self.apply_points_button = QPushButton('应用参数点')
        self.apply_points_button.clicked.connect(self.apply_points_editor)

        # ── 网格与吸附：绘图时的辅助对齐 ──
        self.grid_checkbox = QCheckBox('显示网格')
        self.grid_checkbox.setChecked(True)
        self.grid_checkbox.stateChanged.connect(self.toggle_grid)
        self.snap_checkbox = QCheckBox('吸附网格')
        self.snap_checkbox.setChecked(False)
        self.snap_checkbox.stateChanged.connect(self.toggle_snap)
        self.snap_step_spin = QSpinBox(self)
        self.snap_step_spin.setRange(1, 1000)
        self.snap_step_spin.setValue(SNAP_DEFAULT_STEP)
        self.snap_step_spin.valueChanged.connect(self.change_snap_step)


        # ── 图层 tab：网格控制 + 图元列表 + 画布概览 ──
        layer_tab_layout = QVBoxLayout()
        layer_tab_layout.addWidget(self.grid_checkbox)
        snap_layout = QHBoxLayout()
        snap_layout.addWidget(self.snap_checkbox)
        snap_layout.addWidget(QLabel('步长'))
        snap_layout.addWidget(self.snap_step_spin)
        layer_tab_layout.addLayout(snap_layout)
        layer_title = QLabel('图层 / 图元列表')
        layer_title.setObjectName('panelTitle')
        layer_tab_layout.addWidget(layer_title)
        layer_tab_layout.addWidget(self.list_widget)
        overview_title = QLabel('画布概览')
        overview_title.setObjectName('panelTitle')
        layer_tab_layout.addWidget(overview_title)
        # 缩略图视图：共享 scene，只读、不可交互
        self.overview_view = QGraphicsView(self.scene, self)
        self.overview_view.setObjectName('overviewView')
        self.overview_view.setMinimumHeight(110)
        self.overview_view.setMaximumHeight(140)
        self.overview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.overview_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.overview_view.setInteractive(False)
        layer_tab_layout.addWidget(self.overview_view)
        layer_tab = QWidget()
        layer_tab.setLayout(layer_tab_layout)

        # ── 属性 tab：只读表格 + 算法选择 + 开关 + 颜色 + 参数点编辑 ──
        property_tab_layout = QVBoxLayout()
        property_tab_layout.addWidget(self.property_table)
        algorithm_layout = QHBoxLayout()
        algorithm_layout.addWidget(QLabel('算法'))
        algorithm_layout.addWidget(self.algorithm_combo)
        property_tab_layout.addLayout(algorithm_layout)
        flags_layout = QHBoxLayout()
        flags_layout.addWidget(self.prop_visible_checkbox)
        flags_layout.addWidget(self.prop_locked_checkbox)
        flags_layout.addWidget(self.prop_fill_checkbox)
        property_tab_layout.addLayout(flags_layout)
        color_layout = QGridLayout()
        color_layout.addWidget(self.pen_color_button, 0, 0)
        color_layout.addWidget(self.pen_color_swatch, 0, 1)
        color_layout.addWidget(self.item_color_button, 1, 0)
        color_layout.addWidget(self.fill_color_button, 1, 1)
        property_tab_layout.addLayout(color_layout)
        points_title = QLabel('参数点')
        points_title.setObjectName('panelTitle')
        property_tab_layout.addWidget(points_title)
        property_tab_layout.addWidget(self.points_table)
        property_tab_layout.addWidget(self.apply_points_button)
        property_tab = QWidget()
        property_tab.setLayout(property_tab_layout)

        # ── 命令面板：CLI 指令编辑 + 操作日志 ──
        self.command_editor = LineNumberTextEdit(self)

        save_button = QToolButton(self)
        save_button.setIcon(icon('save'))
        save_button.setToolTip('校验并应用编辑器中的指令到画布')
        save_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        save_button.setFixedSize(28, 28)
        save_button.clicked.connect(self.save_command_editor)

        title_row = QHBoxLayout()
        cli_title = QLabel('CLI 指令编辑')
        cli_title.setObjectName('panelTitle')
        title_row.addWidget(cli_title)
        title_row.addStretch(1)
        title_row.addWidget(save_button)

        cli_layout = QVBoxLayout()
        cli_layout.addLayout(title_row)
        cli_layout.addWidget(self.command_editor)
        cli_tab = QWidget()
        cli_tab.setLayout(cli_layout)

        # ── 操作日志：只读文本，GUI 操作自动追加；可导出为指令文件复现 ──
        self.operation_text = QTextEdit(self)
        self.operation_text.setReadOnly(True)
        export_log_button = QPushButton('导出操作历史')
        clear_log_button = QPushButton('清空')
        export_log_button.clicked.connect(self.export_operation_history)
        clear_log_button.clicked.connect(self.clear_operation_log)
        operation_actions = QHBoxLayout()
        operation_actions.addWidget(export_log_button)
        operation_actions.addWidget(clear_log_button)
        operation_actions.addStretch(1)
        operation_tab_layout = QVBoxLayout()
        operation_tab_layout.addWidget(QLabel('GUI 操作日志'))
        operation_tab_layout.addWidget(self.operation_text)
        operation_tab_layout.addLayout(operation_actions)
        operation_tab = QWidget()
        operation_tab.setLayout(operation_tab_layout)

        self.command_tabs = QTabWidget(self)
        self.command_tabs.addTab(cli_tab, '指令编辑')
        self.command_tabs.addTab(operation_tab, '操作日志')
        command_panel_layout = QVBoxLayout()
        command_panel_layout.addWidget(self.command_tabs)
        command_panel = QWidget()
        command_panel.setLayout(command_panel_layout)

        # ── 右侧面板：三个 tab（图层 / 属性 / 命令） ──
        self.side_tabs = QTabWidget(self)
        self.side_tabs.addTab(layer_tab, '图层')
        self.side_tabs.addTab(property_tab, '属性')
        self.side_tabs.addTab(command_panel, '命令')

        side_layout = QVBoxLayout()
        side_layout.addWidget(self.side_tabs)
        side_panel = QWidget()
        side_panel.setObjectName('sidePanel')
        side_panel.setMinimumWidth(260)
        side_panel.setMaximumWidth(320)
        side_panel.setLayout(side_layout)

        # ── 主布局：左侧工具条 | 中间画布 | 右侧面板 ──
        self.tool_rail = self._build_tool_rail()
        self.canvas_workspace = self._build_canvas_workspace()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tool_rail)
        layout.addWidget(self.canvas_workspace, 1)
        layout.addWidget(side_panel)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._build_menus()
        self._build_toolbars()
        self._build_shortcuts()
        self._build_status_widgets()
        # 加载示例图元但不记录历史 —— 这是初始状态，不应出现在撤销栈中
        self.load_demo_items(record_history=False)
        self._set_active_tool('select')
        self._update_pen_color_swatch()
        self.statusBar().showMessage('已加载示例图元，可直接编辑或继续绘制')
        self.resize(1080, 720)
        self.setWindowTitle('CG 2026 GUI')

    # ── 菜单栏 ──────────────────────────────────────────────
    # 用声明式规格 + 递归构建，避免每个菜单项手写七八行样板代码。

    def _build_menus(self):
        """从声明式规格递归构建菜单栏。"""
        self._build_menu(self.menuBar(), self._menu_spec())

    def _menu_spec(self):
        """菜单树声明式规格。

        每项为 (label, callback, shortcut)：
        - callback 为 list → 递归创建子菜单
        - callback 为可调用 → 创建 QAction 并连接信号
        - shortcut 为 None → 无快捷键
        """
        return [
            ('文件', [
                ('加载指令文件', self.load_scene_file, None),
                ('导出指令文件', self.export_scene_file, None),
                ('导出操作历史', self.export_operation_history, None),
                ('设置画笔颜色', self.set_pen_color, None),
                ('重置画布', self.reset_canvas_dialog, None),
                ('保存画布', self.save_canvas, None),
                ('取消当前绘制', self.cancel_draw_mode, None),
                ('退出', qApp.quit, None),
            ], None),
            ('绘制', [
                ('线段', [
                    ('Naive', lambda: self.start_draw('line', 'Naive'), None),
                    ('DDA', lambda: self.start_draw('line', 'DDA'), None),
                    ('Bresenham', lambda: self.start_draw('line', 'Bresenham'), None),
                ], None),
                ('多边形', [
                    ('DDA', lambda: self.start_draw('polygon', 'DDA'), None),
                    ('Bresenham', lambda: self.start_draw('polygon', 'Bresenham'), None),
                ], None),
                ('椭圆', lambda: self.start_draw('ellipse'), None),
                ('曲线', [
                    ('Bezier', lambda: self.start_draw('curve', 'Bezier'), None),
                    ('B-spline', lambda: self.start_draw('curve', 'B-spline'), None),
                ], None),
            ], None),
            ('模板', [
                ('综合示例', lambda: self.load_template_scene('综合示例'), None),
                ('裁剪示例', lambda: self.load_template_scene('裁剪示例'), None),
                ('曲线示例', lambda: self.load_template_scene('曲线示例'), None),
                ('变换示例', lambda: self.load_template_scene('变换示例'), None),
            ], None),
            ('编辑', [
                ('撤销', self.undo, 'Ctrl+Z'),
                ('重做', self.redo, 'Ctrl+Shift+Z'),
                ('复制当前图元', self.duplicate_selected, 'Ctrl+D'),
                ('重命名当前图元', self.rename_selected, 'Ctrl+R'),
                ('修改当前图元颜色', self.recolor_selected, None),
                ('上移一层', self.bring_selected_forward, None),
                ('下移一层', self.send_selected_backward, None),
                ('交互式旋转', lambda: self.start_interactive_transform('rotate'), None),
                ('交互式缩放', lambda: self.start_interactive_transform('scale'), None),
                ('裁剪', [
                    ('Cohen-Sutherland', lambda: self.start_interactive_clip('Cohen-Sutherland'), None),
                    ('Liang-Barsky', lambda: self.start_interactive_clip('Liang-Barsky'), None),
                    ('Sutherland-Hodgman 多边形', lambda: self.start_interactive_clip('Sutherland-Hodgman'), None),
                ], None),
                ('交互式裁剪', [
                    ('Cohen-Sutherland', lambda: self.start_interactive_clip('Cohen-Sutherland'), None),
                    ('Liang-Barsky', lambda: self.start_interactive_clip('Liang-Barsky'), None),
                ], None),
                ('删除当前图元', self.delete_selected, 'Delete'),
            ], None),
            ('演示', [
                ('算法过程演示', self.show_algorithm_demo, None),
                ('算法对比', self.show_algorithm_compare, None),
                ('裁剪算法对比', self.show_clip_compare, None),
            ], None),
        ]

    def _build_menu(self, parent, spec):
        """递归构建菜单树。"""
        for label, callback, shortcut in spec:
            if isinstance(callback, list):
                sub = parent.addMenu(label)
                self._build_menu(sub, callback)
            else:
                act = parent.addAction(label)
                if shortcut:
                    act.setShortcut(shortcut)
                if callback:
                    act.triggered.connect(callback)

    # ── 工具栏 ───────────────────────────────────────────────
    # 工具栏分组布局：每组是一行 QFrame，内嵌标签 + 按钮/下拉菜单。

    def _build_toolbars(self):
        toolbar = QToolBar('快捷操作', self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        self._add_toolbar_group(toolbar, '文件', [
            ('action', '加载指令', 'import', self.load_scene_file, False, False),
            ('action', '导出指令', 'export', self.export_scene_file, False, False),
            ('action', '导出历史', 'history', self.export_operation_history, False, False),
            ('action', '保存画布', 'save', self.save_canvas, True, False),
            ('action', '重置画布', 'reset', self.reset_canvas_dialog, False, False),
        ])
        self._add_toolbar_group(toolbar, '编辑', [
            ('action', '撤销', 'undo', self.undo, False, False),
            ('action', '重做', 'redo', self.redo, False, False),
            ('action', '复制', 'copy', self.duplicate_selected, False, False),
            ('action', '删除', 'trash', self.delete_selected, False, True),
        ])
        self._add_toolbar_group(toolbar, '视图', [
            ('action', '画笔颜色', 'palette', self.set_pen_color, False, False),
            ('action', '适配画布', 'fit', self.fit_canvas_view, False, False),
            ('action', '恢复 100%', 'zoom', self.reset_canvas_zoom, False, False),
        ])
        self._add_toolbar_group(toolbar, '资源', [
            ('dropdown', '模板', 'template', [
            ('综合示例', lambda: self.load_template_scene('综合示例')),
            ('裁剪示例', lambda: self.load_template_scene('裁剪示例')),
            ('曲线示例', lambda: self.load_template_scene('曲线示例')),
            ('变换示例', lambda: self.load_template_scene('变换示例')),
            ]),
        ])

    def _add_toolbar_group(self, toolbar, title, entries):
        group = QFrame(self)
        group.setObjectName('toolbarGroup')
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        label = QLabel(title, group)
        label.setObjectName('toolbarGroupLabel')
        layout.addWidget(label)
        for entry in entries:
            if entry[0] == 'action':
                _, text, icon_name, callback, primary, danger = entry
                layout.addWidget(
                    self._make_toolbar_button(
                        text, icon_name, callback, primary=primary, danger=danger
                    )
                )
            elif entry[0] == 'dropdown':
                _, text, icon_name, dropdown_entries = entry
                layout.addWidget(
                    self._create_dropdown_button(text, icon_name, dropdown_entries)
                )
        group.setLayout(layout)
        toolbar.addWidget(group)

    def _make_toolbar_button(
        self, text, icon_name, callback, primary=False, danger=False
    ):
        """工具栏按钮工厂：icon-only 风格，可标为主操作/危险操作。"""
        button = QToolButton(self)
        button.setText(text)
        button.setToolTip(text)
        button.setIcon(icon(icon_name))
        button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        button.clicked.connect(callback)
        if primary:
            button.setObjectName('primaryButton')
        elif danger:
            button.setObjectName('dangerButton')
        return button

    def _build_tool_rail(self):
        """左侧工具条：绘图/操作模式切换（互斥选中），与顶部工具栏的高频操作互补。"""
        rail = QFrame(self)
        rail.setObjectName('toolRail')
        rail.setFixedWidth(70)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        self.tool_button_group = QButtonGroup(self)
        self.tool_button_group.setExclusive(True)

        tools = [
            ('section', '选择'),
            ('select', '选择', 'select', '选择、框选和拖拽编辑 (V)', self.cancel_draw_mode),
            ('section', '绘制'),
            ('line', '线段', 'line', '', lambda: self.start_draw('line', self._rail_algorithms.get('line', 'DDA'))),
            (
                'polygon',
                '多边形',
                'polygon',
                '',
                lambda: self.start_draw('polygon', self._rail_algorithms.get('polygon', 'Bresenham')),
            ),
            ('ellipse', '椭圆', 'ellipse', '中点椭圆 (E)', lambda: self.start_draw('ellipse')),
            (
                'bezier',
                'Bezier',
                'bezier',
                'Bezier 曲线 (B)',
                lambda: self.start_draw('curve', 'Bezier'),
            ),
            (
                'bspline',
                'B-spline',
                'bspline',
                '三次均匀 B-spline 曲线',
                lambda: self.start_draw('curve', 'B-spline'),
            ),
            ('section', '操作'),
            (
                'clip',
                '裁剪',
                'clip',
                '交互式 Liang-Barsky 裁剪',
                lambda: self.start_interactive_clip('Liang-Barsky'),
            ),
            (
                'rotate',
                '旋转',
                'rotate',
                '交互式旋转',
                lambda: self.start_interactive_transform('rotate'),
            ),
            (
                'scale',
                '缩放',
                'scale',
                '交互式缩放',
                lambda: self.start_interactive_transform('scale'),
            ),
            ('section', '视图'),
        ]
        for tool in tools:
            if tool is None:
                layout.addWidget(self._rail_divider())
                continue
            if tool[0] == 'section':
                if layout.count() > 0:
                    layout.addWidget(self._rail_divider())
                section_label = QLabel(tool[1], self)
                section_label.setObjectName('railSectionLabel')
                section_label.setAlignment(Qt.AlignCenter)
                layout.addWidget(section_label)
                continue
            key, label, icon_name, tooltip, callback = tool
            button = QToolButton(self)
            button.setObjectName('railToolButton')
            button.setText(label)
            button.setToolTip(tooltip)
            button.setIcon(icon(icon_name))
            button.setIconSize(QSize(22, 22))
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(callback)
            self.tool_button_group.addButton(button)
            self.tool_buttons[key] = button
            layout.addWidget(button)

        # ── 线段 / 多边形按钮的算法选择弹出菜单 ──
        self._setup_rail_algorithm_popup('line', ['Naive', 'DDA', 'Bresenham'])
        self._setup_rail_algorithm_popup('polygon', ['DDA', 'Bresenham'])

        layout.addStretch(1)
        fit_button = QToolButton(self)
        fit_button.setObjectName('railToolButton')
        fit_button.setText('适配')
        fit_button.setToolTip('适配画布到当前视图')
        fit_button.setIcon(icon('fit'))
        fit_button.setIconSize(QSize(22, 22))
        fit_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        fit_button.clicked.connect(self.fit_canvas_view)
        layout.addWidget(fit_button)

        zoom_button = QToolButton(self)
        zoom_button.setObjectName('railToolButton')
        zoom_button.setText('100%')
        zoom_button.setToolTip('恢复 100% 缩放')
        zoom_button.setIcon(icon('zoom'))
        zoom_button.setIconSize(QSize(22, 22))
        zoom_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        zoom_button.clicked.connect(self.reset_canvas_zoom)
        layout.addWidget(zoom_button)

        rail.setLayout(layout)
        return rail

    def _build_canvas_workspace(self):
        """画布工作区：canvas_widget 包在 paper 框内，水平垂直居中。

        paper 设置 Fixed size policy 使得 workspace 拉伸时画布尺寸不变，
        只是在视觉上居中 —— 这避免了 canvas resize 引发坐标缩放问题。
        """
        workspace = QFrame(self)
        workspace.setObjectName('canvasWorkspace')
        workspace_layout = QVBoxLayout()
        workspace_layout.setContentsMargins(18, 18, 18, 18)
        workspace_layout.setSpacing(10)

        paper = QFrame(workspace)
        paper.setObjectName('canvasPaperFrame')
        paper_layout = QVBoxLayout()
        paper_layout.setContentsMargins(0, 0, 0, 0)
        paper_layout.addWidget(self.canvas_widget)
        paper.setLayout(paper_layout)
        paper.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        canvas_row = QHBoxLayout()
        canvas_row.setContentsMargins(0, 0, 0, 0)
        canvas_row.addStretch(1)
        canvas_row.addWidget(paper, 0, Qt.AlignCenter)
        canvas_row.addStretch(1)
        workspace_layout.addLayout(canvas_row, 1)
        workspace.setLayout(workspace_layout)
        return workspace

    def _shortcut_select(self):
        """V 键：退出当前绘制模式并切回选择。"""
        self.cancel_draw_mode()
        self._flash_subtitle('快捷键 V：回到选择模式')

    def _build_shortcuts(self):
        """注册全局快捷键，仅当窗口有焦点时生效。"""
        shortcuts = [
            ('V', lambda: self._shortcut_select(), '选择'),
            ('L', lambda: self.start_draw('line', self._rail_algorithms.get('line', 'DDA'), shortcut='L'), '线段'),
            ('P', lambda: self.start_draw('polygon', self._rail_algorithms.get('polygon', 'Bresenham'), shortcut='P'), '多边形'),
            ('E', lambda: self.start_draw('ellipse', shortcut='E'), '椭圆'),
            ('B', lambda: self.start_draw('curve', 'Bezier', shortcut='B'), 'Bezier'),
            ('Ctrl+Y', self.redo, '重做'),
        ]
        for key, callback, label in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            shortcut.setWhatsThis(label)

    def _setup_rail_algorithm_popup(self, key, algorithms):
        """给 rail 按钮挂右键弹出菜单，切换绘制算法（如 DDA/Bresenham）。

        用 MenuButtonPopup 模式：左键直接触发当前算法绘制，右键弹出选择。
        """
        button = self.tool_buttons.get(key)
        if button is None:
            return
        menu = QMenu(button)
        current = self._rail_algorithms.get(key, algorithms[0])
        for algo in algorithms:
            action = menu.addAction(algo)
            action.setCheckable(True)
            action.setChecked(algo == current)
            action.triggered.connect(
                lambda _checked, k=key, a=algo: self._set_rail_algorithm(k, a)
            )
        button.setMenu(menu)
        button.setPopupMode(QToolButton.MenuButtonPopup)
        self._update_rail_algorithm_tooltip(key)

    def _set_rail_algorithm(self, key, algorithm):
        """切换 rail 按钮对应的绘制算法。"""
        self._sync_rail_algorithm(key, algorithm)
        if self.canvas_widget.mode == key:
            if self.canvas_widget.draw_has_draft:
                self._flash_subtitle('请先右键完成或取消当前图元，再切换绘制算法')
                return
            self.start_draw(key, algorithm)
            return
        if key == 'line':
            subtitles = {
                'Naive': '线段绘制 - Naive：直接根据直线方程采样像素',
                'DDA': '线段绘制 - DDA：按最大坐标变化量做增量采样',
                'Bresenham': '线段绘制 - Bresenham：使用误差项递推选择像素',
            }
            self._flash_subtitle(subtitles.get(algorithm, f'线段绘制 - {algorithm}'))
        elif key == 'polygon':
            if algorithm == 'DDA':
                self._flash_subtitle('多边形绘制 - DDA：逐边调用 DDA 线段算法')
            else:
                self._flash_subtitle('多边形绘制 - Bresenham：逐边调用 Bresenham')

    def _sync_rail_algorithm(self, key, algorithm):
        """同步 rail 按钮当前算法，不额外显示字幕。"""
        if key not in ('line', 'polygon') or not algorithm:
            return
        self._rail_algorithms[key] = algorithm
        button = self.tool_buttons.get(key)
        if button is not None and button.menu() is not None:
            for action in button.menu().actions():
                action.setChecked(action.text() == algorithm)
        self._update_rail_algorithm_tooltip(key)

    def _update_rail_algorithm_tooltip(self, key):
        button = self.tool_buttons.get(key)
        if button is None:
            return
        algo = self._rail_algorithms.get(key, '')
        labels = {'line': '线段', 'polygon': '多边形'}
        shortcuts = {'line': '(L)', 'polygon': '(P)'}
        label = labels.get(key, key)
        sc = shortcuts.get(key, '')
        button.setToolTip(f'{label} — {algo} {sc}')

    def _flash_subtitle(self, text, duration_ms=3000):
        """画布底部显示半透明字幕，支持较长操作说明。"""
        from PyQt5.QtGui import QFont, QPen
        # 清除上一个字幕
        self._remove_subtitle_item('_subtitle_item')
        self._remove_subtitle_item('_subtitle_bg')
        self._subtitle_token = getattr(self, '_subtitle_token', 0) + 1
        token = self._subtitle_token
        item = self.scene.addText(text)
        item.setDefaultTextColor(QColor(255, 255, 255))
        sr = self.scene.sceneRect()
        font_size = 22 if len(text) <= 18 else 18
        item.setFont(QFont('PingFang SC', font_size, QFont.Bold))
        max_width = max(260, min(sr.width() - 48, sr.width() * 0.88))
        if len(text) > 18:
            item.setTextWidth(max_width)
        sr = self.scene.sceneRect()
        br = item.boundingRect()
        x = max(12, sr.width() / 2 - br.width() / 2 - 12)
        y = max(12, sr.height() - br.height() - 42)
        # 半透明深色背景
        bg = self.scene.addRect(
            x, y, br.width() + 24, br.height() + 14,
            QPen(Qt.NoPen), QColor(0, 0, 0, 160),
        )
        bg.setZValue(9_999)
        self._subtitle_bg = bg
        item.setPos(x + 12, y + 7)
        item.setZValue(10_000)
        self._subtitle_item = item
        QTimer.singleShot(duration_ms, lambda: self._clear_subtitle(token))

    def _clear_subtitle(self, token=None):
        if token is not None and token != getattr(self, '_subtitle_token', None):
            return
        self._remove_subtitle_item('_subtitle_item')
        self._remove_subtitle_item('_subtitle_bg')

    def _forget_subtitle_items(self):
        """场景整体清空前丢弃字幕引用，并让旧的 singleShot 回调失效。"""
        self._subtitle_token = getattr(self, '_subtitle_token', 0) + 1
        self._subtitle_item = None
        self._subtitle_bg = None

    def _remove_subtitle_item(self, attr_name):
        """安全移除字幕图元；撤销/重做可能已先由 Qt 删除底层对象。"""
        item = getattr(self, attr_name, None)
        if item is None:
            return
        try:
            if sip.isdeleted(item):
                return
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        except RuntimeError:
            pass
        setattr(self, attr_name, None)

    def _rail_divider(self):
        divider = QFrame(self)
        divider.setObjectName('railDivider')
        divider.setFrameShape(QFrame.HLine)
        return divider

    def _build_status_widgets(self):
        """状态栏永久组件：当前模式、鼠标坐标、缩放比例。"""
        self.mode_status_label = QLabel('模式: 选择')
        self.coord_status_label = QLabel('坐标: -')
        self.zoom_status_label = QLabel('缩放: 100%')
        for label in (
            self.mode_status_label,
            self.coord_status_label,
            self.zoom_status_label,
        ):
            label.setObjectName('statusPill')
            self.statusBar().addPermanentWidget(label)

    def _set_active_tool(self, key, label=None):
        """激活工具按钮并更新状态栏，按钮不存在时回退到 select。"""
        self.current_tool_key = key
        button = self.tool_buttons.get(key)
        if button is not None:
            button.setChecked(True)
            label = label or button.text()
        elif self.tool_buttons.get('select') is not None:
            self.tool_buttons['select'].setChecked(True)
            label = label or '选择'
        if hasattr(self, 'mode_status_label'):
            self.mode_status_label.setText(f'模式: {label or key}')

    def _update_pen_color_swatch(self):
        """更新色块标签到当前画笔颜色。"""
        if not hasattr(self, 'pen_color_swatch'):
            return
        color = self.pen_color
        self.pen_color_swatch.setText(
            f'{color.red()}, {color.green()}, {color.blue()}'
        )
        self.pen_color_swatch.setStyleSheet(
            'QLabel#colorSwatch {'
            f'background: rgb({color.red()}, {color.green()}, {color.blue()});'
            'border: 1px solid #D1D5DB;'
            'border-radius: 6px;'
            'padding: 3px 8px;'
            'color: #111827;'
            '}'
        )

    def fit_canvas_view(self):
        """缩放视图使整个画布适配当前窗口。"""
        self.canvas_widget.fit_to_canvas()
        self._update_zoom_status()

    def reset_canvas_zoom(self):
        """恢复 100% 缩放（1 个场景像素 = 1 个屏幕像素）。"""
        self.canvas_widget.reset_zoom()
        self._update_zoom_status()

    def _update_zoom_status(self):
        """更新状态栏的缩放百分比。"""
        zoom_text = f'{int(round(self.canvas_widget.view_scale * 100))}%'
        if hasattr(self, 'zoom_status_label'):
            self.zoom_status_label.setText(f'缩放: {zoom_text}')

    def refresh_overview(self):
        """让缩略图视图重新适配 sceneRect。"""
        if hasattr(self, 'overview_view'):
            self.overview_view.fitInView(
                self.scene.sceneRect(), Qt.KeepAspectRatio
            )

    def show_canvas_context_menu(self, global_pos, scene_pos):
        """画布右键菜单：根据当前选中图元的类型动态拼装菜单项。

        空处右键只显示视图操作；有选中图元时显示编辑/变换/裁剪选项。
        """
        rect = self.scene.sceneRect()
        point = [
            min(max(int(scene_pos.x()), 0), int(rect.width()) - 1),
            min(max(int(scene_pos.y()), 0), int(rect.height()) - 1),
        ]
        self.select_item_at(point, additive=False)

        menu = QMenu(self)
        if not self.selected_id:
            menu.addAction('适配画布', self.fit_canvas_view)
            menu.addAction('恢复 100%', self.reset_canvas_zoom)
            menu.exec_(global_pos)
            return

        item = self.item_dict.get(self.selected_id)
        menu.addAction(f'复制 {self.selected_id}', self.duplicate_selected)
        menu.addAction('重命名', self.rename_selected)
        menu.addAction('改色', self.recolor_selected)
        menu.addSeparator()
        menu.addAction(
            '显示' if item is not None and not item.visible else '隐藏',
            self.toggle_selected_visibility,
        )
        menu.addAction(
            '解锁' if item is not None and item.locked else '锁定',
            self.toggle_selected_lock,
        )
        if item is not None and item.item_type == 'polygon':
            menu.addAction(
                '取消填充' if item.fill_enabled else '填充',
                self.toggle_selected_fill,
            )
            menu.addAction('设置填充色', self.set_selected_fill_color)
        menu.addSeparator()
        menu.addAction('上移一层', self.bring_selected_forward)
        menu.addAction('下移一层', self.send_selected_backward)
        if item is not None and item.item_type != 'ellipse':
            menu.addAction(
                '交互式旋转',
                lambda: self.start_interactive_transform('rotate'),
            )
        if item is not None:
            menu.addAction(
                '交互式缩放',
                lambda: self.start_interactive_transform('scale'),
            )
        if item is not None and item.item_type in ('line', 'polygon'):
            clip_menu = menu.addMenu('裁剪')
            if item.item_type == 'line':
                clip_menu.addAction(
                    'Cohen-Sutherland',
                    lambda: self.start_interactive_clip('Cohen-Sutherland'),
                )
                clip_menu.addAction(
                    'Liang-Barsky',
                    lambda: self.start_interactive_clip('Liang-Barsky'),
                )
            else:
                clip_menu.addAction(
                    'Sutherland-Hodgman',
                    lambda: self.start_interactive_clip('Sutherland-Hodgman'),
                )
        menu.addSeparator()
        delete_action = menu.addAction('删除')
        delete_action.triggered.connect(self.delete_selected)
        menu.exec_(global_pos)

    def _create_dropdown_button(self, title, icon_name, entries):
        """创建带下拉菜单的工具栏按钮（InstantPopup 模式，点击直接弹出）。"""
        button = QToolButton(self)
        button.setText(title)
        button.setToolTip(title)
        button.setIcon(icon(icon_name))
        button.setIconSize(QSize(18, 18))
        button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(button)
        for label, callback in entries:
            menu.addAction(label, callback)
        button.setMenu(menu)
        return button