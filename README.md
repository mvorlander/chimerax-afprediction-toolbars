# ChimeraX AF Prediction Toolbars

## Quickstart

Use one install method only.

Recommended wheel install:

1. Download the latest `.whl` from:
   https://github.com/mvorlander/chimerax-afprediction-toolbars/releases/latest
2. Open ChimeraX.
3. Run this in the ChimeraX command line, replacing the path with your downloaded
   wheel:

```text
toolshed install /path/to/ChimeraX_AFPredictionToolbars-1.3.11-py3-none-any.whl
```

4. Restart ChimeraX.
5. Open the `AF` toolbar tab.

Alternative source install:

```bash
git clone https://github.com/mvorlander/chimerax-afprediction-toolbars.git
cd chimerax-afprediction-toolbars
python3 install_chimerax_bundle.py
```

Restart ChimeraX after installing from source.

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

For AF3 all-hit runs, the bundle displays metadata-based confidence scores in
the model selector when ranking metadata is available. Models with confidence
scores are ordered from highest to lowest score in the slider.

When several models are opened from one prediction run, the bundle aligns them
to the first opened model and adds them to one ChimeraX model group in the
Models panel. Starting another AF2/AF3 run keeps the earlier run loaded; use the
controller drop-down to switch which run's models and PAEs are displayed.

The controller also includes inter-chain PAE controls. Choose `All inter-chain
pairs` or a specific `PAE chain pair`, then use the `PAE cutoff` slider to find
residues by their minimum PAE to the selected partner chain(s). The default
threshold is 10, and smaller values are more stringent. Moving the slider
live-selects matching residues. The PAE overlay marks only the below-cutoff
inter-chain cells that caused those residues to pass the filter, rather than
full rows and columns. `Hide Unselected` hides atoms, pseudobonds, cartoons, and
surfaces outside the current cutoff filter while preserving the current display
style of matching residues. Bond display flags are kept normal so later ChimeraX
`show` commands do not reveal isolated atoms. `Show Only` hides the rest of the
current model and shows cartoons only for those residues, while `Show All`
restores a cartoon-only display for the current model.

The `PAE chain pair` menu does not change which model is displayed. It only
controls which chain pair is considered by the inter-chain PAE cutoff. For
example, `A-B` highlights residues whose best PAE contact is between chains A
and B. `All inter-chain pairs` means a residue passes if at least one residue in
any other chain is below the cutoff; it does not require every chain pair to
pass. Turn off `Live PAE highlight` to stop live selection and PAE overlays
while still using the cutoff for `Show Only`.

Opening a prediction run prepares ChimeraX contact/interface display for every
model, but does not write contact/interface files to disk. The `Save analysis
results` section contains `Save Contacts and Interfaces` for writing formatted
contact and interface reports for the active model to the active run's output
folder. The `AF contacts PAE cutoff` slider controls how stringent ChimeraX's
`alphafold contacts` command is for that save; lower values keep only more
confident contacts. Rerunning contacts/interfaces removes old AF-contact residue
labels before relabeling the current result. Interface residues are shown as
connected residue sticks on top of the cartoon model.

Use `Save PNG` to save the current 3D view as a transparent-background PNG in
the active run's output folder. Use `Save Session` to save a ChimeraX `.cxs`
session to the same active output folder. The optional `File suffix` field is
appended to the filename for the active model/pair, and the `Timestamp` checkbox
controls whether saved PNG/session filenames include a timestamp.
`Copy Output Path` copies the active output folder to the clipboard. `Close Run`
closes the active run's models and PAE plot without disturbing other loaded
runs. `Reset Active Run` restores the active run to its initial slider/display
state: first model selected, one model visible, all chain pairs selected, PAE
threshold reset to 10, AF contacts max PAE reset to 30, cartoon-only model
display, and prepared contact side chains shown. Longer active-run path details
are kept in the collapsed `Run details` panel to keep the controller compact.

The missense panel fetches AlphaMissense scores directly for a human UniProt
accession or entry name, associates them with the selected target chain, colors
the chain by the average AlphaMissense score, and closes the temporary score set.

## Installation

These instructions assume you already have ChimeraX installed.

Choose one installation option only:

- **Option A, recommended:** install the release wheel.
- **Option B, alternative:** install from source with `git clone` and Python.

Do not run both options for the same install. Use Option B only if you want to
test unreleased changes, modify the bundle, or build the wheel yourself.

### Option A: install the release wheel

This is the preferred installation method for most users. It does not require
Git, a source checkout, or running Python yourself.

1. Download the latest `.whl` file from the GitHub release page:
   https://github.com/mvorlander/chimerax-afprediction-toolbars/releases/latest
2. Start ChimeraX.
3. In the ChimeraX command line, run `toolshed install` followed by the path to
   the downloaded wheel:

```text
toolshed install /path/to/ChimeraX_AFPredictionToolbars-1.3.11-py3-none-any.whl
```

On Windows this looks like:

```text
toolshed install C:\Users\yourname\Downloads\ChimeraX_AFPredictionToolbars-1.3.11-py3-none-any.whl
```

On macOS this looks like:

```text
toolshed install /Users/yourname/Downloads/ChimeraX_AFPredictionToolbars-1.3.11-py3-none-any.whl
```

4. Restart ChimeraX.

More detailed wheel instructions are in `INSTALL_WHEEL.md`.

### If you have an older AF toolbar bundle

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

### Confirm the install

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

Download the newer release `.whl`, then install it in ChimeraX with `reinstall
true`:

```text
toolshed install /path/to/ChimeraX_AFPredictionToolbars-1.3.11-py3-none-any.whl reinstall true
```

Restart ChimeraX after upgrading. ChimeraX only loads bundle Python code at
startup.

### Full removal

To remove this bundle from ChimeraX:

```text
toolshed uninstall AFPredictionToolbars forceRemove true
```

Then restart ChimeraX.

### Option B: install from source

This is an alternative to Option A, not an extra step after installing the wheel.
Use it only if you want to test unreleased changes, modify the bundle, or build
the wheel yourself.

Clone the repository:

```bash
git clone https://github.com/mvorlander/chimerax-afprediction-toolbars.git
cd chimerax-afprediction-toolbars
```

Then install from the source checkout:

```bash
python3 install_chimerax_bundle.py
```

If ChimeraX is not auto-detected:

```bash
python3 install_chimerax_bundle.py --chimerax "/path/to/ChimeraX"
```

The source installer auto-detects ChimeraX on macOS, Windows, and Linux, removes
stale local build artifacts, builds a wheel, and installs it with ChimeraX's
`devel install` command.

Double-click source installer fallback:

- On macOS, double-click `install.command`.
- On Windows, double-click `install_windows.bat`.
- More detailed click-by-click instructions are in `INSTALL_NO_TERMINAL.md`.

To run the source-level smoke test before installing:

```bash
python3 tests/smoke_test_discovery.py
```

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

When you click `Save Contacts and Interfaces`, generated contact and interface
files are written under:

```text
<prediction folder>/analysis/<filter-or-folder-name>/<mode>/
```

Formatted reports stay directly in that folder. Raw ChimeraX command output is
kept separately under `raw/af_contacts/` and `raw/interface_residues/`. Contact
reports record the `AF contacts max PAE` threshold used for that rerun.

Saved PNG and ChimeraX session files are also written to the active mode folder.
Their filenames include timestamps only when the display controller's
`Timestamp` checkbox is enabled.

Every run also writes:

```text
analysis_summary.json
analysis_summary.txt
```

These summaries record the bundle version, input folder, active mode, selected
filter, alignment/contact-chain choice, and opened model/data pairs.

The `Align structures on chain` field is optional. If left blank, the first
chain detected in each opened structure is used for alignment and contact
analysis.

## Compatibility Automation

The repository has a monthly GitHub Actions workflow that checks the official
ChimeraX pages for a newer production release. On each run it:

- detects the latest ChimeraX production version,
- compares it with `.github/chimerax_compatibility.json`,
- runs the bundle syntax check and AF2/AF3 discovery smoke test,
- opens a GitHub issue when a newer ChimeraX production release needs manual
  validation.

After validating a new ChimeraX release, update
`.github/chimerax_compatibility.json` so future monthly checks know that version
has been tested.
