#!/usr/bin/env python3
"""Build a standalone zip release for Patchwork Isles."""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import zipapp
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME = "Patchwork-Isles"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package Patchwork Isles into a single zip with launchers.",
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


def build_app_dir(app_dir: Path) -> None:
    engine_src = REPO_ROOT / "engine"
    world_src = REPO_ROOT / "world"
    profile_src = REPO_ROOT / "profile.example.json"

    shutil.copytree(engine_src, app_dir / "engine")
    shutil.copytree(world_src, app_dir / "world")
    shutil.copy2(profile_src, app_dir / "profile.example.json")

    main_path = app_dir / "__main__.py"
    main_path.write_text(
        '''"""Entry point for Patchwork Isles zipapp."""
from engine import engine_min


def main() -> None:
    engine_min.main()


if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )


def build_zipapp(app_dir: Path, target_path: Path) -> None:
    zipapp.create_archive(
        app_dir,
        target=target_path,
        interpreter="/usr/bin/env python3",
    )


def build_launchers(stage_dir: Path, pyz_name: str) -> None:
    run_sh = stage_dir / "run.sh"
    run_sh.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/%s" "$@"
""" % pyz_name,
        encoding="utf-8",
    )
    run_sh.chmod(0o755)

    run_bat = stage_dir / "run.bat"
    run_bat.write_text(
        """@echo off
setlocal
set SCRIPT_DIR=%~dp0
python "%SCRIPT_DIR%%s" %*
endlocal
""" % pyz_name,
        encoding="utf-8",
    )


def artifact_name(base: str, tag: str | None) -> str:
    date_stamp = dt.datetime.utcnow().strftime("%Y%m%d")
    if tag:
        return f"{base}-{tag}-{date_stamp}"
    return f"{base}-{date_stamp}"


def build_release(output_dir: Path, name: str, tag: str | None, keep_build_dir: bool) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_base = artifact_name(name, tag)
    stage_dir = output_dir / f".{artifact_base}-staging"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    app_dir = stage_dir / "app"
    app_dir.mkdir()
    build_app_dir(app_dir)

    pyz_name = f"{name}.pyz"
    pyz_path = stage_dir / pyz_name
    build_zipapp(app_dir, pyz_path)
    build_launchers(stage_dir, pyz_name)

    zip_path = output_dir / f"{artifact_base}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in [pyz_path, stage_dir / "run.sh", stage_dir / "run.bat"]:
            zf.write(item, arcname=item.name)

    if not keep_build_dir:
        shutil.rmtree(stage_dir)

    return zip_path


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    zip_path = build_release(output_dir, args.name, args.tag, args.keep_build_dir)
    print(f"Release created: {zip_path}")


if __name__ == "__main__":
    main()
