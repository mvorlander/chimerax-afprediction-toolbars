# ChimeraX AF Prediction Toolbars

This bundle adds a small `AF` toolbar tab to ChimeraX with five actions:

- `AF3 All Hits`: opens all detected AF3 `model_N` / `data_N` pairs in a prediction folder.
- `AF3 Top Hit`: opens the best detected AF3 model. Ranking metadata is used when available; otherwise the lowest model number is used.
- `AF2 All Hits`: opens all detected AF2 ranked structure/JSON pairs.
- `AF2 Top Hit`: opens only the best detected AF2 rank, preferring `rank_1`.
- `Missense`: maps AlphaMissense scores from a human UniProt entry onto exactly one selected protein chain.

The workflow is implemented in bundled Python code. It does not call external `.cxc`
scripts and does not contain machine-specific paths.

AF2/AF3 runs open a dedicated `AF Model/PAE Slider` controller. The controller
has a prediction-run drop-down and a pair slider. The drop-down chooses which
folder/run is active, and the slider switches the displayed structure and the
displayed PAE matrix together. Each run uses one PAE plot tool and updates the
plot data when the slider changes, so docked PAE windows are not resized by
model changes. PAE plots are opened with `Dragging box colors structure`
disabled by default, and they remain normal ChimeraX tools that can be docked or
floated by the user.

When several models are opened from one prediction run, the bundle aligns them
to the first opened model and adds them to one ChimeraX model group in the
Models panel. Starting another AF2/AF3 run keeps the earlier run loaded; use the
controller drop-down to switch which run's models and PAEs are displayed.

The controller also includes inter-chain PAE controls. Choose `All inter-chain
pairs` or a specific chain pair, then use the threshold field to find residues by
their minimum PAE to the selected partner chain(s). The default threshold is 20,
and smaller values are more stringent. Use `Select` to select matching residues.
`Show Only` hides the rest of the current model and shows cartoons only for
those residues, while `Show All` restores a cartoon-only display for the current
model.

Use `Save PNG` to save the current 3D view as a transparent-background PNG in
the active run's output folder. Use `Save Session` to save a ChimeraX `.cxs`
session to the same active output folder. The optional `File suffix` field is
appended to the filename for the active model/pair, and the `Timestamp` checkbox
controls whether saved PNG/session filenames include a timestamp.
`Copy Output Path` copies the active output folder to the clipboard. `Close Run`
closes the active run's models and PAE plot without disturbing other loaded
runs.

The missense panel fetches AlphaMissense scores directly for a human UniProt
accession or entry name, associates them with the selected target chain, colors
the chain by the average AlphaMissense score, and closes the temporary score set.

## Installation

These instructions assume you have ChimeraX installed. The installer is plain
Python and works on macOS, Windows, and Linux as long as it can find the
ChimeraX executable.

### 0. Get the source

From GitHub:

```bash
git clone https://github.com/mvorlander/chimerax-afprediction-toolbars.git
cd chimerax-afprediction-toolbars
```

If you received a ZIP archive instead, extract it and open a terminal in the
folder that contains `bundle_info.xml`, `src/`, and
`install_chimerax_bundle.py`.

### 1. Uninstall older AF toolbar bundles

If you previously installed one of the older AF toolbar bundles, uninstall it
first to avoid duplicate `AF` toolbar buttons. In the ChimeraX command line,
run:

```text
toolshed list installed
```

Look for any of these bundle names:

```text
AFToolbar
AF3Toolbar
AFPredictionToolbars
```

To remove the older bundle versions, run the matching uninstall command in
ChimeraX:

```text
toolshed uninstall AFToolbar forceRemove true
toolshed uninstall AF3Toolbar forceRemove true
```

If you also want to remove this newer bundle completely, run:

```text
toolshed uninstall AFPredictionToolbars forceRemove true
```

Restart ChimeraX after uninstalling bundles. ChimeraX usually shows bundle names
without the `ChimeraX-` prefix, so `ChimeraX-AFPredictionToolbars` appears as
`AFPredictionToolbars` in `toolshed list installed`.

