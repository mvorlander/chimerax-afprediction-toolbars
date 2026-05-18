from pathlib import Path

from chimerax.core.errors import UserError
from chimerax.core.tools import ToolInstance

from .missense import apply_missense_scores, selected_chain_summary, selected_chain_target


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
        form_layout.addWidget(QLabel("Prediction folder", form), row, 0)
        self._directory_entry = QLineEdit(form)
        self._directory_entry.setPlaceholderText("Choose an AF2 or AF3 output folder")
        self._directory_entry.editingFinished.connect(self._refresh_preview)
        form_layout.addWidget(self._directory_entry, row, 1)
        browse_button = QPushButton("Browse...", form)
        browse_button.clicked.connect(self._choose_directory)
        form_layout.addWidget(browse_button, row, 2)

        row += 1
        form_layout.addWidget(QLabel("Name/filter", form), row, 0)
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
        self._refresh_preview()

        if prompt_for_directory:
            self._choose_directory()

    def _choose_directory(self):
        start_dir = self._directory_entry.text().strip() or str(Path.home())
        selected = self._file_dialog_class.getExistingDirectory(
            self.tool_window.ui_area,
            "Choose AlphaFold prediction folder",
            start_dir,
        )
        if selected:
            self._directory_entry.setText(selected)
            self._refresh_preview()

    def _refresh_preview(self):
        directory_text = self._directory_entry.text().strip()
        if not directory_text:
            self._preview.setPlainText(
                "Choose a folder to preview the model/data pairs that will be opened."
            )
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

        pae_group = QGroupBox("Inter-chain PAE selection", parent)
        pae_group.setStyleSheet(
            "QGroupBox::title { font-weight: bold; font-size: 14px; }"
        )
        pae_group.setToolTip(
            "Select residues by their minimum inter-chain PAE. "
            "'All inter-chain pairs' means a residue passes if at least one "
            "residue in any other chain is below the cutoff."
        )
        pae_group_layout = QVBoxLayout(pae_group)
        pae_group_layout.setContentsMargins(8, 8, 8, 8)
        pae_group_layout.setSpacing(6)
        layout.addWidget(pae_group)

        chain_pair_label = QLabel("PAE chain pair", pae_group)
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

        pae_cutoff_row = QHBoxLayout()
        pae_group_layout.addLayout(pae_cutoff_row)
        cutoff_label = QLabel("PAE cutoff", pae_group)
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
        self._pae_threshold_value_label = QLabel("10", pae_group)
        self._pae_threshold_value_label.setMinimumWidth(24)
        pae_cutoff_row.addWidget(self._pae_threshold_value_label)

        pae_action_row = QHBoxLayout()
        pae_group_layout.addLayout(pae_action_row)
        self._live_pae_highlight = QCheckBox("Live PAE highlight", pae_group)
        self._live_pae_highlight.setChecked(True)
        self._live_pae_highlight.setToolTip(
            "When enabled, moving the cutoff slider live-selects matching "
            "residues and overlays only the below-cutoff inter-chain cells "
            "in the PAE plot."
        )
        self._live_pae_highlight.stateChanged.connect(self._live_pae_highlight_changed)
        pae_action_row.addWidget(self._live_pae_highlight)

        pae_button_row = QHBoxLayout()
        pae_group_layout.addLayout(pae_button_row)
        pae_button_row.addStretch(1)
        hide_unselected_button = QPushButton("Hide Unselected", pae_group)
        hide_unselected_button.setToolTip(
            "Hide atoms, pseudobonds, cartoons, and surfaces outside the "
            "current PAE cutoff filter without forcing a new display style on "
            "the matching residues. Bond display flags are kept normal so "
            "atoms are not later shown without their bonds."
        )
        hide_unselected_button.clicked.connect(self._hide_unselected_low_pae_residues)
        pae_button_row.addWidget(hide_unselected_button)
        show_only_pae_button = QPushButton("Show Only", pae_group)
        show_only_pae_button.clicked.connect(self._show_only_low_pae_residues)
        pae_button_row.addWidget(show_only_pae_button)
        show_all_pae_button = QPushButton("Show All", pae_group)
        show_all_pae_button.clicked.connect(self._show_all_current_model)
        pae_button_row.addWidget(show_all_pae_button)

        save_group = QGroupBox("Save analysis results", parent)
        save_group.setStyleSheet(
            "QGroupBox::title { font-weight: bold; font-size: 14px; }"
        )
        save_group_layout = QVBoxLayout(save_group)
        save_group_layout.setContentsMargins(8, 8, 8, 8)
        save_group_layout.setSpacing(6)
        layout.addWidget(save_group)

        analysis_row = QHBoxLayout()
        save_group_layout.addLayout(analysis_row)
        contact_cutoff_label = QLabel("AF contacts PAE cutoff", save_group)
        contact_cutoff_label.setToolTip(
            "Maximum PAE allowed when saving ChimeraX alphafold contacts. "
            "Lower values make the saved contact pseudobonds, labels, and "
            "contact files more stringent."
        )
        analysis_row.addWidget(contact_cutoff_label)
        self._contact_max_pae_slider = QSlider(Qt.Horizontal, save_group)
        self._contact_max_pae_slider.setMinimum(0)
        self._contact_max_pae_slider.setMaximum(30)
        self._contact_max_pae_slider.setSingleStep(1)
        self._contact_max_pae_slider.setPageStep(5)
        self._contact_max_pae_slider.setTickInterval(5)
        self._contact_max_pae_slider.setTickPosition(QSlider.TicksBelow)
        self._contact_max_pae_slider.setValue(30)
        self._contact_max_pae_slider.valueChanged.connect(
            self._contact_max_pae_changed
        )
        analysis_row.addWidget(self._contact_max_pae_slider, 1)
        self._contact_max_pae_value_label = QLabel("30", save_group)
        self._contact_max_pae_value_label.setMinimumWidth(24)
        analysis_row.addWidget(self._contact_max_pae_value_label)
        run_contacts_button = QPushButton("Save Contacts and Interfaces", save_group)
        run_contacts_button.setToolTip(
            "Run ChimeraX alphafold contacts and interfaces for the active "
            "model only using the selected PAE cutoff, then write formatted "
            "reports to the active output folder."
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
                f"PAE cutoff: < {self._pae_threshold():g}\n"
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
        self._preview_low_pae_residues()

    def _contact_max_pae(self):
        return float(self._contact_max_pae_slider.value())

    def _contact_max_pae_changed(self, value):
        self._contact_max_pae_value_label.setText(str(value))
        self._set_status(
            "AF contacts PAE cutoff set to "
            f"{value}. Click Save Contacts and Interfaces to rerun."
        )

    def _live_pae_highlight_changed(self, *_args):
        self._preview_low_pae_residues()

    def _preview_low_pae_residues(self, *_args):
        from .workflow import preview_interchain_pae_residues

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

    def _show_only_low_pae_residues(self):
        self._apply_interchain_pae_visibility("show_only")

    def _hide_unselected_low_pae_residues(self):
        self._apply_interchain_pae_visibility("hide_unselected")

    def _show_all_current_model(self):
        self._apply_interchain_pae_visibility("show_all")

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
        )
        if mode != "show_all":
            self._preview_low_pae_residues()
        self._set_status(message)
        self.session.logger.info(message)

    def _run_contacts_interfaces(self):
        from .workflow import run_contacts_interfaces_for_pair

        run = self._current_run()
        pair = self._current_pair()
        if run is None or pair is None:
            raise UserError("No active AF prediction run is available.")
        message = run_contacts_interfaces_for_pair(
            self.session,
            pair,
            run["output_dir"],
            requested_chain=run.get("requested_chain"),
            max_pae=self._contact_max_pae(),
        )
        self._preview_low_pae_residues()
        self._set_status(message)
        self.session.logger.info(message)

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
        self._contact_max_pae_slider.blockSignals(True)
        self._contact_max_pae_slider.setValue(30)
        self._contact_max_pae_value_label.setText("30")
        self._contact_max_pae_slider.blockSignals(False)
        self._live_pae_highlight.setChecked(True)
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
            f"PAE < {self._pae_threshold():g}",
        ]
        if not self._live_pae_highlight.isChecked():
            parts.append("live highlight off")
        if self._preview_count is not None:
            parts.append(f"highlighted: {self._preview_count}")
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
            "Apply AlphaMissense scores to exactly one selected chain. "
            "AlphaMissense data is only available for human proteins.",
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
            "Human UniProt accession or entry name, e.g. Q9Y5S1 or TP53_HUMAN"
        )
        layout.addWidget(self._uniprot_entry)

        self._label_checkbox = QCheckBox("Add residue labels", parent)
        layout.addWidget(self._label_checkbox)

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
        )
        self._refresh_selection()
        labels_text = "yes" if result["labels_added"] else "no"
        self._result_label.setText(
            f"Mapped {result['uniprot_id']} onto {result['chain_label']}.\n"
            f"Residue labels: {labels_text}\n"
            "The temporary AlphaMissense data set was closed after mapping."
        )
