from datetime import datetime

from chimerax.core.commands import quote_if_necessary, run
from chimerax.core.errors import UserError


def selected_chain_summary(session):
    chain = _selected_chain(session, required=False)
    if chain is None:
        return "Select exactly one protein chain or enter model and chain manually."
    return f"Selected chain: {_chain_label(chain)}"


def selected_chain_target(session):
    chain = _selected_chain(session, required=False)
    if chain is None:
        return {"model_id": "", "chain_id": ""}
    model_id = ".".join(str(part) for part in getattr(chain.structure, "id", ()))
    return {"model_id": model_id, "chain_id": getattr(chain, "chain_id", "")}


def apply_missense_scores(
    session, uniprot_id, *, model_id=None, chain_id=None, label_residues=False
):
    chain = _resolve_chain(session, model_id=model_id, chain_id=chain_id)
    uniprot_id = uniprot_id.strip()
    if not uniprot_id:
        raise UserError("A human UniProt accession or entry name is required.")

    mutation_set_name = _mutation_set_name(uniprot_id, chain)
    avg_attr_name = "amiss_avg"

    try:
        from chimerax.mutation_scores.alpha_missense import fetch_alpha_missense_scores
        from chimerax.mutation_scores.ms_data import (
            mutation_scores_close,
            mutation_scores_structure,
        )
        from chimerax.mutation_scores.ms_define import mutation_scores_define

        _mset, message = fetch_alpha_missense_scores(
            session, uniprot_id, identifier=mutation_set_name
        )
        session.logger.info(message)

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

        chain_spec = chain.atomspec
        run(
            session,
            f"color byattribute r:{avg_attr_name} {chain_spec} "
            "target csab palette bluered range 0,1",
        )
        run(session, f"cartoon byattribute r:{avg_attr_name} {chain_spec}")

        if label_residues:
            run(
                session,
                "mutationscores label "
                f"{chain_spec} amiss mutationSet {quote_if_necessary(mutation_set_name)} "
                "height 1.5 palette bluered",
            )

        result = {
            "uniprot_id": uniprot_id,
            "chain_label": _chain_label(chain),
            "mutation_set_name": mutation_set_name,
            "attribute_name": avg_attr_name,
            "labels_added": label_residues,
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


def _mutation_set_name(uniprot_id, chain):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    chain_id = getattr(chain, "chain_id", "chain")
    model_id = ".".join(str(part) for part in getattr(chain.structure, "id", ()))
    safe_uniprot = "".join(
        char if char.isalnum() or char in "._-" else "_" for char in uniprot_id
    )
    return f"amiss_{safe_uniprot}_{model_id}_{chain_id}_{timestamp}"
