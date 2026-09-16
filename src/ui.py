"""Compact native Qt views for the shared AF workspace.

Keep workflow state in tool.py. Pages own widgets, never separate tool windows.
"""
from Qt.QtCore import Qt
from Qt.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QStackedWidget, QTabWidget, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)


class CompactLabel(QLabel):
    """Long paths/status messages must never set the dock's minimum width."""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)


def column(parent, margins=10):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(8)
    return layout


def row(layout, *widgets):
    line = QHBoxLayout()
    line.setSpacing(6)
    layout.addLayout(line)
    for widget in widgets:
        line.addWidget(widget)
    return line


def button(text, callback, tip="", primary=False):
    widget = QPushButton(text)
    widget.setToolTip(tip or text)
    widget.clicked.connect(callback)
    widget.setProperty("primary", primary)
    return widget


def combo(items=()):
    widget = QComboBox()
    widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    widget.setMinimumContentsLength(8)
    widget.setMinimumWidth(0)
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    for text, data in items:
        widget.addItem(text, data)
    widget.currentTextChanged.connect(widget.setToolTip)
    return widget


def entry(placeholder=""):
    widget = QLineEdit()
    widget.setMinimumWidth(0)
    widget.setPlaceholderText(placeholder)
    widget.setToolTip(placeholder)
    return widget


def check(text, callback=None, checked=False, tip=""):
    widget = QCheckBox(text)
    widget.setChecked(checked)
    widget.setToolTip(tip or text)
    if callback:
        widget.toggled.connect(callback)
    return widget


def heading(layout, text):
    label = QLabel(text)
    label.setProperty("section", True)
    layout.addWidget(label)
    return label


def scroll_page():
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setMinimumSize(0, 0)
    content = QWidget()
    scroll.setWidget(content)
    return scroll, column(content)


def disclosure(layout, text):
    toggle = QToolButton()
    toggle.setText(text.replace("&", "&&"))
    toggle.setCheckable(True)
    toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    toggle.setArrowType(Qt.RightArrow)
    layout.addWidget(toggle)
    content = QWidget()
    body = column(content, 0)
    content.hide()
    layout.addWidget(content)
    toggle.toggled.connect(content.setVisible)
    toggle.toggled.connect(lambda shown: toggle.setArrowType(Qt.DownArrow if shown else Qt.RightArrow))
    return toggle, content, body


def build_workspace(tool):
    root = tool.tool_window.ui_area
    root.setObjectName("afWorkspace")
    root.setMinimumSize(280, 240)
    # Inherit the application's font and palette, including dark/high contrast themes.
    root.setStyleSheet("""
        QWidget#afWorkspace QPushButton {
            padding: 5px 8px; border: 1px solid palette(mid); border-radius: 5px;
            background: palette(button); color: palette(button-text);
        }
        QWidget#afWorkspace QPushButton:hover { background: palette(midlight); }
        QWidget#afWorkspace QPushButton:pressed { background: palette(light); }
        QWidget#afWorkspace QPushButton:disabled { color: palette(mid); }
        QWidget#afWorkspace QPushButton[primary="true"] {
            font-weight: bold; background: palette(highlight); color: palette(highlighted-text);
            border-color: palette(highlight);
        }
        QWidget#afWorkspace QPushButton:focus { border-color: palette(highlight); }
        QWidget#afWorkspace QLineEdit, QWidget#afWorkspace QTextEdit {
            border: 1px solid palette(mid); border-radius: 5px; padding: 4px;
            background: palette(base); color: palette(text);
        }
        QWidget#afWorkspace QLabel[section="true"] { font-weight: bold; margin-top: 4px; }
        QWidget#afWorkspace QToolButton { padding: 3px; border: none; }
        QWidget#afWorkspace QTabWidget::pane { border: none; }
        QWidget#afWorkspace QTabBar::tab {
            padding: 7px 9px; border: none; border-bottom: 2px solid transparent;
            color: palette(text); background: transparent;
        }
        QWidget#afWorkspace QTabBar::tab:selected { border-bottom-color: palette(highlight); }
    """)
    layout = column(root, 0)
    tool._tabs = QTabWidget()
    tool._tabs.setDocumentMode(True)
    layout.addWidget(tool._tabs)
    page, body = scroll_page()
    tool._tabs.addTab(page, "Open")
    tool._file_dialog_class = QFileDialog
    heading(body, "Open predictions")
    tool._mode_menu = combo([
        ("AF3 · All hits", "af3-all"), ("AF3 · Top hit", "af3-top"),
        ("AF2 · All hits", "af2-all"), ("AF2 · Top hit", "af2-top"),
        ("HT-ColabFold · All ranks", "htcf-all"), ("HT-ColabFold · Top rank", "htcf-top"),
    ])
    body.addWidget(tool._mode_menu)
    tool._directory_label = heading(body, "Folder")
    tool._directory_entry = entry("Prediction folder")
    tool._directory_entry.editingFinished.connect(tool._refresh_preview)
    row(body, tool._directory_entry, button("Browse…", tool._choose_directory))
    tool._filter_label = heading(body, "Filter")
    tool._prediction_filter_entry = entry("Optional filename filter")
    tool._prediction_filter_entry.editingFinished.connect(tool._refresh_preview)
    body.addWidget(tool._prediction_filter_entry)
    _, _, advanced = disclosure(body, "Alignment")
    advanced.addWidget(CompactLabel("Align on chain (blank uses the first chain)."))
    tool._chain_entry = entry("Chain ID, e.g. A")
    advanced.addWidget(tool._chain_entry)
    row(body, button("Scan", tool._refresh_preview),
        button("Open predictions", tool._run_analysis, primary=True))
    heading(body, "Preview")
    tool._preview = QTextEdit()
    tool._preview.setReadOnly(True)
    tool._preview.setMinimumSize(0, 90)
    tool._preview.setMaximumHeight(180)
    body.addWidget(tool._preview)
    body.addStretch(1)
    tool._mode_menu.currentIndexChanged.connect(lambda _: tool.set_mode(tool._mode_menu.currentData()))
    # Reserve lazy pages so opening the workspace does not initialize WebEngine.
    for name in ("Inspect", "Screen", "Missense"):
        tool._tabs.addTab(QWidget(), name)
    tool._tabs.currentChanged.connect(tool._page_changed)


