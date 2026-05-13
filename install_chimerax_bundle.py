#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install the AF prediction toolbar bundle into ChimeraX."
    )
    parser.add_argument(
        "--chimerax",
        "--chimeraX",
        dest="chimerax_bin",
        help="Path to the ChimeraX executable. Overrides auto-detection.",
    )
    parser.add_argument(
        "--bundle-dir",
        default=str(Path(__file__).resolve().parent),
        help="Path to the bundle directory containing bundle_info.xml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the detected executable and install command without running it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle_dir = Path(args.bundle_dir).expanduser().resolve()
    if not (bundle_dir / "bundle_info.xml").is_file():
        raise SystemExit(f"Bundle directory does not contain bundle_info.xml: {bundle_dir}")

    chimerax_bin = find_chimerax_binary(args.chimerax_bin)
    command = [
        str(chimerax_bin),
        "--nogui",
        "--exit",
        "--cmd",
        f'devel install "{bundle_dir}" ; exit',
    ]

    print(f"Using ChimeraX: {chimerax_bin}")
    print(f"Installing bundle from: {bundle_dir}")
    print("Command:")
    print(" ".join(_shell_quote(part) for part in command))
    if args.dry_run:
        return 0

    clean_bundle_artifacts(bundle_dir)
    completed = subprocess.run(command, check=False)
    return completed.returncode


def clean_bundle_artifacts(bundle_dir: Path) -> None:
    for name in ("build", "dist"):
        shutil.rmtree(bundle_dir / name, ignore_errors=True)
    for egg_info in bundle_dir.glob("*.egg-info"):
        shutil.rmtree(egg_info, ignore_errors=True)


def find_chimerax_binary(user_supplied: Optional[str]) -> Path:
    candidates: List[Path] = []

    if user_supplied:
        candidates.append(Path(user_supplied).expanduser())

    for env_name in ("CHIMERAX_BIN", "CHIMERAX"):
        env_path = os.environ.get(env_name)
        if env_path:
            candidates.append(Path(env_path).expanduser())

    for executable_name in ("ChimeraX", "chimerax", "ChimeraX.exe"):
        found = shutil.which(executable_name)
        if found:
            candidates.append(Path(found))

    if sys.platform == "darwin":
        candidates.extend(
            [
                Path("/Applications/ChimeraX.app/Contents/MacOS/ChimeraX"),
                Path("/Applications/ChimeraX.app/Contents/bin/ChimeraX"),
            ]
        )
        candidates.extend(sorted(Path("/Applications").glob("ChimeraX*.app/Contents/MacOS/ChimeraX")))
        candidates.extend(sorted(Path("/Applications").glob("ChimeraX*.app/Contents/bin/ChimeraX")))
    elif sys.platform.startswith("win"):
        program_dirs = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            Path.home() / "AppData" / "Local" / "Programs",
        ]
        for base in program_dirs:
            candidates.extend(sorted(base.glob("ChimeraX*/bin/ChimeraX.exe")))
            candidates.extend(sorted(base.glob("UCSF ChimeraX*/bin/ChimeraX.exe")))
    else:
        for base in (Path("/opt"), Path("/usr/local"), Path("/usr"), Path.home()):
            candidates.extend(sorted(base.glob("ChimeraX*/bin/ChimeraX")))
            candidates.extend(sorted(base.glob("UCSFChimeraX*/bin/ChimeraX")))

    existing = _dedupe_existing_files(candidates)
    if not existing:
        raise SystemExit(
            "Could not find ChimeraX. Pass --chimerax /path/to/ChimeraX "
            "or set CHIMERAX_BIN."
        )
    return max(existing, key=lambda path: path.stat().st_mtime)


def _dedupe_existing_files(candidates: List[Path]) -> List[Path]:
    existing = []
    seen = set()
    for candidate in candidates:
        if not candidate.is_file():
            continue
        resolved = str(candidate.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        existing.append(candidate)
    return existing


def _shell_quote(text: str) -> str:
    if not text or any(char.isspace() or char in "\"'" for char in text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


if __name__ == "__main__":
    raise SystemExit(main())
