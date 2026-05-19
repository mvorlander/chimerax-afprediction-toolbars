from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Dict, List, Optional, Pattern, Set, Tuple, Union

from chimerax.core.commands import quote_if_necessary, run
from chimerax.core.errors import UserError


STRUCTURE_EXTENSIONS = {".cif", ".mmcif", ".pdb"}
JSON_EXTENSION = ".json"
CSV_EXTENSION = ".csv"

AF3_STRUCTURE_PATTERNS = [
    re.compile(r"(?:^|[_\-.])model[_\-.]?(\d+)(?:[_\-.]|$)", re.IGNORECASE),
]
AF3_JSON_PATTERNS = [
    re.compile(r"(?:^|[_\-.])full[_\-.]?data[_\-.]?(\d+)(?:[_\-.]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[_\-.])data[_\-.]?(\d+)(?:[_\-.]|$)", re.IGNORECASE),
]
AF2_RANK_PATTERNS = [
    re.compile(r"(?:^|[_\-.])rank[_\-.]?(\d+)(?:[_\-.]|$)", re.IGNORECASE),
]
AF3_SCORE_PATTERNS = [
    re.compile(
        r"(?:summary[_\-.]?confidences|confidences|ranking|scores).*?(\d+)",
        re.IGNORECASE,
    ),
]
AF3_SCORE_KEYS = ("ranking_score", "aggregate_score", "rank_score")
DEFAULT_CONTACT_MAX_PAE = 30.0


@dataclass(frozen=True)
class PredictionPair:
    label: str
    structure_path: Path
    score_path: Path
    confidence_score: Optional[float] = None
    confidence_missing: bool = False


@dataclass(frozen=True)
class AnalysisResult:
    mode: str
    run_label: str
    input_directory: Path
    requested_chain: Optional[str]
    summary: str
    output_dir: Path
    opened_pairs: Tuple[PredictionPair, ...]
    display_pairs: Tuple[Dict[str, object], ...]
    model_group: object = None


def describe_prediction_folder(
    directory: Path, mode: str, prediction_filter: str = ""
) -> str:
    pairs = _pairs_for_mode(directory, mode, prediction_filter)
    lines = [
        f"Mode: {_mode_label(mode)}",
        f"Folder: {directory}",
        f"Detected pairs: {len(pairs)}",
        "",
    ]
    lines.extend(_format_pair(pair, directory) for pair in pairs)
    return "\n".join(lines)


def run_af_prediction_analysis(
    session,
    mode: str,
    directory: Path,
    prediction_filter: str = "",
    requested_chain: Optional[str] = None,
) -> AnalysisResult:
    pairs = _pairs_for_mode(directory, mode, prediction_filter)
    output_dir = _make_output_dir(directory, mode, prediction_filter)
    run_label = _series_title(mode, prediction_filter, directory)
    display_pairs = []
    structures = []
    pair_summaries = []

    for pair in pairs:
        structure_model, pae = _open_pair(session, pair)
        model_spec = _model_spec(structure_model)
        contact_result = _prepare_contact_interface_display(
            session, pair.label, structure_model, requested_chain
        )
        display_pairs.append(
            {
                "label": pair.label,
                "display_label": _pair_display_label(pair),
                "structure_path": pair.structure_path,
                "score_path": pair.score_path,
                "confidence_score": pair.confidence_score,
                "confidence_missing": pair.confidence_missing,
                "contact_pseudobond_name": contact_result.get("contact_pseudobond_name"),
                "contact_residue_name": contact_result["contact_residue_name"],
                "interface_residue_name": contact_result["interface_residue_name"],
                "contact_residues": contact_result.get("contact_residues"),
                "interface_residues": contact_result.get("interface_residues"),
                "contact_labels_visible": contact_result.get(
                    "contact_labels_visible", False
                ),
                "cutoff_interface_residue_name": None,
                "cutoff_interface_residues": None,
                "contact_analysis_files": {},
                "model": structure_model,
                "pae": pae,
            }
        )
        structures.append(structure_model)
        pair_summaries.append(
            {
                "label": pair.label,
                "structure": str(pair.structure_path),
                "score_data": str(pair.score_path),
                "confidence_score": pair.confidence_score,
                "confidence_missing": pair.confidence_missing,
                "contact_analysis": "prepared in ChimeraX; files not written automatically",
                "requested_contact_chain": requested_chain,
                "contact_residue_name": contact_result["contact_residue_name"],
                "interface_residue_name": contact_result["interface_residue_name"],
                "model_spec": model_spec,
            }
        )

    model_group = _group_structures(session, structures, run_label)
    _align_structures(session, structures, requested_chain)
    for display_pair, pair_summary in zip(display_pairs, pair_summaries):
        pair_summary["model_spec"] = _model_spec(display_pair.get("model"))
    _write_analysis_summary(
        output_dir,
        mode=mode,
        run_label=run_label,
        input_directory=directory,
        prediction_filter=prediction_filter,
        requested_chain=requested_chain,
        pairs=pair_summaries,
    )
    _activate_pair(display_pairs, 0)

    summary = (
        f"Opened {len(pairs)} {_mode_label(mode)} pair(s).\n"
        f"Run metadata was written to:\n{output_dir}\n"
        "Contacts/interfaces were prepared for display. Files are written only "
        "when you use 'Save Contacts and Interfaces' for the active model."
    )
    return AnalysisResult(
        mode=mode,
        run_label=run_label,
        input_directory=directory,
        requested_chain=requested_chain,
        summary=summary,
        output_dir=output_dir,
        opened_pairs=tuple(pairs),
        display_pairs=tuple(display_pairs),
        model_group=model_group,
    )


def _pairs_for_mode(
    directory: Path, mode: str, prediction_filter: str
) -> Tuple[PredictionPair, ...]:
    directory = directory.expanduser()
    if not directory.is_dir():
        raise UserError(f"Prediction folder not found: {directory}")

    if mode == "af3-all":
        return tuple(_discover_af3_pairs(directory, prediction_filter, top_only=False))
    if mode == "af3-top":
        return tuple(_discover_af3_pairs(directory, prediction_filter, top_only=True))
    if mode == "af3":
        return tuple(_discover_af3_pairs(directory, prediction_filter, top_only=False))
    if mode == "af2-all":
        return tuple(_discover_af2_pairs(directory, prediction_filter, top_only=False))
    if mode == "af2-top":
        return tuple(_discover_af2_pairs(directory, prediction_filter, top_only=True))
    raise UserError(f"Unknown AF analysis mode: {mode}")


def _discover_af3_pairs(
    directory: Path, prediction_filter: str, top_only: bool
) -> List[PredictionPair]:
    structures = _files_matching(directory, STRUCTURE_EXTENSIONS, prediction_filter)
    score_files = _files_matching(directory, {JSON_EXTENSION}, prediction_filter)

    structures_by_id = _group_by_id(structures, AF3_STRUCTURE_PATTERNS)
    scores_by_id = _group_by_id(score_files, AF3_JSON_PATTERNS)

    if not structures_by_id and len(structures) == 1:
        structures_by_id["single"] = structures
    if not scores_by_id and len(score_files) == 1:
        scores_by_id["single"] = score_files

    missing_scores = sorted(set(structures_by_id) - set(scores_by_id), key=_natural_key)
    missing_structures = sorted(set(scores_by_id) - set(structures_by_id), key=_natural_key)
    if missing_scores or missing_structures:
        details = []
        if missing_scores:
            details.append(f"missing AF3 data JSON for model(s): {', '.join(map(str, missing_scores))}")
        if missing_structures:
            details.append(f"missing AF3 structure file for model(s): {', '.join(map(str, missing_structures))}")
        raise UserError("AF3 files are incomplete: " + "; ".join(details))

    labels = sorted(structures_by_id, key=_natural_key)
    if not labels:
        raise UserError(
            "No AF3 model/data pairs were found. Expected files such as "
            "'model_0.cif' and 'full_data_0.json' or 'data_0.json'."
        )

    score_by_label = _af3_score_by_label(directory, prediction_filter)
    pairs = []
    if top_only:
        labels = [
            _top_af3_model_label(
                directory, labels, prediction_filter, score_by_label=score_by_label
            )
        ]
    elif score_by_label:
        labels = _af3_labels_by_confidence(labels, score_by_label)

    for label in labels:
        structure = _one_file(structures_by_id[label], "AF3 structure", label, directory)
        score = _one_file(scores_by_id[label], "AF3 data JSON", label, directory)
        pairs.append(
            PredictionPair(
                f"model_{label}",
                structure,
                score,
                confidence_score=score_by_label.get(label),
                confidence_missing=bool(score_by_label) and label not in score_by_label,
            )
        )
    return pairs


def _top_af3_model_label(
    directory: Path,
    labels: List[Union[str, int]],
    prediction_filter: str,
    score_by_label: Optional[Dict[Union[str, int], float]] = None,
) -> Union[str, int]:
    if "single" in labels and len(labels) == 1:
        return "single"

    if score_by_label is None:
        score_by_label = _af3_score_by_label(directory, prediction_filter)
    if score_by_label:
        missing_scores = sorted(set(labels) - set(score_by_label), key=_natural_key)
        if missing_scores:
            raise UserError(
                "AF3 top-hit metadata was found for only some models. Missing "
                "ranking scores for model(s): "
                + ", ".join(map(str, missing_scores))
                + ". Use AF3 All Hits, or remove/narrow incomplete score metadata."
            )
        ordered_labels = sorted(labels, key=_natural_key)
        label_order = {label: index for index, label in enumerate(ordered_labels)}
        return max(labels, key=lambda label: (score_by_label[label], -label_order[label]))

    numeric = sorted(label for label in labels if isinstance(label, int))
    if numeric:
        return numeric[0]
    return sorted(labels, key=_natural_key)[0]


