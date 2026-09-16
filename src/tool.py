from pathlib import Path

from chimerax.core.errors import UserError
from chimerax.core.tools import ToolInstance

from .missense import (
    apply_missense_coloring,
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
        from .ui import build_workspace

        self.display_name = "AF Workspace"
        self.tool_window = MainToolWindow(self, close_destroys=False)
        self._mode = "af3-all"
        self._controller = None
        self._picker = None
        self._missense = None
        build_workspace(self)
        self.set_mode("af3-all")
        self.tool_window.manage(placement="side")

    @classmethod
    def get_singleton(cls, session, create=True, display=False):
        from chimerax.core import tools
        return tools.get_singleton(
            session, cls, "AF Workspace", create=create, display=display
        )

    def set_mode(self, mode, prompt_for_directory=False):
        if mode not in MODES:
            raise UserError(f"Unknown AF launcher mode: {mode}")
        self._mode = mode
        self._mode_menu.blockSignals(True)
        self._mode_menu.setCurrentIndex(self._mode_menu.findData(mode))
        self._mode_menu.blockSignals(False)
        self._mode_menu.setToolTip(MODES[mode]["description"])
        self._sync_mode_labels()
        self._refresh_preview()
        # Toolbar shortcuts select a page; Browse is an explicit action.
        if prompt_for_directory:
            self.show_page(0)

    def _page_changed(self, index):
        if index == 1:
            self._display_controller()
        elif index == 2 and self._picker is None:
            self._picker = HTColabFoldPicker(self.session, workspace=self)
            self._install_page(2, self._picker.page, "Screen")
        elif index == 3:
            if self._missense is None:
                self._missense = AFMissenseTool(self.session, workspace=self)
                self._install_page(3, self._missense.page, "Missense")
            self._missense._refresh_selection()

    def _install_page(self, index, page, name):
        old = self._tabs.widget(index)
        active = self._tabs.currentIndex()
        self._tabs.blockSignals(True)
        self._tabs.removeTab(index)
        self._tabs.insertTab(index, page, name)
        self._tabs.setCurrentIndex(active)
        self._tabs.blockSignals(False)
        old.deleteLater()

    def show_page(self, index):
        self._page_changed(index)
        self._tabs.setCurrentIndex(index)
        self.tool_window.shown = True

    def delete(self):
        if self._controller is not None:
            self._controller.delete()
        super().delete()

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
                "Hit number, e.g. 1"
            )
        else:
            self._directory_label.setText("Folder")
            self._directory_entry.setPlaceholderText("Choose an AF2 or AF3 output folder")
            self._filter_label.setText("Filter")
            self._prediction_filter_entry.setPlaceholderText(
                "Optional filename filter"
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
        if self._controller is None:
            self._controller = AFDisplayController(self.session, workspace=self)
            self._install_page(1, self._controller.page, "Inspect")
        return self._controller


class _WorkspacePanel:
    """Behavior owned by the workspace, without registering another tool/window."""
    def __init__(self, session, workspace):
        self.session = session
        self.workspace = workspace
        self.tool_window = workspace.tool_window


class HTColabFoldPicker(_WorkspacePanel):
    def __init__(self, session, workspace):
        super().__init__(session, workspace)
        self._plot_path = None
        self._plot_html = ""
        self._hits = ()
        self._opened_hit_ids = set()
        from .ui import build_picker
        build_picker(self)

    @classmethod
    def get_singleton(cls, session, create=True, display=False):
        workspace = AFPredictionLauncher.get_singleton(session, create=create)
        if workspace is None:
            return None
        if not create and workspace._picker is None:
            return None
        workspace._page_changed(2)
        if display:
            workspace.show_page(2)
        return workspace._picker

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


class AFDisplayController(_WorkspacePanel):
    SESSION_SAVE = False

    def __init__(self, session, workspace):
        super().__init__(session, workspace)
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
        from Qt.QtCore import QTimer
        self._preview_timer = QTimer(workspace.tool_window.ui_area)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(100)
        self._preview_timer.timeout.connect(self._preview_current_confidence)
        from .ui import build_controller
        build_controller(self)

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
        self.workspace.show_page(1)

    def delete(self):
        self._deleted = True
        self._preview_timer.stop()
        self._remove_selection_sync_handler()
        for run in self._runs:
            plot = run.get("pae_plot")
            if plot is not None and not _plot_closed(plot):
                plot.delete()

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
        self._previous_button.setEnabled(len(pairs) > 1)
        self._next_button.setEnabled(len(pairs) > 1)
        self._pair_slider.setEnabled(len(pairs) > 1 and not self._show_all.isChecked())
        self._pair_menu.setEnabled(bool(pairs))
        self._show_all.setEnabled(bool(pairs))
        self._inspect_tabs.setEnabled(bool(pairs))
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
            plot = create_pae_plot(self.session, pae, stack=self._pae_stack)
            run["pae_plot"] = plot
        elif getattr(plot, "_pae", None) is not pae:
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
            self._preview_timer.start()

    def _plddt_threshold(self):
        return float(self._plddt_threshold_slider.value())

    def _plddt_threshold_changed(self, value):
        self._plddt_threshold_value_label.setText(str(value))
        if self._confidence_mode() == "plddt":
            self._preview_timer.start()

    def _preview_current_confidence(self):
        if self._confidence_mode() == "pae":
            self._preview_low_pae_residues()
        else:
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
        self._pae_panel.setVisible(mode == "pae")
        self._plddt_panel.setVisible(mode == "plddt")
        self._contacts_toggle.setVisible(mode == "pae")
        self._contacts_panel.setVisible(mode == "pae" and self._contacts_toggle.isChecked())

    def _preview_low_pae_residues(self, *_args):
        self._preview_timer.stop()
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
        if not live:
            self._clear_current_pae_highlight()
            self._preview_count = None
            self._update_status_strip()
            return
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
        self._preview_timer.stop()
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
        if not live:
            self._plddt_preview_count = None
            self._update_status_strip()
            return
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
        self._preview_timer.stop()
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
        self._sync_controls()

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
        pair = self._current_pair()
        if pair is None:
            self._status_label.setText("Open predictions to begin.")
            self._status_label.setToolTip(self._last_action)
            return
        mode = self._confidence_mode()
        cutoff = f"PAE < {self._pae_threshold():g}" if mode == "pae" else f"pLDDT ≥ {self._plddt_threshold():g}"
        count = self._preview_count if mode == "pae" else self._plddt_preview_count
        if self._sync_pae_to_selection.isChecked():
            count = self._selection_sync_count
        status = cutoff
        if count is not None:
            status += f" · {count} residues"
        warning = _confidence_warning(self._current_pairs())
        if warning:
            status += f" · {warning}"
        self._status_label.setText(status + "\n" + _compact_status_text(self._last_action, limit=46))
        self._status_label.setToolTip(self._last_action)


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


class AFMissenseTool(_WorkspacePanel):
    SESSION_SAVE = False

    def __init__(self, session, workspace):
        super().__init__(session, workspace)
        self._last_missense_targets = []
        self._last_missense_attr = "amiss_avg"
        from .ui import build_missense
        build_missense(self)

    @classmethod
    def get_singleton(cls, session, create=True, display=False):
        workspace = AFPredictionLauncher.get_singleton(session, create=create)
        if workspace is None:
            return None
        if not create and workspace._missense is None:
            return None
        workspace._page_changed(3)
        if display:
            workspace.show_page(3)
        return workspace._missense

    def _refresh_selection(self):
        summary = selected_chain_summary(self.session)
        if not selected_chain_target(self.session)["chain_id"]:
            self._selection_label.setText("Select a target structure, or use the only open one.")
        else:
            self._selection_label.setText(summary)
        self._selection_label.setToolTip(summary)

    def _fill_from_selection(self):
        target = selected_chain_target(self.session)
        self._model_id_entry.setText(target["model_id"])
        self._chain_id_entry.setText(target["chain_id"])
        self._refresh_selection()

    def _set_advanced_visible(self, visible):
        self._advanced_widget.setVisible(visible)
        self._advanced_toggle.setArrowType(
            self._qt_down_arrow() if visible else self._qt_right_arrow()
        )

    def _qt_down_arrow(self):
        from Qt.QtCore import Qt

        return Qt.DownArrow

    def _qt_right_arrow(self):
        from Qt.QtCore import Qt

        return Qt.RightArrow

    def _apply_mapping(self):
        result = apply_missense_scores(
            self.session,
            self._uniprot_entry.text().strip(),
            model_id=self._model_id_entry.text().strip(),
            chain_id=self._chain_id_entry.text().strip(),
            label_residues=self._label_checkbox.isChecked(),
            show_color_key=self._color_key_checkbox.isChecked(),
            color_range=self._color_range(),
        )
        self._store_missense_targets(result)
        self._refresh_selection()
        labels_text = "yes" if result["labels_added"] else "no"
        key_text = "yes" if result.get("color_key_shown") else "no"
        range_min, range_max = result["color_range"]
        self._result_label.setText(
            f"Mapped {result['uniprot_id']} onto {result['chain_label']}.\n"
            f"Residue labels: {labels_text}\n"
            f"Color key: {key_text}\n"
            f"Color range: {range_min:g} to {range_max:g}\n"
            "The temporary AlphaMissense data set was closed after mapping."
        )

    def _auto_map_missense_to_all_chains(self):
        result = apply_missense_scores_to_structure(
            self.session,
            "",
            model_id=self._model_id_entry.text().strip(),
            label_residues=self._label_checkbox.isChecked(),
            show_color_key=self._color_key_checkbox.isChecked(),
            color_range=self._color_range(),
        )
        self._show_all_chain_mapping_result(result)

    def _apply_mapping_to_all_chains(self):
        result = apply_missense_scores_to_structure(
            self.session,
            self._uniprot_entry.text().strip(),
            model_id=self._model_id_entry.text().strip(),
            label_residues=self._label_checkbox.isChecked(),
            show_color_key=self._color_key_checkbox.isChecked(),
            color_range=self._color_range(),
        )
        self._show_all_chain_mapping_result(result)

    def _show_all_chain_mapping_result(self, result):
        self._store_missense_targets(result)
        self._refresh_selection()
        labels_text = "yes" if result["labels_added"] else "no"
        key_text = "yes" if result.get("color_key_shown") else "no"
        range_min, range_max = result["color_range"]
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
            f"Color range: {range_min:g} to {range_max:g}\n"
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

    def _color_range(self):
        return (self._range_min_spin.value(), self._range_max_spin.value())

    def _store_missense_targets(self, result):
        self._last_missense_targets = list(result.get("target_specs") or [])
        self._last_missense_attr = result.get("attribute_name") or "amiss_avg"

    def _update_color_range(self):
        apply_missense_coloring(
            self.session,
            self._last_missense_targets,
            attr_name=self._last_missense_attr,
            color_range=self._color_range(),
            show_color_key=self._color_key_checkbox.isChecked(),
        )
        range_min, range_max = self._color_range()
        self._result_label.setText(
            "Updated AlphaMissense coloring for the last mapped chain(s).\n"
            f"Color range: {range_min:g} to {range_max:g}\n"
            "No AlphaMissense scores were fetched again."
        )
