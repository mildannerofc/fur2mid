#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller
python3 -m py_compile main.py fur2mid.py packaging/build.py packaging/build_deb.py
python3 -m unittest discover -s tests -v
python3 packaging/build.py --archive --clean
echo
echo "Build complete. See dist/"
