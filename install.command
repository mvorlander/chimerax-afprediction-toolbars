#!/bin/bash
set -u

cd "$(dirname "$0")" || exit 1

echo "ChimeraX AF Prediction Toolbars installer"
echo "Folder: $(pwd)"
echo

PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "Could not find Python."
    echo
    echo "On macOS, install Python 3 from https://www.python.org/downloads/"
    echo "or install Apple's command line tools when prompted by the system."
    echo
    read -r -p "Press Return to close this window."
    exit 1
fi

echo "Using Python: $($PYTHON_BIN --version 2>&1)"
echo

"$PYTHON_BIN" install_chimerax_bundle.py
STATUS=$?

echo
if [ "$STATUS" -eq 0 ]; then
    echo "Install finished."
    echo "Restart ChimeraX, then open the AF toolbar tab."
else
    echo "Install failed."
    echo "If ChimeraX was not found automatically, run the installer again from a terminal with:"
    echo "python3 install_chimerax_bundle.py --chimerax \"/path/to/ChimeraX\""
fi
echo
read -r -p "Press Return to close this window."
exit "$STATUS"
