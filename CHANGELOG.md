# Changelog

## Unreleased

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