def build_controller(tool):
    page = QWidget()
    outer = column(page)
    tool._run_menu = combo()
    tool._run_menu.setPlaceholderText("No predictions loaded")
    tool._run_menu.currentIndexChanged.connect(tool._set_run_index)
    menu_button = QToolButton()
    menu_button.setText("•••")
    menu_button.setToolTip("Run actions")
    menu_button.setAccessibleName("Run actions")
    menu_button.setPopupMode(QToolButton.InstantPopup)
    menu = QMenu(menu_button)
    menu.addAction("Reset display", tool._reset_active_run_display)
    menu.addAction("Copy output path", tool._copy_output_path)
    menu.addSeparator()
    menu.addAction("Close run", tool._close_current_run)
    menu_button.setMenu(menu)
    row(outer, tool._run_menu, menu_button)
    tool._pair_menu = combo()
    tool._pair_menu.currentIndexChanged.connect(tool._set_pair_index)
    outer.addWidget(tool._pair_menu)
    tool._previous_button = button("‹", tool._show_previous, "Previous model")
    tool._next_button = button("›", tool._show_next, "Next model")
    for widget in (tool._previous_button, tool._next_button):
        widget.setFixedWidth(30)
    tool._pair_slider = QSlider(Qt.Horizontal)
    tool._pair_slider.setRange(0, 0)
    tool._pair_slider.valueChanged.connect(tool._set_pair_index)
    tool._slider_value_label = QLabel("0/0")
    row(outer, tool._previous_button, tool._pair_slider, tool._next_button, tool._slider_value_label)
    tool._show_all = check("Overlay models", tool._apply_visibility,
                           tip="Show all structures in the active run; PAE follows the selected model.")
    outer.addWidget(tool._show_all)
    tool._current_label = CompactLabel()
    # Full run/model names already live in the menus; retain details without repeating them.
    tool._current_label.hide()
    tool._inspect_tabs = QTabWidget()
    outer.addWidget(tool._inspect_tabs, 1)
    select_page, body = scroll_page()
    tool._inspect_tabs.addTab(select_page, "Select")
    tool._confidence_mode_menu = combo([("PAE · Inter-chain", "pae"), ("pLDDT · Local", "plddt")])
    tool._confidence_mode_menu.currentIndexChanged.connect(tool._confidence_mode_changed)
    body.addWidget(tool._confidence_mode_menu)
    tool._pae_panel = QWidget()
    pae = column(tool._pae_panel, 0)
    body.addWidget(tool._pae_panel)
    tool._chain_pair_menu = combo([("All inter-chain pairs", None)])
    tool._chain_pair_values.append(None)
    tool._chain_pair_menu.currentIndexChanged.connect(tool._preview_low_pae_residues)
    pae.addWidget(tool._chain_pair_menu)
    tool._pae_threshold_slider, tool._pae_threshold_value_label = threshold(
        pae, "PAE <", 30, 10, tool._pae_threshold_changed, "Lower values are more stringent.")
    tool._live_pae_highlight = check("Live selection", tool._live_pae_highlight_changed, True,
                                     "Select residues and highlight PAE cells below the cutoff.")
    pae.addWidget(tool._live_pae_highlight)
    _, _, overlays = disclosure(pae, "Selection overlay")
    tool._sync_pae_to_selection = check("Follow structure selection", tool._sync_pae_to_selection_changed,
                                       tip="Manual selections drive the PAE overlay and turn off cutoff live selection.")
    tool._sync_pae_interchain_only = check("Inter-chain cells only", tool._sync_pae_interchain_only_changed)
    overlays.addWidget(tool._sync_pae_to_selection)
    overlays.addWidget(tool._sync_pae_interchain_only)
    tool._plddt_panel = QWidget()
    plddt = column(tool._plddt_panel, 0)
    body.addWidget(tool._plddt_panel)
    tool._plddt_threshold_slider, tool._plddt_threshold_value_label = threshold(
        plddt, "pLDDT ≥", 100, 70, tool._plddt_threshold_changed, "Higher values are more stringent.")
    tool._live_plddt_highlight = check("Live selection", tool._live_plddt_highlight_changed)
    plddt.addWidget(tool._live_plddt_highlight)
    row(body, button("Hide rest", tool._hide_unselected_confidence_residues, "Hide residues outside the cutoff in every model."),
        button("Show only", tool._show_only_confidence_residues, "Show cutoff residues and refresh PAE contacts."),
        button("Show all", tool._show_all_current_model, "Restore cartoons for every model in this run."))
    tool._contacts_toggle, tool._contacts_panel, contacts = disclosure(body, "Contacts & interfaces")
    row(contacts, button("Show contacts", tool._show_contact_residues, "Display contacts at the current PAE cutoff."),
        button("Labels", tool._toggle_contact_labels, "Toggle contact residue and PAE labels."))
    tool._interface_area_cutoff_entry = entry("300")
    tool._interface_area_cutoff_entry.setText("300")
    row(contacts, QLabel("Area ≥ (Å²)"), tool._interface_area_cutoff_entry)
    contacts.addWidget(button("Show interfaces", tool._show_cutoff_interfaces,
                              "Display interfaces using the area cutoff and current PAE filter."))
    body.addStretch(1)
    tool._pae_widgets = []
    tool._plddt_widgets = []
    tool._sync_confidence_mode_controls()

    tool._pae_stack = QStackedWidget()
    tool._pae_stack.setProperty("af_style", tool.workspace.tool_window.ui_area.styleSheet())
    def show_pae_tab():
        tool.workspace.show_page(1)
        tool._inspect_tabs.setCurrentIndex(1)
    tool._pae_stack._af_show_tab = show_pae_tab
    empty = CompactLabel("Open predictions to view their PAE matrix.")
    tool._pae_stack.addWidget(empty)
    tool._inspect_tabs.addTab(tool._pae_stack, "PAE")
    save_page, save = scroll_page()
    tool._inspect_tabs.addTab(save_page, "Save")
    heading(save, "Contacts & interfaces")
    tool._contact_scope_menu = combo([("All chain pairs", "all"), ("Selected PAE pair", "selected")])
    save.addWidget(tool._contact_scope_menu)
    save.addWidget(button("Save reports", tool._run_contacts_interfaces,
                          "Save contacts and interfaces for the active model at the current PAE cutoff."))
    heading(save, "Image & session")
    tool._png_suffix_entry = entry("Optional filename suffix")
    save.addWidget(tool._png_suffix_entry)
    tool._timestamp_files = check("Include timestamp", checked=True)
    save.addWidget(tool._timestamp_files)
    row(save, button("Save PNG", tool._save_transparent_png), button("Save session", tool._save_chimerax_session))
    save.addWidget(button("Copy output path", tool._copy_output_path))
    tool._details_group, _, details = disclosure(save, "Run details")
    tool._output_label = CompactLabel()
    details.addWidget(tool._output_label)
    tool._details_group.toggled.connect(lambda shown: tool._sync_controls() if shown else None)
    save.addStretch(1)
    tool._status_label = CompactLabel("Open predictions to begin.")
    tool._status_label.setMaximumHeight(44)
    outer.addWidget(tool._status_label)
    tool.page = page
    tool._sync_controls()


