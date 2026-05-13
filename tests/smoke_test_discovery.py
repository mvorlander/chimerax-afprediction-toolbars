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

        af2 = root / "af2_test"
        for rank in (1, 2, 3):
            _write(af2 / "pdb" / f"job_rank_{rank}_model.pdb", "HEADER test\n")
            _write(af2 / "json" / f"job_rank_{rank}_model.json", "{}\n")

        _assert_labels(
            workflow._pairs_for_mode(af2, "af2-all", ""),
            ["rank_1", "rank_2", "rank_3"],
        )
        _assert_labels(workflow._pairs_for_mode(af2, "af2-top", ""), ["rank_1"])

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

    print("AF2/AF3 discovery smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
