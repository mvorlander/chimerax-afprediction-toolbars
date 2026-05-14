#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_URLS = (
    "https://www.cgl.ucsf.edu/chimerax/",
    "https://www.cgl.ucsf.edu/chimerax/download.html",
)


@dataclass(frozen=True)
class ReleaseMatch:
    version: str
    summary: str
    url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect the current ChimeraX production release."
    )
    parser.add_argument(
        "--known-file",
        type=Path,
        default=Path(".github/chimerax_compatibility.json"),
        help="JSON file containing last_tested_production_version.",
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="Official ChimeraX page to inspect. Can be passed more than once.",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Write current_version, known_version, and new_release to GITHUB_OUTPUT.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    urls = tuple(args.urls) if args.urls else DEFAULT_URLS
    known_version = _read_known_version(args.known_file)
    release = latest_production_release(urls)
    new_release = _version_key(release.version) > _version_key(known_version)

    result = {
        "current_version": release.version,
        "known_version": known_version,
        "new_release": str(new_release).lower(),
        "source_url": release.url,
        "release_summary": release.summary,
    }

    if args.github_output:
        _write_github_output(result)
    print(json.dumps(result, indent=2))
    return 0


def latest_production_release(urls: Iterable[str]) -> ReleaseMatch:
    matches = []
    errors = []
    for url in urls:
        try:
            text = _fetch_text(url)
        except URLError as err:
            errors.append(f"{url}: {err}")
            continue
        matches.extend(_release_matches(text, url))

    if not matches:
        detail = "; ".join(errors) if errors else "no matching release text found"
        raise SystemExit(f"Could not detect a ChimeraX production release: {detail}")
    return max(matches, key=lambda match: _version_key(match.version))


def _fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={"User-Agent": "chimerax-afprediction-toolbars-compatibility-check"},
    )
    with urlopen(request, timeout=30) as response:
        data = response.read()
    return data.decode("utf-8", errors="replace")


def _release_matches(text: str, url: str) -> list[ReleaseMatch]:
    clean = _clean_html(text)
    patterns = (
        re.compile(
            r"(ChimeraX\s+([0-9]+(?:\.[0-9]+)*)\s+production\s+release\s+is\s+available[^.\n]*(?:\.)?)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(ChimeraX\s+([0-9]+(?:\.[0-9]+)*)\s+production\s+release)",
            re.IGNORECASE,
        ),
    )

    matches = []
    seen = set()
    for pattern in patterns:
        for match in pattern.finditer(clean):
            version = match.group(2)
            if version in seen:
                continue
            seen.add(version)
            summary = f"ChimeraX {version} production release is available."
            matches.append(ReleaseMatch(version=version, summary=summary, url=url))
    return matches


def _clean_html(text: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def _read_known_version(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Known compatibility file not found: {path}")
    except json.JSONDecodeError as err:
        raise SystemExit(f"Invalid compatibility JSON in {path}: {err}")

    version = data.get("last_tested_production_version")
    if not isinstance(version, str) or not version.strip():
        raise SystemExit(
            f"{path} must define a non-empty last_tested_production_version string."
        )
    return version.strip()


def _version_key(version: str) -> tuple[int, ...]:
    parts = []
    for part in str(version).split("."):
        match = re.match(r"\d+", part)
        parts.append(int(match.group(0)) if match else 0)
    return tuple(parts)


def _write_github_output(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as stream:
        for key, value in values.items():
            text = str(value).replace("\n", " ")
            stream.write(f"{key}={text}\n")


if __name__ == "__main__":
    raise SystemExit(main())
