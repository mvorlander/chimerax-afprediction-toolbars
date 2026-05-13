# Changelog

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
