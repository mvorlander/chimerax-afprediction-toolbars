# Install From the Release Wheel

This is the easiest route for most users. It does not require installing Python,
cloning the repository, or building the bundle.

## Steps

1. Download the latest `.whl` file from:
   https://github.com/mvorlander/chimerax-afprediction-toolbars/releases/latest
2. Start ChimeraX.
3. In the ChimeraX command line, run `toolshed install`, followed by the full
   path to the downloaded wheel.

Examples:

```text
toolshed install /Users/yourname/Downloads/ChimeraX_AFPredictionToolbars-1.3.14-py3-none-any.whl
```

```text
toolshed install C:\Users\yourname\Downloads\ChimeraX_AFPredictionToolbars-1.3.14-py3-none-any.whl
```

4. Restart ChimeraX.
5. Open the `AF` toolbar tab.

## Upgrade

Download the newer `.whl` file, then install it with:

```text
toolshed install /path/to/ChimeraX_AFPredictionToolbars-1.3.14-py3-none-any.whl reinstall true
```

Restart ChimeraX after upgrading.

## Uninstall

In the ChimeraX command line:

```text
toolshed uninstall AFPredictionToolbars forceRemove true
```

Restart ChimeraX after uninstalling.
