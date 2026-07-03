from pathlib import Path

from chimerax.core.errors import UserError
from chimerax.core.tools import ToolInstance

from .missense import (
    apply_missense_scores,
    apply_missense_scores_to_structure,
    selected_chain_summary,
    selected_chain_target,
)


MODES = {
    "af3-all": {
        "button_label": "AF3 all hits",
        "description": (
            "Opens all detected AF3 model/data pairs in the selected prediction "
            "folder. Model counts are discovered from the files instead of assumed."
        ),
    },
    "af3-top": {
        "button_label": "AF3 top hit",
        "description": (
            "Opens the best detected AF3 model/data pair. Ranking metadata is used "
            "when available; otherwise the lowest model number is used."
        ),
    },
    "af2-all": {
        "button_label": "AF2 all hits",
        "description": (
            "Opens every detected AF2 ranked hit from a folder containing pdb/json "
            "outputs. Use the optional filter when a folder contains several jobs."
        ),
    },
    "af2-top": {
        "button_label": "AF2 top hit",
        "description": (
            "Opens the best detected AF2 ranked hit. Rank 1 is preferred; if rank "
            "labels are absent, a single unranked pair is accepted."
        ),
    },
    "htcf-all": {
        "button_label": "HT-ColabFold all ranks",
        "description": (
            "Opens every detected rank for one hit from an HT-ColabFold screen. "
            "Enter the screen directory and the numeric hit id before the first "
            "underscore."
        ),
    },
    "htcf-top": {
        "button_label": "HT-ColabFold top rank",
        "description": (
            "Opens rank 1 for one hit from an HT-ColabFold screen. Enter the "
            "screen directory and the numeric hit id before the first underscore."
        ),
    },
}


class AFPredictionLauncher(ToolInstance):
    SESSION_SAVE = False

    def __init__(self, session, tool_name):
        super().__init__(session, tool_name)

        from chimerax.ui import MainToolWindow

        self.tool_window = tw = MainToolWindow(self, close_destroys=False)
        parent = tw.ui_area

        from Qt.QtWidgets import (
            QFileDialog,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
        )

        self._file_dialog_class = QFileDialog
        self._mode = "af3-all"
        self._controller = None

        layout = QVBoxLayout(parent)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._title_label = QLabel(parent)
        layout.addWidget(self._title_label)

        self._description_label = QLabel(parent)
        self._description_label.setWordWrap(True)
        layout.addWidget(self._description_label)

        form = QFrame(parent)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(8)
        form_layout.setVerticalSpacing(8)
        layout.addWidget(form)

        row = 0
        self._directory_label = QLabel("Prediction folder", form)
        form_layout.addWidget(self._directory_label, row, 0)
        self._directory_entry = QLineEdit(form)
        self._directory_entry.setPlaceholderText("Choose an AF2 or AF3 output folder")
        self._directory_entry.editingFinished.connect(self._refresh_preview)
        form_layout.addWidget(self._directory_entry, row, 1)
        browse_button = QPushButton("Browse...", form)
        browse_button.clicked.connect(self._choose_directory)
        form_layout.addWidget(browse_button, row, 2)

        row += 1
        self._filter_label = QLabel("Name/filter", form)
        form_layout.addWidget(self._filter_label, row, 0)
        self._prediction_filter_entry = QLineEdit(form)
        self._prediction_filter_entry.setPlaceholderText(
            "Optional text that must appear in matching filenames"
        )
        self._prediction_filter_entry.editingFinished.connect(self._refresh_preview)
        form_layout.addWidget(self._prediction_filter_entry, row, 1, 1, 2)

        row += 1
        form_layout.addWidget(QLabel("Align structures on chain", form), row, 0)
        self._chain_entry = QLineEdit(form)
        self._chain_entry.setPlaceholderText("Blank = first chain in each structure")
        form_layout.addWidget(self._chain_entry, row, 1, 1, 2)

        self._preview = QTextEdit(parent)
        self._preview.setReadOnly(True)
        self._preview.setMinimumHeight(120)
        layout.addWidget(self._preview)

        button_row = QHBoxLayout()
        layout.addLayout(button_row)
        button_row.addStretch(1)

        scan_button = QPushButton("Scan", parent)
        scan_button.clicked.connect(self._refresh_preview)
        button_row.addWidget(scan_button)

        run_button = QPushButton("Run", parent)
        run_button.clicked.connect(self._run_analysis)
        button_row.addWidget(run_button)

        layout.addStretch(1)

        self.set_mode("af3-all", prompt_for_directory=False)
        tw.manage(placement="side")

    @classmethod
    def get_singleton(cls, session, create=True, display=False):
        from chimerax.core import tools

        return tools.get_singleton(
            session, cls, "AF Prediction Launcher", create=create, display=display
        )

    def set_mode(self, mode, prompt_for_directory=False):
        if mode not in MODES:
            raise UserError(f"Unknown AF launcher mode: {mode}")

        self._mode = mode
        config = MODES[mode]
        self._title_label.setText(f"<b>{config['button_label']}</b>")
        self._description_label.setText(config["description"])
        self._sync_mode_labels()
        self._refresh_preview()

        if prompt_for_directory:
            self._choose_directory()

    def _choose_directory(self):
        start_dir = self._directory_entry.text().strip() or str(Path.home())
        title = (
            "Choose HT-ColabFold screen directory"
            if self._is_screen_mode()
            else "Choose AlphaFold prediction folder"
        )
        selected = self._file_dialog_class.getExistingDirectory(
            self.tool_window.ui_area,
            title,
            start_dir,
        )
        if selected:
            self._directory_entry.setText(selected)
            self._refresh_preview()

    def _refresh_preview(self):
        directory_text = self._directory_entry.text().strip()
        if not directory_text:
            if self._is_screen_mode():
                message = (
                    "Choose a screen directory and enter a hit id to preview the "
                    "ranked model/data pairs that will be opened."
                )
            else:
                message = (
                    "Choose a folder to preview the model/data pairs that will be opened."
                )
            self._preview.setPlainText(message)
            return

        try:
            from .workflow import describe_prediction_folder

            directory = Path(directory_text).expanduser()
            prediction_filter = self._prediction_filter_entry.text().strip()
            self._preview.setPlainText(
                describe_prediction_folder(directory, self._mode, prediction_filter)
            )
        except Exception as err:
            self._preview.setPlainText(str(err))

    def _is_screen_mode(self):
        return self._mode.startswith("htcf-")

    def _sync_mode_labels(self):
        if self._is_screen_mode():
            self._directory_label.setText("Screen dir")
            self._directory_entry.setPlaceholderText(
                "Choose an HT-ColabFold screen directory"
            )
            self._filter_label.setText("Hit id")
            self._prediction_filter_entry.setPlaceholderText(
                "Number before first underscore, e.g. 1"
            )
        else:
            self._directory_label.setText("Prediction folder")
            self._directory_entry.setPlaceholderText("Choose an AF2 or AF3 output folder")
            self._filter_label.setText("Name/filter")
            self._prediction_filter_entry.setPlaceholderText(
                "Optional text that must appear in matching filenames"
            )

    def _run_analysis(self):
        from .workflow import describe_prediction_folder, run_af_prediction_analysis

        directory = Path(self._directory_entry.text().strip()).expanduser()
        prediction_filter = self._prediction_filter_entry.text().strip()
        chain_id = self._chain_entry.text().strip()

        describe_prediction_folder(directory, self._mode, prediction_filter)
        result = run_af_prediction_analysis(
            self.session,
            mode=self._mode,
            directory=directory,
            prediction_filter=prediction_filter,
            requested_chain=chain_id or None,
        )
        self._display_controller().add_run(result)
        self._preview.setPlainText(result.summary)
        self.session.logger.info(result.summary)

    def _display_controller(self):
        if self._controller is None or getattr(self._controller, "_deleted", False):
            self._controller = AFDisplayController(self.session)
        return self._controller


