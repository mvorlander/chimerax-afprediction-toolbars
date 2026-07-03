#!/usr/bin/env python3
from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _install_chimerax_stubs() -> None:
    chimerax = types.ModuleType("chimerax")
    core = types.ModuleType("chimerax.core")
    commands = types.ModuleType("chimerax.core.commands")
    errors = types.ModuleType("chimerax.core.errors")

    class UserError(Exception):
        pass

    commands.quote_if_necessary = lambda text: f'"{text}"' if " " in str(text) else str(text)
    commands.run = lambda *_args, **_kwargs: None
    errors.UserError = UserError

    sys.modules.setdefault("chimerax", chimerax)
    sys.modules.setdefault("chimerax.core", core)
    sys.modules.setdefault("chimerax.core.commands", commands)
    sys.modules.setdefault("chimerax.core.errors", errors)


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _assert_labels(pairs, expected) -> None:
    labels = [pair.label for pair in pairs]
    if labels != expected:
        raise AssertionError(f"expected labels {expected!r}, got {labels!r}")


def _assert_scores(pairs, expected) -> None:
    scores = [pair.confidence_score for pair in pairs]
    if scores != expected:
        raise AssertionError(f"expected scores {expected!r}, got {scores!r}")


def main() -> int:
    _install_chimerax_stubs()

    workflow_path = REPO_ROOT / "src" / "workflow.py"
    spec = importlib.util.spec_from_file_location("af_toolbar_workflow_smoke", workflow_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load workflow module from {workflow_path}")
    workflow = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = workflow
    spec.loader.exec_module(workflow)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        af3 = root / "fold_2026_05_13_test"
        for model_id in range(3):
            _write(af3 / f"fold_test_model_{model_id}.cif", "data_test\n")
            _write(
                af3 / f"fold_test_full_data_{model_id}.json",
                json.dumps({"pae": [[0, 1], [1, 0]]}),
            )

        _assert_labels(
            workflow._pairs_for_mode(af3, "af3-all", ""),
            ["model_0", "model_1", "model_2"],
        )
        _assert_labels(workflow._pairs_for_mode(af3, "af3-top", ""), ["model_0"])

        af3_scored = root / "fold_2026_05_13_scored"
        for model_id, score in ((0, 0.63), (1, 0.91), (2, 0.72)):
            _write(af3_scored / f"fold_test_model_{model_id}.cif", "data_test\n")
            _write(
                af3_scored / f"fold_test_full_data_{model_id}.json",
                json.dumps({"pae": [[0, 1], [1, 0]]}),
            )
            _write(
                af3_scored / f"fold_test_summary_confidences_{model_id}.json",
                json.dumps({"ranking_score": score}),
            )

        scored_all = workflow._pairs_for_mode(af3_scored, "af3-all", "")
        _assert_labels(scored_all, ["model_1", "model_2", "model_0"])
        _assert_scores(scored_all, [0.91, 0.72, 0.63])
        _assert_labels(workflow._pairs_for_mode(af3_scored, "af3-top", ""), ["model_1"])

        af3_partial_scores = root / "fold_2026_05_13_partial_scores"
        for model_id in range(3):
            _write(af3_partial_scores / f"fold_test_model_{model_id}.cif", "data_test\n")
            _write(
                af3_partial_scores / f"fold_test_full_data_{model_id}.json",
                json.dumps({"pae": [[0, 1], [1, 0]]}),
            )
        _write(
            af3_partial_scores / "fold_test_summary_confidences_2.json",
            json.dumps({"ranking_score": 0.88}),
        )

        partial_all = workflow._pairs_for_mode(af3_partial_scores, "af3-all", "")
        _assert_labels(partial_all, ["model_2", "model_0", "model_1"])
        missing_flags = [pair.confidence_missing for pair in partial_all]
        if missing_flags != [False, True, True]:
            raise AssertionError(f"unexpected confidence-missing flags {missing_flags!r}")

        af2 = root / "af2_test"
        for rank in (1, 2, 3):
            _write(af2 / "pdb" / f"job_rank_{rank}_model.pdb", "HEADER test\n")
            _write(af2 / "json" / f"job_rank_{rank}_model.json", "{}\n")

        _assert_labels(
            workflow._pairs_for_mode(af2, "af2-all", ""),
            ["rank_1", "rank_2", "rank_3"],
        )
        _assert_labels(workflow._pairs_for_mode(af2, "af2-top", ""), ["rank_1"])

        htcf = root / "ht_colabfold_screen"
        _write(
            htcf / "IPTM_vs_PTM.txt",
            "\t".join(
                [
                    "NAME",
                    "IPTM",
                    "PTM",
                    "IPTMavg",
                    "PTMavg",
                    "RATIO",
                    "PEAK",
                    "PEAKavg",
                    "scaled_PEAK",
                    "scaled_PEAKavg",
                ]
            )
            + "\n"
            + "\t".join(
                [
                    ">1_sp-O75391-SPAG7_HUMAN_vs_sp-O00267-SPT5H_HUMAN",
                    "0.52:0.47:0.44:0.41:0.40",
                    "0.31:0.30:0.29:0.28:0.27",
                    "0.448",
                    "0.29",
                    "1.54",
                    "2.1:2.2:2.3:2.4:2.5",
                    "2.3",
                    "0.91:0.90:0.89:0.88:0.87",
                    "0.912",
                ]
            )
            + "\n",
        )
        for rank in range(1, 6):
            stem = f"1_sp-O75391-SPAG7_HUMAN_vs_sp-O00267-SPT5H_HUMAN_unrelaxed_rank_{rank}"
            _write(htcf / "pdb" / f"{stem}.pdb", "HEADER test\n")
            _write(htcf / "json" / f"{stem}.json", json.dumps({"pae": [[0, 1], [1, 0]]}))
        for rank in (1, 2):
            stem = f"10_sp-test_vs_sp-other_unrelaxed_rank_{rank}"
            _write(htcf / "pdb" / f"{stem}.pdb", "HEADER test\n")
            _write(htcf / "json" / f"{stem}.json", "{}\n")

        htcf_all = workflow._pairs_for_mode(htcf, "htcf-all", "1")
        _assert_labels(
            htcf_all,
            [
                "hit_1_rank_1",
                "hit_1_rank_2",
                "hit_1_rank_3",
                "hit_1_rank_4",
                "hit_1_rank_5",
            ],
        )
        _assert_scores(htcf_all, [0.52, 0.47, 0.44, 0.41, 0.4])
        _assert_labels(workflow._pairs_for_mode(htcf, "htcf-top", "1"), ["hit_1_rank_1"])
        _assert_labels(
            workflow._pairs_for_mode(htcf, "htcf-all", "10"),
            ["hit_10_rank_1", "hit_10_rank_2"],
        )
        hits = workflow.ht_colabfold_screen_hits(htcf)
        if len(hits) != 1 or hits[0]["hit_id"] != "1":
            raise AssertionError(f"unexpected parsed HT-ColabFold hits: {hits!r}")
        if hits[0]["scaled_peakavg"] != 0.912:
            raise AssertionError(f"unexpected parsed PEAK score: {hits[0]!r}")
        plot_path, plot_hits = workflow.write_ht_colabfold_peak_iptm_plot(htcf)
        if not plot_path.is_file():
            raise AssertionError(f"expected generated plot at {plot_path}")
        plot_html = plot_path.read_text(encoding="utf-8")
        if 'href="#hit-1"' not in plot_html or "scaled_PEAKavg" not in plot_html:
            raise AssertionError("generated HT-ColabFold picker plot is missing click targets")
        if plot_hits != hits:
            raise AssertionError("plot hit metadata should match parsed screen hits")
        plot_path, _plot_hits = workflow.write_ht_colabfold_peak_iptm_plot(
            htcf, opened_hit_ids={"1"}
        )
        opened_html = plot_path.read_text(encoding="utf-8")
        if "viewed-row" not in opened_html or ">opened</td>" not in opened_html:
            raise AssertionError("generated HT-ColabFold picker plot should mark opened hits")

        try:
            workflow._pairs_for_mode(htcf, "htcf-all", "")
        except Exception as err:
            if "Enter an HT-ColabFold hit id" not in str(err):
                raise AssertionError(f"unexpected empty hit-id error: {err}") from err
        else:
            raise AssertionError("empty HT-ColabFold hit id should fail")

        htcf_missing_json = root / "ht_colabfold_missing_json"
        _write(
            htcf_missing_json
            / "pdb"
            / "2_sp-O75391-SPAG7_HUMAN_vs_sp-O00267-SPT5H_HUMAN_unrelaxed_rank_1.pdb",
            "HEADER test\n",
        )
        try:
            workflow._pairs_for_mode(htcf_missing_json, "htcf-top", "2")
        except Exception as err:
            if "no matching archived JSON PAE files" not in str(err):
                raise AssertionError(f"unexpected missing-json error: {err}") from err
        else:
            raise AssertionError("HT-ColabFold hit with PDB but no JSON should fail")

        output_dir = workflow._make_output_dir(af3, "af3-all", "")
        expected_output = af3 / "analysis" / af3.name / "af3-all"
        if output_dir != expected_output:
            raise AssertionError(f"expected output dir {expected_output}, got {output_dir}")

        filtered_output = workflow._make_output_dir(af3, "af3-top", "fold_test")
        expected_filtered = af3 / "analysis" / "fold_test" / "af3-top"
        if filtered_output != expected_filtered:
            raise AssertionError(
                f"expected filtered output dir {expected_filtered}, got {filtered_output}"
            )

    print("AF2/AF3/HT-ColabFold discovery smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