def threshold(layout, text, maximum, value, callback, tip):
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, maximum)
    slider.setValue(value)
    slider.setToolTip(tip)
    slider.valueChanged.connect(callback)
    label = QLabel(str(value))
    label.setMinimumWidth(24)
    row(layout, QLabel(text), slider, label)
    return slider, label


def build_missense(tool):
    tool.page, body = scroll_page()
    heading(body, "AlphaMissense")
    body.addWidget(CompactLabel("Human proteins only. Auto-map uses chain UniProt IDs from mmCIF."))
    tool._selection_label = CompactLabel()
    body.addWidget(tool._selection_label)
    body.addWidget(button("Auto-map all chains", tool._auto_map_missense_to_all_chains,
                          "Map all protein chains in the selected or only open structure.", primary=True))
    tool._advanced_toggle, tool._advanced_widget, advanced = disclosure(body, "Custom mapping")
    advanced.addWidget(CompactLabel("Set both model and chain, or leave both blank to use one selected chain."))
    tool._model_id_entry = entry("Model ID, e.g. 1")
    tool._chain_id_entry = entry("Chain ID, e.g. A")
    row(advanced, tool._model_id_entry, tool._chain_id_entry)
    tool._uniprot_entry = entry("Human UniProt ID (optional override)")
    advanced.addWidget(tool._uniprot_entry)
    row(advanced, button("Use selection", tool._fill_from_selection), button("Refresh", tool._refresh_selection))
    row(advanced, button("Map chain", tool._apply_mapping), button("Map all chains", tool._apply_mapping_to_all_chains))
    heading(body, "Color scale")
    tool._range_min_spin = QDoubleSpinBox()
    tool._range_max_spin = QDoubleSpinBox()
    for spin, value in ((tool._range_min_spin, 0), (tool._range_max_spin, 1)):
        spin.setRange(0, 1)
        spin.setDecimals(2)
        spin.setSingleStep(0.05)
        spin.setValue(value)
    row(body, QLabel("Blue"), tool._range_min_spin, QLabel("Red"), tool._range_max_spin)
    body.addWidget(button("Update colors", tool._update_color_range, "Recolor mapped chains without fetching scores again."))
    tool._color_key_checkbox = check("Show color key", checked=True)
    tool._label_checkbox = check("Residue labels")
    body.addWidget(tool._color_key_checkbox)
    body.addWidget(tool._label_checkbox)
    tool._result_label = CompactLabel()
    body.addWidget(tool._result_label)
    body.addStretch(1)
    tool._refresh_selection()