class HTColabFoldPicker(ToolInstance):
    SESSION_SAVE = False

    def __init__(self, session, tool_name="HT-ColabFold Picker"):
        super().__init__(session, tool_name)

        from chimerax.ui import MainToolWindow
        from Qt.QtCore import Qt, QUrl
        from Qt.QtGui import QColor
        from Qt.QtWidgets import (
            QAbstractItemView,
            QFileDialog,
            QComboBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
        )

        self.tool_window = tw = MainToolWindow(self, close_destroys=False)
        parent = tw.ui_area
        self._file_dialog_class = QFileDialog
        self._qt = Qt
        self._table_item_class = QTableWidgetItem
        self._opened_background = QColor("#e3f8e8")
        self._qurl_class = QUrl
        self._plot_path = None
        self._plot_html = ""
        self._hits = ()
        self._opened_hit_ids = set()

        layout = QVBoxLayout(parent)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("<b>HT-ColabFold screen picker</b>", parent)
        layout.addWidget(title)
        description = QLabel(
            "Loads IPTM_vs_PTM.txt, regenerates a clickable PEAK/IPTM plot, "
            "and opens the clicked hit with the AF Model/PAE Slider.",
            parent,
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        folder_row = QHBoxLayout()
        layout.addLayout(folder_row)
        folder_row.addWidget(QLabel("Screen dir", parent))
        self._directory_entry = QLineEdit(parent)
        self._directory_entry.setPlaceholderText("Choose an HT-ColabFold screen directory")
        folder_row.addWidget(self._directory_entry, 1)
        browse_button = QPushButton("Browse...", parent)
        browse_button.clicked.connect(self._choose_directory)
        folder_row.addWidget(browse_button)

        control_row = QHBoxLayout()
        layout.addLayout(control_row)
        control_row.addWidget(QLabel("Open mode", parent))
        self._mode_combo = QComboBox(parent)
        self._mode_combo.addItem("All ranks", "htcf-all")
        self._mode_combo.addItem("Top rank", "htcf-top")
        control_row.addWidget(self._mode_combo)
        load_button = QPushButton("Load Plot", parent)
        load_button.clicked.connect(self._load_plot)
        control_row.addWidget(load_button)
        browser_button = QPushButton("Open HTML", parent)
        browser_button.clicked.connect(self._open_html_in_browser)
        control_row.addWidget(browser_button)
        control_row.addStretch(1)

        self._status_label = QLabel("Choose a screen directory and load the plot.", parent)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._plot_widget = self._make_plot_widget(parent)
        layout.addWidget(self._plot_widget, 1)

        self._hit_table = QTableWidget(parent)
        self._hit_table.setColumnCount(6)
        self._hit_table.setHorizontalHeaderLabels(
            ["Hit id", "IPTMavg", "scaled_PEAKavg", "Status", "Opened", "Name"]
        )
        self._hit_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._hit_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._hit_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._hit_table.itemDoubleClicked.connect(
            lambda item: self._open_hit_from_row(item.row())
        )
        layout.addWidget(self._hit_table, 1)

        table_row = QHBoxLayout()
        layout.addLayout(table_row)
        open_selected_button = QPushButton("Open Selected Hit", parent)
        open_selected_button.clicked.connect(self._open_selected_hit)
        table_row.addWidget(open_selected_button)
        table_row.addStretch(1)

        tw.manage(placement="side")

    @classmethod
    def get_singleton(cls, session, create=True, display=False):
        from chimerax.core import tools

        return tools.get_singleton(
            session, cls, "HT-ColabFold Picker", create=create, display=display
        )

    def _make_plot_widget(self, parent):
        try:
            from Qt.QtWebEngineWidgets import QWebEngineView

            widget = QWebEngineView(parent)
            widget.urlChanged.connect(self._handle_url)
            self._web_engine_available = True
            return widget
        except Exception:
            from Qt.QtWidgets import QTextBrowser

            widget = QTextBrowser(parent)
            widget.setOpenLinks(False)
            widget.anchorClicked.connect(self._handle_url)
            self._web_engine_available = False
            return widget

    def _choose_directory(self):
        start_dir = self._directory_entry.text().strip() or str(Path.home())
        selected = self._file_dialog_class.getExistingDirectory(
            self.tool_window.ui_area,
            "Choose HT-ColabFold screen directory",
            start_dir,
        )
        if selected:
            self._directory_entry.setText(selected)
            self._load_plot()

    def _load_plot(self):
        from .workflow import write_ht_colabfold_peak_iptm_plot

        directory = Path(self._directory_entry.text().strip()).expanduser()
        try:
            plot_path, hits = write_ht_colabfold_peak_iptm_plot(
                directory, opened_hit_ids=self._opened_hit_ids
            )
        except Exception as err:
            self._status_label.setText(str(err))
            return

        self._plot_path = plot_path
        self._hits = hits
        self._plot_html = plot_path.read_text(encoding="utf-8")
        ready = sum(1 for hit in hits if hit.get("has_structure") and hit.get("has_score_data"))
        self._status_label.setText(
            f"Loaded {len(hits)} hits; {ready} have PDB and JSON files. "
            f"Interactive HTML written to {plot_path}."
        )
        self._populate_hit_table()
        self._set_plot_html()

    def _populate_hit_table(self):
        hits = sorted(
            self._hits,
            key=lambda hit: (-(hit.get("iptmavg") or -1.0), _natural_hit_id(hit)),
        )
        self._hit_table.setRowCount(len(hits))
        for row, hit in enumerate(hits):
            hit_id = str(hit.get("hit_id") or "")
            status = (
                "ready"
                if hit.get("has_structure") and hit.get("has_score_data")
                else "missing JSON/PDB"
            )
            values = [
                hit_id,
                _format_picker_float(hit.get("iptmavg")),
                _format_picker_float(hit.get("scaled_peakavg")),
                status,
                "yes" if hit_id in self._opened_hit_ids else "",
                str(hit.get("name") or ""),
            ]
            for column, value in enumerate(values):
                item = self._table_item_class(value)
                item.setData(self._qt.UserRole, hit_id)
                if hit_id in self._opened_hit_ids:
                    item.setBackground(self._opened_background)
                self._hit_table.setItem(row, column, item)
        self._hit_table.resizeColumnsToContents()

    def _set_plot_html(self):
        if not self._plot_html:
            return
        if self._web_engine_available:
            base_url = self._qurl_class.fromLocalFile(str(self._plot_path))
            self._plot_widget.setHtml(self._plot_html, base_url)
        else:
            self._plot_widget.setHtml(self._plot_html)

    def _handle_url(self, url):
        url_text = url.toString() if hasattr(url, "toString") else str(url)
        hit_id = self._hit_id_from_url(url_text)
        if not hit_id:
            return
        self._open_hit(hit_id)

    def _hit_id_from_url(self, url_text):
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url_text)
        if parsed.scheme == "chimerax-htcf":
            return (parse_qs(parsed.query).get("hit") or [""])[0]
        fragment = parsed.fragment or ""
        if fragment.startswith("hit-"):
            return fragment[4:]
        return ""

    def _open_selected_hit(self):
        row = self._hit_table.currentRow()
        if row < 0:
            self._status_label.setText("Select a hit row first.")
            return
        self._open_hit_from_row(row)

    def _open_hit_from_row(self, row):
        item = self._hit_table.item(row, 0)
        if item is None:
            return
        hit_id = item.data(self._qt.UserRole) or item.text()
        if hit_id:
            self._open_hit(str(hit_id))

    def _open_hit(self, hit_id):
        from .workflow import describe_prediction_folder, run_af_prediction_analysis

        directory = Path(self._directory_entry.text().strip()).expanduser()
        mode = self._mode_combo.currentData()
        try:
            describe_prediction_folder(directory, mode, hit_id)
            result = run_af_prediction_analysis(
                self.session,
                mode=mode,
                directory=directory,
                prediction_filter=hit_id,
                requested_chain=None,
            )
        except Exception as err:
            self._status_label.setText(f"Could not open hit {hit_id}: {err}")
            self.session.logger.error(str(err))
            return

        launcher = AFPredictionLauncher.get_singleton(
            self.session, create=True, display=False
        )
        launcher.set_mode(mode, prompt_for_directory=False)
        launcher._directory_entry.setText(str(directory))
        launcher._prediction_filter_entry.setText(hit_id)
        launcher._refresh_preview()
        launcher._display_controller().add_run(result)
        self._opened_hit_ids.add(str(hit_id))
        self._refresh_loaded_state()
        self._status_label.setText(result.summary)
        self.session.logger.info(result.summary)

    def _refresh_loaded_state(self):
        if self._plot_path is None:
            return
        from .workflow import write_ht_colabfold_peak_iptm_plot

        try:
            plot_path, hits = write_ht_colabfold_peak_iptm_plot(
                Path(self._directory_entry.text().strip()).expanduser(),
                output_path=self._plot_path,
                opened_hit_ids=self._opened_hit_ids,
            )
        except Exception as err:
            self._status_label.setText(str(err))
            return
        self._plot_path = plot_path
        self._hits = hits
        self._plot_html = plot_path.read_text(encoding="utf-8")
        self._populate_hit_table()
        self._set_plot_html()

    def _open_html_in_browser(self):
        if self._plot_path is None:
            self._load_plot()
        if self._plot_path is None:
            return
        try:
            from Qt.QtCore import QUrl
            from Qt.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._plot_path)))
        except Exception as err:
            self._status_label.setText(f"Could not open HTML file: {err}")


def _natural_hit_id(hit):
    try:
        return int(hit.get("hit_id") or 0)
    except (TypeError, ValueError):
        return str(hit.get("hit_id") or "")


def _format_picker_float(value):
    if value is None:
        return ""
    return f"{float(value):.4g}"


