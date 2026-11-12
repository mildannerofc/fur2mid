<img width="652" height="563" alt="image" src="https://github.com/user-attachments/assets/4b38fc8c-a023-4e13-81fc-de497109226f" />

# fur2mid

**fur2mid** is a Python utility that converts Furnace Tracker `.fur` modules into editable Standard MIDI Files. It reads the Furnace module structure directly; it does not require an intermediate VGM export.

The project is designed for arranging and editing tracker music in a MIDI sequencer. It reconstructs note events from Furnace orders and patterns, creates a separate MIDI track for each source chip channel, assigns editable General MIDI programs, builds a tempo map, converts common tracker effects into MIDI controllers and pitch bends, and records effects that cannot be represented faithfully as MIDI as timeline markers.

> **Important:** Standard MIDI cannot carry a Furnace FM patch, chip register state, hardware envelope, wavetable, or sample bank. fur2mid preserves instrument labels and creates editable GM program assignments, but GM playback is an approximation of the original chip timbres.

## Features

- Reads zlib-compressed and uncompressed Furnace modules.
- Parses the legacy `INFO` song header used by the supplied Furnace v232 test module.
- Includes a parser path for the newer `INF2` / `SNG2` module layout.
- Reads `PATN` pattern data and `INS2` instrument names.
- Builds a playback sequence from the order table, including `0Bxx` order jumps.
- Expands order loops into a finite MIDI arrangement. The default is **two additional loop passes** after the first pass.
- Exports one MIDI track per Furnace chip channel, with native channel labels such as `YM2612 - FM1`, `YM2612 - FM6/DAC`, `SN76489 - PSG1`, and `SN76489 - Noise`.
- Maps Furnace instruments to editable GM program changes using name-based heuristics and chip-appropriate fallbacks; every track also receives an initial GM patch.
- Exports chip/song volume and pattern volume as MIDI CC 7; the output volume can be adjusted from 0% to 200%. Notes use a neutral velocity of 100 so channel volume is not applied twice.
- Exports chip panning and supported panning effects as MIDI CC 10.
- Converts Furnace vibrato to the MIDI Modulation Wheel (CC 1), with vibrato rate on CC 76.
- Converts portamento and pitch slides into pitch-bend events, and writes MIDI RPN 0,0 to set a known ±24-semitone bend range.
- Writes a tempo map from Furnace tick rate, row speed, virtual tempo, row/beat settings, and legacy or modern groove patterns; `09xx` and `0Fxx` update the active speed/groove state.
- Adds order, loop, instrument, and unsupported-effect markers to help with manual editing.
- Removes redundant repeated controller/program/pitch-bend events during MIDI export.
- Includes a small English-language desktop interface with drag-and-drop support (when `tkinterdnd2` is installed), plus a command-line interface.
- Writes a `.fur2mid.json` sidecar with the instrument map, MIDI channel map, effects encountered, and conversion warnings.

## Quick start on Windows

1. Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/). During setup, enable the Python launcher (`py`).
2. Extract this ZIP file to a normal folder.
3. Double-click `run_windows.bat`.
4. Drop a `.fur` file into the window, or click **Browse...**.
5. Set the loop repeat count and master output volume, then click **Convert to MIDI**.

The first launch installs the Python dependencies from `requirements.txt`.

### Enable drag and drop

The GUI uses `tkinterdnd2` for native file dropping. It is included in `requirements.txt`. If it is unavailable on the system, the application still opens and the **Browse...** button remains usable.

## Command-line usage

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Convert a module using default settings:

```bash
python main.py "song.fur"
```

Choose an output path:

```bash
python main.py "song.fur" --output "song_editable.mid"
```

Control loop expansion and output level:

```bash
python main.py "song.fur" --loop-repeats 2 --volume 100
```

Available options:

| Option | Default | Description |
|---|---:|---|
| `input` | — | Input Furnace `.fur` file. |
| `-o`, `--output` | Same basename with `.mid` | Output MIDI path. |
| `--loop-repeats` | `2` | Number of extra passes through a backward `0Bxx` order loop (0–32). `0` disables loop expansion. |
| `--volume` | `100` | Master output scaling, from 0 to 200 percent. |
| `--ppq` | `480` | MIDI ticks per quarter note. |
| `--no-gui` | Off | Use command-line mode only. |
| `--no-optimize` | Off | Keep redundant controller/program events instead of compacting them. |

## Effect conversion

MIDI has no direct representation for every Furnace command. fur2mid converts the effects that have a useful MIDI equivalent and writes markers for hardware-specific or otherwise non-portable commands.

