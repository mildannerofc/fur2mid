# Building fur2mid

This folder contains the native build recipe and GitHub Actions workflow. It only
builds and packages fur2mid; it does not change the converter's playback or
conversion logic.

## GitHub Actions

The workflow at `.github/workflows/build.yml` builds on native runners:

| Runner | Output |
|---|---|
| Windows x64 | `fur2mid-windows-x64.zip` |
| Ubuntu 22.04 x64 | `fur2mid-linux-x64.tar.gz` |
| Ubuntu 22.04 x64 | `fur2mid_0.1.1_all.deb` |
| macOS Apple Silicon | `fur2mid-macos-arm64.zip` |
| macOS Intel | `fur2mid-macos-x64.zip` |

It runs on pushes to `main`, pull requests to `main`, tags beginning with
`v`, and manual dispatch. Each run uploads build artifacts to the Actions run.
It does not publish a GitHub Release or upload files to a package repository.

Builds are native: PyInstaller must run on the operating system it targets.
The macOS jobs use separate native ARM64 and Intel runners.

## Local build

Python 3.10 or newer is required. The CI Linux build uses Ubuntu 22.04's
system Python (3.10) together with the distribution Tkinter package, inside a
project-local virtual environment for the pip-installed build tools.

### Windows

```bat
build_windows.bat
```

### Linux

```bash
chmod +x build_linux.sh
./build_linux.sh
```

The Linux script creates both a portable `.tar.gz` and a native `.deb`.

### macOS

```bash
chmod +x build_macos.sh
./build_macos.sh
```

### Run the shared recipe directly

Install dependencies first:

```bash
python -m pip install -r requirements.txt pyinstaller
```

Then use:

```bash
python packaging/build.py --archive
```

Linux Debian package only:

```bash
python packaging/build.py --deb
```

The build script accepts `--clean` to remove old `build/` and `dist/` output
before compiling, and `--dry-run` to preview commands.

## Debian package

The `.deb` is intentionally a native Python package rather than a frozen
PyInstaller bundle. It installs the application source under
`/usr/lib/fur2mid`, a launcher at `/usr/bin/fur2mid`, and a desktop entry.

Install it on Debian 13 (Trixie) or a compatible derivative:

```bash
sudo apt update
sudo apt install ./dist/fur2mid_0.1.1_all.deb
```

The package dependencies are:

- `python3 (>= 3.10)`
- `python3-tk`
- `python3-mido (>= 1.3.0)`

Debian 13 provides Python 3.13 and Mido 1.3.3 in its stable package archive.
The optional `tkinterdnd2` drag-and-drop extension is bundled in the PyInstaller
builds; the native Debian package uses the normal Tkinter file browser when
that optional extension is absent.

To remove the installed package:

```bash
sudo apt remove fur2mid
```

## Output files

All build output is written to `dist/`. Temporary PyInstaller and Debian staging
files are written to `build/`. The `.deb` is architecture-independent (`all`);
the PyInstaller output is specific to the runner architecture and operating
system.

## Notes

- The Linux portable archive is built on Ubuntu 22.04 to keep its glibc baseline
  lower than a build made on a newer distribution.
- The Debian package is for Debian 13+ (or derivatives with the declared
  dependency versions); it is not a universal package for every older Debian.
- This workflow compiles and packages only. It does not create an installer for
  Android, iOS, or other mobile platforms.
