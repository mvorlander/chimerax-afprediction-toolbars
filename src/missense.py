from datetime import datetime
from pathlib import Path
import shlex

from chimerax.core.commands import quote_if_necessary, run
from chimerax.core.errors import UserError


def selected_chain_summary(session):
    chain = _selected_chain(session, required=False)
    if chain is None:
        return (
            "Select exactly one protein chain, or enter a model id. "
            "UniProt IDs are read from mmCIF metadata when available."
        )
    uniprot_id = _uniprot_id_for_chain(chain)
    suffix = f" (UniProt {uniprot_id})" if uniprot_id else " (UniProt not found)"
    return f"Selected chain: {_chain_label(chain)}{suffix}"


def selected_chain_target(session):
    chain = _selected_chain(session, required=False)
    if chain is None:
        return {"model_id": "", "chain_id": ""}
    model_id = ".".join(str(part) for part in getattr(chain.structure, "id", ()))
    return {"model_id": model_id, "chain_id": getattr(chain, "chain_id", "")}


def apply_missense_scores(
    session,
    uniprot_id,
    *,
    model_id=None,
    chain_id=None,
    label_residues=False,
    show_color_key=True,
    color_range=(0.0, 1.0),
):
    chain = _resolve_chain(session, model_id=model_id, chain_id=chain_id)
    uniprot_id = (uniprot_id or "").strip() or _uniprot_id_for_chain(chain)
    if not uniprot_id:
        raise UserError(
            "Could not find a UniProt accession for the selected chain in the "
            "structure metadata. Enter a human UniProt accession manually."
        )

    mutation_set_name = _mutation_set_name(uniprot_id, chain)
    avg_attr_name = "amiss_avg"

    try:
        from chimerax.mutation_scores.alpha_missense import fetch_alpha_missense_scores

        _mset, message = fetch_alpha_missense_scores(
            session, uniprot_id, identifier=mutation_set_name
        )
        session.logger.info(message)

        _map_chain_with_mutation_set(
            session,
            chain,
            mutation_set_name,
            avg_attr_name,
            label_residues=label_residues,
            show_color_key=show_color_key,
            color_range=color_range,
        )

        result = {
            "uniprot_id": uniprot_id,
            "chain_label": _chain_label(chain),
            "target_specs": [chain.atomspec],
            "mutation_set_name": mutation_set_name,
            "attribute_name": avg_attr_name,
            "labels_added": label_residues,
            "color_key_shown": show_color_key,
            "color_range": _normalized_score_range(color_range),
        }
        session.logger.status(
            f"Applied AlphaMissense mapping from {uniprot_id} to {_chain_label(chain)}.",
            log=True,
        )
        return result
    finally:
        try:
            from chimerax.mutation_scores.ms_data import mutation_scores_close

            mutation_scores_close(session, mutation_set_name)
        except Exception:
            pass


def apply_missense_scores_to_structure(
    session,
    uniprot_id,
    *,
    model_id=None,
    label_residues=False,
    show_color_key=True,
    color_range=(0.0, 1.0),
):
    structure = _resolve_structure(session, model_id=model_id)
    chains = _protein_chains(structure)
    if not chains:
        raise UserError(f"No protein chains were found in {_structure_label(structure)}.")

    uniprot_override = (uniprot_id or "").strip()
    avg_attr_name = "amiss_avg"
    mapped = []
    failed = []
    chain_uniprot_ids = {}
    targets_by_uniprot = _chains_by_uniprot(chains, uniprot_override)

    for chain in chains:
        chain_label = _chain_label(chain)
        chain_uniprot = uniprot_override or _uniprot_id_for_chain(chain)
        if chain_uniprot:
            chain_uniprot_ids[chain_label] = chain_uniprot
        else:
            failed.append(
                (
                    chain_label,
                    "no UniProt accession found in mmCIF metadata",
                )
            )

    if not targets_by_uniprot:
        raise UserError(
            "Could not find UniProt accessions for any protein chain in "
            f"{_structure_label(structure)}. Enter a human UniProt accession "
            "manually to use it as an override for all chains."
        )

    from chimerax.mutation_scores.alpha_missense import fetch_alpha_missense_scores

    for target_uniprot, target_chains in targets_by_uniprot.items():
        mutation_set_name = _structure_mutation_set_name(target_uniprot, structure)
        _mset, message = fetch_alpha_missense_scores(
            session, target_uniprot, identifier=mutation_set_name
        )
        session.logger.info(message)

        try:
            for chain in target_chains:
                try:
                    _map_chain_with_mutation_set(
                        session,
                        chain,
                        mutation_set_name,
                        avg_attr_name,
                        label_residues=label_residues,
                        show_color_key=show_color_key,
                        color_range=color_range,
                    )
                except Exception as err:
                    failed.append((_chain_label(chain), str(err)))
                    try:
                        session.logger.warning(
                            f"Could not map AlphaMissense to {_chain_label(chain)}: {err}"
                        )
                    except Exception:
                        pass
                else:
                    mapped.append(_chain_label(chain))
        finally:
            try:
                from chimerax.mutation_scores.ms_data import mutation_scores_close

                mutation_scores_close(session, mutation_set_name)
            except Exception:
                pass

    if not mapped:
        details = "; ".join(f"{label}: {error}" for label, error in failed[:5])
        raise UserError(
            "AlphaMissense mapping failed for every protein chain in "
            f"{_structure_label(structure)}. {details}"
        )

    result = {
        "uniprot_id": uniprot_override,
        "structure_label": _structure_label(structure),
        "attribute_name": avg_attr_name,
        "labels_added": label_residues,
        "color_key_shown": show_color_key,
        "color_range": _normalized_score_range(color_range),
        "mapped_chain_labels": mapped,
        "target_specs": [
            chain.atomspec
            for target_chains in targets_by_uniprot.values()
            for chain in target_chains
            if _chain_label(chain) in mapped
        ],
        "failed_chains": failed,
        "chain_uniprot_ids": chain_uniprot_ids,
        "used_uniprot_override": bool(uniprot_override),
    }
    source = uniprot_override or "mmCIF chain metadata"
    session.logger.status(
        "Applied AlphaMissense mapping from "
        f"{source} to {len(mapped)} chain(s) in {_structure_label(structure)}.",
        log=True,
    )
    return result