| Furnace effect | MIDI conversion |
|---|---|
| `00xy` Arpeggio | Alternating short MIDI notes inside the tracker row. `E0xx` changes the arpeggio step interval. |
| `01xx`, `02xx` Pitch slide | Pitch-bend movement. |
| `03xx` Portamento | Pitch-bend glide from the held note to the new target note. |
| `04xy` Vibrato | Modulation Wheel CC 1; vibrato rate is also sent on CC 76. |
| `07xy` Tremolo | Repeating Expression CC 11 values. |
| `08xy`, `80xx` Panning | Approximate stereo balance on CC 10. |
| `0Axy`, `FAxy` Volume slide | CC 7 volume changes. `FAxy` uses a faster scale. |
| `0Bxx` Jump to order | Reconstructs the playback route and expands backward jumps into finite repeated sections. Loop markers are added to the conductor track. |
| `0Cxx` Retrigger | Repeated note-off/note-on events at the requested tracker tick interval. |
| `0Dxx` Pattern break | Advances to the next order at the requested row. |
| `0Fxx`, `09xx` Speed | Updates the row-speed state and therefore the following MIDI tempo map. |
| `Cxxx`, `F0xx` Tick rate / BPM | Changes the following tempo-map entries. |
| `81xx`, `82xx` Left/right volume | Approximate stereo balance and level using CC 10 and CC 11. |
| `83xy`, `84xy` Pan slide / panbrello | CC 10 movement / oscillation. |
| `D3xx`, `D4xx` Volume portamento | CC 7 ramp toward the row's volume-column target. |
| `DCxx` Delayed mute | Sets CC 7 to zero after the requested tick count. |
| `E1xy`, `E2xy`, `E5xx`, `F1xx`, `F2xx` Pitch adjustments | Pitch-bend offsets or slides. |
| `E3xx`, `E4xx` Vibrato shape / range | Shape is a marker; range is sent approximately through CC 77 and also retained as a marker. |
| `E6xy`, `E8xy`, `E9xy` Quick legato | Transposed note event after the requested delay. |
| `ECxx`, `EDxx`, `FCxx` Note cut / delay / release | Note-off timing and delayed note-on events. |
| `F3xx`, `F4xx`, `F8xx`, `F9xx` Fine/single-tick volume | CC 7 changes. |
| `E7xx`, `F5xx`, `F6xx`, `F7xx` Macro controls | Timed macro-release and macro-control timeline markers because MIDI has no Furnace macro engine. |
| `90xx`, `91xx`, `92xx` Sample offset | Timeline markers; MIDI has no sample-memory offset command. |
| Rear-channel and chip-specific effects | Timeline markers when no reliable standard MIDI equivalent exists. |

Effects such as chip-specific waveform, register, filter, macro, sample-bank, and hardware-envelope commands cannot be recreated as standard MIDI data. They are not silently discarded: unsupported commands are retained as readable markers and counted in the JSON sidecar.

## Instrument mapping

Each Furnace instrument is assigned a General MIDI program number. The converter first checks the source instrument name for common terms such as `piano`, `bass`, `guitar`, `bell`, `organ`, `strings`, `brass`, `lead`, `pad`, or `noise`. If no match is found, it uses a stable chip/type fallback (usually a synth lead).

The output contains:

- MIDI program changes for instruments used on each channel.
- An instrument marker with the original Furnace instrument index and name.
- A sidecar JSON map containing all parsed instrument names and their assigned GM program numbers.

The map is intended to make the MIDI easy to re-voice manually in a DAW. It is not an FM patch conversion or a soundfont extraction feature.

## Output files

For `song.fur`, the default output is:

- `song.mid` — Standard MIDI File, Type 1, with a conductor/tempo track and one track per Furnace channel.
- `song.fur2mid.json` — instrument assignments, channel mapping, effects encountered, and warnings.

## Build a standalone Windows application

The source distribution includes `build_exe.bat`. Run it on Windows after installing Python 3.10+:

```bat
build_exe.bat
```

PyInstaller writes the application under `dist\fur2mid\`. The executable is not included in this source ZIP because it must be built for the target Windows environment.

## Tests

The ZIP includes the user-provided sample module and reference MIDI in `examples/`.

Run the included tests with:

```bash
python -m unittest discover -s tests -v
```

The test suite checks the supplied v232 module, verifies the exported MIDI tracks and events, and exercises bounded `0Bxx` loop expansion with a synthetic pattern.

## Format and design references

- [Furnace file format (`papers/format.md`)](https://github.com/tildearrow/furnace/blob/master/papers/format.md) — module header, legacy `INFO`, newer `INF2` / `SNG2`, orders, patterns, and element blocks.
- [Furnace effect list (`doc/3-pattern/effects.md`)](https://github.com/tildearrow/furnace/blob/master/doc/3-pattern/effects.md) — effect IDs, effect values, continuous effects, and their tracker behavior.
- [Furnace instrument format (`papers/newIns.md`)](https://github.com/tildearrow/furnace/blob/master/papers/newIns.md) — `INS2` feature blocks and instrument-name data.
- [VGM-Studio](https://github.com/EdwardPaulsen/VGM-Studio) — a reference for reconstructing chip-channel events into editable MIDI tracks. fur2mid is a separate Python implementation and does not include VGM-Studio source code.

## Current test note

The bundled `options music.fur` sample is Furnace format version **232**. It is compressed with zlib and contains a Genesis/Mega Drive YM2612 + SN76489 setup, 14 instruments, 10 channels, and 20 pattern blocks. The included generated MIDI is a basic conversion smoke test, not a guarantee that every Furnace-specific feature in every module will be perfectly represented.

## License

This project is distributed under the MIT License. The Furnace format and effect documentation remain the work of the Furnace project and its contributors; see the reference links above for the upstream project and its license.

## Cross-platform build workflow

The repository now includes `.github/workflows/build.yml` for native Windows,
Linux, and macOS builds. Build outputs are uploaded as GitHub Actions artifacts.
Debian users can also build/install the native `fur2mid_<version>_all.deb`
package. See [BUILDING.md](BUILDING.md) for local build commands, Debian
dependencies, and artifact names.
