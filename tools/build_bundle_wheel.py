#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from email.message import EmailMessage
import hashlib
from pathlib import Path
import re
import shutil
from xml.etree import ElementTree as ET
import zipfile


def parse_args():
    parser = argparse.ArgumentParser(description="Build a ChimeraX bundle wheel.")
    parser.add_argument(
        "--bundle-dir",
        default=".",
        help="Repository directory containing bundle_info.xml and src/.",
    )
    parser.add_argument(
        "--dist-dir",
        default="dist",
        help="Directory where the wheel should be written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle_dir = Path(args.bundle_dir).resolve()
    dist_dir = Path(args.dist_dir).resolve()
    wheel_path = build_wheel(bundle_dir, dist_dir)
    print(wheel_path)
    return 0


def build_wheel(bundle_dir: Path, dist_dir: Path) -> Path:
    info_path = bundle_dir / "bundle_info.xml"
    if not info_path.is_file():
        raise SystemExit(f"Missing bundle_info.xml: {info_path}")

    info = BundleInfo(info_path)
    dist_name = _normalize_distribution(info.name)
    dist_info = f"{dist_name}-{info.version}.dist-info"
    wheel_name = f"{info.name.replace('-', '_')}-{info.version}-py3-none-any.whl"
    wheel_path = dist_dir / wheel_name

    shutil.rmtree(dist_dir, ignore_errors=True)
    dist_dir.mkdir(parents=True, exist_ok=True)

    records = []
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for source, arcname in _package_files(bundle_dir, info.package):
            _write_file(wheel, source, arcname, records)

        metadata = _metadata_text(info).encode("utf-8")
        _write_bytes(wheel, metadata, f"{dist_info}/METADATA", records)
        _write_bytes(wheel, _wheel_text().encode("utf-8"), f"{dist_info}/WHEEL", records)
        _write_bytes(
            wheel,
            f"{info.package}\n".encode("utf-8"),
            f"{dist_info}/top_level.txt",
            records,
        )

        record_path = f"{dist_info}/RECORD"
        record_lines = [f"{path},{digest},{size}" for path, digest, size in records]
        record_lines.append(f"{record_path},,")
        wheel.writestr(record_path, "\n".join(record_lines) + "\n")

    return wheel_path


def _package_files(bundle_dir: Path, package: str):
    src_dir = bundle_dir / "src"
    if not src_dir.is_dir():
        raise SystemExit(f"Missing src directory: {src_dir}")
    for path in sorted(src_dir.rglob("*")):
        if (
            path.is_file()
            and "__pycache__" not in path.parts
            and not any(part.startswith(".") for part in path.relative_to(src_dir).parts)
            and path.suffix not in {".pyc", ".pyo"}
        ):
            yield path, f"{package}/{path.relative_to(src_dir).as_posix()}"


def _write_file(wheel, source: Path, arcname: str, records):
    data = source.read_bytes()
    _write_bytes(wheel, data, arcname, records)


def _write_bytes(wheel, data: bytes, arcname: str, records):
    wheel.writestr(arcname, data)
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    records.append((arcname, f"sha256={digest.decode('ascii')}", str(len(data))))


def _metadata_text(info) -> str:
    message = EmailMessage()
    message["Metadata-Version"] = "2.4"
    message["Name"] = info.name
    message["Version"] = info.version
    message["Summary"] = info.synopsis
    if info.url:
        message["Home-page"] = info.url
    if info.author:
        message["Author"] = info.author
    if info.email:
        message["Author-email"] = info.email
    for classifier in info.classifiers:
        message["Classifier"] = classifier
    message["Requires-Python"] = ">=3.7"
    for dependency in info.dependencies:
        message["Requires-Dist"] = dependency
    return message.as_string() + "\n" + info.description.strip() + "\n"


def _wheel_text() -> str:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: afprediction-toolbars build_bundle_wheel.py\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )


def _normalize_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


class BundleInfo:
    def __init__(self, path: Path):
        root = ET.parse(path).getroot()
        self.name = root.attrib["name"]
        self.version = root.attrib["version"]
        self.package = root.attrib["package"]
        self.author = _node_text(root, "Author")
        self.email = _node_text(root, "Email")
        self.url = _node_text(root, "URL")
        self.synopsis = _node_text(root, "Synopsis")
        self.description = _node_text(root, "Description")
        self.dependencies = self._dependencies(root)
        self.classifiers = self._classifiers(root)

    def _dependencies(self, root):
        dependencies = []
        for node in root.findall("./Dependencies/Dependency"):
            name = node.attrib.get("name", "").strip()
            version = node.attrib.get("version", "").strip()
            if name and version:
                dependencies.append(f"{name}{version}")
            elif name:
                dependencies.append(name)
        return dependencies

    def _classifiers(self, root):
        classifiers = [
            "Framework :: ChimeraX",
            "Intended Audience :: Science/Research",
            "Programming Language :: Python :: 3",
            "Topic :: Scientific/Engineering :: Visualization",
            "Topic :: Scientific/Engineering :: Chemistry",
            "Topic :: Scientific/Engineering :: Bio-Informatics",
            "Environment :: MacOS X :: Aqua",
            "Environment :: Win32 (MS Windows)",
            "Environment :: X11 Applications",
            "Operating System :: MacOS :: MacOS X",
            "Operating System :: Microsoft :: Windows :: Windows 10",
            "Operating System :: POSIX :: Linux",
            (
                "ChimeraX :: Bundle :: General :: 1,1 :: "
                f"{self.package} ::  :: "
            ),
        ]
        for node in root.findall("./Classifiers/PythonClassifier"):
            text = (node.text or "").strip()
            if text:
                classifiers.append(text)
        for node in root.findall("./Classifiers/ChimeraXClassifier"):
            text = (node.text or "").strip()
            if text:
                classifiers.append(text)
        for provider in root.findall("./Providers/Provider"):
            classifiers.append(_provider_classifier(provider))
        return classifiers


def _provider_classifier(provider):
    name = provider.attrib["name"]
    manager = provider.getparent().attrib["manager"] if hasattr(provider, "getparent") else "toolbar"
    fields = [f"ChimeraX :: Provider :: {name} :: {manager}"]
    for key in ("tab", "section", "display_name", "icon", "description"):
        value = provider.attrib.get(key)
        if value:
            fields.append(f"{key}:{_quote_classifier_value(value)}")
    return " :: ".join(fields)


def _quote_classifier_value(value):
    if any(char.isspace() for char in value):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _node_text(root, name):
    node = root.find(name)
    return (node.text or "").strip() if node is not None else ""


if __name__ == "__main__":
    raise SystemExit(main())