class AFDisplayController(ToolInstance):
    SESSION_SAVE = False

    def __init__(self, session):
        from chimerax.ui import MainToolWindow
        from Qt.QtCore import Qt
        from Qt.QtWidgets import (
            QCheckBox,
            QComboBox,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QSlider,
            QVBoxLayout,
        )

        super().__init__(session, "AF Display Controller")

        self._runs = []
        self._current_run_index = -1
        self._current_pair_index = 0
        self._deleted = False
        self._chain_pair_values = []
        self._last_action = "Ready."
        self._preview_count = None
        self._plddt_preview_count = None
        self._selection_sync_count = None
        self._selection_sync_handler = None

        self.tool_window = tw = MainToolWindow(self)
        parent = tw.ui_area

        layout = QVBoxLayout(parent)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("<b>AF Model/PAE Slider</b>", parent)
        layout.addWidget(title)

        top_action_row = QHBoxLayout()
        layout.addLayout(top_action_row)
        reset_display_button = QPushButton("Reset Active Run", parent)
        reset_display_button.setToolTip(
            "Restore this run to the initial model, PAE plot, cutoff, chain "
            "filter, selection, and cartoon/contact-sidechain display."
        )
        reset_display_button.clicked.connect(self._reset_active_run_display)
        top_action_row.addWidget(reset_display_button)
        top_action_row.addStretch(1)

        layout.addWidget(QLabel("Prediction run", parent))
        self._run_menu = QComboBox(parent)
        self._run_menu.currentIndexChanged.connect(self._set_run_index)
        layout.addWidget(self._run_menu)

        self._current_label = QLabel(parent)
        self._current_label.setWordWrap(True)
        layout.addWidget(self._current_label)

        self._pair_menu = QComboBox(parent)
        self._pair_menu.currentIndexChanged.connect(self._set_pair_index)
        layout.addWidget(self._pair_menu)

        slider_row = QHBoxLayout()
        layout.addLayout(slider_row)
        slider_row.addWidget(QLabel("Model/PAE", parent))
        self._pair_slider = QSlider(Qt.Horizontal, parent)
        self._pair_slider.setMinimum(0)
        self._pair_slider.setMaximum(0)
        self._pair_slider.setSingleStep(1)
        self._pair_slider.setPageStep(1)
        self._pair_slider.setTickInterval(1)
        self._pair_slider.setTickPosition(QSlider.TicksBelow)
        self._pair_slider.valueChanged.connect(self._set_pair_index)
        slider_row.addWidget(self._pair_slider, 1)
        self._slider_value_label = QLabel(parent)
        slider_row.addWidget(self._slider_value_label)

        nav_row = QHBoxLayout()
        layout.addLayout(nav_row)
        self._previous_button = QPushButton("Previous", parent)
        self._previous_button.clicked.connect(self._show_previous)
        nav_row.addWidget(self._previous_button)
        self._next_button = QPushButton("Next", parent)
        self._next_button.clicked.connect(self._show_next)
        nav_row.addWidget(self._next_button)

        self._show_all = QCheckBox("Show all structures in active run", parent)
        self._show_all.stateChanged.connect(self._apply_visibility)
        layout.addWidget(self._show_all)

        confidence_header = QLabel(
            "<b>Selection by prediction confidence</b>", parent
        )
        layout.addWidget(confidence_header)

        pae_group = QGroupBox(parent)
        pae_group.setToolTip(
            "Select residues by prediction confidence. Use inter-chain PAE "
            "for multimer contacts, or pLDDT for local confidence in monomers "
            "and individual chains."
        )
        pae_group_layout = QVBoxLayout(pae_group)
        pae_group_layout.setContentsMargins(8, 8, 8, 8)
        pae_group_layout.setSpacing(6)
        layout.addWidget(pae_group)

        mode_row = QHBoxLayout()
        pae_group_layout.addLayout(mode_row)
        mode_row.addWidget(QLabel("Selection mode", pae_group))
        self._confidence_mode_menu = QComboBox(pae_group)
        self._confidence_mode_menu.addItem("PAE (inter-chain)", "pae")
        self._confidence_mode_menu.addItem("pLDDT", "plddt")
        self._confidence_mode_menu.currentIndexChanged.connect(
            self._confidence_mode_changed
        )
        mode_row.addWidget(self._confidence_mode_menu, 1)

        note = QLabel(
            "PAE: lower is more stringent. pLDDT: higher is more stringent.",
            pae_group,
        )
        note.setWordWrap(True)
        pae_group_layout.addWidget(note)

        pae_subheader = QLabel("<b>Inter-chain PAE</b>", pae_group)
        pae_group_layout.addWidget(pae_subheader)

        chain_pair_label = QLabel("PAE chain pair", pae_group)
        self._pae_widgets = [pae_subheader, chain_pair_label]
        chain_pair_label.setToolTip(
            "Choose which chain pair is used by the PAE cutoff. "
            "'All inter-chain pairs' means the best contact to any other "
            "chain is considered."
        )
        pae_group_layout.addWidget(chain_pair_label)
        self._chain_pair_menu = QComboBox(pae_group)
        self._chain_pair_menu.addItem("All inter-chain pairs")
        self._chain_pair_menu.setToolTip(
            "Filters the PAE cutoff tool. It does not change which model is "
            "displayed. All inter-chain pairs selects a residue if its "
            "minimum PAE to at least one residue in any other chain is below "
            "the cutoff."
        )
        self._chain_pair_menu.currentIndexChanged.connect(self._preview_low_pae_residues)
        self._chain_pair_values.append(None)
        pae_group_layout.addWidget(self._chain_pair_menu)
        self._pae_widgets.append(self._chain_pair_menu)

        pae_cutoff_row = QHBoxLayout()
        pae_group_layout.addLayout(pae_cutoff_row)
        cutoff_label = QLabel("PAE cutoff", pae_group)
        self._pae_widgets.append(cutoff_label)
        cutoff_label.setToolTip(
            "Live-highlight residues whose best PAE to the selected partner "
            "chain(s) is below this value. With All inter-chain pairs, at "
            "least one partner residue in any other chain must be below the "
            "cutoff. Smaller values are more stringent."
        )
        pae_cutoff_row.addWidget(cutoff_label)
        self._pae_threshold_slider = QSlider(Qt.Horizontal, pae_group)
        self._pae_threshold_slider.setMinimum(0)
        self._pae_threshold_slider.setMaximum(30)
        self._pae_threshold_slider.setSingleStep(1)
        self._pae_threshold_slider.setPageStep(5)
        self._pae_threshold_slider.setTickInterval(5)
        self._pae_threshold_slider.setTickPosition(QSlider.TicksBelow)
        self._pae_threshold_slider.setValue(10)
        self._pae_threshold_slider.valueChanged.connect(self._pae_threshold_changed)
        pae_cutoff_row.addWidget(self._pae_threshold_slider, 1)
        self._pae_widgets.append(self._pae_threshold_slider)
        self._pae_threshold_value_label = QLabel("10", pae_group)
        self._pae_threshold_value_label.setMinimumWidth(24)
        pae_cutoff_row.addWidget(self._pae_threshold_value_label)
        self._pae_widgets.append(self._pae_threshold_value_label)

        pae_action_row = QHBoxLayout()
        pae_group_layout.addLayout(pae_action_row)
        self._live_pae_highlight = QCheckBox("Live PAE highlight", pae_group)
        self._pae_widgets.append(self._live_pae_highlight)
        self._live_pae_highlight.setChecked(True)
        self._live_pae_highlight.setToolTip(
            "When enabled, moving the cutoff slider live-selects matching "
            "residues and overlays only the below-cutoff inter-chain cells "
            "in the PAE plot."
        )
        self._live_pae_highlight.stateChanged.connect(self._live_pae_highlight_changed)
        pae_action_row.addWidget(self._live_pae_highlight)

        self._sync_pae_to_selection = QCheckBox("Sync PAE to selection", pae_group)
        self._pae_widgets.append(self._sync_pae_to_selection)
        self._sync_pae_to_selection.setChecked(False)
        self._sync_pae_to_selection.setToolTip(
            "When enabled, ChimeraX residue selections made in the structure "
            "or command line highlight the corresponding rows and columns in "
            "the active PAE plot. This switches the PAE overlay from cutoff "
            "previewing to manual selection tracking."
        )
        self._sync_pae_to_selection.stateChanged.connect(
            self._sync_pae_to_selection_changed
        )
        pae_action_row.addWidget(self._sync_pae_to_selection)

        self._sync_pae_interchain_only = QCheckBox("Only inter-chain PAE", pae_group)
        self._pae_widgets.append(self._sync_pae_interchain_only)
        self._sync_pae_interchain_only.setChecked(False)
        self._sync_pae_interchain_only.setToolTip(
            "When Sync PAE to selection is enabled, limit the PAE overlay to "
            "cells between different chains. Leave this off to highlight the "
            "full selected-residue rows and columns."
        )
        self._sync_pae_interchain_only.stateChanged.connect(
            self._sync_pae_interchain_only_changed
        )
        pae_action_row.addWidget(self._sync_pae_interchain_only)

        plddt_subheader = QLabel("<b>pLDDT confidence</b>", pae_group)
        pae_group_layout.addWidget(plddt_subheader)

        plddt_cutoff_row = QHBoxLayout()
        pae_group_layout.addLayout(plddt_cutoff_row)
        plddt_cutoff_label = QLabel("pLDDT cutoff", pae_group)
        self._plddt_widgets = [plddt_subheader, plddt_cutoff_label]
        plddt_cutoff_label.setToolTip(
            "Select residues whose pLDDT confidence score is at or above this "
            "value. Higher values are more stringent."
        )
        plddt_cutoff_row.addWidget(plddt_cutoff_label)
        self._plddt_threshold_slider = QSlider(Qt.Horizontal, pae_group)
        self._plddt_threshold_slider.setMinimum(0)
        self._plddt_threshold_slider.setMaximum(100)
        self._plddt_threshold_slider.setSingleStep(1)
        self._plddt_threshold_slider.setPageStep(10)
        self._plddt_threshold_slider.setTickInterval(10)
        self._plddt_threshold_slider.setTickPosition(QSlider.TicksBelow)
        self._plddt_threshold_slider.setValue(70)
        self._plddt_threshold_slider.valueChanged.connect(self._plddt_threshold_changed)
        plddt_cutoff_row.addWidget(self._plddt_threshold_slider, 1)
        self._plddt_widgets.append(self._plddt_threshold_slider)
        self._plddt_threshold_value_label = QLabel("70", pae_group)
        self._plddt_threshold_value_label.setMinimumWidth(28)
        plddt_cutoff_row.addWidget(self._plddt_threshold_value_label)
        self._plddt_widgets.append(self._plddt_threshold_value_label)

        plddt_action_row = QHBoxLayout()
        pae_group_layout.addLayout(plddt_action_row)
        self._live_plddt_highlight = QCheckBox("Live pLDDT selection", pae_group)
        self._plddt_widgets.append(self._live_plddt_highlight)
        self._live_plddt_highlight.setChecked(False)
        self._live_plddt_highlight.setToolTip(
            "When enabled, moving the pLDDT cutoff slider live-selects "
            "matching residues. It is off by default so it does not override "
            "the inter-chain PAE live selection."
        )
        self._live_plddt_highlight.stateChanged.connect(self._live_plddt_highlight_changed)
        plddt_action_row.addWidget(self._live_plddt_highlight)

        confidence_button_row = QHBoxLayout()
        pae_group_layout.addLayout(confidence_button_row)
        confidence_button_row.addStretch(1)
        hide_unselected_button = QPushButton("Hide Unselected", pae_group)
        hide_unselected_button.setToolTip(
            "Hide atoms, pseudobonds, cartoons, and surfaces outside the "
            "current confidence cutoff filter for every model in the active "
            "run. Bond display flags are kept normal so atoms are not later "
            "shown without their bonds."
        )
        hide_unselected_button.clicked.connect(
            self._hide_unselected_confidence_residues
        )
        confidence_button_row.addWidget(hide_unselected_button)
        show_only_button = QPushButton("Show Only", pae_group)
        show_only_button.setToolTip(
            "Apply the active confidence cutoff to every model in the active "
            "run. In PAE mode this also refreshes AlphaFold contact side "
            "chains, labels, and pseudobonds at the current threshold."
        )
        show_only_button.clicked.connect(self._show_only_confidence_residues)
        confidence_button_row.addWidget(show_only_button)
        show_all_button = QPushButton("Show All", pae_group)
        show_all_button.setToolTip(
            "Restore cartoon-only display for every model in the active run."
        )
        show_all_button.clicked.connect(self._show_all_current_model)
        confidence_button_row.addWidget(show_all_button)

        contact_display_row = QHBoxLayout()
        pae_group_layout.addLayout(contact_display_row)
        contact_display_row.addStretch(1)
        show_contacts_button = QPushButton("Show AF contacts at threshold", pae_group)
        show_contacts_button.setToolTip(
            "Show AlphaFold contact side chains, labels, and pseudobonds for "
            "the active model using the current PAE cutoff and PAE chain-pair "
            "selection. AlphaFold contacts are based on prediction confidence "
            "and spatial proximity. No files are written."
        )
        show_contacts_button.clicked.connect(self._show_contact_residues)
        contact_display_row.addWidget(show_contacts_button)
        self._pae_widgets.append(show_contacts_button)
        toggle_contact_labels_button = QPushButton("Toggle Contact Labels", pae_group)
        toggle_contact_labels_button.setToolTip(
            "Hide or restore residue labels and PAE-value labels on the "
            "currently displayed AlphaFold contact pseudobonds."
        )
        toggle_contact_labels_button.clicked.connect(self._toggle_contact_labels)
        contact_display_row.addWidget(toggle_contact_labels_button)
        self._pae_widgets.append(toggle_contact_labels_button)

        interface_display_row = QHBoxLayout()
        pae_group_layout.addLayout(interface_display_row)
        interface_area_label = QLabel("Buried area cutoff", pae_group)
        interface_area_label.setToolTip(
            "Chain-level buried solvent-accessible surface area cutoff for "
            "the ChimeraX interfaces command, in square Angstroms."
        )
        interface_display_row.addWidget(interface_area_label)
        self._pae_widgets.append(interface_area_label)
        self._interface_area_cutoff_entry = QLineEdit(pae_group)
        self._interface_area_cutoff_entry.setText("300")
        self._interface_area_cutoff_entry.setPlaceholderText("300")
        self._interface_area_cutoff_entry.setToolTip(
            "Default is 300 A^2, matching ChimeraX's chain interface area cutoff."
        )
        interface_display_row.addWidget(self._interface_area_cutoff_entry, 1)
        self._pae_widgets.append(self._interface_area_cutoff_entry)
        show_interfaces_button = QPushButton("Show interfaces at cutoff", pae_group)
        show_interfaces_button.setToolTip(
            "Run ChimeraX interfaces between the current PAE chain pair(s), "
            "but only using residues that pass the current PAE cutoff. "
            "Interface residues are then based on ChimeraX's spatial buried-area "
            "criterion, not on AlphaFold contact confidence. The resulting "
            "interface residues are shown as full sticks."
        )
        show_interfaces_button.clicked.connect(self._show_cutoff_interfaces)
        interface_display_row.addWidget(show_interfaces_button)
        self._pae_widgets.append(show_interfaces_button)

        self._sync_confidence_mode_controls()

        save_header = QLabel("<b>Save analysis results</b>", parent)
        layout.addWidget(save_header)
        save_group = QGroupBox(parent)
        save_group_layout = QVBoxLayout(save_group)
        save_group_layout.setContentsMargins(8, 8, 8, 8)
        save_group_layout.setSpacing(6)
        layout.addWidget(save_group)

        analysis_row = QHBoxLayout()
        save_group_layout.addLayout(analysis_row)
        contact_settings_label = QLabel("Contacts use current PAE cutoff", save_group)
        contact_settings_label.setToolTip(
            "Saved AlphaFold contacts use the current PAE cutoff slider from "
            "Selection by prediction confidence. Lower values are more stringent."
        )
        analysis_row.addWidget(contact_settings_label)
        self._contact_scope_menu = QComboBox(save_group)
        self._contact_scope_menu.addItem("All chain pairs", "all")
        self._contact_scope_menu.addItem("Selected PAE pair", "selected")
        self._contact_scope_menu.setToolTip(
            "Choose whether saved AlphaFold contacts/interfaces are computed "
            "for every inter-chain pair in the active model or only for the "
            "specific pair currently chosen in the PAE chain-pair menu. If "
            "the PAE menu is set to All inter-chain pairs, both options use "
            "all pairs."
        )
        analysis_row.addWidget(self._contact_scope_menu)
        run_contacts_button = QPushButton("Save Contacts and Interfaces", save_group)
        run_contacts_button.setToolTip(
            "Run ChimeraX alphafold contacts and interfaces for the active "
            "model only using the selected PAE cutoff and chain-pair scope, "
            "then write formatted reports to the active output folder."
        )
        run_contacts_button.clicked.connect(self._run_contacts_interfaces)
        analysis_row.addWidget(run_contacts_button)

        save_row = QHBoxLayout()
        save_group_layout.addLayout(save_row)
        save_row.addWidget(QLabel("File suffix", save_group))
        self._png_suffix_entry = QLineEdit(save_group)
        self._png_suffix_entry.setPlaceholderText("Optional filename suffix")
        save_row.addWidget(self._png_suffix_entry, 1)
        self._timestamp_files = QCheckBox("Timestamp", save_group)
        self._timestamp_files.setChecked(True)
        save_row.addWidget(self._timestamp_files)
        save_png_button = QPushButton("Save PNG", save_group)
        save_png_button.clicked.connect(self._save_transparent_png)
        save_row.addWidget(save_png_button)
        save_session_button = QPushButton("Save Session", save_group)
        save_session_button.clicked.connect(self._save_chimerax_session)
        save_row.addWidget(save_session_button)

        output_row = QHBoxLayout()
        save_group_layout.addLayout(output_row)
        output_row.addStretch(1)
        copy_output_button = QPushButton("Copy Output Path", save_group)
        copy_output_button.clicked.connect(self._copy_output_path)
        output_row.addWidget(copy_output_button)

        manage_row = QHBoxLayout()
        layout.addLayout(manage_row)
        manage_row.addStretch(1)
        close_run_button = QPushButton("Close Run", parent)
        close_run_button.clicked.connect(self._close_current_run)
        manage_row.addWidget(close_run_button)

        self._status_label = QLabel(parent)
        self._status_label.setWordWrap(True)
        self._status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._status_label)

        self._details_group = QGroupBox("Run details", parent)
        self._details_group.setCheckable(True)
        self._details_group.setChecked(False)
        details_layout = QVBoxLayout(self._details_group)
        details_layout.setContentsMargins(8, 8, 8, 8)
        self._output_label = QLabel(self._details_group)
        self._output_label.setWordWrap(True)
        self._output_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details_layout.addWidget(self._output_label)
        self._output_label.setVisible(False)
        self._details_group.toggled.connect(self._output_label.setVisible)
        layout.addWidget(self._details_group)

        layout.addStretch(1)

        tw.manage(placement="side")

    def _show_previous(self):
        pairs = self._current_pairs()
        if pairs:
            self._pair_menu.setCurrentIndex((self._current_pair_index - 1) % len(pairs))

    def _show_next(self):
        pairs = self._current_pairs()
        if pairs:
            self._pair_menu.setCurrentIndex((self._current_pair_index + 1) % len(pairs))

    def add_run(self, result):
        run = {
            "label": self._unique_run_label(result),
            "output_dir": result.output_dir,
            "input_directory": result.input_directory,
            "requested_chain": result.requested_chain,
            "model_group": result.model_group,
            "pae_plot": None,
            "pairs": list(result.display_pairs),
        }
        self._runs.append(run)
        self._run_menu.blockSignals(True)
        self._run_menu.addItem(run["label"])
        self._run_menu.blockSignals(False)
        self._set_run_index(len(self._runs) - 1)
        try:
            self.tool_window.shown = True
        except Exception:
            pass

    def delete(self):
        self._deleted = True
        self._remove_selection_sync_handler()
        super().delete()

    def _unique_run_label(self, result):
        base = result.run_label
        label = base
        existing = {run["label"] for run in self._runs}
        if label not in existing:
            return label
        counter = 2
        while f"{label} #{counter}" in existing:
            counter += 1
        return f"{label} #{counter}"

    def _set_run_index(self, index):
        if index < 0 or index >= len(self._runs):
            return
        self._current_run_index = index
        self._current_pair_index = 0
        self._populate_pair_menu()
        self._apply_visibility()

    def _set_pair_index(self, index):
        pairs = self._current_pairs()
        if index < 0 or index >= len(pairs):
            return
        self._current_pair_index = index
        self._populate_chain_pair_menu()
        self._sync_controls()
        self._apply_visibility()

    def _populate_pair_menu(self):
        pairs = self._current_pairs()
        self._pair_menu.blockSignals(True)
        self._pair_menu.clear()
        self._pair_menu.addItems([_display_pair_label(pair) for pair in pairs])
        self._pair_menu.setCurrentIndex(self._current_pair_index if pairs else -1)
        self._pair_menu.blockSignals(False)
        self._pair_slider.blockSignals(True)
        self._pair_slider.setMaximum(max(len(pairs) - 1, 0))
        self._pair_slider.setValue(self._current_pair_index if pairs else 0)
        self._pair_slider.blockSignals(False)
        self._populate_chain_pair_menu()

    def _sync_controls(self):
        run = self._current_run()
        pairs = self._current_pairs()
        self._run_menu.blockSignals(True)
        self._run_menu.setCurrentIndex(self._current_run_index)
        self._run_menu.blockSignals(False)

        self._pair_menu.blockSignals(True)
        self._pair_menu.setCurrentIndex(self._current_pair_index if pairs else -1)
        self._pair_menu.blockSignals(False)
        self._pair_slider.blockSignals(True)
        self._pair_slider.setMaximum(max(len(pairs) - 1, 0))
        self._pair_slider.setValue(self._current_pair_index if pairs else 0)
        self._pair_slider.blockSignals(False)
        if pairs:
            self._slider_value_label.setText(
                f"{self._current_pair_index + 1}/{len(pairs)}"
            )
        else:
            self._slider_value_label.setText("0/0")
        if run is not None:
            pair = self._current_pair()
            self._output_label.setText(
                f"Active: {_display_pair_label(pair) if pair is not None else '(none)'}\n"
                f"Confidence mode: {self._confidence_mode_label()}\n"
                f"PAE cutoff: < {self._pae_threshold():g}\n"
                f"pLDDT cutoff: >= {self._plddt_threshold():g}\n"
                f"PAE chain pair: {_chain_pair_label(self._current_chain_pair())}\n"
                f"Last action: {self._last_action}\n\n"
                f"Input folder:\n{run['input_directory']}\n\n"
                f"Output folder:\n{run['output_dir']}"
            )
        self._update_status_strip()

    def _apply_visibility(self, *_args):
        run = self._current_run()
        pairs = self._current_pairs()
        if run is None or not pairs:
            self._current_label.setText("No AF prediction runs are loaded.")
            self._sync_controls()
            return

        show_all = self._show_all.isChecked()
        current_pair = pairs[self._current_pair_index]
        for run_index, run_entry in enumerate(self._runs):
            active_run = run_index == self._current_run_index
            group = run_entry.get("model_group")
            if group is not None and not getattr(group, "deleted", False):
                try:
                    group.display = active_run
                except Exception:
                    pass
            for pair_index, pair in enumerate(run_entry["pairs"]):
                visible = active_run and (
                    show_all or pair_index == self._current_pair_index
                )
                model = pair["model"]
                if model is not None and not getattr(model, "deleted", False):
                    _restore_model_bonds(model)
                    model.display = visible
            plot = run_entry.get("pae_plot")
            if active_run:
                plot = self._ensure_run_pae_plot(run_entry, current_pair)
            if plot is not None and not _plot_closed(plot):
                plot.display(active_run)

        self._current_label.setText(
            f"Current view: {run['label']} / {_display_pair_label(current_pair)} "
            f"({self._current_pair_index + 1}/{len(pairs)})"
        )
        self._previous_button.setEnabled(len(pairs) > 1)
        self._next_button.setEnabled(len(pairs) > 1)
        self._pair_slider.setEnabled(len(pairs) > 1 and not show_all)
        self._sync_controls()
        self._preview_low_pae_residues()
        self._preview_plddt_residues()

    def _current_run(self):
        if 0 <= self._current_run_index < len(self._runs):
            return self._runs[self._current_run_index]
        return None

    def _current_pairs(self):
        run = self._current_run()
        return run["pairs"] if run is not None else []

    def _current_pair(self):
        pairs = self._current_pairs()
        if not pairs:
            return None
        return pairs[self._current_pair_index]

    def _ensure_run_pae_plot(self, run, pair):
        from .workflow import create_pae_plot, set_pae_plot_data

        pae = pair.get("pae")
        if pae is None:
            return None
        plot = run.get("pae_plot")
        if plot is None or _plot_closed(plot):
            plot = create_pae_plot(self.session, pae)
            run["pae_plot"] = plot
        else:
            set_pae_plot_data(plot, pae)
        return plot

    def _current_pae(self):
        pair = self._current_pair()
        return pair.get("pae") if pair is not None else None

    def _current_chain_pair(self):
        index = self._chain_pair_menu.currentIndex()
        if 0 <= index < len(self._chain_pair_values):
            return self._chain_pair_values[index]
        return None

    def _populate_chain_pair_menu(self):
        previous_value = self._current_chain_pair()
        pair = self._current_pair()
        chain_pairs = []
        if pair is not None:
            from .workflow import chain_pair_options

            chain_pairs = chain_pair_options(pair.get("model"))

        self._chain_pair_menu.blockSignals(True)
        self._chain_pair_menu.clear()
        self._chain_pair_values = [None]
        self._chain_pair_menu.addItem("All inter-chain pairs")
        for chain_pair in chain_pairs:
            self._chain_pair_values.append(chain_pair)
            self._chain_pair_menu.addItem(f"{chain_pair[0]} - {chain_pair[1]}")
        try:
            index = self._chain_pair_values.index(previous_value)
        except ValueError:
            index = 0
        self._chain_pair_menu.setCurrentIndex(index)
        self._chain_pair_menu.blockSignals(False)

    def _pae_threshold(self):
        return float(self._pae_threshold_slider.value())

    def _pae_threshold_changed(self, value):
        self._pae_threshold_value_label.setText(str(value))
        if self._confidence_mode() == "pae":
            self._preview_low_pae_residues()

    def _plddt_threshold(self):
        return float(self._plddt_threshold_slider.value())

    def _plddt_threshold_changed(self, value):
        self._plddt_threshold_value_label.setText(str(value))
        if self._confidence_mode() == "plddt":
            self._preview_plddt_residues()

    def _interface_area_cutoff(self):
        text = self._interface_area_cutoff_entry.text().strip()
        if not text:
            return 300.0
        try:
            value = float(text)
        except ValueError:
            raise UserError(
                f"Buried area cutoff must be a number in square Angstroms, got {text!r}."
            )
        if value < 0:
            raise UserError("Buried area cutoff must be zero or greater.")
        return value

    def _live_pae_highlight_changed(self, *_args):
        if (
            self._live_pae_highlight.isChecked()
            and self._sync_pae_to_selection.isChecked()
        ):
            self._sync_pae_to_selection.setChecked(False)
        if self._confidence_mode() == "pae":
            self._preview_low_pae_residues()

    def _sync_pae_to_selection_changed(self, *_args):
        if self._sync_pae_to_selection.isChecked():
            if self._live_pae_highlight.isChecked():
                self._live_pae_highlight.blockSignals(True)
                self._live_pae_highlight.setChecked(False)
                self._live_pae_highlight.blockSignals(False)
            self._add_selection_sync_handler()
            self._sync_pae_highlight_to_selection()
        else:
            self._remove_selection_sync_handler()
            self._selection_sync_count = None
            if (
                self._confidence_mode() == "pae"
                and self._live_pae_highlight.isChecked()
            ):
                self._preview_low_pae_residues()
            else:
                self._clear_current_pae_highlight()
                self._update_status_strip()

    def _sync_pae_interchain_only_changed(self, *_args):
        if self._sync_pae_to_selection.isChecked():
            self._sync_pae_highlight_to_selection()
        else:
            self._update_status_strip()

    def _add_selection_sync_handler(self):
        if self._selection_sync_handler is not None:
            return
        from chimerax.core.selection import SELECTION_CHANGED

        self._selection_sync_handler = self.session.triggers.add_handler(
            SELECTION_CHANGED, self._selection_changed
        )

    def _remove_selection_sync_handler(self):
        handler = self._selection_sync_handler
        if handler is None:
            return
        self._selection_sync_handler = None
        try:
            self.session.triggers.remove_handler(handler)
        except Exception:
            pass

    def _selection_changed(self, *_args):
        if self._sync_pae_to_selection.isChecked():
            self._sync_pae_highlight_to_selection()

    def _sync_pae_highlight_to_selection(self):
        from .workflow import highlight_selected_residues_in_pae

        if (
            self._confidence_mode() != "pae"
            or not self._sync_pae_to_selection.isChecked()
        ):
            return
        pae = self._current_pae()
        run = self._current_run()
        if pae is None or run is None:
            self._selection_sync_count = None
            self._clear_current_pae_highlight()
            self._update_status_strip()
            return
        residues, _message = highlight_selected_residues_in_pae(
            self.session,
            pae,
            plot=run.get("pae_plot"),
            interchain_only=self._sync_pae_interchain_only.isChecked(),
        )
        self._preview_count = None
        self._selection_sync_count = len(residues)
        self._update_status_strip()

    def _clear_current_pae_highlight(self):
        from .workflow import clear_pae_highlight

        run = self._current_run()
        if run is not None:
            clear_pae_highlight(run.get("pae_plot"))

    def _live_plddt_highlight_changed(self, *_args):
        if self._confidence_mode() == "plddt":
            self._preview_plddt_residues()

    def _confidence_mode(self):
        try:
            data = self._confidence_mode_menu.currentData()
        except AttributeError:
            data = self._confidence_mode_menu.itemData(
                self._confidence_mode_menu.currentIndex()
            )
        return data or "pae"

    def _confidence_mode_label(self):
        return _confidence_mode_label_for_value(self._confidence_mode())

    def _confidence_mode_changed(self, *_args):
        if (
            self._confidence_mode() != "pae"
            and self._sync_pae_to_selection.isChecked()
        ):
            self._sync_pae_to_selection.setChecked(False)
        self._sync_confidence_mode_controls()
        self._preview_count = None
        self._plddt_preview_count = None
        self._selection_sync_count = None
        if self._confidence_mode() == "pae":
            self._preview_low_pae_residues()
        else:
            self._preview_plddt_residues()

    def _sync_confidence_mode_controls(self):
        mode = self._confidence_mode()
        for widget in getattr(self, "_pae_widgets", []):
            widget.setEnabled(mode == "pae")
        for widget in getattr(self, "_plddt_widgets", []):
            widget.setEnabled(mode == "plddt")

    def _preview_low_pae_residues(self, *_args):
        from .workflow import preview_interchain_pae_residues

        if self._confidence_mode() != "pae":
            self._preview_count = None
            self._update_status_strip()
            return
        if self._sync_pae_to_selection.isChecked():
            self._sync_pae_highlight_to_selection()
            return
        pae = self._current_pae()
        run = self._current_run()
        if pae is None or run is None:
            self._preview_count = None
            self._update_status_strip()
            return
        plot = run.get("pae_plot")
        live = self._live_pae_highlight.isChecked()
        residues, message = preview_interchain_pae_residues(
            self.session,
            pae,
            self._pae_threshold(),
            chain_pair=self._current_chain_pair(),
            plot=plot,
            select=live,
            highlight=live,
        )
        self._preview_count = len(residues) if live else None
        self._update_status_strip()

    def _preview_plddt_residues(self, *_args):
        from .workflow import preview_plddt_residues

        if self._confidence_mode() != "plddt":
            self._plddt_preview_count = None
            self._update_status_strip()
            return
        pair = self._current_pair()
        if pair is None:
            self._plddt_preview_count = None
            self._update_status_strip()
            return
        live = self._live_plddt_highlight.isChecked()
        residues, _message = preview_plddt_residues(
            self.session,
            pair.get("model"),
            self._plddt_threshold(),
            select=live,
        )
        self._plddt_preview_count = len(residues) if live else None
        self._update_status_strip()

    def _show_only_confidence_residues(self):
        if self._confidence_mode() == "pae":
            self._show_only_pae_for_run()
        else:
            self._show_only_plddt_for_run()

    def _hide_unselected_confidence_residues(self):
        if self._confidence_mode() == "pae":
            self._hide_unselected_pae_for_run()
        else:
            self._hide_unselected_plddt_for_run()

    def _show_all_current_model(self):
        if self._confidence_mode() == "pae":
            self._show_all_pae_for_run()
        else:
            self._show_all_plddt_for_run()

    def _show_contact_residues(self):
        from .workflow import show_contact_residues_for_pair

        run = self._current_run()
        pair = self._current_pair()
        if run is None or pair is None:
            raise UserError("No active AF prediction run is available.")
        chain_pair = self._current_chain_pair()
        message = show_contact_residues_for_pair(
            self.session,
            pair,
            requested_chain=run.get("requested_chain"),
            max_pae=self._pae_threshold(),
            chain_pair=chain_pair,
            all_chain_pairs=chain_pair is None,
        )
        self._set_status(message)
        self.session.logger.info(message)

    def _toggle_contact_labels(self):
        from .workflow import toggle_contact_text_labels

        pair = self._current_pair()
        if pair is None:
            raise UserError("No active AF prediction model is available.")
        message = toggle_contact_text_labels(self.session, pair)
        self._set_status(message)
        self.session.logger.info(message)

    def _show_cutoff_interfaces(self):
        from .workflow import show_cutoff_interfaces_for_pair

        run = self._current_run()
        pair = self._current_pair()
        pae = self._current_pae()
        if run is None or pair is None or pae is None:
            raise UserError("No active AF prediction run and PAE data are available.")
        chain_pair = self._current_chain_pair()
        message = show_cutoff_interfaces_for_pair(
            self.session,
            pair,
            pae,
            requested_chain=run.get("requested_chain"),
            max_pae=self._pae_threshold(),
            buried_area_cutoff=self._interface_area_cutoff(),
            chain_pair=chain_pair,
            all_chain_pairs=chain_pair is None,
        )
        self._set_status(message)
        self.session.logger.info(message)

    def _apply_interchain_pae_visibility(self, mode):
        from .workflow import apply_interchain_pae_visibility

        pae = self._current_pae()
        if pae is None:
            raise UserError("No active PAE data is available for the current model.")
        threshold = self._pae_threshold() if mode != "show_all" else 0
        message = apply_interchain_pae_visibility(
            self.session,
            pae,
            threshold,
            mode,
            chain_pair=self._current_chain_pair(),
            plot=self._current_run().get("pae_plot") if self._current_run() else None,
            highlight=not self._sync_pae_to_selection.isChecked(),
        )
        if mode != "show_all":
            self._preview_low_pae_residues()
        self._set_status(message)
        self.session.logger.info(message)

    def _hide_unselected_pae_for_run(self):
        from .workflow import apply_interchain_pae_visibility

        run = self._current_run()
        pairs = self._current_pairs()
        if run is None or not pairs:
            raise UserError("No active AF prediction run is available.")
        threshold = self._pae_threshold()
        chain_pair = self._current_chain_pair()
        current_pair = self._current_pair()
        current_plot = run.get("pae_plot")
        sync_selection = self._sync_pae_to_selection.isChecked()
        messages = []
        for pair in pairs:
            if pair is current_pair:
                continue
            pae = pair.get("pae")
            if pae is not None:
                messages.append(
                    apply_interchain_pae_visibility(
                        self.session,
                        pae,
                        threshold,
                        "hide_unselected",
                        chain_pair=chain_pair,
                        plot=None,
                        select=False,
                        highlight=False,
                    )
                )
        if current_pair is not None and current_pair.get("pae") is not None:
            messages.append(
                apply_interchain_pae_visibility(
                    self.session,
                    current_pair.get("pae"),
                    threshold,
                    "hide_unselected",
                    chain_pair=chain_pair,
                    plot=current_plot,
                    select=True,
                    highlight=not sync_selection,
                )
            )
        if sync_selection:
            self._sync_pae_highlight_to_selection()
        self._set_status(
            f"Applied PAE hide-unselected to {len(messages)} model(s) in this run."
        )
        self.session.logger.info(self._last_action)

    def _show_only_pae_for_run(self):
        from .workflow import (
            apply_interchain_pae_visibility,
            show_contact_residues_for_pair,
        )

        run = self._current_run()
        pairs = self._current_pairs()
        if run is None or not pairs:
            raise UserError("No active AF prediction run is available.")
        threshold = self._pae_threshold()
        chain_pair = self._current_chain_pair()
        current_pair = self._current_pair()
        current_plot = run.get("pae_plot")
        sync_selection = self._sync_pae_to_selection.isChecked()
        visibility_count = 0
        contact_count = 0
        for pair in pairs:
            pae = pair.get("pae")
            if pae is None:
                continue
            is_current = pair is current_pair
            apply_interchain_pae_visibility(
                self.session,
                pae,
                threshold,
                "show_only",
                chain_pair=chain_pair,
                plot=current_plot if is_current else None,
                select=is_current,
                highlight=is_current and not sync_selection,
            )
            visibility_count += 1
            show_contact_residues_for_pair(
                self.session,
                pair,
                requested_chain=run.get("requested_chain"),
                max_pae=threshold,
                chain_pair=chain_pair,
                all_chain_pairs=chain_pair is None,
            )
            contact_count += 1
        if sync_selection:
            self._sync_pae_highlight_to_selection()
        self._set_status(
            "Applied PAE show-only and refreshed AlphaFold contacts at "
            f"threshold {threshold:g} for {visibility_count} model(s) in this "
            f"run. Contact display was refreshed for {contact_count} model(s)."
        )
        self.session.logger.info(self._last_action)

    def _show_all_pae_for_run(self):
        from .workflow import apply_interchain_pae_visibility

        run = self._current_run()
        pairs = self._current_pairs()
        if run is None or not pairs:
            raise UserError("No active AF prediction run is available.")
        current_pair = self._current_pair()
        current_plot = run.get("pae_plot")
        count = 0
        for pair in pairs:
            pae = pair.get("pae")
            if pae is None:
                continue
            apply_interchain_pae_visibility(
                self.session,
                pae,
                0,
                "show_all",
                chain_pair=self._current_chain_pair(),
                plot=current_plot if pair is current_pair else None,
                select=False,
                highlight=False,
            )
            count += 1
        if self._sync_pae_to_selection.isChecked():
            self._sync_pae_highlight_to_selection()
        self._set_status(
            f"Restored cartoon-only display for {count} PAE model(s) in this run."
        )
        self.session.logger.info(self._last_action)

    def _hide_unselected_plddt_for_run(self):
        from .workflow import apply_plddt_visibility

        pairs = self._current_pairs()
        if not pairs:
            raise UserError("No active AF prediction run is available.")
        threshold = self._plddt_threshold()
        current_pair = self._current_pair()
        messages = []
        for pair in pairs:
            if pair is current_pair:
                continue
            messages.append(
                apply_plddt_visibility(
                    self.session,
                    pair.get("model"),
                    threshold,
                    "hide_unselected",
                    select=False,
                )
            )
        if current_pair is not None:
            messages.append(
                apply_plddt_visibility(
                    self.session,
                    current_pair.get("model"),
                    threshold,
                    "hide_unselected",
                    select=True,
                )
            )
        self._set_status(
            f"Applied pLDDT hide-unselected to {len(messages)} model(s) in this run."
        )
        self.session.logger.info(self._last_action)

    def _show_only_plddt_for_run(self):
        from .workflow import apply_plddt_visibility

        pairs = self._current_pairs()
        if not pairs:
            raise UserError("No active AF prediction run is available.")
        threshold = self._plddt_threshold()
        current_pair = self._current_pair()
        count = 0
        for pair in pairs:
            apply_plddt_visibility(
                self.session,
                pair.get("model"),
                threshold,
                "show_only",
                select=pair is current_pair,
            )
            count += 1
        self._set_status(
            f"Applied pLDDT show-only to {count} model(s) in this run."
        )
        self.session.logger.info(self._last_action)

    def _show_all_plddt_for_run(self):
        from .workflow import apply_plddt_visibility

        pairs = self._current_pairs()
        if not pairs:
            raise UserError("No active AF prediction run is available.")
        count = 0
        for pair in pairs:
            apply_plddt_visibility(
                self.session,
                pair.get("model"),
                self._plddt_threshold(),
                "show_all",
                select=False,
            )
            count += 1
        self._set_status(
            f"Restored cartoon-only display for {count} pLDDT model(s) in this run."
        )
        self.session.logger.info(self._last_action)

    def _apply_plddt_visibility(self, mode):
        from .workflow import apply_plddt_visibility

        pair = self._current_pair()
        if pair is None:
            raise UserError("No active structure model is available.")
        message = apply_plddt_visibility(
            self.session,
            pair.get("model"),
            self._plddt_threshold(),
            mode,
        )
        if mode != "show_all":
            self._preview_plddt_residues()
        self._set_status(message)
        self.session.logger.info(message)

    def _run_contacts_interfaces(self):
        from .workflow import run_contacts_interfaces_for_pair

        run = self._current_run()
        pair = self._current_pair()
        if run is None or pair is None:
            raise UserError("No active AF prediction run is available.")
        chain_pair = self._contact_chain_pair_scope()
        message = run_contacts_interfaces_for_pair(
            self.session,
            pair,
            run["output_dir"],
            requested_chain=run.get("requested_chain"),
            max_pae=self._pae_threshold(),
            chain_pair=chain_pair,
            all_chain_pairs=self._contact_scope() == "all" or chain_pair is None,
        )
        self._set_status(message)
        self.session.logger.info(message)

    def _contact_scope(self):
        try:
            data = self._contact_scope_menu.currentData()
        except Exception:
            data = None
        return data or "all"

    def _contact_chain_pair_scope(self):
        if self._contact_scope() != "selected":
            return None
        return self._current_chain_pair()

    def _save_transparent_png(self):
        from .workflow import save_active_view_png

        run = self._current_run()
        pairs = self._current_pairs()
        if run is None or not pairs:
            raise UserError("No active AF prediction run is available.")
        pair = pairs[self._current_pair_index]
        suffix = self._png_suffix_entry.text().strip()
        path = save_active_view_png(
            self.session,
            run["output_dir"],
            pair["label"],
            suffix=suffix,
            timestamp=self._timestamp_files.isChecked(),
        )
        self._set_status(f"Saved transparent PNG:\n{path}")
        self.session.logger.info(f"Saved transparent PNG: {path}")

    def _save_chimerax_session(self):
        from .workflow import save_chimerax_session

        run = self._current_run()
        pairs = self._current_pairs()
        if run is None or not pairs:
            raise UserError("No active AF prediction run is available.")
        pair = pairs[self._current_pair_index]
        suffix = self._png_suffix_entry.text().strip()
        path = save_chimerax_session(
            self.session,
            run["output_dir"],
            pair["label"],
            suffix=suffix,
            timestamp=self._timestamp_files.isChecked(),
        )
        self._set_status(f"Saved ChimeraX session:\n{path}")
        self.session.logger.info(f"Saved ChimeraX session: {path}")

    def _copy_output_path(self):
        run = self._current_run()
        if run is None:
            raise UserError("No active AF prediction run is available.")
        text = str(run["output_dir"])
        from Qt.QtWidgets import QApplication

        QApplication.clipboard().setText(text)
        self._set_status(f"Copied output folder:\n{text}")

    def _reset_active_run_display(self):
        from .workflow import reset_prediction_display

        run = self._current_run()
        pairs = self._current_pairs()
        if run is None or not pairs:
            raise UserError("No active AF prediction run is available.")

        reset_prediction_display(self.session, pairs)
        self._show_all.blockSignals(True)
        self._show_all.setChecked(False)
        self._show_all.blockSignals(False)
        self._pae_threshold_slider.blockSignals(True)
        self._pae_threshold_slider.setValue(10)
        self._pae_threshold_value_label.setText("10")
        self._pae_threshold_slider.blockSignals(False)
        self._confidence_mode_menu.blockSignals(True)
        self._confidence_mode_menu.setCurrentIndex(0)
        self._confidence_mode_menu.blockSignals(False)
        self._sync_confidence_mode_controls()
        self._plddt_threshold_slider.blockSignals(True)
        self._plddt_threshold_slider.setValue(70)
        self._plddt_threshold_value_label.setText("70")
        self._plddt_threshold_slider.blockSignals(False)
        self._interface_area_cutoff_entry.setText("300")
        self._sync_pae_to_selection.setChecked(False)
        self._sync_pae_interchain_only.setChecked(False)
        self._live_pae_highlight.setChecked(True)
        self._live_plddt_highlight.setChecked(False)
        self._plddt_preview_count = None
        self._selection_sync_count = None
        self._current_pair_index = 0
        self._populate_pair_menu()
        self._chain_pair_menu.setCurrentIndex(0)
        self._apply_visibility()
        message = f"Reset display for {run['label']}."
        self._set_status(message)
        self.session.logger.info(message)

    def _close_current_run(self):
        if not self._runs:
            return
        run_index = self._current_run_index
        run = self._runs.pop(run_index)
        self._close_run_models_and_tools(run)
        self._run_menu.blockSignals(True)
        self._run_menu.removeItem(run_index)
        self._run_menu.blockSignals(False)

        if self._runs:
            self._set_run_index(min(run_index, len(self._runs) - 1))
        else:
            self._current_run_index = -1
            self._current_pair_index = 0
            self._pair_menu.clear()
            self._pair_slider.setMaximum(0)
            self._chain_pair_menu.clear()
            self._chain_pair_menu.addItem("All inter-chain pairs")
            self._chain_pair_values = [None]
            self._current_label.setText("No AF prediction runs are loaded.")
            self._output_label.clear()
        self._set_status(f"Closed run: {run['label']}")

    def _close_run_models_and_tools(self, run):
        plot = run.get("pae_plot")
        if plot is not None and not _plot_closed(plot):
            try:
                plot.delete()
            except Exception:
                plot.display(False)

        models = []
        group = run.get("model_group")
        if group is not None and not getattr(group, "deleted", False):
            models.append(group)
        else:
            for pair in run.get("pairs", []):
                model = pair.get("model")
                if model is not None and not getattr(model, "deleted", False):
                    models.append(model)
        if models:
            try:
                self.session.models.close(models)
            except Exception as err:
                self.session.logger.warning(f"Could not close AF run models: {err}")

    def _set_status(self, text):
        self._last_action = text
        self._update_status_strip()

    def _update_status_strip(self):
        run = self._current_run()
        pair = self._current_pair()
        last = _compact_status_text(self._last_action)
        if run is None or pair is None:
            self._status_label.setText(f"Last: {last}")
            return
        parts = [
            f"{_display_pair_label(pair)}",
            self._confidence_mode_label(),
            f"PAE < {self._pae_threshold():g}",
            f"pLDDT >= {self._plddt_threshold():g}",
        ]
        if self._sync_pae_to_selection.isChecked():
            selection_text = f"PAE synced to selection: {self._selection_sync_count or 0}"
            if self._sync_pae_interchain_only.isChecked():
                selection_text += " inter-chain only"
            parts.append(selection_text)
        elif not self._live_pae_highlight.isChecked():
            parts.append("live highlight off")
        if self._preview_count is not None:
            parts.append(f"PAE highlighted: {self._preview_count}")
        if self._plddt_preview_count is not None:
            parts.append(f"pLDDT selected: {self._plddt_preview_count}")
        confidence_warning = _confidence_warning(self._current_pairs())
        if confidence_warning:
            parts.append(confidence_warning)
        self._status_label.setText(" | ".join(parts) + f" | Last: {last}")