def _af3_labels_by_confidence(
    labels: List[Union[str, int]], score_by_label: Dict[Union[str, int], float]
) -> List[Union[str, int]]:
    ordered_labels = sorted(labels, key=_natural_key)
    label_order = {label: index for index, label in enumerate(ordered_labels)}
    return sorted(
        ordered_labels,
        key=lambda label: (
            label not in score_by_label,
            -score_by_label.get(label, 0.0),
            label_order[label],
        ),
    )


def _af3_score_by_label(directory: Path, prediction_filter: str) -> Dict[Union[str, int], float]:
    scores = _af3_score_by_label_from_json(directory, prediction_filter)
    scores.update(_af3_score_by_label_from_csv(directory, prediction_filter))
    return scores


def _af3_score_by_label_from_json(
    directory: Path, prediction_filter: str
) -> Dict[Union[str, int], float]:
    score_files = _files_matching(directory, {JSON_EXTENSION}, prediction_filter)
    score_files_by_id = _group_by_id(score_files, AF3_SCORE_PATTERNS)
    scores: Dict[Union[str, int], float] = {}

    for label, files in score_files_by_id.items():
        scored_files = []
        for path in files:
            score = _score_from_json_file(path)
            if score is not None:
                scored_files.append((path, score))
        if len(scored_files) > 1:
            rel_paths = "\n".join(f"  - {_relative(path, directory)}" for path, _score in scored_files)
            raise UserError(
                f"Found multiple AF3 ranking JSON files for model {label}; "
                f"add a more specific name/filter.\n{rel_paths}"
            )
        if scored_files:
            scores[label] = scored_files[0][1]
    return scores


def _af3_score_by_label_from_csv(
    directory: Path, prediction_filter: str
) -> Dict[Union[str, int], float]:
    csv_files = [
        path
        for path in _files_matching(directory, {CSV_EXTENSION}, prediction_filter)
        if any(term in path.name.casefold() for term in ("rank", "score", "confidence"))
    ]
    scores: Dict[Union[str, int], float] = {}
    for path in csv_files:
        scores.update(_scores_from_csv_file(path))
    return scores


def _discover_af2_pairs(
    directory: Path, prediction_filter: str, top_only: bool
) -> List[PredictionPair]:
    structure_roots = _preferred_roots(directory, "pdb", "structures")
    json_roots = _preferred_roots(directory, "json", "scores")
    structures = _files_matching_many(structure_roots, STRUCTURE_EXTENSIONS, prediction_filter)
    score_files = _files_matching_many(json_roots, {JSON_EXTENSION}, prediction_filter)

    structures_by_rank = _group_by_id(structures, AF2_RANK_PATTERNS)
    scores_by_rank = _group_by_id(score_files, AF2_RANK_PATTERNS)

    if not structures_by_rank and len(structures) == 1:
        structures_by_rank["unranked"] = structures
    if not scores_by_rank and len(score_files) == 1:
        scores_by_rank["unranked"] = score_files

    missing_scores = sorted(set(structures_by_rank) - set(scores_by_rank), key=_natural_key)
    missing_structures = sorted(set(scores_by_rank) - set(structures_by_rank), key=_natural_key)
    if missing_scores or missing_structures:
        details = []
        if missing_scores:
            details.append(f"missing AF2 JSON for rank(s): {', '.join(map(str, missing_scores))}")
        if missing_structures:
            details.append(f"missing AF2 structure for rank(s): {', '.join(map(str, missing_structures))}")
        raise UserError("AF2 files are incomplete: " + "; ".join(details))

    ranks = sorted(structures_by_rank, key=_natural_key)
    if not ranks:
        raise UserError(
            "No AF2 structure/JSON pairs were found. Expected ranked files such as "
            "'rank_1.pdb' and 'rank_1.json', commonly under pdb/ and json/ folders."
        )
    if top_only:
        ranks = [_top_rank(ranks)]

    pairs = []
    for rank in ranks:
        structure = _one_file(structures_by_rank[rank], "AF2 structure", rank, directory)
        score = _one_file(scores_by_rank[rank], "AF2 JSON", rank, directory)
        pairs.append(PredictionPair(f"rank_{rank}", structure, score))
    return pairs


def _files_matching(root: Path, extensions: Set[str], prediction_filter: str) -> List[Path]:
    return _files_matching_many([root], extensions, prediction_filter)


def _files_matching_many(
    roots: List[Path], extensions: Set[str], prediction_filter: str
) -> List[Path]:
    needle = prediction_filter.casefold()
    files = []
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.casefold() not in extensions:
                continue
            key = path.resolve()
            if key in seen:
                continue
            if needle and needle not in str(path).casefold():
                continue
            seen.add(key)
            files.append(path)
    return sorted(files, key=lambda path: _natural_key(str(path)))


def _preferred_roots(directory: Path, *names: str) -> List[Path]:
    roots = [directory / name for name in names if (directory / name).is_dir()]
    return roots or [directory]


def _group_by_id(
    files: List[Path], patterns: List[Pattern]
) -> Dict[Union[str, int], List[Path]]:
    grouped: Dict[Union[str, int], List[Path]] = {}
    for path in files:
        identifier = _extract_identifier(path.name, patterns)
        if identifier is None:
            continue
        grouped.setdefault(identifier, []).append(path)
    return grouped


def _extract_identifier(name: str, patterns: List[Pattern]) -> Optional[int]:
    for pattern in patterns:
        match = pattern.search(name)
        if match:
            return int(match.group(1))
    return None


def _one_file(files: List[Path], kind: str, label: Union[str, int], root: Path) -> Path:
    if len(files) == 1:
        return files[0]

    rel_paths = "\n".join(f"  - {_relative(path, root)}" for path in files[:8])
    if len(files) > 8:
        rel_paths += f"\n  - ... {len(files) - 8} more"
    raise UserError(
        f"Found {len(files)} {kind} candidates for {label}; add a more specific "
        f"name/filter.\n{rel_paths}"
    )


def _top_rank(ranks: List[Union[str, int]]) -> Union[str, int]:
    if "unranked" in ranks and len(ranks) == 1:
        return "unranked"
    numeric = sorted(rank for rank in ranks if isinstance(rank, int))
    if numeric:
        return numeric[0]
    raise UserError("Could not identify the top AF2 hit from the detected ranks.")


def _score_from_json_file(path: Path) -> Optional[float]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except Exception:
        return None
    return _score_from_mapping(data)


def _score_from_mapping(value) -> Optional[float]:
    if not isinstance(value, dict):
        return None

    normalized_keys = {_normalize_key(key): key for key in value}
    for score_key in AF3_SCORE_KEYS:
        original_key = normalized_keys.get(_normalize_key(score_key))
        if original_key is None:
            continue
        score = _to_float(value[original_key])
        if score is not None:
            return score

    for child in value.values():
        score = _score_from_mapping(child)
        if score is not None:
            return score
    return None


