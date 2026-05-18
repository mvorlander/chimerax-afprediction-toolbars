# Changelog

## 1.3.13

- Changed confidence selection to an explicit either/or mode switch with PAE as
  the default and pLDDT as the alternate mode.
- Added controller guidance that lower PAE cutoffs are more stringent while
  higher pLDDT cutoffs are more stringent.
- Made `Hide Unselected` propagate the active confidence filter across all
  models in the active run.
- Replaced the save-results group title with an explicit bold section header.

## 1.3.12

- Renamed the confidence-selection section to `Selection by prediction
  confidence` and kept the section headers visibly bold.
- Added a pLDDT confidence selector for monomeric predictions and local
  confidence filtering. It supports cutoff-based live selection, hide
  unselected, show only, and show all actions.
- Added pLDDT cutoff state to the display controller status/details and reset
  path.

## 1.3.11

- Preserved normal bond display flags in AF display actions so a later bare
  ChimeraX `show` command does not reveal isolated atoms.
- Restored bond display flags whenever AF run visibility is updated, repairing
  sessions affected by older bundle versions that hid bonds directly.
- Renamed the launcher `Contact chain` field to `Align structures on chain`.
- Reworked the display controller layout: `Reset Active Run` is now at the top,
  inter-chain PAE and save-result sections have clearer headers, contact saving
  is labeled `Save Contacts and Interfaces`, and PNG/session/output-path controls
  are grouped under `Save analysis results`.

## 1.3.10

- Added a `Hide Unselected` action to the inter-chain PAE cutoff tool. It hides
  atoms, bonds, pseudobonds, cartoons, and surfaces outside the current cutoff
  filter while preserving the display style of matching residues.
- Changed live PAE plot highlighting to mark only below-cutoff inter-chain PAE
  cells instead of full rows and columns for selected residues.
- Moved verbose active-run input/output paths into a collapsed `Run details`
  panel to keep the controller compact.
- Updated live PAE selection to select residue bonds and pseudobonds as well as
  atoms, preventing atom-only displays when users apply ChimeraX show actions to
  the highlighted selection.

## 1.3.9

- Added an `AF contacts max PAE` slider to the display controller so the active
  model can be rerun with a stricter or looser ChimeraX `alphafold contacts`
  threshold.
- Rerunning `Run Contacts/Interfaces` now removes old AF-contact residue labels
  before relabeling the current contact set.
- Contact reports now record the AF contacts max PAE threshold used for the
  rerun.

## 1.3.8

- Replaced combined pseudobond labels such as `X to Y` with separate residue
  endpoint labels for AlphaFold contact residues.
- Set contact residue label colors from the displayed residue color when
  possible.
- Moved raw ChimeraX contact/interface command output into `raw/af_contacts/`
  and `raw/interface_residues/` subfolders, leaving formatted reports in the
  main output folder.

## 1.3.7

- Prepare AlphaFold contacts and interface selections for display when models
  are opened, while keeping contact/interface file writing behind the explicit
  `Run Contacts/Interfaces` button.
- Show bonds for interface and contact-sidechain stick displays so interface
  residues appear as connected residue sticks instead of isolated atoms.
- Clarified that `All inter-chain pairs` in the PAE cutoff tool means a residue
  passes if at least one partner residue in any other chain is below the cutoff.
- Changed the default PAE cutoff from 20 to 10.
- Visually grouped the inter-chain PAE controls into a dedicated panel.

## 1.3.6

- Removed the duplicate launcher `Choose Folder` button; the folder row now has
  the single `Browse...` picker.
- Stopped running `alphafold contacts` and `interfaces` automatically when
  opening all predictions. The controller now runs contacts/interfaces only for
  the active model on demand.
- Added formatted contact and interface reports alongside raw ChimeraX output.
- Changed interface display to residue-level selections shown as full sticks
  on top of cartoon, instead of the raw atom-level selection.
- Renamed controller labels for clearer model/PAE and PAE cutoff controls.

## 1.3.5

- Rearranged inter-chain PAE controls so the cutoff slider has its own row.
- Removed `Select Highlighted` because live highlighting already selects
  matching residues by default.

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
