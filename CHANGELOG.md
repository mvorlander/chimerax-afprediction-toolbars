# Changelog

## 1.3.4

- Added a `Live PAE highlight` toggle to turn live structure selection and PAE
  plot overlays on or off while keeping cutoff-based actions available.

## 1.3.3

- Replaced the inter-chain PAE cutoff text box with a live slider.
- Added live structure selection and PAE plot overlays for residues below the
  current inter-chain PAE cutoff.
- Renamed `Reset Display` to `Reset Active Run` and made it restore contact
  side chains as part of the initial display.
- Added a compact active-run status strip with current model, cutoff, chain-pair
  filter, highlighted residue count, and last action.
- Show missing-confidence badges when AF3 all-hit ranking metadata is incomplete.
- Restore side-chain display for residues involved in AlphaFold contact
  pseudobonds.

## 1.3.2

- Add a `Reset Display` button that restores the active prediction run to its
  initial model/PAE display state.
- Display AF3 metadata confidence scores in the model selector and order AF3
  all-hit models by descending confidence score when available.
- Added a monthly GitHub Actions compatibility check for new ChimeraX production
  releases.
- Moved the README Quickstart section to the top of the document.
- Added a bottom-of-README Quickstart section with concise wheel and source
  install instructions.
- Clarified that users should choose only one installation option: release wheel
  or source install.
- Reordered the README installation section to make the release wheel the
  preferred GitHub-facing installation route, with source install documented as
  an alternative.

## 1.3.1

- Added GitHub release wheel installation as the recommended non-developer path.
- Added double-click macOS and Windows installers for users who do not want to
  use the command line.
- Added no-terminal installation instructions.

## 1.3.0

- Added per-chain-pair inter-chain PAE controls in the AF model/PAE controller.
- Added `Copy Output Path` and `Close Run` controller actions.
- Added stable `analysis_summary.json` and `analysis_summary.txt` files for each run.
- Added transparent PNG and ChimeraX session saving to the active run output folder.
- Made analysis output folders stable instead of timestamped. Optional timestamps now apply only to saved PNG and session filenames.
- Kept PAE plot tools dockable and updated their data in place to avoid window resizing while changing models.
- Added a no-ChimeraX smoke test for AF2/AF3 folder-discovery behavior.

## 1.2.0

- Added synchronized model/PAE slider controls with prediction-run selection.
- Added AF3 top-hit and all-hit support.
- Added AF2 top-hit and all-hit support.
- Added AlphaMissense mapping for one selected protein chain.
- Removed dependency on external `.cxc` workflow scripts.