def _map_chain_with_mutation_set(
    session,
    chain,
    mutation_set_name,
    avg_attr_name,
    *,
    label_residues=False,
    show_color_key=True,
    color_range=(0.0, 1.0),
):
    from chimerax.mutation_scores.ms_data import mutation_scores_structure
    from chimerax.mutation_scores.ms_define import mutation_scores_define

    mutation_scores_structure(
        session,
        [chain],
        allow_mismatches=True,
        minimum_percent_identity=20,
        align_sequences=True,
        mutation_set=mutation_set_name,
    )
    mutation_scores_define(
        session,
        avg_attr_name,
        from_score_name="amiss",
        mutation_set=mutation_set_name,
        combine="mean",
        set_attribute=True,
    )

    apply_missense_coloring(
        session,
        [chain.atomspec],
        attr_name=avg_attr_name,
        color_range=color_range,
        show_color_key=show_color_key,
    )

    if label_residues:
        run(
            session,
            "mutationscores label "
            f"{chain.atomspec} amiss mutationSet {quote_if_necessary(mutation_set_name)} "
            "height 1.5 palette bluered",
        )


def apply_missense_coloring(
    session,
    target_specs,
    *,
    attr_name="amiss_avg",
    color_range=(0.0, 1.0),
    show_color_key=True,
):
    score_min, score_max = _normalized_score_range(color_range)
    specs = [str(spec).strip() for spec in target_specs if str(spec).strip()]
    if not specs:
        raise UserError("No mapped AlphaMissense chains are available to recolor.")

    range_text = f"{score_min:g},{score_max:g}"
    for index, target_spec in enumerate(specs):
        run(
            session,
            f"color byattribute r:{attr_name} {target_spec} "
            f"target csab palette bluered range {range_text}"
            + (" key true" if show_color_key and index == 0 else ""),
        )
        run(session, f"cartoon byattribute r:{attr_name} {target_spec}")


def _normalized_score_range(color_range):
    try:
        score_min, score_max = color_range
        score_min = float(score_min)
        score_max = float(score_max)
    except Exception:
        raise UserError("AlphaMissense color range must contain two numeric values.")
    if score_min >= score_max:
        raise UserError("AlphaMissense color range minimum must be below maximum.")
    return score_min, score_max


def _resolve_chain(session, *, model_id=None, chain_id=None):
    model_id = (model_id or "").strip()
    chain_id = (chain_id or "").strip()
    if not model_id and not chain_id:
        return _selected_chain(session, required=True)
    if not model_id or not chain_id:
        raise UserError(
            "Specify both model id and chain id, or leave both empty and use a selection."
        )

    structure = _find_structure(session, model_id)
    for chain in structure.chains:
        if getattr(chain, "chain_id", None) == chain_id:
            return chain
    raise UserError(f"Model #{model_id} has no chain {chain_id}.")


