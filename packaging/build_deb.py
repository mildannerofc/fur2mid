#!/usr/bin/env python3
"""Create a native, architecture-independent Debian package for fur2mid."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
APP = "fur2mid"
STAGE = ROOT / "build" / "deb-root"
OUTPUT = ROOT / "dist" / f"{APP}_{VERSION}_all.deb"


def write_file(relative_path: str, content: str, mode: int = 0o644) -> None:
    destination = STAGE / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8", newline="\n")
    destination.chmod(mode)


def build(dry_run: bool = False) -> Path:
    if not shutil.which("dpkg-deb"):
        raise SystemExit("dpkg-deb was not found. Install it with: sudo apt install dpkg-dev")

    print("Preparing architecture-independent Debian package...")
    print(f"  package: {OUTPUT.name}")
    print("  runtime: system Python 3 + Tkinter + Mido")

    if dry_run:
        print("Dry run: package staging and dpkg-deb were not executed.")
        return OUTPUT

    if STAGE.exists():
        shutil.rmtree(STAGE)
    (STAGE / "DEBIAN").mkdir(parents=True)
    # dpkg-deb rejects setgid inherited from some CI/workspace filesystems.
    STAGE.chmod(0o755)
    (STAGE / "DEBIAN").chmod(0o755)
    (STAGE / "usr" / "lib" / APP).mkdir(parents=True)

    shutil.copy2(ROOT / "fur2mid.py", STAGE / "usr" / "lib" / APP / "fur2mid.py")
    doc_dir = STAGE / "usr" / "share" / "doc" / APP
    doc_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "README.md", doc_dir / "README.md")
    shutil.copy2(ROOT / "LICENSE", doc_dir / "copyright")

    launcher = (
        "#!/bin/sh\n"
        "set -e\n"
        "exec /usr/bin/python3 /usr/lib/fur2mid/fur2mid.py \"$@\"\n"
    )
    write_file("usr/bin/fur2mid", launcher, 0o755)

    desktop = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=fur2mid\n"
        "GenericName=Furnace to MIDI Converter\n"
        "Comment=Convert Furnace Tracker modules into editable MIDI files\n"
        "Exec=fur2mid\n"
        "Icon=audio-midi\n"
        "Terminal=false\n"
        "Categories=AudioVideo;Audio;Utility;\n"
    )
    write_file("usr/share/applications/fur2mid.desktop", desktop)

    control = (
        f"Package: {APP}\n"
        f"Version: {VERSION}\n"
        "Section: sound\n"
        "Priority: optional\n"
        "Architecture: all\n"
        "Maintainer: fur2mid contributors\n"
        "Depends: python3 (>= 3.10), python3-tk, python3-mido (>= 1.3.0)\n"
        "Description: Furnace Tracker to editable MIDI converter\n"
        " Converts Furnace Tracker .fur modules into Standard MIDI files.\n"
        " Reconstructs song orders and patterns, assigns editable General MIDI\n"
        " programs, and maps supported tracker effects to MIDI controllers.\n"
    )
    write_file("DEBIAN/control", control)
    write_file("DEBIAN/md5sums", "", 0o644)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()
    result = subprocess.run(
        ["dpkg-deb", "--build", "--root-owner-group", str(STAGE), str(OUTPUT)],
        cwd=ROOT,
    )
    if result.returncode:
        raise SystemExit(result.returncode)

    print(f"Created: {OUTPUT}")
    return OUTPUT


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the native fur2mid Debian package.")
    parser.add_argument("--dry-run", action="store_true", help="Show package metadata without creating the .deb.")
    args = parser.parse_args()
    build(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
