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


@dataclass(frozen=True)
class PredictionPair:
    label: str
    structure_path: Path
    score_path: Path


@dataclass(frozen=True)
class AnalysisResult:
    mode: str
    run_label: str
    input_directory: Path
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
        chain_id = _resolve_chain_id(structure_model, requested_chain)
        model_spec = _model_spec(structure_model)
        _run_contact_workflow(session, pair, output_dir, chain_id, model_spec)
        display_pairs.append({"label": pair.label, "model": structure_model, "pae": pae})
        structures.append(structure_model)
        pair_summaries.append(
            {
                "label": pair.label,
                "structure": str(pair.structure_path),
                "score_data": str(pair.score_path),
                "contact_chain": chain_id,
                "model_spec": model_spec,
            }
        )

    _align_structures(session, structures, requested_chain)
    model_group = _group_structures(session, structures, run_label)
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
        f"Analysis files were written to:\n{output_dir}"
    )
    return AnalysisResult(
        mode=mode,
        run_label=run_label,
        input_directory=directory,
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

    pairs = []
    if top_only:
        labels = [_top_af3_model_label(directory, labels, prediction_filter)]

    for label in labels:
        structure = _one_file(structures_by_id[label], "AF3 structure", label, directory)
        score = _one_file(scores_by_id[label], "AF3 data JSON", label, directory)
        pairs.append(PredictionPair(f"model_{label}", structure, score))
    return pairs


def _top_af3_model_label(
    directory: Path, labels: List[Union[str, int]], prediction_filter: str
) -> Union[str, int]:
    if "single" in labels and len(labels) == 1:
        return "single"

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


def _run_contact_workflow(
    session,
    pair: PredictionPair,
    output_dir: Path,
    chain_id: str,
    model_spec: Optional[str],
) -> None:
    label = _safe_token(pair.label)
    structure_spec = model_spec or "last-opened"
    chain_spec = f"{structure_spec}&/{chain_id}"
    contact_file = output_dir / f"af_contacts_{label}.txt"
    interface_name = f"interface_residues_{label}"
    interface_file = output_dir / f"interface_residues_{label}_buriedArea_300.txt"
    _unlink_if_exists(contact_file)
    _unlink_if_exists(interface_file)

    commands = [
        "hide",
        "show c",
        "alphafold contacts "
        + chain_spec
        + " outputFile "
        + quote_if_necessary(str(contact_file)),
        "select " + structure_spec + "&pbonds",
        (
            'label sel pseudobonds text '
            '"{0.atoms[0].residue.name} {0.atoms[0].residue.number} to '
            '{0.atoms[1].residue.name} {0.atoms[1].residue.number}"'
        ),
        "interfaces select "
        + chain_spec
        + " contacting "
        + structure_spec
        + "&~/"
        + chain_id
        + " bothSides true",
        "name frozen " + interface_name + " sel",
        "show " + interface_name,
        "style " + interface_name + " ball",
        "info residues "
        + interface_name
        + " saveFile "
        + quote_if_necessary(str(interface_file)),
        "rainbow " + structure_spec + " chains palette bupu",
        "color byhetero",
    ]
    for command in commands:
        run(session, command)


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
        "",
        "Opened pairs:",
    ]
    for pair in pairs:
        lines.extend(
            [
                f"- {pair['label']}",
                f"  structure: {pair['structure']}",
                f"  data: {pair['score_data']}",
                f"  contact chain: {pair['contact_chain']}",
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
) -> str:
    structure = getattr(pae, "structure", None)
    model_spec = _model_spec(structure)
    if structure is None or model_spec is None:
        raise UserError("The active PAE plot is not associated with an open structure.")

    targets = ("atoms", "bonds", "pseudobonds", "cartoons", "surfaces")
    if mode == "show_all":
        for target in ("atoms", "bonds", "pseudobonds", "surfaces"):
            run(session, f"hide {model_spec} {target}")
        run(session, f"show {model_spec} cartoons")
        return f"Restored cartoon-only display for {structure}."

    residues = _residues_with_min_interchain_pae_below(pae, max_pae, chain_pair)
    scope = _chain_pair_scope_label(chain_pair)
    if not residues:
        return (
            f"No residues with minimum {scope} PAE < {max_pae:g} were found."
        )

    from chimerax.atomic import concise_residue_spec

    residue_spec = concise_residue_spec(session, residues)
    if mode == "select":
        run(session, f"select {residue_spec}")
        return (
            f"Selected {len(residues)} residue(s) with minimum {scope} "
            f"PAE < {max_pae:g}."
        )
    elif mode == "show_only":
        for target in targets:
            run(session, f"hide {model_spec} {target}")
        run(session, f"show {residue_spec} cartoons")
        action = "Showing only"
    else:
        raise UserError(f"Unknown PAE visibility mode: {mode}")

    return (
        f"{action} {len(residues)} residue(s) with minimum {scope} "
        f"PAE < {max_pae:g}."
    )


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


def chain_pair_options(structure_model) -> Tuple[Tuple[str, str], ...]:
    chain_ids = _chain_ids(structure_model)
    pairs = []
    for index, chain_a in enumerate(chain_ids):
        for chain_b in chain_ids[index + 1 :]:
            pairs.append((chain_a, chain_b))
    return tuple(pairs)


def _residues_with_min_interchain_pae_below(pae, max_pae: float, chain_pair=None):
    matrix = pae.pae_matrix
    rows = pae.row_residues_or_atoms()
    row_residues = [_residue_for_pae_row(row) for row in rows]
    residues = []
    allowed_chain_pairs = _allowed_chain_pairs(chain_pair)
    size = len(row_residues)
    for i in range(size):
        ri = row_residues[i]
        if ri is None or getattr(ri, "deleted", False):
            continue
        min_interchain_pae = None
        for j in range(size):
            if j == i:
                continue
            rj = row_residues[j]
            if rj is None or getattr(rj, "deleted", False):
                continue
            if not _chains_allowed(ri.chain_id, rj.chain_id, allowed_chain_pairs):
                continue
            pair_pae = min(float(matrix[i, j]), float(matrix[j, i]))
            if min_interchain_pae is None or pair_pae < min_interchain_pae:
                min_interchain_pae = pair_pae
                if min_interchain_pae < max_pae:
                    residues.append(ri)
                    break
    return residues


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
        return "inter-chain"
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
    target_spec = _model_spec(target)
    if target_spec is None:
        return
    target_chain = _resolve_chain_id(target, requested_chain)
    target_chain_spec = f"{target_spec}/{target_chain}"

    for structure in structures[1:]:
        model_spec = _model_spec(structure)
        if model_spec is None:
            continue
        try:
            chain_id = _resolve_chain_id(structure, requested_chain)
            run(session, f"mm {model_spec}/{chain_id} to {target_chain_spec}")
        except Exception as err:
            name = getattr(structure, "name", model_spec)
            session.logger.warning(f"Could not align {name} to {target_spec}: {err}")


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
        f"{pair.label}\n"
        f"  structure: {_relative(pair.structure_path, root)}\n"
        f"  data:      {_relative(pair.score_path, root)}"
    )


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