def _resolve_structure(session, *, model_id=None):
    model_id = (model_id or "").strip()
    if model_id:
        return _find_structure(session, model_id)

    selected_structure = _selected_structure(session)
    if selected_structure is not None:
        return selected_structure

    structures = _open_structures(session)
    if len(structures) == 1:
        return structures[0]
    if not structures:
        raise UserError("No atomic structure is open.")
    raise UserError(
        "Several atomic structures are open. Enter a model id before applying "
        "AlphaMissense to all chains."
    )


def _find_structure(session, model_id):
    try:
        wanted = tuple(int(part) for part in model_id.split(".") if part)
    except ValueError:
        raise UserError(f'Invalid model id "{model_id}".')
    if not wanted:
        raise UserError(f'Invalid model id "{model_id}".')

    for model in session.models.list():
        if getattr(model, "id", None) == wanted and hasattr(model, "chains"):
            return model
    raise UserError(f"No atomic structure with model id #{model_id} is open.")


def _selected_structure(session):
    from chimerax.atomic import selected_chains

    chains = selected_chains(session)
    structures = {chain.structure for chain in chains}
    if len(structures) == 1:
        return next(iter(structures))
    return None


def _open_structures(session):
    return [
        model
        for model in session.models.list()
        if hasattr(model, "chains") and hasattr(model, "atoms")
    ]


def _protein_chains(structure):
    return [chain for chain in structure.chains if _is_protein_chain(chain)]


def _is_protein_chain(chain):
    residues = getattr(chain, "residues", [])
    for residue in residues:
        name = str(getattr(residue, "name", "")).upper()
        if name in _AMINO_ACID_RESIDUE_NAMES:
            return True
    return False


def _chains_by_uniprot(chains, uniprot_override):
    grouped = {}
    for chain in chains:
        uniprot_id = uniprot_override or _uniprot_id_for_chain(chain)
        if not uniprot_id:
            continue
        grouped.setdefault(uniprot_id, []).append(chain)
    return grouped


def _uniprot_id_for_chain(chain):
    for attr_name in (
        "uniprot_id",
        "uniprot",
        "uniprot_accession",
        "db_accession",
        "database_accession",
    ):
        value = getattr(chain, attr_name, None)
        if value:
            return str(value).strip()

    structure = getattr(chain, "structure", None)
    if structure is None:
        return ""
    mapping = _structure_uniprot_map(structure)
    chain_ids = [
        getattr(chain, "chain_id", None),
        getattr(chain, "id", None),
        getattr(chain, "name", None),
    ]
    for chain_id in chain_ids:
        if chain_id is None:
            continue
        value = mapping.get(str(chain_id))
        if value:
            return value
    return ""


def _structure_uniprot_map(structure):
    cached = getattr(structure, "_af_toolbar_uniprot_map", None)
    if cached is not None:
        return cached

    mapping = {}
    path = _structure_source_path(structure)
    if path is not None:
        try:
            mapping = _uniprot_map_from_mmcif(path)
        except Exception:
            mapping = {}

    try:
        setattr(structure, "_af_toolbar_uniprot_map", mapping)
    except Exception:
        pass
    return mapping


def _structure_source_path(structure):
    for attr_name in (
        "filename",
        "file_name",
        "path",
        "filepath",
        "data_path",
        "opened_data_path",
        "_filename",
    ):
        value = getattr(structure, attr_name, None)
        if not value:
            continue
        path = Path(str(value)).expanduser()
        if path.is_file():
            return path
    return None


def _uniprot_map_from_mmcif(path):
    loops = _mmcif_loops(path)
    refs = {}
    chain_map = {}
    entity_chain_map = {}

    for tags, rows in loops:
        if not tags:
            continue
        category = tags[0].split(".", 1)[0]
        tag_names = [_tag_name(tag) for tag in tags]
        if category == "_struct_ref":
            for row in rows:
                record = dict(zip(tag_names, row))
                ref_id = _clean_mmcif_value(record.get("id"))
                accession = _clean_mmcif_value(record.get("pdbx_db_accession"))
                db_name = _clean_mmcif_value(record.get("db_name")).upper()
                entity_id = _clean_mmcif_value(record.get("entity_id"))
                if accession and _is_uniprot_db_name(db_name):
                    refs[ref_id] = {"accession": accession, "entity_id": entity_id}
        elif category == "_entity_poly":
            for row in rows:
                record = dict(zip(tag_names, row))
                entity_id = _clean_mmcif_value(record.get("entity_id"))
                strands = _split_chain_list(record.get("pdbx_strand_id"))
                if entity_id and strands:
                    entity_chain_map.setdefault(entity_id, set()).update(strands)
        elif category == "_pdbx_poly_seq_scheme":
            for row in rows:
                record = dict(zip(tag_names, row))
                entity_id = _clean_mmcif_value(record.get("entity_id"))
                chain_ids = [
                    _clean_mmcif_value(record.get("pdb_strand_id")),
                    _clean_mmcif_value(record.get("auth_asym_id")),
                    _clean_mmcif_value(record.get("asym_id")),
                ]
                for chain_id in chain_ids:
                    if entity_id and chain_id:
                        entity_chain_map.setdefault(entity_id, set()).add(chain_id)

    for tags, rows in loops:
        if not tags or tags[0].split(".", 1)[0] != "_struct_ref_seq":
            continue
        tag_names = [_tag_name(tag) for tag in tags]
        for row in rows:
            record = dict(zip(tag_names, row))
            ref = refs.get(_clean_mmcif_value(record.get("ref_id")))
            if ref is None:
                continue
            chains = _split_chain_list(record.get("pdbx_strand_id"))
            if not chains:
                chains = sorted(entity_chain_map.get(ref.get("entity_id"), []))
            for chain_id in chains:
                chain_map[chain_id] = ref["accession"]

    for ref in refs.values():
        for chain_id in entity_chain_map.get(ref.get("entity_id"), []):
            chain_map.setdefault(chain_id, ref["accession"])
    return chain_map


