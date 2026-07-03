#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _install_chimerax_stubs(selected=None) -> None:
    chimerax = types.ModuleType("chimerax")
    core = types.ModuleType("chimerax.core")
    commands = types.ModuleType("chimerax.core.commands")
    errors = types.ModuleType("chimerax.core.errors")
    atomic = types.ModuleType("chimerax.atomic")
    mutation_scores = types.ModuleType("chimerax.mutation_scores")
    ms_data = types.ModuleType("chimerax.mutation_scores.ms_data")
    ms_define = types.ModuleType("chimerax.mutation_scores.ms_define")

    class UserError(Exception):
        pass

    commands.quote_if_necessary = lambda text: str(text)
    commands.run = lambda *_args, **_kwargs: None
    errors.UserError = UserError
    atomic.selected_chains = lambda _session: list(selected or [])
    ms_data.mutation_scores_structure = lambda *_args, **_kwargs: None
    ms_define.mutation_scores_define = lambda *_args, **_kwargs: None

    sys.modules.setdefault("chimerax", chimerax)
    sys.modules.setdefault("chimerax.core", core)
    sys.modules.setdefault("chimerax.core.commands", commands)
    sys.modules.setdefault("chimerax.core.errors", errors)
    sys.modules["chimerax.atomic"] = atomic
    sys.modules["chimerax.mutation_scores"] = mutation_scores
    sys.modules["chimerax.mutation_scores.ms_data"] = ms_data
    sys.modules["chimerax.mutation_scores.ms_define"] = ms_define


class Residue:
    def __init__(self, name):
        self.name = name


class Chain:
    def __init__(self, chain_id, residue_names):
        self.chain_id = chain_id
        self.residues = [Residue(name) for name in residue_names]
        self.atomspec = f"/{chain_id}"
        self.structure = None


class Structure:
    def __init__(self, model_id, name, chains):
        self.id = model_id
        self.name = name
        self.chains = chains
        self.atoms = object()
        for chain in chains:
            chain.structure = self


class Models:
    def __init__(self, structures):
        self._structures = structures

    def list(self):
        return list(self._structures)


class Session:
    def __init__(self, structures):
        self.models = Models(structures)


def _load_missense():
    missense_path = REPO_ROOT / "src" / "missense.py"
    spec = importlib.util.spec_from_file_location("af_toolbar_missense_smoke", missense_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load missense module from {missense_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    protein_a = Chain("A", ["ALA", "GLY"])
    protein_b = Chain("B", ["MSE", "LYS"])
    ligand = Chain("L", ["HEM"])
    structure = Structure((1,), "test", [protein_a, protein_b, ligand])

    _install_chimerax_stubs(selected=[protein_a])
    missense = _load_missense()

    session = Session([structure])
    if missense._resolve_structure(session, model_id="1") is not structure:
        raise AssertionError("model-id structure resolution failed")
    if missense._resolve_structure(session, model_id="") is not structure:
        raise AssertionError("selected-structure resolution failed")

    protein_chains = missense._protein_chains(structure)
    if [chain.chain_id for chain in protein_chains] != ["A", "B"]:
        raise AssertionError(f"unexpected protein chains: {protein_chains!r}")

    with tempfile.TemporaryDirectory() as tmp:
        cif_path = Path(tmp) / "test.cif"
        cif_path.write_text(
            """data_test
#
loop_
_struct_ref.id
_struct_ref.db_name
_struct_ref.pdbx_db_accession
_struct_ref.entity_id
_struct_ref.pdbx_seq_one_letter_code
1 UNP P12345 1
;MSTNPKPQR
;
2 UNP Q99999 2
;MAAAAAAAA
;
#
loop_
_struct_ref_seq.align_id
_struct_ref_seq.ref_id
_struct_ref_seq.pdbx_strand_id
1 1 A
2 2 B
#
loop_
_entity_poly.entity_id
_entity_poly.pdbx_strand_id
1 A
2 B
#
""",
            encoding="utf-8",
        )
        structure.filename = str(cif_path)
        mapping = missense._structure_uniprot_map(structure)
        if mapping != {"A": "P12345", "B": "Q99999"}:
            raise AssertionError(f"unexpected UniProt mapping: {mapping!r}")
        if missense._uniprot_id_for_chain(protein_a) != "P12345":
            raise AssertionError("chain A UniProt lookup failed")
        grouped = missense._chains_by_uniprot([protein_a, protein_b, ligand], "")
        if sorted(grouped) != ["P12345", "Q99999"]:
            raise AssertionError(f"unexpected grouped UniProt targets: {grouped!r}")
        override = missense._chains_by_uniprot([protein_a, protein_b], "OVERRIDE")
        if list(override) != ["OVERRIDE"] or len(override["OVERRIDE"]) != 2:
            raise AssertionError(f"UniProt override grouping failed: {override!r}")

    commands_run = []
    missense.run = lambda _session, command: commands_run.append(command)
    missense._map_chain_with_mutation_set(
        session,
        protein_a,
        "amiss_test",
        "amiss_avg",
        show_color_key=True,
    )
    if not any("key true" in command for command in commands_run):
        raise AssertionError(f"missing color-key option in commands: {commands_run!r}")

    commands_run.clear()
    missense._map_chain_with_mutation_set(
        session,
        protein_a,
        "amiss_test",
        "amiss_avg",
        show_color_key=False,
    )
    if any("key true" in command for command in commands_run):
        raise AssertionError(f"color-key option should be omitted: {commands_run!r}")

    print("AlphaMissense target smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
