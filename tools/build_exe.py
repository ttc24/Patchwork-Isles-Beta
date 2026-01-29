#!/usr/bin/env python3
"""Build a standalone executable with PyInstaller."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME = "Patchwork-Isles"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package Patchwork Isles into a standalone PyInstaller executable.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "dist"),
        help="Directory to write release artifacts (default: ./dist).",
    )
    parser.add_argument(
        "--name",
        default=DEFAULT_NAME,
        help="Release base name (default: Patchwork-Isles).",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Optional tag string to append to the artifact name (ex: v0.9-beta).",
    )
    parser.add_argument(
        "--keep-build-dir",
        action="store_true",
        help="Do not delete the temporary build directory.",
    )
    return parser.parse_args()


def artifact_name(base: str, tag: str | None) -> str:
    date_stamp = dt.datetime.utcnow().strftime("%Y%m%d")
    if tag:
        return f"{base}-{tag}-{date_stamp}"
    return f"{base}-{date_stamp}"


def build_executable(output_dir: Path, name: str, tag: str | None, keep_build_dir: bool) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_base = artifact_name(name, tag)
    stage_dir = output_dir / f".{artifact_base}-pyinstaller"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    world_src = REPO_ROOT / "world"
    entry_point = REPO_ROOT / "engine" / "engine_min.py"
    data_sep = ";" if os.name == "nt" else ":"
    data_spec = f"{world_src}{data_sep}world"

    command = [
        "python",
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        artifact_base,
        "--distpath",
        str(output_dir),
        "--workpath",
        str(stage_dir / "build"),
        "--specpath",
        str(stage_dir),
        "--add-data",
        data_spec,
        str(entry_point),
    ]

    subprocess.run(command, check=True)

    artifact_path = output_dir / artifact_base
    if os.name == "nt":
        artifact_path = artifact_path.with_suffix(".exe")

    if not keep_build_dir:
        shutil.rmtree(stage_dir)

    return artifact_path


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    artifact_path = build_executable(output_dir, args.name, args.tag, args.keep_build_dir)
    print(f"Executable created: {artifact_path}")


if __name__ == "__main__":
    main()