def _scores_from_csv_file(path: Path) -> Dict[Union[str, int], float]:
    scores: Dict[Union[str, int], float] = {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except Exception:
        return scores

    if not rows:
        return scores

    fieldnames = rows[0].keys()
    model_field = _first_matching_field(fieldnames, ("model", "model_id", "sample"))
    score_field = _first_matching_field(fieldnames, AF3_SCORE_KEYS)
    if model_field is None or score_field is None:
        return scores

    for row in rows:
        model_value = row.get(model_field, "")
        label = _extract_identifier(model_value, AF3_STRUCTURE_PATTERNS + AF3_SCORE_PATTERNS)
        score = _to_float(row.get(score_field))
        if label is not None and score is not None:
            scores[label] = score
    return scores


def _first_matching_field(fieldnames, candidates: Tuple[str, ...]) -> Optional[str]:
    normalized_candidates = {_normalize_key(candidate) for candidate in candidates}
    for fieldname in fieldnames:
        normalized = _normalize_key(fieldname)
        if normalized in normalized_candidates:
            return fieldname
    for fieldname in fieldnames:
        normalized = _normalize_key(fieldname)
        if any(candidate in normalized for candidate in normalized_candidates):
            return fieldname
    return None


def _to_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _open_pair(session, pair: PredictionPair):
    models, status = session.open_command.open_data(
        str(pair.structure_path), in_file_history=True
    )
    if not models:
        raise UserError(f"Could not open structure file: {pair.structure_path}")
    session.models.add(models)
    structure_model = models[0]
    if status:
        session.logger.info(status)

    from chimerax.alphafold.pae import alphafold_pae

    pae = alphafold_pae(session, structure=structure_model, file=str(pair.score_path), plot=False)
    return structure_model, pae


def run_contacts_interfaces_for_pair(
    session,
    display_pair: Dict[str, object],
    output_dir: Path,
    requested_chain: Optional[str] = None,
    max_pae: Optional[float] = DEFAULT_CONTACT_MAX_PAE,
    chain_pair=None,
    all_chain_pairs: bool = False,
) -> str:
    model = display_pair.get("model")
    model_spec = _model_spec(model)
    if model_spec is None:
        raise UserError("No active structure model is available for contact analysis.")

    label = str(display_pair.get("label") or "model")
    max_pae = _validate_contact_max_pae(max_pae)
    chain_pairs = _contact_chain_pairs(
        model,
        requested_chain=requested_chain,
        chain_pair=chain_pair,
        all_chain_pairs=all_chain_pairs,
    )
    result = _run_contact_workflow(
        session,
        label,
        output_dir,
        chain_pairs,
        model_spec,
        model,
        write_files=True,
        max_pae=max_pae,
        update_display=False,
    )
    display_pair["contact_analysis_files"] = result["files"]
    return (
        f"Saved contacts/interfaces for {label} on {_chain_pairs_label(chain_pairs)}. "
        f"AF contacts max PAE: {max_pae:g}. Contacts: {result['contact_count']}; "
        f"interface residues: "
        f"{result['interface_residue_count']}. Files were written to:\n{output_dir}"
    )


def show_contact_residues_for_pair(
    session,
    display_pair: Dict[str, object],
    requested_chain: Optional[str] = None,
    max_pae: Optional[float] = DEFAULT_CONTACT_MAX_PAE,
    chain_pair=None,
    all_chain_pairs: bool = False,
) -> str:
    model = display_pair.get("model")
    model_spec = _model_spec(model)
    if model_spec is None:
        raise UserError("No active structure model is available for contact display.")

    label = str(display_pair.get("label") or "model")
    max_pae = _validate_contact_max_pae(max_pae)
    chain_pairs = _contact_chain_pairs(
        model,
        requested_chain=requested_chain,
        chain_pair=chain_pair,
        all_chain_pairs=all_chain_pairs,
    )
    _delete_contact_text_labels(
        session,
        model,
        display_pair.get("contact_pseudobond_name"),
        display_pair.get("contact_residues"),
    )
    _hide_contact_sidechains(session, display_pair.get("contact_residue_name"))

    safe_label = _safe_token(label)
    contact_pseudobond_name = f"af_contacts_{safe_label}"
    contact_residue_name = _contact_residue_name(label)
    contact_count = 0
    for pair_index, (chain_a, chain_b) in enumerate(chain_pairs):
        contact_count += _run_alphafold_contacts_for_chain_pair(
            session,
            model,
            chain_a,
            chain_b,
            contact_pseudobond_name,
            max_pae=max_pae,
            replace=(pair_index == 0),
            output_file=None,
        )

    contact_residues = _contact_residues_from_pseudobonds(
        model, contact_pseudobond_name
    )
    display_pair["contact_pseudobond_name"] = contact_pseudobond_name
    display_pair["contact_residues"] = contact_residues
    display_pair["contact_residue_name"] = (
        contact_residue_name if len(contact_residues) > 0 else None
    )
    display_pair["contact_labels_visible"] = False
    if len(contact_residues) == 0:
        return (
            f"No AlphaFold contacts with PAE <= {max_pae:g} were found for "
            f"{label} on {_chain_pairs_label(chain_pairs)}."
        )

    _name_residues_from_residues(session, contact_residues, contact_residue_name)
    _show_contact_sidechains(session, contact_residue_name)
    _label_contact_residues(session, model, contact_residues)
    pae_label_count = _label_contact_pseudobonds(
        session, model, contact_pseudobond_name
    )
    display_pair["contact_labels_visible"] = True
    return (
        f"Shown and labelled {len(contact_residues)} contact residue(s) from "
        f"{contact_count} AlphaFold contact(s) for {label} on "
        f"{_chain_pairs_label(chain_pairs)} with PAE <= {max_pae:g}."
        f" Added {pae_label_count} PAE-value pseudobond label(s)."
    )


def toggle_contact_text_labels(session, display_pair: Dict[str, object]) -> str:
    model = display_pair.get("model")
    label = str(display_pair.get("label") or "model")
    pseudobond_name = display_pair.get("contact_pseudobond_name")
    residues = display_pair.get("contact_residues")
    if model is None or getattr(model, "deleted", False):
        raise UserError("No active structure model is available for contact labels.")
    if not pseudobond_name or _pseudobond_count(model, pseudobond_name) == 0:
        raise UserError(
            "No AlphaFold contact pseudobonds are available. Use "
            "'Show & Label Contacts' first."
        )

    if display_pair.get("contact_labels_visible", True):
        _delete_contact_text_labels(session, model, pseudobond_name, residues)
        display_pair["contact_labels_visible"] = False
        return f"Hid AlphaFold contact text labels for {label}."

    if residues is not None and len(residues) > 0:
        _label_contact_residues(session, model, residues)
    pae_label_count = _label_contact_pseudobonds(session, model, pseudobond_name)
    display_pair["contact_labels_visible"] = True
    return (
        f"Restored AlphaFold contact text labels for {label}: "
        f"{pae_label_count} PAE-value pseudobond label(s)."
    )


def show_cutoff_interfaces_for_pair(
    session,
    display_pair: Dict[str, object],
    pae,
    requested_chain: Optional[str] = None,
    max_pae: Optional[float] = DEFAULT_CONTACT_MAX_PAE,
    buried_area_cutoff: Optional[float] = 300.0,
    chain_pair=None,
    all_chain_pairs: bool = False,
) -> str:
    model = display_pair.get("model")
    model_spec = _model_spec(model)
    if model_spec is None:
        raise UserError("No active structure model is available for interface display.")
    if pae is None:
        raise UserError("No active PAE data is available for interface display.")

    label = str(display_pair.get("label") or "model")
    max_pae = _validate_contact_max_pae(max_pae)
    buried_area_cutoff = _validate_buried_area_cutoff(buried_area_cutoff)
    chain_pairs = _contact_chain_pairs(
        model,
        requested_chain=requested_chain,
        chain_pair=chain_pair,
        all_chain_pairs=all_chain_pairs,
    )
    _delete_residue_labels(session, display_pair.get("cutoff_interface_residues"))
    _hide_residue_atoms_and_bonds(
        session, display_pair.get("cutoff_interface_residue_name")
    )

    interface_residues = _run_cutoff_interfaces_for_chain_pairs(
        session,
        model,
        model_spec,
        pae,
        max_pae,
        chain_pairs,
        buried_area_cutoff,
    )
    display_pair["cutoff_interface_residues"] = interface_residues
    interface_name = f"cutoff_interface_residues_{_safe_token(label)}"
    display_pair["cutoff_interface_residue_name"] = (
        interface_name if len(interface_residues) > 0 else None
    )
    if len(interface_residues) == 0:
        return (
            f"No interface residues were found for {label} on "
            f"{_chain_pairs_label(chain_pairs)} using PAE < {max_pae:g} and "
            f"buried area >= {buried_area_cutoff:g} A^2."
        )

    _name_residues_from_residues(session, interface_residues, interface_name)
    run(session, "select " + interface_name)
    run(session, "show " + interface_name + " atoms")
    run(session, "show " + interface_name + " bonds")
    run(session, "style " + interface_name + " stick")
    return (
        f"Shown {len(interface_residues)} interface residue(s) for {label} on "
        f"{_chain_pairs_label(chain_pairs)} using PAE < {max_pae:g} and "
        f"buried area >= {buried_area_cutoff:g} A^2."
    )


def _prepare_contact_interface_display(
    session, pair_label: str, structure_model, requested_chain: Optional[str]
) -> Dict[str, object]:
    model_spec = _model_spec(structure_model)
    if model_spec is None:
        return _empty_contact_result()
    chain_pairs = _contact_chain_pairs(
        structure_model,
        requested_chain=requested_chain,
        all_chain_pairs=False,
    )
    try:
        return _run_contact_workflow(
            session,
            pair_label,
            None,
            chain_pairs,
            model_spec,
            structure_model,
            write_files=False,
            max_pae=DEFAULT_CONTACT_MAX_PAE,
            update_display=True,
        )
    except Exception as err:
        name = getattr(structure_model, "name", pair_label)
        session.logger.warning(
            f"Could not prepare contacts/interfaces for {name}: {err}"
        )
        return _empty_contact_result()


def _run_contact_workflow(
    session,
    pair_label: str,
    output_dir: Optional[Path],
    chain_pairs,
    model_spec: Optional[str],
    structure_model,
    *,
    write_files: bool,
    max_pae: Optional[float],
    update_display: bool,
) -> Dict[str, object]:
    max_pae = _validate_contact_max_pae(max_pae)
    chain_pairs = tuple(chain_pairs or ())
    if not chain_pairs:
        raise UserError("No inter-chain pairs are available for contact analysis.")
    if write_files:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    label = _safe_token(pair_label)
    structure_spec = model_spec or "last-opened"
    contact_pseudobond_name = (
        f"af_contacts_{label}"
        if update_display
        else f"af_contacts_save_{label}_{datetime.now().strftime('%H%M%S%f')}"
    )
    contact_raw_dir = output_dir / "raw" / "af_contacts" if write_files else None
    contact_tsv_file = output_dir / f"af_contacts_{label}.tsv" if write_files else None
    contact_report_file = output_dir / f"af_contacts_{label}.txt" if write_files else None
    contact_residue_name = _contact_residue_name(pair_label)
    interface_name = (
        f"interface_residues_{label}"
        if update_display
        else f"interface_save_residues_{label}_{datetime.now().strftime('%H%M%S%f')}"
    )
    interface_raw_dir = output_dir / "raw" / "interface_residues" if write_files else None
    interface_raw_file = (
        interface_raw_dir / f"interface_residues_{label}_raw.txt"
        if write_files
        else None
    )
    interface_report_file = output_dir / f"interface_residues_{label}.txt" if write_files else None
    if write_files:
        contact_raw_dir.mkdir(parents=True, exist_ok=True)
        interface_raw_file.parent.mkdir(parents=True, exist_ok=True)
        for path in (
            contact_tsv_file,
            contact_report_file,
            interface_raw_file,
            interface_report_file,
        ):
            _unlink_if_exists(path)

    if update_display:
        _clear_contact_labels(session, contact_residue_name)
        _restore_bond_displays(structure_model)
        commands = [
            "hide " + structure_spec + " atoms",
            "hide " + structure_spec + " surfaces",
            "show " + structure_spec + " cartoons",
        ]
        for command in commands:
            run(session, command)

    contact_raw_files = []
    contact_count = 0
    for pair_index, (chain_a, chain_b) in enumerate(chain_pairs):
        raw_file = (
            contact_raw_dir
            / f"af_contacts_{label}_{_safe_token(chain_a)}_{_safe_token(chain_b)}_raw.txt"
            if write_files
            else None
        )
        if raw_file is not None:
            _unlink_if_exists(raw_file)
            contact_raw_files.append(raw_file)
        contact_count += _run_alphafold_contacts_for_chain_pair(
            session,
            structure_model,
            chain_a,
            chain_b,
            contact_pseudobond_name,
            max_pae=max_pae,
            replace=(pair_index == 0),
            output_file=raw_file,
        )

    contact_rows = []
    if write_files:
        for raw_file in contact_raw_files:
            contact_rows.extend(_read_contact_rows(raw_file))
    if write_files:
        _write_contact_reports(
            contact_rows,
            contact_report_file,
            contact_tsv_file,
            pair_label=pair_label,
            model_spec=structure_spec,
            chain_scope=_chain_pairs_label(chain_pairs),
            max_pae=max_pae,
        )
    contact_residues = (
        _contact_residues_from_pseudobonds(structure_model, contact_pseudobond_name)
        if update_display
        else []
    )
    contact_residues_named = (
        _name_residues_from_residues(session, contact_residues, contact_residue_name)
        if update_display
        else False
    )

    interface_residues = _run_interfaces_for_chain_pairs(
        session, structure_model, structure_spec, chain_pairs
    )
    if update_display:
        commands = [
            "rainbow " + structure_spec + " chains palette bupu",
            "color byhetero",
        ]
        for command in commands:
            run(session, command)

    interface_named = _name_residues_from_residues(
        session, interface_residues, interface_name
    )
    interface_tokens = _residue_tokens_from_residues(interface_residues)
    if write_files:
        if interface_named:
            run(
                session,
                "info residues "
                + interface_name
                + " saveFile "
                + quote_if_necessary(str(interface_raw_file)),
            )
        _write_interface_report(
            interface_tokens,
            interface_report_file,
            pair_label=pair_label,
            model_spec=structure_spec,
            chain_scope=_chain_pairs_label(chain_pairs),
        )
    if update_display and interface_named:
        run(session, "select " + interface_name)
        run(session, "show " + interface_name + " atoms")
        run(session, "show " + interface_name + " bonds")
        run(session, "style " + interface_name + " stick")
    pae_label_count = 0
    if update_display and contact_residues_named:
        _show_contact_sidechains(session, contact_residue_name)
        _label_contact_residues(session, structure_model, contact_residues)
        pae_label_count = _label_contact_pseudobonds(
            session, structure_model, contact_pseudobond_name
        )

    if not update_display:
        _delete_pseudobond_group(structure_model, contact_pseudobond_name)
        if interface_named:
            try:
                run(session, "name delete " + interface_name)
            except Exception:
                pass

    return {
        "contact_pseudobond_name": contact_pseudobond_name if update_display else None,
        "contact_residue_name": contact_residue_name if contact_residues_named else None,
        "interface_residue_name": interface_name if update_display and interface_named else None,
        "contact_residues": contact_residues,
        "interface_residues": interface_residues,
        "contact_labels_visible": bool(
            update_display and contact_residues_named and pae_label_count >= 0
        ),
        "contact_count": len(contact_rows) if write_files else contact_count,
        "interface_residue_count": len(interface_tokens),
        "files": _contact_output_files(
            contact_report_file,
            contact_tsv_file,
            contact_raw_files,
            interface_report_file,
            interface_raw_file,
        ),
    }


def _empty_contact_result() -> Dict[str, object]:
    return {
        "contact_pseudobond_name": None,
        "contact_residue_name": None,
        "interface_residue_name": None,
        "contact_residues": None,
        "interface_residues": None,
        "contact_labels_visible": False,
        "contact_count": 0,
        "interface_residue_count": 0,
        "files": {},
    }


def _contact_output_files(
    contact_report_file,
    contact_tsv_file,
    contact_raw_file,
    interface_report_file,
    interface_raw_file,
) -> Dict[str, Path]:
    files = {
        "contact_report": contact_report_file,
        "contact_tsv": contact_tsv_file,
        "contact_raw": contact_raw_file,
        "interface_report": interface_report_file,
        "interface_raw": interface_raw_file,
    }
    return {key: value for key, value in files.items() if value is not None}


def _disable_pae_drag_coloring(plot) -> None:
    if plot is not None and hasattr(plot, "_drag_colors_structure"):
        plot._drag_colors_structure = False


def create_pae_plot(session, pae):
    from chimerax.alphafold.pae import AlphaFoldPAEPlot

    plot = AlphaFoldPAEPlot(
        session,
        "AlphaFold Predicted Aligned Error",
        pae,
        divider_lines=True,
    )
    _prepare_pae_plot(plot, pae)
    return plot


def set_pae_plot_data(plot, pae) -> None:
    if plot is None or _plot_closed(plot):
        return
    plot.set_pae(pae)
    if hasattr(plot, "show_chain_dividers"):
        plot.show_chain_dividers(getattr(plot, "_showing_chain_dividers", True))
    _prepare_pae_plot(plot, pae)


def _prepare_pae_plot(plot, pae) -> None:
    _clear_pae_highlight(plot)
    _disable_pae_drag_coloring(plot)
    heading = getattr(plot, "_heading", None)
    if heading is not None:
        sname = f"for {pae.structure}" if getattr(pae, "structure", None) else ""
        heading.setText(
            f"<html>Predicted aligned errors (PAE) {sname}"
            "<br>Drag a box to select structure residues and atoms.</html>"
        )


def _write_analysis_summary(
    output_dir: Path,
    *,
    mode: str,
    run_label: str,
    input_directory: Path,
    prediction_filter: str,
    requested_chain: Optional[str],
    pairs: List[Dict[str, object]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now().isoformat(timespec="seconds")
    data = {
        "created_at": created_at,
        "bundle_version": _bundle_version(),
        "mode": mode,
        "run_label": run_label,
        "input_directory": str(input_directory),
        "output_dir": str(output_dir),
        "prediction_filter": prediction_filter,
        "requested_chain": requested_chain,
        "opened_pairs": pairs,
    }
    json_path = output_dir / "analysis_summary.json"
    text_path = output_dir / "analysis_summary.txt"
    json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"Created: {created_at}",
        f"Bundle version: {data['bundle_version']}",
        f"Mode: {mode}",
        f"Run label: {run_label}",
        f"Input folder: {input_directory}",
        f"Output folder: {output_dir}",
        f"Name/filter: {prediction_filter or '(none)'}",
        f"Requested contact chain: {requested_chain or '(first chain per structure)'}",
        "Contact/interface display: prepared on open.",
        "Contact/interface files: written only when the controller button is "
        "used for the active model.",
        "",
        "Opened pairs:",
    ]
    for pair in pairs:
        lines.extend(
            [
                f"- {pair['label']}",
                f"  structure: {pair['structure']}",
                f"  data: {pair['score_data']}",
                f"  confidence score: {_format_confidence(pair.get('confidence_score'))}",
                f"  confidence missing: {bool(pair.get('confidence_missing'))}",
                f"  contact analysis: {pair['contact_analysis']}",
                f"  requested contact chain: {pair.get('requested_contact_chain') or '(first chain)'}",
                f"  model spec: {pair['model_spec']}",
            ]
        )
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _bundle_version() -> str:
    try:
        from importlib.metadata import version

        return version("ChimeraX-AFPredictionToolbars")
    except Exception:
        return "unknown"


def apply_interchain_pae_visibility(
    session,
    pae,
    max_pae: float,
    mode: str,
    chain_pair=None,
    plot=None,
    select: bool = True,
    highlight: bool = True,
) -> str:
    structure = getattr(pae, "structure", None)
    model_spec = _model_spec(structure)
    if structure is None or model_spec is None:
        raise UserError("The active PAE plot is not associated with an open structure.")

    targets = ("atoms", "pseudobonds", "cartoons", "surfaces")
    _restore_bond_displays(structure)
    if mode == "show_all":
        for target in ("atoms", "pseudobonds", "surfaces"):
            run(session, f"hide {model_spec} {target}")
        run(session, f"show {model_spec} cartoons")
        _clear_pae_highlight(plot)
        return f"Restored cartoon-only display for {structure}."

    residues, cells = _interchain_pae_filter(pae, max_pae, chain_pair)
    if highlight:
        highlight_pae_cells(plot, cells)
    elif plot is not None:
        _clear_pae_highlight(plot)
    scope = _chain_pair_scope_label(chain_pair)
    if not residues:
        return (
            f"No residues with minimum {scope} PAE < {max_pae:g} were found."
        )

    if select:
        _select_residues(session, residues)
    if mode == "select":
        return (
            f"Selected {len(residues)} residue(s) with minimum {scope} "
            f"PAE < {max_pae:g}."
        )
    elif mode == "hide_unselected":
        _hide_unselected_residue_display(session, structure, residues)
        action = "Hid residues outside"
    elif mode == "show_only":
        _show_only_residue_cartoons(session, structure, residues)
        action = "Showing only"
    else:
        raise UserError(f"Unknown PAE visibility mode: {mode}")

    return (
        f"{action} {len(residues)} residue(s) with minimum {scope} "
        f"PAE < {max_pae:g}."
    )


def preview_interchain_pae_residues(
    session,
    pae,
    max_pae: float,
    chain_pair=None,
    plot=None,
    select: bool = True,
    highlight: bool = True,
):
    residues, cells = _interchain_pae_filter(pae, max_pae, chain_pair)
    if select:
        _select_residues(session, residues)
    if highlight:
        highlight_pae_cells(plot, cells)
    else:
        _clear_pae_highlight(plot)
    scope = _chain_pair_scope_label(chain_pair)
    return residues, f"Previewing {len(residues)} residue(s) with minimum {scope} PAE < {max_pae:g}."


def apply_plddt_visibility(
    session,
    structure_model,
    min_plddt: float,
    mode: str,
    select: bool = True,
) -> str:
    model_spec = _model_spec(structure_model)
    if structure_model is None or model_spec is None:
        raise UserError("No active structure model is available for pLDDT selection.")

    _restore_bond_displays(structure_model)
    if mode == "show_all":
        for target in ("atoms", "pseudobonds", "surfaces"):
            run(session, f"hide {model_spec} {target}")
        run(session, f"show {model_spec} cartoons")
        return f"Restored cartoon-only display for {structure_model}."

    residues = _residues_with_plddt_at_or_above(structure_model, min_plddt)
    if not residues:
        return f"No residues with pLDDT >= {min_plddt:g} were found."

    if select:
        _select_residues(session, residues)
    if mode == "select":
        return f"Selected {len(residues)} residue(s) with pLDDT >= {min_plddt:g}."
    elif mode == "hide_unselected":
        _hide_unselected_residue_display(session, structure_model, residues)
        action = "Hid residues outside"
    elif mode == "show_only":
        _show_only_residue_cartoons(session, structure_model, residues)
        action = "Showing only"
    else:
        raise UserError(f"Unknown pLDDT visibility mode: {mode}")

    return f"{action} {len(residues)} residue(s) with pLDDT >= {min_plddt:g}."


def preview_plddt_residues(
    session,
    structure_model,
    min_plddt: float,
    select: bool = True,
):
    residues = _residues_with_plddt_at_or_above(structure_model, min_plddt)
    if select:
        _select_residues(session, residues)
    return residues, f"Previewing {len(residues)} residue(s) with pLDDT >= {min_plddt:g}."


def reset_prediction_display(session, display_pairs) -> None:
    for pair in display_pairs:
        model = pair.get("model")
        model_spec = _model_spec(model)
        if model_spec is None:
            continue
        _restore_bond_displays(model)
        for target in ("atoms", "pseudobonds", "surfaces"):
            run(session, f"hide {model_spec} {target}")
        run(session, f"show {model_spec} cartoons")
        contact_name = pair.get("contact_residue_name")
        if contact_name:
            _show_contact_sidechains(session, contact_name)
    run(session, "select clear")


def save_active_view_png(
    session,
    output_dir: Path,
    pair_label: str,
    suffix: str = "",
    timestamp: bool = True,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _saved_filename("view", pair_label, suffix, ".png", timestamp)
    path = _unique_path(output_dir / filename)

    from chimerax.image_formats.save import save_image

    save_image(
        session,
        str(path),
        format_name="PNG",
        supersample=3,
        transparent_background=True,
    )
    return path


def save_chimerax_session(
    session,
    output_dir: Path,
    pair_label: str,
    suffix: str = "",
    timestamp: bool = True,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _saved_filename("session", pair_label, suffix, ".cxs", timestamp)
    path = _unique_path(output_dir / filename)
    run(session, "save " + quote_if_necessary(str(path)))
    return path


def _saved_filename(prefix: str, pair_label: str, suffix: str, extension: str, timestamp: bool) -> str:
    clean_pair = _safe_token(pair_label)
    clean_suffix = _safe_token(_strip_known_suffix(suffix)) if suffix else ""
    parts = [prefix, clean_pair]
    if clean_suffix:
        parts.append(clean_suffix)
    if timestamp:
        parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
    return "_".join(parts) + extension


def _strip_known_suffix(text: str) -> str:
    lower = text.casefold()
    for extension in (".png", ".cxs"):
        if lower.endswith(extension):
            return text[: -len(extension)]
    return text


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _validate_contact_max_pae(max_pae: Optional[float]) -> float:
    if max_pae is None:
        return DEFAULT_CONTACT_MAX_PAE
    try:
        value = float(max_pae)
    except (TypeError, ValueError):
        raise UserError(f"AF contacts max PAE must be a number, got {max_pae!r}.")
    if value < 0:
        raise UserError("AF contacts max PAE must be zero or greater.")
    return value


def _validate_buried_area_cutoff(buried_area_cutoff: Optional[float]) -> float:
    if buried_area_cutoff is None:
        return 300.0
    try:
        value = float(buried_area_cutoff)
    except (TypeError, ValueError):
        raise UserError(
            f"Buried area cutoff must be a number, got {buried_area_cutoff!r}."
        )
    if value < 0:
        raise UserError("Buried area cutoff must be zero or greater.")
    return value


def _clear_contact_labels(session, contact_residue_name) -> None:
    return


def _contact_residue_name(pair_label: str) -> str:
    return f"af_contact_residues_{_safe_token(pair_label)}"


def _pae_filter_residue_name(structure_model) -> str:
    model_id = getattr(structure_model, "id_string", None) or getattr(
        structure_model, "name", "model"
    )
    return f"pae_filter_residues_{_safe_token(str(model_id))}"


def _plddt_filter_residue_name(structure_model) -> str:
    model_id = getattr(structure_model, "id_string", None) or getattr(
        structure_model, "name", "model"
    )
    return f"plddt_filter_residues_{_safe_token(str(model_id))}"


def _name_contact_residues_from_file(
    session, contact_file: Path, structure_spec: str, contact_residue_name: str
) -> bool:
    residue_tokens = _contact_residue_tokens(contact_file)
    return _name_residues_from_tokens(
        session, residue_tokens, structure_spec, contact_residue_name
    )


def _name_residues_from_tokens(
    session, residue_tokens: Tuple[str, ...], structure_spec: str, selection_name: str
) -> bool:
    if not residue_tokens:
        return False
    residue_specs = " ".join(structure_spec + token for token in residue_tokens)
    run(session, f"name frozen {selection_name} {residue_specs}")
    return True


def _name_residues_from_residues(session, residues, selection_name: str) -> bool:
    if residues is None or len(residues) == 0:
        return False
    from chimerax.atomic import concise_residue_spec

    residue_spec = concise_residue_spec(session, residues)
    run(session, f"name frozen {selection_name} {residue_spec}")
    return True


def _show_contact_sidechains(session, contact_residue_name: str) -> None:
    run(session, f"show {contact_residue_name}&sidechain atoms")
    run(session, f"show {contact_residue_name}&sidechain bonds")
    run(session, f"style {contact_residue_name}&sidechain stick")


def _hide_contact_sidechains(session, contact_residue_name) -> None:
    if not contact_residue_name:
        return
    try:
        run(session, f"hide {contact_residue_name}&sidechain atoms")
        run(session, f"hide {contact_residue_name}&sidechain bonds")
    except Exception:
        pass


def _hide_residue_atoms_and_bonds(session, residue_name) -> None:
    if not residue_name:
        return
    try:
        run(session, f"hide {residue_name} atoms")
        run(session, f"hide {residue_name} bonds")
    except Exception:
        pass


def _restore_bond_displays(structure_model) -> None:
    if structure_model is None or getattr(structure_model, "deleted", False):
        return None
    try:
        structure_model.bonds.displays = True
    except Exception:
        return None
    return None


def _hide_unselected_residue_display(session, structure_model, residues) -> None:
    keep_residues = _residues_for_structure(structure_model, residues)
    outside_residues = _residue_complement(structure_model, keep_residues)
    _restore_bond_displays(structure_model)
    if len(outside_residues) == 0:
        return

    outside_atoms = outside_residues.atoms
    outside_atoms.displays = False
    outside_residues.ribbon_displays = False
    _hide_bonds_touching_residues(structure_model, outside_residues)
    _hide_pseudobonds_touching_residues(structure_model, outside_residues)
    _hide_surface_patches_for_atoms(outside_atoms)


def _show_only_residue_cartoons(session, structure_model, residues) -> None:
    keep_residues = _residues_for_structure(structure_model, residues)
    try:
        structure_model.atoms.displays = False
        structure_model.residues.ribbon_displays = False
        structure_model.bonds.displays = False
    except Exception:
        model_spec = _model_spec(structure_model)
        if model_spec is not None:
            for target in ("atoms", "pseudobonds", "cartoons", "surfaces"):
                run(session, f"hide {model_spec} {target}")
            if len(keep_residues) > 0:
                from chimerax.atomic import concise_residue_spec

                run(session, f"show {concise_residue_spec(session, keep_residues)} cartoons")
        return

    _hide_all_pseudobonds(structure_model)
    _hide_surface_patches_for_atoms(structure_model.atoms)
    if len(keep_residues) > 0:
        keep_residues.ribbon_displays = True


def _residues_for_structure(structure_model, residues):
    from chimerax.atomic import Residues

    if structure_model is None or residues is None:
        return Residues([])
    selected = [
        residue
        for residue in residues
        if residue is not None
        and not getattr(residue, "deleted", False)
        and getattr(residue, "structure", None) is structure_model
    ]
    return Residues(selected)


def _residue_complement(structure_model, keep_residues):
    from chimerax.atomic import Residues

    if structure_model is None or getattr(structure_model, "deleted", False):
        return Residues([])
    keep = set(keep_residues)
    return Residues([residue for residue in structure_model.residues if residue not in keep])


def _hide_bonds_touching_residues(structure_model, residues) -> None:
    residue_set = set(residues)
    if not residue_set:
        return
    try:
        from chimerax.atomic import Bonds

        bonds = []
        for bond in structure_model.bonds:
            atom_a, atom_b = bond.atoms
            if atom_a.residue in residue_set or atom_b.residue in residue_set:
                bonds.append(bond)
        if bonds:
            Bonds(bonds).displays = False
    except Exception:
        pass


def _hide_pseudobonds_touching_residues(structure_model, residues) -> None:
    residue_set = set(residues)
    if not residue_set:
        return
    try:
        from chimerax.atomic import Pseudobonds

        pbonds = []
        for group in structure_model.pbg_map.values():
            for pseudobond in group.pseudobonds:
                atom_a, atom_b = pseudobond.atoms
                if atom_a.residue in residue_set or atom_b.residue in residue_set:
                    pbonds.append(pseudobond)
        if pbonds:
            Pseudobonds(pbonds).displays = False
    except Exception:
        pass


def _hide_all_pseudobonds(structure_model) -> None:
    try:
        for group in structure_model.pbg_map.values():
            group.pseudobonds.displays = False
    except Exception:
        pass


def _delete_pseudobond_group(structure_model, pseudobond_name: str) -> None:
    try:
        group = structure_model.pseudobond_group(pseudobond_name, create_type=None)
    except TypeError:
        try:
            group = structure_model.pbg_map.get(pseudobond_name)
        except Exception:
            group = None
    except Exception:
        group = None
    if group is None:
        return
    try:
        group.pseudobonds.delete()
        structure_model.session.models.close([group])
    except Exception:
        pass


def _delete_residue_labels(session, residues) -> None:
    if residues is None or len(residues) == 0:
        return
    try:
        from chimerax.core.objects import Objects
        from chimerax.label.label3d import label_delete

        label_delete(session, Objects(atoms=residues.atoms), object_type="residues")
    except Exception as err:
        session.logger.warning(f"Could not clear previous AF contact labels: {err}")


def _delete_contact_text_labels(
    session, structure_model, pseudobond_name, residues
) -> None:
    _delete_residue_labels(session, residues)
    if structure_model is None or not pseudobond_name:
        return
    pbonds = _pseudobonds_for_group(structure_model, pseudobond_name)
    if pbonds is None or len(pbonds) == 0:
        return
    try:
        from chimerax.core.objects import Objects
        from chimerax.label.label3d import label_delete

        label_delete(session, Objects(pseudobonds=pbonds), object_type="pseudobonds")
    except Exception as err:
        session.logger.warning(
            f"Could not clear previous AF contact PAE labels: {err}"
        )


def _hide_surface_patches_for_atoms(atoms) -> None:
    try:
        from chimerax.atomic import molsurf

        molsurf.hide_surface_atom_patches(atoms)
    except Exception:
        pass


def _label_contact_residues(session, structure_model, residues) -> None:
    if residues is None or len(residues) == 0:
        return
    try:
        from chimerax.core.objects import Objects
        from chimerax.label.label3d import label, labels_model

        label(
            session,
            Objects(atoms=residues.atoms),
            object_type="residues",
            bg_color="none",
            position="primary atom",
        )
        label_model = labels_model(structure_model)
        if label_model is None:
            return
        for label_object in label_model.labels(residues):
            label_object.color = _residue_display_color(label_object.residue)
        label_model.update_labels()
    except Exception as err:
        session.logger.warning(f"Could not label AF contact residues: {err}")


def _label_contact_pseudobonds(session, structure_model, pseudobond_name: str) -> int:
    pbonds = _pseudobonds_for_group(structure_model, pseudobond_name)
    if pbonds is None or len(pbonds) == 0:
        return 0
    try:
        from chimerax.atomic import Pseudobonds
        from chimerax.core.objects import Objects
        from chimerax.label.label3d import label

        label_count = 0
        for pseudobond in pbonds:
            pae_value = _pseudobond_pae_value(structure_model, pseudobond)
            if pae_value is None:
                continue
            label(
                session,
                Objects(pseudobonds=Pseudobonds([pseudobond])),
                object_type="pseudobonds",
                text=f"{pae_value:.1f}",
                color=tuple(pseudobond.color),
                bg_color="none",
            )
            label_count += 1
        return label_count
    except Exception as err:
        session.logger.warning(
            f"Could not label AF contact pseudobonds with PAE values: {err}"
        )
        return 0


def _pseudobond_pae_value(structure_model, pseudobond):
    pae = getattr(structure_model, "alphafold_pae", None)
    if pae is None:
        return None
    object_a = None
    object_b = None
    try:
        atom_a, atom_b = pseudobond.atoms
        object_a = _pae_value_object_for_atom(atom_a)
        object_b = _pae_value_object_for_atom(atom_b)
        return float(pae.value(object_a, object_b))
    except Exception:
        if object_a is None or object_b is None:
            return None
        try:
            return float(pae.value(object_b, object_a))
        except Exception:
            return None


def _pae_value_object_for_atom(atom):
    try:
        from chimerax.alphafold.pae import per_residue_pae

        residue = atom.residue
        return residue if per_residue_pae(residue) else atom
    except Exception:
        return atom


def _contact_chain_pairs(
    structure_model,
    *,
    requested_chain: Optional[str] = None,
    chain_pair=None,
    all_chain_pairs: bool = False,
) -> Tuple[Tuple[str, str], ...]:
    chain_ids = _chain_ids(structure_model)
    if chain_pair is not None:
        chain_a, chain_b = chain_pair
        missing = [chain for chain in (chain_a, chain_b) if chain not in chain_ids]
        if missing:
            raise UserError(
                "Contact chain pair contains chain(s) not found in the active "
                f"model: {', '.join(missing)}. Available chains: {', '.join(chain_ids)}"
            )
        return ((chain_a, chain_b),)

    pairs = chain_pair_options(structure_model)
    if all_chain_pairs:
        return pairs

    chain_id = _resolve_chain_id(structure_model, requested_chain)
    return tuple((chain_id, other) for other in chain_ids if other != chain_id)


def _chain_pairs_label(chain_pairs) -> str:
    chain_pairs = tuple(chain_pairs or ())
    if not chain_pairs:
        return "no chain pairs"
    if len(chain_pairs) == 1:
        return f"chain pair {chain_pairs[0][0]}-{chain_pairs[0][1]}"
    return "all chain pairs (" + ", ".join(f"{a}-{b}" for a, b in chain_pairs) + ")"


def _run_alphafold_contacts_for_chain_pair(
    session,
    structure_model,
    chain_a: str,
    chain_b: str,
    pseudobond_name: str,
    *,
    max_pae: float,
    replace: bool,
    output_file: Optional[Path],
) -> int:
    atoms = _atoms_for_chain(structure_model, chain_a)
    to_atoms = _atoms_for_chain(structure_model, chain_b)
    if atoms is None or len(atoms) == 0:
        raise UserError(f"No atoms found for contact chain {chain_a}.")
    if to_atoms is None or len(to_atoms) == 0:
        raise UserError(f"No atoms found for contact partner chain {chain_b}.")

    from chimerax.alphafold.contacts import alphafold_contacts

    pbonds = alphafold_contacts(
        session,
        atoms,
        to_atoms=to_atoms,
        max_pae=max_pae,
        name=pseudobond_name,
        replace=replace,
        output_file=str(output_file) if output_file is not None else None,
    )
    return len(pbonds)


def _run_interfaces_for_chain_pairs(session, structure_model, structure_spec: str, chain_pairs):
    from chimerax.atomic import Residues

    residues = []
    seen = set()
    for chain_a, chain_b in chain_pairs:
        run(
            session,
            "interfaces select "
            + f"{structure_spec}&/{chain_a}"
            + " contacting "
            + f"{structure_spec}&/{chain_b}"
            + " bothSides true",
        )
        for residue in _selected_residues_for_structure(session, structure_model):
            if residue not in seen:
                seen.add(residue)
                residues.append(residue)
    return Residues(residues)


def _run_cutoff_interfaces_for_chain_pairs(
    session,
    structure_model,
    structure_spec: str,
    pae,
    max_pae: float,
    chain_pairs,
    buried_area_cutoff: float,
):
    from chimerax.atomic import Residues
    from chimerax.interfaces.cmd import interfaces_select

    residues = []
    seen = set()
    for chain_a, chain_b in chain_pairs:
        pae_residues, _cells = _interchain_pae_filter(
            pae, max_pae, chain_pair=(chain_a, chain_b)
        )
        atoms_a = _residues_for_chain(structure_model, pae_residues, chain_a).atoms
        atoms_b = _residues_for_chain(structure_model, pae_residues, chain_b).atoms
        if len(atoms_a) == 0 or len(atoms_b) == 0:
            continue
        try:
            pair_residues = interfaces_select(
                session,
                atoms=atoms_a,
                contacting=atoms_b,
                both_sides=True,
                area_cutoff=buried_area_cutoff,
            )
        except Exception as err:
            session.logger.warning(
                f"Could not run interfaces for {structure_spec} chains "
                f"{chain_a}-{chain_b}: {err}"
            )
            continue
        for residue in pair_residues:
            if residue not in seen:
                seen.add(residue)
                residues.append(residue)
    return Residues(residues)


def _residues_for_chain(structure_model, residues, chain_id: str):
    from chimerax.atomic import Residues

    if structure_model is None or residues is None:
        return Residues([])
    selected = [
        residue
        for residue in residues
        if residue is not None
        and not getattr(residue, "deleted", False)
        and getattr(residue, "structure", None) is structure_model
        and getattr(residue, "chain_id", None) == chain_id
    ]
    return Residues(selected)


def _residue_display_color(residue) -> Tuple[int, int, int, int]:
    for attr_name in ("ribbon_color", "ring_color"):
        color = getattr(residue, attr_name, None)
        rgba = _normalize_rgba8(color)
        if rgba is not None:
            return rgba
    try:
        atom = residue.principal_atom
        rgba = _normalize_rgba8(getattr(atom, "color", None))
        if rgba is not None:
            return rgba
    except Exception:
        pass
    try:
        atoms = residue.atoms
        if len(atoms) > 0:
            rgba = _normalize_rgba8(atoms.colors[0])
            if rgba is not None:
                return rgba
    except Exception:
        pass
    return (255, 255, 255, 255)


def _normalize_rgba8(color) -> Optional[Tuple[int, int, int, int]]:
    if color is None:
        return None
    try:
        values = [int(component) for component in color]
    except Exception:
        return None
    if len(values) == 3:
        values.append(255)
    if len(values) != 4:
        return None
    return tuple(max(0, min(255, value)) for value in values)


def _contact_residue_tokens(contact_file: Path) -> Tuple[str, ...]:
    try:
        lines = contact_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()

    tokens = []
    seen = set()
    for line in lines:
        fields = line.split()
        for token in fields[:2]:
            if not token.startswith("/") or ":" not in token or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tuple(tokens)


def _contact_residues_from_pseudobonds(structure_model, pseudobond_name: str):
    if structure_model is None:
        return None
    try:
        group = structure_model.pseudobond_group(pseudobond_name)
        pbonds = group.pseudobonds
        atoms1, atoms2 = pbonds.atoms
        from chimerax.atomic import Atoms, concatenate

        atoms = concatenate((atoms1, atoms2), Atoms)
        return atoms.unique_residues
    except Exception:
        return None


def _pseudobond_count(structure_model, pseudobond_name: str) -> int:
    if structure_model is None:
        return 0
    try:
        return len(structure_model.pseudobond_group(pseudobond_name).pseudobonds)
    except Exception:
        return 0


def _pseudobonds_for_group(structure_model, pseudobond_name: str):
    if structure_model is None or not pseudobond_name:
        return None
    try:
        group = structure_model.pseudobond_group(pseudobond_name)
        return group.pseudobonds
    except Exception:
        return None


def _selected_residues_for_structure(session, structure_model):
    from chimerax.atomic import Residues, selected_residues

    residues = selected_residues(session)
    if structure_model is None or len(residues) == 0:
        return residues
    selected = [
        residue
        for residue in residues
        if getattr(residue, "structure", None) is structure_model
    ]
    return Residues(selected)


def _residue_tokens_from_residues(residues) -> Tuple[str, ...]:
    if residues is None:
        return ()
    tokens = []
    for residue in residues:
        chain_id = getattr(residue, "chain_id", "") or "?"
        number = getattr(residue, "number", "")
        insertion_code = getattr(residue, "insertion_code", "") or ""
        tokens.append(f"/{chain_id}:{number}{insertion_code}")
    return tuple(tokens)


def _read_contact_rows(contact_file: Path) -> List[Tuple[str, str, Optional[float]]]:
    try:
        lines = contact_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    rows = []
    for line in lines:
        fields = line.split()
        if len(fields) < 2:
            continue
        value = None
        if len(fields) >= 3:
            try:
                value = float(fields[2])
            except ValueError:
                value = None
        rows.append((fields[0], fields[1], value))
    return rows


def _write_contact_reports(
    rows: List[Tuple[str, str, Optional[float]]],
    report_file: Path,
    tsv_file: Path,
    *,
    pair_label: str,
    model_spec: str,
    chain_scope: str,
    max_pae: float,
) -> None:
    created = datetime.now().isoformat(timespec="seconds")
    with tsv_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["query_residue", "partner_residue", "pae"])
        for residue_a, residue_b, pae_value in rows:
            writer.writerow(
                [
                    residue_a,
                    residue_b,
                    "" if pae_value is None else f"{pae_value:.3f}",
                ]
            )

    lines = [
        f"AlphaFold contact report: {pair_label}",
        f"Generated: {created}",
        f"Model: {model_spec}",
        f"Chain scope: {chain_scope}",
        f"AF contacts max PAE: {max_pae:g}",
        "",
        "What this file contains",
        "This report lists inter-chain contacts produced by ChimeraX's "
        "'alphafold contacts' command for the active model and selected chain "
        "scope. Only contacts with PAE values at or below the current PAE "
        "cutoff are included. Lower PAE values indicate a more confident "
        "relative placement.",
        "",
        f"Contact count: {len(rows)}",
        "",
        "Contacts",
        "query_residue\tpartner_residue\tpae",
    ]
    for residue_a, residue_b, pae_value in rows:
        formatted = "not reported" if pae_value is None else f"{pae_value:.3f}"
        lines.append(f"{residue_a}\t{residue_b}\t{formatted}")
    if not rows:
        lines.append("(none)")
    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _info_residue_tokens(info_file: Path) -> Tuple[str, ...]:
    try:
        text = info_file.read_text(encoding="utf-8")
    except OSError:
        return ()
    tokens = []
    seen = set()
    for match in re.finditer(r"\bresidue\s+id\s+(\S+)", text):
        token = match.group(1)
        if token.startswith("/") and ":" in token and token not in seen:
            seen.add(token)
            tokens.append(token)
    return tuple(tokens)


def _write_interface_report(
    residue_tokens: Tuple[str, ...],
    report_file: Path,
    *,
    pair_label: str,
    model_spec: str,
    chain_scope: str,
) -> None:
    created = datetime.now().isoformat(timespec="seconds")
    by_chain: Dict[str, List[str]] = {}
    for token in residue_tokens:
        chain, residue = _split_residue_token(token)
        by_chain.setdefault(chain, []).append(residue)

    lines = [
        f"Interface residue report: {pair_label}",
        f"Generated: {created}",
        f"Model: {model_spec}",
        f"Chain scope: {chain_scope}",
        "",
        "What this file contains",
        "This report lists the residue-level interface selected by ChimeraX's "
        "'interfaces select' command for the active model. The bundle converts "
        "that result into a residue-level named selection so full amino-acid "
        "residues can be displayed, rather than isolated contacting atoms.",
        "",
        f"Interface residue count: {len(residue_tokens)}",
        "",
        "Residues by chain",
    ]
    if by_chain:
        for chain in sorted(by_chain):
            residues = ", ".join(by_chain[chain])
            lines.append(f"/{chain}: {residues}")
    else:
        lines.append("(none)")
    lines.extend(["", "Residue tokens", "residue"])
    lines.extend(residue_tokens or ["(none)"])
    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _split_residue_token(token: str) -> Tuple[str, str]:
    match = re.match(r"/([^:]+):(.+)$", token)
    if not match:
        return "?", token
    return match.group(1), match.group(2)


def highlight_pae_cells(plot, cells) -> None:
    _clear_pae_highlight(plot)
    if plot is None or _plot_closed(plot) or not cells:
        return
    try:
        view = plot._pae_view
        scene = view.scene()
    except Exception:
        return

    try:
        from Qt.QtGui import QBrush, QColor, QPen

        brush = QBrush(QColor(255, 191, 0, 45))
        pen = QPen(QColor(0, 0, 0, 180))
        items = []
        for top, left, bottom, right in _cell_rectangles(cells):
            items.append(
                scene.addRect(
                    left,
                    top,
                    right - left + 1,
                    bottom - top + 1,
                    pen=pen,
                    brush=brush,
                )
            )
        for item in items:
            item.setZValue(2)
        plot._af_toolbar_highlight_items = items
    except Exception:
        _clear_pae_highlight(plot)


def _clear_pae_highlight(plot) -> None:
    if plot is None:
        return
    items = getattr(plot, "_af_toolbar_highlight_items", None)
    if not items:
        return
    try:
        scene = plot._pae_view.scene()
        for item in list(items):
            scene.removeItem(item)
    except Exception:
        pass
    plot._af_toolbar_highlight_items = []


def _select_residues(session, residues) -> None:
    session.selection.clear()
    if not residues:
        return
    from chimerax.atomic import Atoms

    atoms = []
    for residue in residues:
        if residue is not None and not getattr(residue, "deleted", False):
            atoms.extend(residue.atoms)
    if atoms:
        selected_atoms = Atoms(atoms)
        selected_atoms.intra_bonds.displays = True
        selected_atoms.selected = True
        selected_atoms.intra_bonds.selected = True
        selected_atoms.intra_pseudobonds.selected = True


def _contiguous_ranges(indices):
    indices = sorted(set(indices))
    if not indices:
        return
    start = previous = indices[0]
    for index in indices[1:]:
        if index == previous + 1:
            previous = index
            continue
        yield start, previous
        start = previous = index
    yield start, previous


def _cell_rectangles(cells):
    rows = {}
    for row, column in cells:
        rows.setdefault(row, []).append(column)

    active = {}
    for row in sorted(rows):
        current_keys = set()
        for start, end in _contiguous_ranges(rows[row]):
            key = (start, end)
            current_keys.add(key)
            if key in active and active[key][1] == row - 1:
                active[key][1] = row
            else:
                if key in active:
                    top, bottom = active.pop(key)
                    yield top, start, bottom, end
                active[key] = [row, row]

        for key in list(active):
            if key not in current_keys and active[key][1] < row:
                top, bottom = active.pop(key)
                start, end = key
                yield top, start, bottom, end

    for key, (top, bottom) in active.items():
        start, end = key
        yield top, start, bottom, end


def chain_pair_options(structure_model) -> Tuple[Tuple[str, str], ...]:
    chain_ids = _chain_ids(structure_model)
    pairs = []
    for index, chain_a in enumerate(chain_ids):
        for chain_b in chain_ids[index + 1 :]:
            pairs.append((chain_a, chain_b))
    return tuple(pairs)


def _residues_with_plddt_at_or_above(structure_model, min_plddt: float):
    if structure_model is None or getattr(structure_model, "deleted", False):
        return []
    residues = []
    for residue in getattr(structure_model, "residues", []):
        value = _residue_plddt(residue)
        if value is not None and value >= min_plddt:
            residues.append(residue)
    return residues


def _residue_plddt(residue) -> Optional[float]:
    if residue is None or getattr(residue, "deleted", False):
        return None
    try:
        atom = residue.principal_atom
        if atom is not None:
            value = float(atom.bfactor)
            if value == value:
                return value
    except Exception:
        pass
    try:
        atoms = residue.atoms
        values = [
            float(atom.bfactor)
            for atom in atoms
            if atom is not None and not getattr(atom, "deleted", False)
        ]
    except Exception:
        values = []
    values = [value for value in values if value == value]
    if not values:
        return None
    return sum(values) / len(values)


def _residues_with_min_interchain_pae_below(pae, max_pae: float, chain_pair=None):
    residues, _cells = _interchain_pae_filter(pae, max_pae, chain_pair)
    return residues


def _interchain_pae_filter(pae, max_pae: float, chain_pair=None):
    matrix = pae.pae_matrix
    rows = pae.row_residues_or_atoms()
    row_residues = [_residue_for_pae_row(row) for row in rows]
    selected_residue_set = set()
    cells = set()
    allowed_chain_pairs = _allowed_chain_pairs(chain_pair)
    size = len(row_residues)
    for i in range(size):
        ri = row_residues[i]
        if ri is None or getattr(ri, "deleted", False):
            continue
        for j in range(size):
            if j == i:
                continue
            rj = row_residues[j]
            if rj is None or getattr(rj, "deleted", False):
                continue
            if not _chains_allowed(ri.chain_id, rj.chain_id, allowed_chain_pairs):
                continue
            pair_pae = float(matrix[i, j])
            if pair_pae < max_pae:
                cells.add((i, j))
                selected_residue_set.add(ri)
                selected_residue_set.add(rj)
    residues = []
    seen = set()
    for residue in row_residues:
        if residue in selected_residue_set and residue not in seen:
            residues.append(residue)
            seen.add(residue)
    return residues, cells


def _allowed_chain_pairs(chain_pair):
    if chain_pair is None:
        return None
    chain_a, chain_b = chain_pair
    return {tuple(sorted((chain_a, chain_b)))}


def _chains_allowed(chain_a: str, chain_b: str, allowed_chain_pairs) -> bool:
    if chain_a == chain_b:
        return False
    if allowed_chain_pairs is None:
        return True
    return tuple(sorted((chain_a, chain_b))) in allowed_chain_pairs


def _chain_pair_scope_label(chain_pair) -> str:
    if chain_pair is None:
        return "any inter-chain pair"
    return f"{chain_pair[0]}-{chain_pair[1]}"


def _residue_for_pae_row(row):
    from chimerax.atomic import Atom, Residue

    if isinstance(row, Residue):
        return row
    if isinstance(row, Atom):
        return row.residue
    return None


def _align_structures(session, structures, requested_chain: Optional[str]) -> None:
    structures = [
        structure
        for structure in structures
        if structure is not None and not getattr(structure, "deleted", False)
    ]
    if len(structures) < 2:
        return

    target = structures[0]
    target_chain = _resolve_chain_id(target, requested_chain)
    target_atoms = _atoms_for_chain(target, target_chain)
    target_spec = _model_spec(target)
    if target_atoms is None or len(target_atoms) == 0 or target_spec is None:
        session.logger.warning(
            f"Could not align AF models: no atoms found for reference chain {target_chain}."
        )
        return

    for structure in structures[1:]:
        model_spec = _model_spec(structure)
        if model_spec is None:
            continue
        chain_id = "?"
        try:
            chain_id = _resolve_chain_id(structure, requested_chain)
            moving_atoms = _atoms_for_chain(structure, chain_id)
            if moving_atoms is None or len(moving_atoms) == 0:
                raise UserError(f"no atoms found for chain {chain_id}")
            _match_chain_atoms(session, moving_atoms, target_atoms)
        except Exception as err:
            name = getattr(structure, "name", model_spec)
            session.logger.warning(
                f"Could not align {name} chain {chain_id} to "
                f"{target_spec} chain {target_chain}: {err}"
            )


def _atoms_for_chain(structure_model, chain_id: str):
    if structure_model is None or getattr(structure_model, "deleted", False):
        return None
    try:
        for chain in structure_model.chains:
            if chain.chain_id == chain_id:
                return chain.existing_residues.atoms
    except Exception:
        pass
    try:
        residues = structure_model.residues
        return residues[residues.chain_ids == chain_id].atoms
    except Exception:
        return None


def _match_chain_atoms(session, moving_atoms, target_atoms) -> None:
    try:
        from chimerax.match_maker.match import CP_SPECIFIC_SPECIFIC, cmd_match

        cmd_match(
            session,
            moving_atoms,
            to=target_atoms,
            pairing=CP_SPECIFIC_SPECIFIC,
            show_alignment=False,
            log_parameters=False,
        )
    except Exception:
        moving_spec = _atom_collection_spec(moving_atoms)
        target_spec = _atom_collection_spec(target_atoms)
        if moving_spec is None or target_spec is None:
            raise
        run(
            session,
            "matchmaker "
            f"{moving_spec} to {target_spec} pairing ss "
            "showAlignment false logParameters false",
        )


def _atom_collection_spec(atoms) -> Optional[str]:
    try:
        structures = atoms.structures.unique()
        chain_ids = atoms.residues.unique_chain_ids
    except Exception:
        return None
    if len(structures) != 1 or len(chain_ids) != 1:
        return None
    model_spec = _model_spec(structures[0])
    if model_spec is None:
        return None
    from chimerax.atomic import Chain

    return f"{model_spec}{Chain.chain_id_to_atom_spec(chain_ids[0])}"


def _group_structures(session, structures, group_name: str):
    structures = [
        structure
        for structure in structures
        if structure is not None and not getattr(structure, "deleted", False)
    ]
    if not structures:
        return None
    try:
        return session.models.add_group(structures, name=group_name)
    except Exception as err:
        session.logger.warning(f"Could not group opened AF models: {err}")
        return None


def _activate_pair(display_pairs, current_index: int, show_all: bool = False) -> None:
    for pair_index, display_pair in enumerate(display_pairs):
        visible = show_all or pair_index == current_index
        model = display_pair.get("model")
        plot = display_pair.get("plot")
        if model is not None and not getattr(model, "deleted", False):
            model.display = visible
        if plot is not None and not _plot_closed(plot):
            _disable_pae_drag_coloring(plot)
            plot.display(visible)


def _plot_closed(plot) -> bool:
    closed = getattr(plot, "closed", None)
    return bool(closed()) if callable(closed) else False


def _resolve_chain_id(structure_model, requested_chain: Optional[str]) -> str:
    chain_ids = _chain_ids(structure_model)
    if requested_chain:
        if chain_ids and requested_chain not in chain_ids:
            raise UserError(
                f"Chain '{requested_chain}' was not found. Available chains: "
                + ", ".join(chain_ids)
            )
        return requested_chain
    if chain_ids:
        return chain_ids[0]
    return "A"


def _chain_ids(structure_model) -> List[str]:
    if structure_model is None:
        return []
    try:
        ids = {chain.chain_id for chain in structure_model.chains if chain.chain_id}
    except Exception:
        return []
    return sorted(ids)


def _last_atomic_structure(session):
    try:
        models = list(session.models.list())
    except Exception:
        return None
    for model in reversed(models):
        if hasattr(model, "atoms") and hasattr(model, "chains"):
            return model
    return None


def _model_spec(structure_model) -> Optional[str]:
    if structure_model is None:
        return None
    id_string = getattr(structure_model, "id_string", None)
    if not id_string:
        return None
    return "#" + id_string


def _make_output_dir(directory: Path, mode: str, prediction_filter: str) -> Path:
    prediction = _safe_token(prediction_filter) if prediction_filter else _safe_token(directory.name)
    output_dir = directory / "analysis" / prediction / mode
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _series_title(mode: str, prediction_filter: str, directory: Path) -> str:
    subject = prediction_filter or directory.name
    return f"{_mode_label(mode)} {subject}"


def _mode_label(mode: str) -> str:
    labels = {
        "af3": "AF3 all hits",
        "af3-all": "AF3 all hits",
        "af3-top": "AF3 top hit",
        "af2-all": "AF2 all hits",
        "af2-top": "AF2 top hit",
    }
    return labels.get(mode, mode)


def _format_pair(pair: PredictionPair, root: Path) -> str:
    return (
        f"{_pair_display_label(pair)}\n"
        f"  structure: {_relative(pair.structure_path, root)}\n"
        f"  data:      {_relative(pair.score_path, root)}"
    )


def _pair_display_label(pair: PredictionPair) -> str:
    if pair.confidence_missing:
        return f"{pair.label} (confidence missing)"
    if pair.confidence_score is None:
        return pair.label
    return f"{pair.label} (confidence {_format_confidence(pair.confidence_score)})"


def _format_confidence(score) -> str:
    if score is None:
        return "not available"
    return f"{float(score):.4g}"


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _safe_token(text: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
    return token.strip("._-") or "prediction"


def _natural_key(value) -> tuple:
    text = str(value)
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text))
