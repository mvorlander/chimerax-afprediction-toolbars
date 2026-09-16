"""Array equivalence: python3 tests/smoke_test_performance.py.

Native checks/benchmarks: ChimeraX --exit --script tests/smoke_test_performance.py.
Optional AF_PERF_BASELINE points to the previous workflow.py for before/after timing.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


arrays = load_module("af_performance_arrays", ROOT / "src" / "performance.py")


def array_checks():
    rng = np.random.default_rng(42)
    for size in (0, 1, 9, 131):
        chains = rng.integers(-1, 4, size=size)
        matrix = rng.integers(0, 31, size=(size, size)).astype(np.float32)
        if size > 1:
            matrix[0, 0] = np.nan
            matrix[0, 1] = np.inf
        for pair in (None, (0, 2), (3, 0), (1, 1), (-2, 0)):
            for cutoff in (0, 10, 10.0000001, 31):
                expected = np.zeros((size, size), dtype=bool)
                for i in range(size):
                    for j in range(size):
                        a, b = chains[i], chains[j]
                        if a >= 0 and b >= 0 and a != b and (
                            pair is None or (a, b) in (pair, pair[::-1])
                        ):
                            expected[i, j] = float(matrix[i, j]) < cutoff
                endpoints = expected.any(axis=0) | expected.any(axis=1)
                for include in (True, False):
                    selected, cells = arrays.interchain_mask(matrix, chains, cutoff, pair, include)
                    np.testing.assert_array_equal(selected, endpoints)
                    if include:
                        np.testing.assert_array_equal(cells, expected)
                    else:
                        assert cells is None
        selected = rng.random(size) < 0.3
        selected[chains < 0] = False
        for interchain in (True, False):
            cells, emphasis = arrays.selection_masks(selected, chains, interchain)
            expected = np.zeros((size, size), dtype=bool)
            strong = expected.copy()
            for i in np.flatnonzero(selected):
                for j in range(size):
                    if interchain and (chains[j] < 0 or chains[i] == chains[j]):
                        continue
                    expected[i, j] = expected[j, i] = True
                    if selected[j]:
                        strong[i, j] = strong[j, i] = True
            np.testing.assert_array_equal(cells, expected)
            np.testing.assert_array_equal(emphasis, strong)
            pixels = arrays.overlay_indices(cells, emphasis)
            np.testing.assert_array_equal(pixels != 0, cells)
            np.testing.assert_array_equal(pixels >= 3, emphasis)


def native_checks(session):
    from src import workflow as current
    from src import missense
    from chimerax.atomic import AtomicStructure, Element, Residue, Residues
    from chimerax.alphafold.pae import AlphaFoldPAE
    from chimerax.core.commands import run
    from chimerax.label.label3d import labels_model, label_delete
    from chimerax.core.objects import Objects
    from Qt.QtWidgets import QGraphicsView, QGraphicsScene
    baseline_path = os.environ.get("AF_PERF_BASELINE")
    previous = load_module("af_workflow_baseline", baseline_path) if baseline_path else None
    measurements = {}

    def timed(name, operation):
        start = time.perf_counter()
        result = operation()
        measurements[name] = round(time.perf_counter() - start, 6)
        return result

    model = AtomicStructure(session)
    model.name = "AF performance fixture"
    session.models.add([model])
    count = 3000
    for i in range(count):
        residue = model.new_residue("ALA", ("A", "DX", "L1", "B")[i // 750], i % 750 + 1)
        last = None
        for j, name in enumerate(("N", "CA", "C", "O", "CB")):
            atom = model.new_atom(name, Element.get_element(name[0]))
            residue.add_atom(atom)
            atom.coord = (i * 3.8 + j * 0.4, i // 750 * 8, j * 0.1)
            atom.bfactor = 40 + i % 60
            if last is not None:
                model.new_bond(last, atom)
            last = atom
    residues = list(model.residues)
    rng = np.random.default_rng(19)
    # Interleave chains in the PAE rows; never assume one contiguous block per chain.
    rows = residues[::3]
    rng.shuffle(rows)
    matrix = rng.uniform(0, 30, (len(rows), len(rows))).astype(np.float32)
    pae = SimpleNamespace(structure=model, pae_matrix=matrix, row_residues_or_atoms=lambda: rows)
    new_residues, mask = timed("pae_filter_new", lambda: current._interchain_pae_filter(pae, 10))
    if previous:
        old_residues, cells = timed("pae_filter_before", lambda: previous._interchain_pae_filter(pae, 10))
        assert old_residues == new_residues
        assert cells == set(zip(*np.nonzero(mask)))
        del cells
    timed("pae_filter_no_overlay", lambda: current._interchain_pae_filter(pae, 10, include_cells=False))
    for scope in (("DX", "A"), ("missing", "A")):
        found, mask = current._interchain_pae_filter(pae, 10, scope)
        if previous:
            expected, cells = previous._interchain_pae_filter(pae, 10, scope)
            assert expected == found and cells == set(zip(*np.nonzero(mask)))

    group = model.pseudobond_group("benchmark contacts")
    for i in range(600):
        group.new_pseudobond(residues[i].find_atom("CA"), residues[750 + i].find_atom("CA"))
    outside = Residues(residues[::2])
    keep = Residues(residues[1::2])
    def reset():
        model.atoms.displays = True
        model.residues.ribbon_displays = True
        model.bonds.displays = True
        group.pseudobonds.displays = True
    def flags():
        return [model.atoms.displays.copy(), model.residues.ribbon_displays.copy(),
                model.bonds.displays.copy(), group.pseudobonds.displays.copy()]
    for action in ("_hide_unselected_residue_display", "_show_only_residue_cartoons"):
        reset()
        timed(action + "_new", lambda: getattr(current, action)(session, model, keep))
        actual = flags()
        if previous:
            reset()
            timed(action + "_before", lambda: getattr(previous, action)(session, model, keep))
            for a, b in zip(actual, flags()):
                np.testing.assert_array_equal(a, b)
    timed("selection_new", lambda: current._select_residues(session, keep))
    selected = model.atoms.selected.copy()
    if previous:
        timed("selection_before", lambda: previous._select_residues(session, keep))
        np.testing.assert_array_equal(selected, model.atoms.selected)

    view = QGraphicsView()
    scene = QGraphicsScene(view)
    view.setScene(scene)
    plot = SimpleNamespace(_pae_view=view, closed=lambda: False)
    _, mask = current._interchain_pae_filter(pae, 10)
    timed("overlay_new", lambda: current.highlight_pae_cells(plot, mask))
    assert len(plot._af_toolbar_highlight_items) == 1
    assert plot._af_toolbar_highlight_items[0].pixmap().width() == len(rows)
    current.clear_pae_highlight(plot)
    # Benchmark the fragmented overlay at 400 rows, avoiding millions of old scene items.
    small = mask[:400, :400]
    if previous:
        cells = set(zip(*np.nonzero(small)))
        timed("overlay_400_before", lambda: previous.highlight_pae_cells(plot, cells))
        measurements["overlay_400_items_before"] = len(plot._af_toolbar_highlight_items)
        previous.clear_pae_highlight(plot)
    timed("overlay_400_new", lambda: current.highlight_pae_cells(plot, small))
    current.clear_pae_highlight(plot)

    # Native domain algorithm/data are unchanged; compare exact atom/ribbon colors.
    colors = np.array([[20, 50, 100, 255], [200, 90, 30, 255]], dtype=np.uint8)
    domain = SimpleNamespace(structure=model, _clusters=[list(range(0, count, 2)), list(range(1, count, 2))],
                             _cluster_colors=colors, row_residues_or_atoms=lambda: residues,
                             residues_or_atoms_deleted=lambda: False,
                             set_default_domain_clustering=lambda *args: None)
    timed("domain_colors_before", lambda: AlphaFoldPAE.color_domains(domain, log_command=True))
    atom_colors, ribbon_colors = model.atoms.colors.copy(), model.residues.ribbon_colors.copy()
    timed("domain_colors_new", lambda: current.color_pae_domains(domain))
    np.testing.assert_array_equal(atom_colors, model.atoms.colors)
    np.testing.assert_array_equal(ribbon_colors, model.residues.ribbon_colors)

    # PAE labels retain their individual values/colors after batching.
    model.alphafold_pae = SimpleNamespace(value=lambda a, b:
        (getattr(a, "residue", a).number + getattr(b, "residue", b).number) / 100)
    if previous:
        n = timed("labels_before", lambda: previous._label_contact_pseudobonds(session, model, group.name))
        assert n == 600, n
        expected = [(label.text, label.color) for label in labels_model(group).labels(group.pseudobonds)]
        assert n == 600
        label_delete(session, Objects(pseudobonds=group.pseudobonds), object_type="pseudobonds")
    n = timed("labels_new", lambda: current._label_contact_pseudobonds(session, model, group.name))
    assert n == 600
    actual = [(label.text, label.color) for label in labels_model(group).labels(group.pseudobonds)]
    if previous:
        assert expected == actual

    Residue.register_attr(session, "amiss_avg", "AF benchmark", attr_type=float)
    for i, residue in enumerate(residues):
        residue.amiss_avg = (i % 99) / 100
    specs = [f"#{model.id_string}/{chain}" for chain in ("A", "DX", "L1", "B")]
    def legacy_colors():
        for spec in specs:
            run(session, f"color byattribute r:amiss_avg {spec} target csab palette bluered range 0.1,0.7")
            run(session, f"cartoon byattribute r:amiss_avg {spec}")
    timed("missense_colors_before", legacy_colors)
    atom_colors, ribbon_colors = model.atoms.colors.copy(), model.residues.ribbon_colors.copy()
    timed("missense_colors_new", lambda: missense.apply_missense_coloring(
        session, specs, color_range=(0.1, 0.7), show_color_key=False))
    np.testing.assert_array_equal(atom_colors, model.atoms.colors)
    np.testing.assert_array_equal(ribbon_colors, model.residues.ribbon_colors)
    measurements["fixture"] = {"residues": count, "atoms": len(model.atoms), "pae_rows": len(rows)}
    session.models.close([model])
    return measurements


if "session" in globals():
    output = Path(os.environ.get("AF_PERF_OUTPUT", "/tmp/af-performance-results.json"))
    try:
        array_checks()
        results = native_checks(session)
        results["status"] = "PASS"
    except Exception:
        results = {"status": "FAIL", "traceback": traceback.format_exc()}
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
else:
    array_checks()
    print("Confidence masks and overlay coverage match the reference implementation.")