From a terminal, the same uninstall can be run through ChimeraX:

```bash
ChimeraX --nogui --exit --cmd "toolshed uninstall AFToolbar forceRemove true ; toolshed uninstall AF3Toolbar forceRemove true ; exit"
```

If `ChimeraX` is not on your `PATH`, replace it with the full executable path,
for example on macOS:

```bash
/Applications/ChimeraX.app/Contents/MacOS/ChimeraX --nogui --exit --cmd "toolshed uninstall AFToolbar forceRemove true ; toolshed uninstall AF3Toolbar forceRemove true ; exit"
```

On Windows, the full executable path is often similar to:

```powershell
& "C:\Program Files\ChimeraX\bin\ChimeraX.exe" --nogui --exit --cmd "toolshed uninstall AFToolbar forceRemove true ; toolshed uninstall AF3Toolbar forceRemove true ; exit"
```

### 2. Install this bundle

From this folder:

```bash
python3 install_chimerax_bundle.py
```

If ChimeraX is not auto-detected:

```bash
python3 install_chimerax_bundle.py --chimerax "/path/to/ChimeraX"
```

Examples:

```bash
python3 install_chimerax_bundle.py --chimerax "/Applications/ChimeraX.app/Contents/MacOS/ChimeraX"
```

```powershell
py install_chimerax_bundle.py --chimerax "C:\Program Files\ChimeraX\bin\ChimeraX.exe"
```

You can also set `CHIMERAX_BIN` to the ChimeraX executable.

The installer auto-detects ChimeraX on macOS, Windows, and Linux, removes stale
local build artifacts, builds a wheel, and installs it with ChimeraX's
`devel install` command.

To check what would be run without changing anything:

```bash
python3 install_chimerax_bundle.py --dry-run
```

To run the source-level smoke test before installing:

```bash
python3 tests/smoke_test_discovery.py
```

### 3. Confirm the install

Restart ChimeraX and check the toolbar. The `AF` tab should contain:

```text
AF3 > All Hits
AF3 > Top Hit
AF2 > All Hits
AF2 > Top Hit
Annotate > Missense
```

You can also confirm from the ChimeraX command line:

```text
toolshed list installed
```

The installed bundle should appear as:

```text
AFPredictionToolbars
```

### Upgrade

To upgrade this bundle after pulling or receiving new source files, run:

```bash
git pull
python3 install_chimerax_bundle.py
```

Restart ChimeraX after the installer completes. You do not need to uninstall
`AFPredictionToolbars` before an upgrade because the installer rebuilds and
reinstalls the bundle.

If ChimeraX was already open while you upgraded, quit and reopen it before
testing the toolbar. ChimeraX only loads bundle Python code at startup.

### Full Removal

To remove this bundle from ChimeraX:

```text
toolshed uninstall AFPredictionToolbars forceRemove true
```

Then restart ChimeraX.

## Expected Input

AF3 folders should contain matching structure and data files with model numbers in
their names, for example:

```text
fold_job_model_0.cif
fold_job_full_data_0.json
fold_job_model_1.cif
fold_job_full_data_1.json
```

AF2 folders commonly contain `pdb/` and `json/` subfolders with matching rank
numbers, for example:

```text
pdb/job_rank_1_model_3.pdb
json/job_rank_1_model_3.json
pdb/job_rank_2_model_1.pdb
json/job_rank_2_model_1.json
```

Use the `Name/filter` field when a folder contains outputs for more than one
prediction. The bundle refuses ambiguous matches and shows the candidate files so
the filter can be narrowed.

## Output

Generated contact and interface files are written under:

```text
<prediction folder>/analysis/<filter-or-folder-name>/<mode>/
```

Saved PNG and ChimeraX session files are also written to the active mode folder.
Their filenames include timestamps only when the display controller's
`Timestamp` checkbox is enabled.

Every run also writes:

```text
analysis_summary.json
analysis_summary.txt
```

These summaries record the bundle version, input folder, active mode, selected
filter, contact-chain choice, and opened model/data pairs.

The `Contact chain` field is optional. If left blank, the first chain detected in
each opened structure is used.