def _mmcif_loops(path):
    tokens = _mmcif_tokens(path)
    loops = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.lower() != "loop_":
            index += 1
            continue
        index += 1
        tags = []
        while index < len(tokens) and tokens[index].startswith("_"):
            tags.append(tokens[index])
            index += 1
        values = []
        while index < len(tokens):
            next_token = tokens[index]
            next_lower = next_token.lower()
            if (
                next_lower == "loop_"
                or next_lower.startswith("data_")
                or next_token.startswith("_")
            ):
                break
            values.append(next_token)
            index += 1
        if tags and values:
            width = len(tags)
            rows = [
                values[offset : offset + width]
                for offset in range(0, len(values) - len(values) % width, width)
            ]
            loops.append((tags, rows))
    return loops


def _mmcif_tokens(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tokens = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        if line.startswith(";"):
            block = []
            first = line[1:]
            if first:
                block.append(first)
            index += 1
            while index < len(lines):
                if lines[index].startswith(";"):
                    index += 1
                    break
                block.append(lines[index])
                index += 1
            tokens.append("\n".join(block))
            continue
        tokens.extend(_tokenize_mmcif_line(line))
        index += 1
    return tokens


def _tokenize_mmcif_line(line):
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _tag_name(tag):
    return tag.rsplit(".", 1)[-1]


def _clean_mmcif_value(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text in ("?", "."):
        return ""
    return text


def _is_uniprot_db_name(db_name):
    normalized = db_name.replace("-", "").replace("_", "")
    return normalized in {"UNP", "UNIPROT", "SWISSPROT", "TREMBL"}


def _split_chain_list(value):
    text = _clean_mmcif_value(value)
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _selected_chain(session, *, required):
    from chimerax.atomic import selected_chains

    chains = selected_chains(session)
    if len(chains) == 1:
        return chains[0]
    if required:
        raise UserError(
            "Select residues from exactly one chain before applying missense mapping."
        )
    return None


def _chain_label(chain):
    structure_name = getattr(chain.structure, "name", "structure")
    chain_id = getattr(chain, "chain_id", "?")
    return f"{structure_name} /{chain_id}"


def _structure_label(structure):
    name = getattr(structure, "name", "structure")
    model_id = ".".join(str(part) for part in getattr(structure, "id", ()))
    return f"{name} #{model_id}" if model_id else name


def _mutation_set_name(uniprot_id, chain):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    chain_id = getattr(chain, "chain_id", "chain")
    model_id = ".".join(str(part) for part in getattr(chain.structure, "id", ()))
    safe_uniprot = "".join(
        char if char.isalnum() or char in "._-" else "_" for char in uniprot_id
    )
    return f"amiss_{safe_uniprot}_{model_id}_{chain_id}_{timestamp}"


def _structure_mutation_set_name(uniprot_id, structure):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    model_id = ".".join(str(part) for part in getattr(structure, "id", ()))
    safe_uniprot = "".join(
        char if char.isalnum() or char in "._-" else "_" for char in uniprot_id
    )
    return f"amiss_{safe_uniprot}_{model_id}_all_chains_{timestamp}"


_AMINO_ACID_RESIDUE_NAMES = {
    "ALA",
    "ARG",
    "ASN",
    "ASP",
    "CYS",
    "GLN",
    "GLU",
    "GLY",
    "HIS",
    "ILE",
    "LEU",
    "LYS",
    "MET",
    "PHE",
    "PRO",
    "SER",
    "THR",
    "TRP",
    "TYR",
    "VAL",
    "MSE",
    "SEC",
    "PYL",
    "ASX",
    "GLX",
    "UNK",
}
