#!/usr/bin/env python3
"""Build fur2mid for the host platform and optionally create a Debian package.

PyInstaller is deliberately run on the target OS. This is a native build
recipe, not a cross-compiler:
  Windows -> portable Windows folder ZIP
  Linux   -> portable Linux folder TAR.GZ
  macOS   -> .app bundle ZIP
  Linux   -> optional architecture-independent Debian .deb
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
ENTRY = ROOT / "main.py"
APP = "fur2mid"


def read_version() -> str:
    value = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not value or any(ch not in "0123456789.+~-" for ch in value):
        raise SystemExit(f"Invalid version string in VERSION: {value!r}")
    return value


def architecture() -> str:
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    if machine in ("i386", "i686", "x86"):
        return "x86"
    return machine.replace("/", "-")


def platform_slug() -> str:
    if sys.platform == "win32":
        return f"windows-{architecture()}"
    if sys.platform == "darwin":
        return f"macos-{architecture()}"
    if sys.platform.startswith("linux"):
        return f"linux-{architecture()}"
    raise SystemExit(f"Unsupported build platform: {sys.platform}")


def run(command: list[str], *, dry_run: bool = False) -> None:
    printable = " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)
    print(f"$ {printable}", flush=True)
    if dry_run:
        return
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def clean() -> None:
    for path in (DIST, BUILD, ROOT / f"{APP}.spec"):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def build_app(*, dry_run: bool = False) -> Path:
    """Freeze the current source tree with PyInstaller."""
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name", APP,
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        "--collect-all", "mido",
        "--collect-all", "tkinterdnd2",
        "--hidden-import", "tkinterdnd2",
        str(ENTRY),
    ]
    run(command, dry_run=dry_run)
    if sys.platform == "darwin":
        return DIST / f"{APP}.app"
    return DIST / APP


def archive_app(app_path: Path, *, dry_run: bool = False) -> Path:
    slug = platform_slug()
    if sys.platform == "win32" or sys.platform == "darwin":
        output = DIST / f"{APP}-{slug}.zip"
        if dry_run:
            print(f"Would create {output}")
            return output
        if sys.platform == "darwin":
            # ditto preserves the .app bundle's symlinks and executable modes.
            run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app_path), str(output)])
        else:
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for item in sorted(app_path.rglob("*")):
                    if item.is_file():
                        archive.write(item, f"{APP}/{item.relative_to(app_path).as_posix()}")
        return output

    output = DIST / f"{APP}-{slug}.tar.gz"
    if dry_run:
        print(f"Would create {output}")
        return output
    import tarfile
    with tarfile.open(output, "w:gz") as archive:
        archive.add(app_path, arcname=APP)
    return output


def build_deb(*, dry_run: bool = False) -> Path:
    """Delegate native Debian packaging to the small, standalone helper."""
    output = DIST / f"{APP}_{read_version()}_all.deb"
    command = [sys.executable, str(ROOT / "packaging" / "build_deb.py")]
    if dry_run:
        command.append("--dry-run")
    run(command, dry_run=False)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build fur2mid for the current operating system.")
    parser.add_argument("--archive", action="store_true", help="Create a ZIP/TAR.GZ archive after the PyInstaller build.")
    parser.add_argument("--deb", action="store_true", help="Also create a native Debian .deb package (Linux only).")
    parser.add_argument("--clean", action="store_true", help="Remove previous build and dist output before building.")
    parser.add_argument("--dry-run", action="store_true", help="Print the build commands without compiling.")
    args = parser.parse_args(argv)

    if args.deb and not sys.platform.startswith("linux"):
        raise SystemExit("--deb is only supported on Linux/Debian build hosts.")

    if args.clean:
        clean()
    if not args.deb or args.archive:
        app_path = build_app(dry_run=args.dry_run)
        if args.archive:
            archive_app(app_path, dry_run=args.dry_run)
    if args.deb:
        build_deb(dry_run=args.dry_run)

    print(f"Build recipe finished for {platform_slug()} ({read_version()}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
