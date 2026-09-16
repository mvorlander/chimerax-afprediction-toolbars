"""Run in a fresh GUI ChimeraX: ChimeraX --exit --script tests/smoke_test_ui.py.

Exercises real Qt sizing, shared tool lifecycle, native PAE, and run switching.
Results/screenshots go to AF_UI_TEST_OUTPUT (default /tmp/af-ui-test).
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

from Qt.QtWidgets import QApplication, QScrollArea, QToolButton

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT = Path(os.environ.get("AF_UI_TEST_OUTPUT", "/tmp/af-ui-test"))
OUTPUT.mkdir(parents=True, exist_ok=True)


def fixture(directory):
    for rank in (1, 2):
        pdb = directory / "pdb" / f"sample_rank_{rank}_model_{rank}.pdb"
        pdb.parent.mkdir(exist_ok=True)
        lines = []
        serial = 0
        for chain_index, chain in enumerate("AB"):
            for residue in range(1, 5):
                for name, dx, dy, element in (("N", 0, 0, "N"), ("CA", 1.2, 0, "C"),
                                              ("C", 2.4, 0, "C"), ("O", 2.6, 1, "O"),
                                              ("CB", 1.2, 1.4, "C")):
                    serial += 1
                    x, y, z = residue * 3.8 + dx, chain_index * 5 + dy, rank * 0.1
                    lines.append(f"ATOM  {serial:5d} {name:^4s} ALA {chain}{residue:4d}    "
                                 f"{x:8.3f}{y:8.3f}{z:8.3f}{1:6.2f}{90:6.2f}          {element:>2s}\n")
            lines.append("TER\n")
        pdb.write_text("".join(lines) + "END\n")
        data = directory / "json" / f"sample_rank_{rank}_model_{rank}.json"
        data.parent.mkdir(exist_ok=True)
        data.write_text(json.dumps({"pae": [[0 if i == j else 5 for j in range(8)] for i in range(8)],
                                    "plddt": [90] * 8, "iptm": 0.9 - rank * 0.1}))


def exercise():
    report = []
    try:
        from src import bundle_api
        from src.tool import AFPredictionLauncher, AFMissenseTool, HTColabFoldPicker
        from src.workflow import run_af_prediction_analysis
        workspace = AFPredictionLauncher.get_singleton(session, create=True, display=True)
        workspace.tool_window.floating = True
        window = workspace.tool_window.ui_area.window()
        window.resize(340, 560)
        for index in range(4):
            workspace.show_page(index)
            QApplication.processEvents()
            window.resize(340, 560)
            QApplication.processEvents()
            assert window.width() <= 340, (index, window.size(), window.minimumSizeHint())
            window.grab().save(str(OUTPUT / f"page-{index}.png"))
            report.append(f"Page {index}: {window.width()} × {window.height()}")
        assert AFMissenseTool.get_singleton(session, display=True) is workspace._missense
        assert HTColabFoldPicker.get_singleton(session, display=True) is workspace._picker
        assert workspace._missense.tool_window is workspace.tool_window
        assert workspace._picker.tool_window is workspace.tool_window
        for provider, page in (("af3-all", 0), ("af3-top", 0), ("af2-all", 0),
                               ("af2-top", 0), ("htcf-all", 0), ("htcf-top", 0),
                               ("htcf-picker", 2), ("missense-map", 3)):
            bundle_api.run_provider(session, provider, None)
            assert workspace._tabs.currentIndex() == page
            assert len(session.tools.find_by_class(AFPredictionLauncher)) == 1
        for index in range(4):
            workspace.show_page(index)
            for toggle in workspace._tabs.currentWidget().findChildren(QToolButton):
                if toggle.isCheckable():
                    toggle.setChecked(True)
            QApplication.processEvents()
            window.resize(320, 480)
            QApplication.processEvents()
            assert window.width() <= 320
            for scroll in workspace._tabs.currentWidget().findChildren(QScrollArea):
                if scroll.isVisible():
                    assert scroll.widget().width() <= scroll.viewport().width(), (index, scroll.widget().size(), scroll.viewport().size())
            for toggle in workspace._tabs.currentWidget().findChildren(QToolButton):
                if toggle.isCheckable():
                    toggle.setChecked(False)
        controller = workspace._display_controller()
        controller._confidence_mode_menu.setCurrentIndex(1)
        assert controller._pae_panel.isHidden()
        assert not controller._plddt_panel.isHidden()
        controller._confidence_mode_menu.setCurrentIndex(0)
        with tempfile.TemporaryDirectory(prefix="af-ui-fixture-") as tmp:
            directory = Path(tmp)
            fixture(directory)
            for count in range(2):
                result = run_af_prediction_analysis(session, mode="af2-all", directory=directory,
                                                    prediction_filter="", requested_chain=None)
                controller.add_run(result)
                plot = controller._current_run()["pae_plot"]
                view = plot._pae_view
                if count == 0:
                    assert not plot._embedded and plot.tool_window.shown
                    plot.tool_window.ui_area.window().resize(340, 440)
                    QApplication.processEvents()
                    plot.tool_window.ui_area.window().grab().save(str(OUTPUT / "pae-window.png"))
                    plot.set_embedded(True)
                assert plot._embedded and not plot.tool_window.shown
                assert plot._pae_view is view
                assert workspace._tabs.currentIndex() == 1
                assert len(controller._current_pairs()) == 2
                controller._show_next()
                assert controller._current_pair_index == 1
                assert controller._current_run()["pae_plot"]._pae is controller._current_pae()
                controller._inspect_tabs.setCurrentIndex(1)
                QApplication.processEvents()
                window.resize(340, 560)
                QApplication.processEvents()
                assert window.width() <= 340
                window.grab().save(str(OUTPUT / f"pae-run-{count}.png"))
            controller._set_run_index(0)
            assert controller._pae_stack.currentWidget() is controller._runs[0]["pae_plot"]._embedded_page
            assert all(not run["pae_plot"].tool_window.shown for run in controller._runs)
            plot = controller._current_run()["pae_plot"]
            plot.set_embedded(False)
            assert plot.tool_window.shown and not plot._embedded
            assert not controller._runs[1]["pae_plot"].tool_window.shown
            # Closing the separate plot only hides it; the tab can show it again.
            plot.tool_window.ui_area.window().close()
            assert not plot.closed()
            plot.display(True)
            assert plot.tool_window.shown
            plot.set_embedded(True)
            assert controller._inspect_tabs.currentIndex() == 1
            controller._inspect_tabs.setCurrentIndex(0)
            window.resize(340, 560)
            QApplication.processEvents()
            window.grab().save(str(OUTPUT / "workspace-select.png"))
            controller._pae_threshold_slider.setValue(8)
            from Qt.QtCore import QEventLoop, QTimer
            assert controller._preview_timer.isActive()
            wait = QEventLoop()
            QTimer.singleShot(150, wait.quit)
            wait.exec()
            assert not controller._preview_timer.isActive()
            assert controller._preview_count == 8
            controller._sync_pae_to_selection.setChecked(True)
            assert controller._selection_sync_handler is not None
            controller._sync_pae_to_selection.setChecked(False)
            assert controller._selection_sync_handler is None
            # Long prediction names/paths must not widen any tab.
            controller._run_menu.setItemText(0, "very_long_prediction_" * 40)
            for index in range(3):
                controller._inspect_tabs.setCurrentIndex(index)
                QApplication.processEvents()
                window.resize(320, 480)
                QApplication.processEvents()
                assert window.width() <= 320, (index, window.size())
                window.grab().save(str(OUTPUT / f"inspect-{index}.png"))
            controller._close_current_run()
            assert len(controller._runs) == 1
            controller._close_current_run()
            assert not controller._runs
            assert controller._pae_stack.count() == 1
        workspace.tool_window.shown = False
        assert AFPredictionLauncher.get_singleton(session, display=True) is workspace
        workspace.delete()
        QApplication.processEvents()
        report.append("PASS: shared workspace, narrow layouts, native PAE, two runs, selection sync, close/reopen")
        (OUTPUT / "result.txt").write_text("\n".join(report), encoding="utf-8")
    except Exception:
        (OUTPUT / "result.txt").write_text("\n".join(report) + "\n" + traceback.format_exc(), encoding="utf-8")


exercise()