def build_picker(tool):
    from Qt.QtCore import QUrl
    from Qt.QtGui import QColor
    from Qt.QtWidgets import QAbstractItemView, QTableWidget, QTableWidgetItem
    tool.page = QWidget()
    body = column(tool.page)
    tool._file_dialog_class = QFileDialog
    tool._qt = Qt
    tool._table_item_class = QTableWidgetItem
    tool._opened_background = QColor("#e3f8e8")
    tool._qurl_class = QUrl
    heading(body, "HT-ColabFold screen")
    tool._directory_entry = entry("Screen folder")
    row(body, tool._directory_entry, button("Browse…", tool._choose_directory))
    tool._mode_combo = combo([("All ranks", "htcf-all"), ("Top rank", "htcf-top")])
    row(body, tool._mode_combo, button("Load", tool._load_plot), button("HTML ↗", tool._open_html_in_browser))
    views = QTabWidget()
    body.addWidget(views, 1)
    tool._hit_table = QTableWidget()
    tool._hit_table.setColumnCount(6)
    tool._hit_table.setHorizontalHeaderLabels(["Hit", "ipTM", "PEAK", "Status", "Opened", "Name"])
    tool._hit_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    tool._hit_table.setSelectionMode(QAbstractItemView.SingleSelection)
    tool._hit_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tool._hit_table.verticalHeader().hide()
    tool._hit_table.setMinimumSize(0, 80)
    tool._hit_table.itemDoubleClicked.connect(lambda item: tool._open_hit_from_row(item.row()))
    views.addTab(tool._hit_table, "Hits")
    tool._plot_widget = tool._make_plot_widget(tool.page)
    tool._plot_widget.setMinimumSize(0, 0)
    views.addTab(tool._plot_widget, "Plot")
    body.addWidget(button("Open selected hit", tool._open_selected_hit, primary=True))
    tool._status_label = CompactLabel("Choose a screen folder, then load hits.")
    tool._status_label.setMaximumHeight(60)
    body.addWidget(tool._status_label)