def _plot_closed(plot):
    closed = getattr(plot, "closed", None)
    return bool(closed()) if callable(closed) else False


def _display_pair_label(pair):
    return str(pair.get("display_label") or pair.get("label") or "")


def _chain_pair_label(chain_pair):
    if chain_pair is None:
        return "all inter-chain pairs"
    return f"{chain_pair[0]}-{chain_pair[1]}"


def _confidence_mode_label_for_value(mode):
    if mode == "plddt":
        return "pLDDT mode"
    return "PAE mode"


def _confidence_warning(pairs):
    missing = sum(1 for pair in pairs if pair.get("confidence_missing"))
    if missing:
        return f"confidence missing: {missing}"
    return ""


def _restore_model_bonds(model):
    if model is None or getattr(model, "deleted", False):
        return
    try:
        model.bonds.displays = True
    except Exception:
        pass


def _compact_status_text(text, limit=120):
    one_line = " ".join(str(text).split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: max(0, limit - 3)] + "..."


class AFMissenseTool(ToolInstance):
    SESSION_SAVE = False

    def __init__(self, session, tool_name):
        super().__init__(session, tool_name)

        from chimerax.ui import MainToolWindow
        from Qt.QtCore import Qt
        from Qt.QtWidgets import (
            QCheckBox,
            QGridLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        self.tool_window = tw = MainToolWindow(self, close_destroys=False)
        parent = tw.ui_area

        layout = QVBoxLayout(parent)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("<b>AlphaMissense Mapping</b>", parent)
        layout.addWidget(title)

        note = QLabel(
            "Apply AlphaMissense scores to one selected chain, or to all "
            "protein chains in one structure. AlphaMissense data is only "
            "available for human proteins.",
            parent,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self._selection_label = QLabel(parent)
        self._selection_label.setWordWrap(True)
        self._selection_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._selection_label)

        target_form = QWidget(parent)
        target_layout = QGridLayout(target_form)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setHorizontalSpacing(8)
        target_layout.setVerticalSpacing(8)
        layout.addWidget(target_form)

        target_layout.addWidget(QLabel("Model id", target_form), 0, 0)
        self._model_id_entry = QLineEdit(target_form)
        self._model_id_entry.setPlaceholderText("Example: 1")
        target_layout.addWidget(self._model_id_entry, 0, 1)

        target_layout.addWidget(QLabel("Chain id", target_form), 1, 0)
        self._chain_id_entry = QLineEdit(target_form)
        self._chain_id_entry.setPlaceholderText("Example: A")
        target_layout.addWidget(self._chain_id_entry, 1, 1)

        self._uniprot_entry = QLineEdit(parent)
        self._uniprot_entry.setPlaceholderText(
            "Optional override: human UniProt accession or entry name"
        )
        layout.addWidget(self._uniprot_entry)

        self._label_checkbox = QCheckBox("Add residue labels", parent)
        layout.addWidget(self._label_checkbox)

        self._color_key_checkbox = QCheckBox("Show AlphaMissense color key", parent)
        self._color_key_checkbox.setChecked(True)
        self._color_key_checkbox.setToolTip(
            "Show a ChimeraX color key for the blue-red AlphaMissense score "
            "scale, where 0 is blue and 1 is red."
        )
        layout.addWidget(self._color_key_checkbox)

        button_row = QHBoxLayout()
        layout.addLayout(button_row)

        refresh_button = QPushButton("Refresh Selection", parent)
        refresh_button.clicked.connect(self._refresh_selection)
        button_row.addWidget(refresh_button)

        fill_button = QPushButton("Use Selected Chain", parent)
        fill_button.clicked.connect(self._fill_from_selection)
        button_row.addWidget(fill_button)

        apply_button = QPushButton("Apply to Selected Chain", parent)
        apply_button.clicked.connect(self._apply_mapping)
        button_row.addWidget(apply_button)

        apply_all_button = QPushButton("Apply to All Chains in Model", parent)
        apply_all_button.setToolTip(
            "Uses the model id field, or the selected structure if model id is blank. "
            "The chain id field is ignored."
        )
        apply_all_button.clicked.connect(self._apply_mapping_to_all_chains)
        button_row.addWidget(apply_all_button)

        self._result_label = QLabel(parent)
        self._result_label.setWordWrap(True)
        self._result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._result_label)

        layout.addStretch(1)

        self._refresh_selection()
        tw.manage(placement="side")

    @classmethod
    def get_singleton(cls, session, create=True, display=False):
        from chimerax.core import tools

        return tools.get_singleton(
            session, cls, "AF Missense Mapping", create=create, display=display
        )

    def _refresh_selection(self):
        self._selection_label.setText(selected_chain_summary(self.session))

    def _fill_from_selection(self):
        target = selected_chain_target(self.session)
        self._model_id_entry.setText(target["model_id"])
        self._chain_id_entry.setText(target["chain_id"])
        self._refresh_selection()

    def _apply_mapping(self):
        result = apply_missense_scores(
            self.session,
            self._uniprot_entry.text().strip(),
            model_id=self._model_id_entry.text().strip(),
            chain_id=self._chain_id_entry.text().strip(),
            label_residues=self._label_checkbox.isChecked(),
            show_color_key=self._color_key_checkbox.isChecked(),
        )
        self._refresh_selection()
        labels_text = "yes" if result["labels_added"] else "no"
        key_text = "yes" if result.get("color_key_shown") else "no"
        self._result_label.setText(
            f"Mapped {result['uniprot_id']} onto {result['chain_label']}.\n"
            f"Residue labels: {labels_text}\n"
            f"Color key: {key_text}\n"
            "The temporary AlphaMissense data set was closed after mapping."
        )

    def _apply_mapping_to_all_chains(self):
        result = apply_missense_scores_to_structure(
            self.session,
            self._uniprot_entry.text().strip(),
            model_id=self._model_id_entry.text().strip(),
            label_residues=self._label_checkbox.isChecked(),
            show_color_key=self._color_key_checkbox.isChecked(),
        )
        self._refresh_selection()
        labels_text = "yes" if result["labels_added"] else "no"
        key_text = "yes" if result.get("color_key_shown") else "no"
        mapped = result["mapped_chain_labels"]
        failed = result["failed_chains"]
        if result.get("used_uniprot_override"):
            source = result.get("uniprot_id") or "manual UniProt override"
        else:
            source = "chain UniProt IDs from mmCIF metadata"
        chain_sources = result.get("chain_uniprot_ids") or {}
        summary = (
            f"Mapped {source} onto {len(mapped)} chain(s) in "
            f"{result['structure_label']}.\n"
            f"Residue labels: {labels_text}\n"
            f"Color key: {key_text}\n"
            f"Mapped chains: {', '.join(mapped)}\n"
            "The temporary AlphaMissense data set was closed after mapping."
        )
        if chain_sources and not result.get("used_uniprot_override"):
            source_text = "; ".join(
                f"{label}: {uniprot_id}"
                for label, uniprot_id in list(chain_sources.items())[:8]
            )
            if len(chain_sources) > 8:
                source_text += f"; ... {len(chain_sources) - 8} more"
            summary += f"\nUniProt sources: {source_text}"
        if failed:
            skipped = "; ".join(f"{label}: {error}" for label, error in failed[:4])
            if len(failed) > 4:
                skipped += f"; ... {len(failed) - 4} more"
            summary += f"\nSkipped chains: {skipped}"
        self._result_label.setText(summary)
