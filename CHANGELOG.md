## 0.1.1 - Cross-platform build workflow

- Added a reusable PyInstaller build recipe for Windows, Linux, and macOS.
- Added GitHub Actions matrix builds and downloadable workflow artifacts.
- Added native Debian 13+ `.deb` packaging using system Python, Tkinter, and Mido.
- Added local build scripts and BUILDING.md instructions.

# Changelog

## 0.1.0 - Initial test build

- Added zlib and uncompressed `.fur` loading.
- Added legacy `INFO` parsing and a newer `INF2` / `SNG2` parser path.
- Added `PATN` row decoding and `INS2` instrument-name parsing.
- Added order playback reconstruction and bounded `0Bxx` loop expansion.
- Added MIDI Type 1 export with a conductor track and per-chip-channel tracks.
- Added GM program heuristics, volume/pan controls, pitch bends, modulation, tempo mapping, timeline markers, and JSON sidecar output.
- Added English Tkinter GUI, optional drag-and-drop, CLI, Windows launch/build scripts, sample files, and tests.