def workspace_pae_plot(session, pae, stack):
    """Native PAE opens separately; the same view can move into the workspace."""
    from chimerax.alphafold.pae import AlphaFoldPAEPlot

    class WorkspacePAEPlot(AlphaFoldPAEPlot):
        SESSION_SAVE = False

        def __init__(self):
            self._embedded_page = None
            self._active = False
            self._embedded = False
            super().__init__(session, "AF PAE", pae, divider_lines=True)
            self.tool_window.shown = False
            self.tool_window.close_destroys = False
            native_parent = self.tool_window.ui_area
            native_layout = native_parent.layout()
            self._heading.hide()
            # Replace the native long heading/button row with compact controls.
            self._info_label.parentWidget().hide()
            self._plot_content = QWidget()
            self._plot_content.setObjectName("afWorkspace")
            self._plot_content.setStyleSheet(stack.property("af_style") or "")
            content = column(self._plot_content, 4)
            self._move_button = button("Move to tab", lambda: self.set_embedded(not self._embedded))
            row(content, QLabel("PAE"), self._move_button)
            content.addWidget(CompactLabel("Drag to select. Right-click for plot options."))
            self._pae_view.setMinimumSize(0, 0)
            content.addWidget(self._pae_view, 1)
            content.addWidget(self._info_label)
            self._info_label.setMinimumWidth(0)
            self._info_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            row(content, button("Color domains", self._color_domains),
                button("Color pLDDT", self._color_plddt))
            native_layout.addWidget(self._plot_content)

            self._embedded_page = QWidget()
            self._embedded_page._af_plot = self
            page = column(self._embedded_page, 0)
            self._detached_notice = QWidget()
            notice = column(self._detached_notice)
            notice.addWidget(CompactLabel("The PAE plot is open in a separate window."))
            notice.addWidget(button("Show window", lambda: self.display(True)))
            notice.addWidget(button("Move to tab", lambda: self.set_embedded(True)))
            notice.addStretch(1)
            page.addWidget(self._detached_notice)
            stack.addWidget(self._embedded_page)

            def context_menu(point):
                menu = QMenu(self._pae_view)
                self._fill_context_menu(menu, point.x(), point.y())
                menu.addAction("Help", self._show_help)
                menu.exec(self._pae_view.mapToGlobal(point))
            self._pae_view.setContextMenuPolicy(Qt.CustomContextMenu)
            self._pae_view.customContextMenuRequested.connect(context_menu)
            self._move_plot(bool(getattr(stack, "_af_embed_plots", False)))

        def set_embedded(self, embedded):
            # Use one placement preference for existing and subsequently opened runs.
            stack._af_embed_plots = embedded
            for index in range(stack.count()):
                plot = getattr(stack.widget(index), "_af_plot", None)
                if plot is not None:
                    plot._move_plot(embedded)
            if embedded:
                stack._af_show_tab()

        def _move_plot(self, embedded):
            self._embedded = embedded
            layout = (self._embedded_page.layout() if embedded
                      else self.tool_window.ui_area.layout())
            layout.addWidget(self._plot_content)
            self._plot_content.show()
            self._detached_notice.setVisible(not embedded)
            self._move_button.setText("Open window" if embedded else "Move to tab")
            self.tool_window.shown = self._active and not embedded

        def display(self, show):
            self._active = show
            if show and self._embedded_page is not None:
                stack.setCurrentWidget(self._embedded_page)
            self.tool_window.shown = show and not self._embedded

        def _color_domains(self):
            from .workflow import color_pae_domains
            color_pae_domains(self._pae)

        def set_pae(self, pae, colormap=None):
            handler = getattr(self, "_structure_delete_handler", None)
            if handler is not None:
                handler.remove()
                self._structure_delete_handler = None
            super().set_pae(pae, colormap)
            if pae.structure is not None:
                self._structure_delete_handler = pae.structure.triggers.add_handler(
                    "deleted", self._structure_deleted)

        def delete(self):
            handler = getattr(self, "_structure_delete_handler", None)
            if handler is not None:
                handler.remove()
                self._structure_delete_handler = None
            if self._embedded_page is not None:
                stack.removeWidget(self._embedded_page)
                self._plot_content.setParent(self.tool_window.ui_area)
                self._embedded_page.deleteLater()
                self._embedded_page = None
            super().delete()

    return WorkspacePAEPlot()
