#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Debian/Ubuntu prerequisites for a Tkinter + PyInstaller build and .deb output.
sudo apt-get update
sudo apt-get install -y --no-install-recommends python3-venv python3-tk dpkg-dev

# Use a project-local venv; --system-site-packages keeps Debian's Tk runtime
# visible while pip-managed Python build tools remain isolated.
python3 -m venv --system-site-packages .venv-build
PYTHON="$PWD/.venv-build/bin/python"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt pyinstaller
"$PYTHON" -m py_compile main.py fur2mid.py packaging/build.py packaging/build_deb.py
"$PYTHON" -m unittest discover -s tests -v
"$PYTHON" packaging/build.py --archive --deb --clean

echo
echo "Build complete. See dist/"
