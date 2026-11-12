#!/usr/bin/env python3
"""fur2mid - convert Furnace Tracker modules (.fur) into editable Standard MIDI files."""
import sys

# fur2mid uses modern standard-library and third-party package features.
# Check the interpreter before importing dataclasses or mido so older Python
# versions fail with an actionable message instead of a confusing traceback.
if sys.version_info < (3, 10):
    detected = ".".join(str(part) for part in sys.version_info[:3])
    raise SystemExit(
        "fur2mid requires Python 3.10 or newer; detected Python " + detected + ".\n"
        "Install Python 3.10+ and launch with 'py -3.10 main.py' or run_windows.bat."
    )

import argparse
import json
import math
import re
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable

try:
    import mido
except ImportError as exc:  # pragma: no cover - message is shown to CLI users
    raise SystemExit("Missing dependency: mido. Install it with: python -m pip install -r requirements.txt") from exc

MAGIC = b"-Furnace module-"

# Furnace system IDs and nominal channel counts. The list follows papers/format.md.
SYSTEMS: Dict[int, Tuple[str, int]] = {
    0x01: ("YMU759", 17), 0x03: ("SN76489", 4), 0x04: ("Game Boy", 4),
    0x05: ("PC Engine", 6), 0x06: ("NES", 5), 0x07: ("C64 8580", 3),
    0x47: ("C64 6581", 3), 0x80: ("AY-3-8910", 3), 0x81: ("Amiga", 4),
    0x82: ("YM2151", 8), 0x83: ("YM2612", 6), 0x84: ("TIA", 2),
    0x85: ("VIC-20", 4), 0x86: ("PET", 1), 0x87: ("SNES", 8),
    0x88: ("VRC6", 3), 0x89: ("YM2413 OPLL", 9), 0x8A: ("FDS", 1),
    0x8B: ("MMC5", 3), 0x8C: ("Namco 163", 8), 0x8D: ("YM2203", 6),
    0x8E: ("YM2608", 16), 0x8F: ("YM3526 OPL", 9), 0x90: ("YM3812 OPL2", 9),
    0x91: ("YMF262 OPL3", 18), 0x92: ("MultiPCM", 28), 0x93: ("PC Speaker", 1),
    0x94: ("POKEY", 4), 0x95: ("RF5C68", 8), 0x96: ("WonderSwan", 4),
    0x97: ("SAA1099", 6), 0x98: ("YM2414 OPZ", 8), 0x99: ("Pokémon Mini", 1),
    0x9A: ("AY8930", 3), 0x9B: ("SegaPCM", 16), 0x9C: ("Virtual Boy", 6),
    0x9D: ("VRC7", 6), 0x9E: ("YM2610B", 16), 0x9F: ("ZX Spectrum Beeper", 6),
    0xA0: ("YM2612 Extended", 9), 0xA1: ("SCC", 5), 0xA2: ("YM3526 OPL Drums", 11),
    0xA3: ("YM3812 OPL2 Drums", 11), 0xA4: ("YMF262 OPL3 Drums", 20),
    0xA5: ("Neo Geo YM2610", 14), 0xA6: ("Neo Geo YM2610 Extended", 17),
    0xA7: ("YM2413 OPLL Drums", 11), 0xA8: ("Atari Lynx", 4),
    0xAA: ("MSM6295", 4), 0xAB: ("MSM6258", 1), 0xAC: ("VERA", 17),
    0xAD: ("Bubble System WSG", 2), 0xAE: ("YMF278B OPL4", 42),
    0xAF: ("YMF278B OPL4 Drums", 44), 0xB0: ("X1-010", 16), 0xB1: ("ES5506", 32),
    0xB2: ("Y8950", 10), 0xB3: ("Y8950 Drums", 12), 0xB4: ("SCC+", 5),
    0xB5: ("Furnace Sound Unit", 8), 0xB6: ("YM2203 Extended", 9),
    0xB7: ("YM2608 Extended", 19), 0xB8: ("YMZ280B", 8), 0xB9: ("Namco WSG", 3),
    0xBA: ("Namco C15", 8), 0xBB: ("Namco C30", 8), 0xBC: ("MSM5232", 8),
    0xBD: ("YM2612 DualPCM Extended", 11), 0xBE: ("YM2612 DualPCM", 7),
    0xBF: ("T6W28", 4), 0xC0: ("PCM DAC", 1), 0xC1: ("YM2612 CSM", 10),
    0xC2: ("Neo Geo CSM", 18), 0xC3: ("YM2203 CSM", 10), 0xC4: ("YM2608 CSM", 20),
    0xC5: ("YM2610B CSM", 20), 0xC6: ("K007232", 2), 0xC7: ("GA20", 4),
    0xC8: ("SM8521", 3), 0xCA: ("ZX Spectrum QuadTone", 5), 0xCB: ("PV-1000", 3),
    0xCC: ("K053260", 4), 0xCD: ("TED", 2), 0xCE: ("C140", 24), 0xCF: ("C219", 16),
    0xD1: ("ESFM", 18), 0xD4: ("PowerNoise", 4), 0xD5: ("Dave", 6),
    0xD6: ("Nintendo DS", 16), 0xD7: ("GBA Direct Sound", 2), 0xD8: ("GBA MinMod", 16),
    0xD9: ("Bifurcator", 4), 0xE0: ("QSound", 19), 0xE2: ("C64 6581 PCM", 4),
    0xE3: ("Watara Supervision", 4), 0xE4: ("Namco Pole Position WSG", 8),
    0xE5: ("µPD1771C", 4), 0xE7: ("Klattsch", 1), 0xE9: ("SAA1099 Timers", 8),
    0xF0: ("SID2", 3), 0xF1: ("5E01", 5), 0xF5: ("SID3", 7), 0xFC: ("Pong", 1),
    0xFD: ("Dummy System", 8),
    # Legacy compound systems
    0x02: ("Genesis (YM2612 + SN76489)", 10),
    0x08: ("Arcade (YM2151 + SegaPCM)", 13),
    0x42: ("Genesis Extended (YM2612 + SN76489)", 13),
    0x43: ("SMS + OPLL", 13), 0x46: ("NES + VRC7", 11),
    0x09: ("Neo Geo CD", 13), 0x49: ("Neo Geo CD Extended", 16), 0xA9: ("SegaPCM Legacy", 5),
}


def _default_channel_names(system_id: int, count: int) -> List[str]:
    if system_id in (0x02, 0x42):
        return ["FM1", "FM2", "FM3", "FM4", "FM5", "FM6/DAC"] + ["PSG1", "PSG2", "PSG3"][:max(0, count-7)] + (["Noise"] if count > 10 else [])
    if system_id == 0x83:
        return ["FM1", "FM2", "FM3", "FM4", "FM5", "FM6/DAC"][:count]
    if system_id == 0xA0:
        return ["FM1", "FM2", "FM3", "FM4", "FM5", "FM6/DAC"] + [f"FM{i+1}" for i in range(6, count)]
    if system_id in (0xBD, 0xBE):
        return ["FM1", "FM2", "FM3", "FM4", "FM5", "FM6/DAC"] + [f"PCM{i+1}" for i in range(max(0, count-6))]
    if system_id == 0xC1:
        return [f"FM/CSM {i+1}" for i in range(count)]
    if system_id == 0x03 or system_id == 0xBF:
        return ["PSG1", "PSG2", "PSG3", "Noise"][:count]
    if system_id == 0x82:
        return [f"FM{i+1}" for i in range(count)]
    if system_id == 0x04:
        return ["Square 1", "Square 2", "Wave", "Noise"][:count]
    if system_id in (0x05,):
        return ["Wave 1", "Wave 2", "Wave 3", "Wave 4", "Wave 5", "Noise"][:count]
    if system_id in (0x06, 0x8B):
        names = ["Pulse 1", "Pulse 2", "Triangle", "Noise", "DPCM"]
        return names[:count]
    if system_id in (0x80, 0x9A):
        return [f"Tone {i+1}" for i in range(count)]
    if system_id in (0x87,):
        return [f"Voice {i+1}" for i in range(count)]
    if system_id in (0x81,):
        return [f"Sample {i+1}" for i in range(count)]
    label = SYSTEMS.get(system_id, (f"Chip {system_id:02X}", count))[0]
    return [f"{label} {i+1}" for i in range(count)]


class FurFormatError(ValueError):
    """Raised when a .fur file is malformed or unsupported."""


class Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def seek(self, pos: int) -> None:
        if pos < 0 or pos > len(self.data):
            raise FurFormatError(f"Offset outside file: 0x{pos:X}")
        self.pos = pos

    def read(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise FurFormatError(f"Unexpected end of file at 0x{self.pos:X} (wanted {n} bytes)")
        out = self.data[self.pos:self.pos+n]
        self.pos += n
        return out

    def u8(self) -> int: return self.read(1)[0]
    def i8(self) -> int: return struct.unpack("<b", self.read(1))[0]
    def u16(self) -> int: return struct.unpack("<H", self.read(2))[0]
    def i16(self) -> int: return struct.unpack("<h", self.read(2))[0]
    def u32(self) -> int: return struct.unpack("<I", self.read(4))[0]
    def i32(self) -> int: return struct.unpack("<i", self.read(4))[0]
    def f32(self) -> float: return struct.unpack("<f", self.read(4))[0]

    def cstring(self) -> str:
        end = self.data.find(b"\0", self.pos)
        if end < 0:
            raise FurFormatError(f"Unterminated string at 0x{self.pos:X}")
        raw = self.data[self.pos:end]
        self.pos = end + 1
        return raw.decode("utf-8", "replace")


@dataclass
class Cell:
    note: Optional[int] = None
    instrument: Optional[int] = None
    volume: Optional[int] = None
    raw_frequency: Optional[int] = None
    effects: List[Tuple[int, int]] = field(default_factory=list)


@dataclass
class Instrument:
    index: int
    name: str
    ins_type: int = 0
    gm_program: int = 80


@dataclass
class Pattern:
    subsong: int
    channel: int
    index: int
    name: str = ""
    rows: Dict[int, Cell] = field(default_factory=dict)


@dataclass
class SubSong:
    name: str = ""
    pattern_length: int = 64
    orders_length: int = 1
    highlight_a: int = 4
    highlight_b: int = 16
    hz: float = 60.0
    speed1: int = 6
    speed2: int = 6
    speed_pattern: List[int] = field(default_factory=list)
    virtual_tempo_n: int = 1
    virtual_tempo_d: int = 1
    orders: List[List[int]] = field(default_factory=list)  # channel -> order index
    effect_columns: List[int] = field(default_factory=list)
    channel_names: List[str] = field(default_factory=list)
    patterns: Dict[Tuple[int, int], Pattern] = field(default_factory=dict)  # (channel, pattern index)
    grooves: List[List[int]] = field(default_factory=list)


@dataclass
class FurSong:
    version: int
    name: str = ""
    author: str = ""
    system_name: str = ""
    master_volume: float = 1.0
    systems: List[Tuple[int, str, int, float, float, float]] = field(default_factory=list)
    instruments: List[Instrument] = field(default_factory=list)
    subsong: SubSong = field(default_factory=SubSong)
    warnings: List[str] = field(default_factory=list)

    @property
    def channel_count(self) -> int:
        return sum(s[2] for s in self.systems)

    def channel_meta(self) -> List[dict]:
        out = []
        global_index = 0
        for sid, label, count, volume, pan, _front in self.systems:
            defaults = _default_channel_names(sid, count)
            for i in range(count):
                explicit = self.subsong.channel_names[global_index] if global_index < len(self.subsong.channel_names) else ""
                ch_name = explicit.strip() or defaults[i]
                out.append({"index": global_index, "system_id": sid, "system": label,
                            "chip_channel": i, "name": ch_name,
                            "volume": volume, "pan": pan})
                global_index += 1
        return out


def _decompress_fur(raw: bytes) -> bytes:
    if raw.startswith(MAGIC):
        return raw
    try:
        data = zlib.decompress(raw)
    except zlib.error as exc:
        raise FurFormatError(f"Not a valid Furnace module or zlib stream: {exc}") from exc
    if not data.startswith(MAGIC):
        raise FurFormatError("The decompressed file does not contain the Furnace module signature")
    return data


def _read_pointer_list(r: Reader, count: int) -> List[int]:
    if count < 0 or count > 100000:
        raise FurFormatError(f"Implausible pointer count: {count}")
    return [r.u32() for _ in range(count)]


def _parse_old_info(data: bytes, info_pos: int, version: int) -> Tuple[FurSong, List[int], List[int]]:
    r = Reader(data, info_pos)
    if r.read(4) != b"INFO":
        raise FurFormatError("Invalid INFO header (legacy Furnace song header)")
    r.u32()  # block size
    time_base = r.u8()
    s1, s2, _arp = r.u8(), r.u8(), r.u8()
    hz = r.f32()
    pat_len, orders_len = r.u16(), r.u16()
    hilight_a, hilight_b = r.u8(), r.u8()
    ins_count, wave_count, sample_count = r.u16(), r.u16(), r.u16()
    pattern_count = r.u32()
    if pat_len < 1 or pat_len > 256 or orders_len < 1 or orders_len > 256:
        raise FurFormatError(f"Unsupported pattern/order dimensions: {pat_len} rows, {orders_len} orders")
    if ins_count > 256 or pattern_count > 100000:
        raise FurFormatError("Implausible instrument or pattern count")

    system_ids = list(r.read(32))
    old_volumes = [r.i8() / 64.0 for _ in range(32)]
    old_pans = [r.i8() / 127.0 for _ in range(32)]
    sys_flags = _read_pointer_list(r, 32)

    name, author = r.cstring(), r.cstring()
    tuning = r.f32() if version >= 33 else (r.u32() and 440.0)
    if not (20.0 <= tuning <= 2000.0):
        tuning = 440.0

    if version >= 37:
        r.read(20)  # legacy compatibility flags; values do not affect MIDI event extraction
    else:
        r.read(20)

    instrument_ptrs = _read_pointer_list(r, ins_count)
    if wave_count: r.read(4 * wave_count)
    if sample_count: r.read(4 * sample_count)
    pattern_ptrs = _read_pointer_list(r, pattern_count)

    # Expand legacy compound chip IDs the same way the Furnace loader does.
    systems: List[Tuple[int, str, int, float, float, float]] = []
    for idx, sid in enumerate(system_ids):
        if sid == 0:
            continue
        if sid not in SYSTEMS:
            raise FurFormatError(f"Unsupported Furnace system ID 0x{sid:02X}")
        label, count = SYSTEMS[sid]
        volume = old_volumes[idx]
        pan = old_pans[idx]
        if sid in (0x02, 0x42):
            if sid == 0x02:
                systems.append((0x83, "YM2612", 6, volume, pan, 0.0))
                systems.append((0x03, "SN76489", 4, volume * 0.375, pan, 0.0))
            else:
                systems.append((0xA0, "YM2612 Extended", 9, volume, pan, 0.0))
                systems.append((0x03, "SN76489", 4, volume * 0.375, pan, 0.0))
        elif sid == 0x08:
            systems.append((0x82, "YM2151", 8, volume, pan, 0.0))
            systems.append((0x9B, "SegaPCM", 5, volume, pan, 0.0))
        elif sid == 0x09:
            systems.append((0xA5, "Neo Geo YM2610", count, volume, pan, 0.0))
        elif sid == 0x49:
            systems.append((0xA6, "Neo Geo YM2610 Extended", count, volume, pan, 0.0))
        elif sid == 0xA9:
            systems.append((0x9B, "SegaPCM", count, volume, pan, 0.0))
        elif sid == 0x43:
            systems.append((0x03, "SN76489", 4, volume, pan, 0.0))
            systems.append((0x89, "YM2413 OPLL", 9, volume, pan, 0.0))
        elif sid == 0x46:
            systems.append((0x06, "NES", 5, volume, pan, 0.0))
            systems.append((0x9D, "VRC7", 6, volume, pan, 0.0))
        else:
            systems.append((sid, label, count, volume, pan, 0.0))

    total_channels = sum(s[2] for s in systems)
    if total_channels < 1 or total_channels > 128:
        raise FurFormatError(f"Invalid channel count: {total_channels}")

    # Orders are stored as channel-major rows.
    orders = [[r.u8() for _ in range(orders_len)] for _ in range(total_channels)]
    effect_columns = [r.u8() for _ in range(total_channels)]
    if any(c > 8 for c in effect_columns):
        raise FurFormatError("Unreasonably large effect-column count")
    channel_names = [""] * total_channels
    if version >= 39:
        r.read(total_channels)  # visibility
        r.read(total_channels)  # collapsed state
        channel_names = [r.cstring() for _ in range(total_channels)]
        r.read(total_channels)  # short names
        _song_notes = r.cstring()

    master_volume = r.f32() if version >= 59 else 2.0

    # Compatibility flags added after format 0.6pre0. The count is 28 bytes for v232.
    if version >= 70:
        ext_count = 28
        r.read(ext_count)

    if version >= 96:
        vt_n, vt_d = r.u16(), r.u16()
    else:
        r.read(4)
        vt_n, vt_d = 1, 1

    subsong_name = ""
    extra_subsong_ptrs: List[int] = []
    if version >= 95:
        subsong_name = r.cstring()
        r.cstring()  # subsong comment
        additional_subsongs = r.u8()
        r.read(3)
        extra_subsong_ptrs = _read_pointer_list(r, additional_subsongs)

    system_name = ""
    if version >= 103:
        system_name = r.cstring()
        r.cstring()  # category
        for _ in range(4): r.cstring()

    if version >= 135:
        updated = []
        for sid, label, count, _vol, _pan, _fr in systems:
            vol, pan, front = r.f32(), r.f32(), r.f32()
            updated.append((sid, label, count, vol, pan, front))
        systems = updated
        conn_count = r.u32()
        if conn_count > 100000: raise FurFormatError("Implausible patchbay connection count")
        r.read(conn_count * 4)
    if version >= 136:
        r.u8()  # automatic patchbay
    if version >= 138:
        r.read(8)  # newer compatibility flags

    speed_pattern: List[int] = []
    grooves: List[List[int]] = []
    if version >= 139:
        speed_len = r.u8()
        speeds = [r.u8() for _ in range(16)]
        if speed_len < 1 or speed_len > 16:
            speed_len = 1
        speed_pattern = [max(1, x * (time_base + 1)) for x in speeds[:speed_len]]
        groove_count = r.u8()
        if groove_count > 128: raise FurFormatError("Implausible groove count")
        for _ in range(groove_count):
            glen = r.u8()
            vals = [r.u8() for _ in range(16)]
            grooves.append(vals[:max(1, min(glen, 16))])
    else:
        # Before format 139 Furnace alternates between speed 1 and speed 2.
        speed_pattern = []

    if version >= 156:
        r.read(12)  # three asset-directory pointers

    sub = SubSong(name=subsong_name, pattern_length=pat_len, orders_length=orders_len,
                  highlight_a=max(1, hilight_a or 4), highlight_b=max(1, hilight_b or 16),
                  hz=hz if 1.0 <= hz <= 1000.0 else 60.0,
                  speed1=max(1, s1 * (time_base + 1)), speed2=max(1, s2 * (time_base + 1)),
                  speed_pattern=speed_pattern, virtual_tempo_n=max(1, vt_n),
                  virtual_tempo_d=max(1, vt_d), orders=orders,
                  effect_columns=effect_columns, channel_names=channel_names, grooves=grooves)
    song = FurSong(version=version, name=name, author=author, system_name=system_name,
                   master_volume=max(0.0, min(4.0, master_volume)), systems=systems, subsong=sub)
    if extra_subsong_ptrs:
        song.warnings.append(f"This module contains {len(extra_subsong_ptrs)} additional subsong(s); fur2mid exports the first subsong.")
    return song, instrument_ptrs, pattern_ptrs


def _parse_new_info(data: bytes, info_pos: int, version: int) -> Tuple[FurSong, List[int], List[int], List[int]]:
    r = Reader(data, info_pos)
    if r.read(4) != b"INF2":
        raise FurFormatError("Invalid INF2 header")
    r.u32()  # block size
    name, author = r.cstring(), r.cstring()
    system_name, _category = r.cstring(), r.cstring()
    for _ in range(4): r.cstring()  # Japanese metadata
    _tuning = r.f32()
    _auto_system = r.u8()
    master_volume = r.f32()
    channel_count, chip_count = r.u16(), r.u16()
    if channel_count < 1 or channel_count > 128 or chip_count < 1 or chip_count > 32:
        raise FurFormatError("Invalid INF2 channel/chip counts")
    systems = []
    total = 0
    for _ in range(chip_count):
        sid, ch_count = r.u16(), r.u16()
        vol, pan, front = r.f32(), r.f32(), r.f32()
        if sid not in SYSTEMS:
            label = f"Chip {sid:04X}"
        else:
            label = SYSTEMS[sid][0]
        systems.append((sid, label, ch_count, vol, pan, front))
        total += ch_count
    if total != channel_count:
        raise FurFormatError("INF2 total chip channels do not match the declared channel count")
    connections = r.u32()
    if connections > 100000: raise FurFormatError("Implausible patchbay connection count")
    r.read(connections * 4)
    r.u8()  # automatic patchbay

    element_ptrs: Dict[int, List[int]] = {}
    for _ in range(32):
        element_type = r.u8()
        if element_type == 0:
            break
        count = r.u32()
        element_ptrs[element_type] = _read_pointer_list(r, count)
    sub_ptrs = element_ptrs.get(1, [])
    instrument_ptrs = element_ptrs.get(4, [])
    pattern_ptrs = element_ptrs.get(7, [])
    if not sub_ptrs:
        raise FurFormatError("INF2 module does not contain a subsong")

    sr = Reader(data, sub_ptrs[0])
    if sr.read(4) != b"SNG2":
        raise FurFormatError("Invalid SNG2 subsong block")
    sr.u32()
    hz = sr.f32()
    _arp_speed, _effect_divider = sr.u8(), sr.u8()
    pattern_length, orders_length = sr.u16(), sr.u16()
    hilight_a, hilight_b = sr.u8(), sr.u8()
    vt_n, vt_d = max(1, sr.u16()), max(1, sr.u16())
    speed_len = sr.u8()
    speeds = [sr.i16() for _ in range(16)]
    if speed_len < 1 or speed_len > 16: speed_len = 1
    sub_name, _comment = sr.cstring(), sr.cstring()
    if pattern_length < 1 or pattern_length > 256 or orders_length < 1 or orders_length > 256:
        raise FurFormatError("Invalid SNG2 dimensions")
    orders = [[sr.u8() for _ in range(orders_length)] for _ in range(channel_count)]
    effect_cols = [sr.u8() for _ in range(channel_count)]
    sr.read(channel_count)  # hidden
    sr.read(channel_count)  # collapsed
    channel_names = [sr.cstring() for _ in range(channel_count)]
    sr.read(channel_count)  # short names
    # channel colors are 4 bytes each, used only for UI

    grooves: List[List[int]] = []
    for groove_ptr in element_ptrs.get(10, []):
        gr = Reader(data, groove_ptr)
        if gr.read(4) != b"GROV":
            raise FurFormatError(f"Invalid GROV block at 0x{groove_ptr:X}")
        gr.u32()  # block size
        groove_len = gr.u8()
        if groove_len < 1 or groove_len > 16:
            raise FurFormatError(f"Invalid GROV length: {groove_len}")
        groove_values = [gr.i16() for _ in range(16)]
        grooves.append([max(1, int(x)) for x in groove_values[:groove_len]])

    sub = SubSong(name=sub_name, pattern_length=pattern_length, orders_length=orders_length,
                  highlight_a=max(1, hilight_a or 4), highlight_b=max(1, hilight_b or 16),
                  hz=hz if 1.0 <= hz <= 1000.0 else 60.0,
                  speed_pattern=[max(1, int(x)) for x in speeds[:speed_len]],
                  virtual_tempo_n=vt_n, virtual_tempo_d=vt_d, orders=orders,
                  effect_columns=effect_cols, channel_names=channel_names, grooves=grooves)
    song = FurSong(version=version, name=name, author=author, system_name=system_name,
                   master_volume=max(0.0, min(4.0, master_volume)), systems=systems, subsong=sub)
    if len(sub_ptrs) > 1:
        song.warnings.append(f"This module contains {len(sub_ptrs)-1} additional subsong(s); fur2mid exports the first subsong.")
    return song, instrument_ptrs, pattern_ptrs, sub_ptrs


def _parse_instrument(data: bytes, ptr: int, index: int, version: int) -> Instrument:
    if ptr <= 0 or ptr + 12 > len(data):
        return Instrument(index, f"Instrument {index+1}")
    r = Reader(data, ptr)
    magic = r.read(4)
    block_size = r.u32()
    if magic not in (b"INS2", b"INST"):
        return Instrument(index, f"Instrument {index+1}")
    block_end = min(len(data), ptr + 8 + block_size)
    if magic == b"INS2":
        _format_version = r.u16()
        ins_type = r.u16()
        name = ""
        while r.pos + 4 <= block_end:
            code = r.read(2)
            size = r.u16()
            payload = r.read(size)
            if code == b"NA":
                name = payload.rstrip(b"\0").decode("utf-8", "replace")
            if code == b"EN":
                break
        return Instrument(index, name or f"Instrument {index+1}", ins_type)
    # Legacy INST instruments are uncommon in current modules. Read the version/type header
    # and keep a safe generated name rather than guessing at a version-specific structure.
    if r.pos + 3 <= block_end:
        _format_version = r.u16()
        ins_type = r.u8()
    else:
        ins_type = 0
    return Instrument(index, f"Instrument {index+1}", ins_type)


def _parse_pattern(data: bytes, ptr: int, version: int, default_subsong: int = 0, effect_columns=1, pattern_length: int = 256) -> Pattern:
    r = Reader(data, ptr)
    magic = r.read(4)
    block_size = r.u32()
    if magic == b"PATN":
        subsong = r.u8()
        channel = r.u16() if version >= 240 else r.u8()
        index = r.u16()
        pattern = Pattern(subsong, channel, index, r.cstring())
        end_pos = min(len(data), ptr + 8 + block_size)
        row = 0
        while row < 256 and r.pos < end_pos:
            mask = r.u8()
            if mask == 0xFF:
                break
            if mask & 0x80:
                row += (mask & 0x7F) + 2
                continue
            effect_mask = 0
            if mask & 0x20:
                effect_mask |= r.u8()
            if mask & 0x40:
                effect_mask |= r.u8() << 8
            if mask & 0x08: effect_mask |= 1
            if mask & 0x10: effect_mask |= 2
            cell = Cell()
            if mask & 0x01:
                note = r.u8()
                if note == 180: cell.note = 180
                elif note == 181: cell.note = 181
                elif note == 182: cell.note = 182
                elif note == 183:
                    # Preserve the raw chip frequency for a readable MIDI marker.
                    cell.raw_frequency = r.u32()
                    cell.note = None
                elif note < 180: cell.note = note
            if mask & 0x02: cell.instrument = r.u8()
            if mask & 0x04: cell.volume = r.u8()
            effects: List[Tuple[int, int]] = []
            for fx_index in range(8):
                code = None
                value = None
                if effect_mask & (1 << (fx_index * 2)):
                    code = r.u8()
                if effect_mask & (1 << (fx_index * 2 + 1)):
                    value = r.u8()
                if code is not None:
                    effects.append((code, value if value is not None else 0))
            cell.effects = effects
            if (cell.note is not None or cell.instrument is not None or cell.volume is not None
                    or cell.raw_frequency is not None or effects):
                pattern.rows[row] = cell
            row += 1
        return pattern

    if magic == b"PATR":
        channel, index = r.u16(), r.u16()
        subsong = r.u16() if version >= 95 else default_subsong
        r.u16()  # reserved
        # Legacy pattern payload: fixed-size rows of note/octave/ins/vol/effect pairs.
        pattern = Pattern(subsong, channel, index, "")
        channel_fx_cols = effect_columns[channel] if isinstance(effect_columns, list) and channel < len(effect_columns) else effect_columns
        for row in range(min(256, pattern_length)):
            note, octave = r.i16(), r.i16()
            ins, vol = r.i16(), r.i16()
            effects = []
            for _ in range(max(1, min(8, int(channel_fx_cols)))):
                fx, val = r.i16(), r.i16()
                if fx >= 0: effects.append((fx & 0xFF, val & 0xFF if val >= 0 else 0))
            cell = Cell()
            if not (note == 0 and octave == 0):
                if note == 0 and octave != 0:
                    note, octave = 12, octave - 1
                cell.note = ((octave + 5) * 12 + (note % 12))
            if ins >= 0: cell.instrument = ins & 0xFF
            if vol >= 0: cell.volume = vol & 0xFF
            cell.effects = effects
            if cell.note is not None or cell.instrument is not None or cell.volume is not None or effects:
                pattern.rows[row] = cell
        return pattern

    raise FurFormatError(f"Unknown pattern block signature {magic!r} at 0x{ptr:X}")


def load_fur(path: Path) -> FurSong:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FurFormatError(f"Could not read {path}: {exc}") from exc
    data = _decompress_fur(raw)
    if len(data) < 32 or data[:16] != MAGIC:
        raise FurFormatError("Invalid Furnace module header")
    hr = Reader(data, 16)
    version = hr.u16()
    hr.u16()  # reserved
    info_pos = hr.u32()
    if info_pos <= 0 or info_pos >= len(data):
        raise FurFormatError("Invalid song-info offset in module header")

    if version >= 240:
        song, ins_ptrs, pat_ptrs, _subsong_ptrs = _parse_new_info(data, info_pos, version)
    else:
        song, ins_ptrs, pat_ptrs = _parse_old_info(data, info_pos, version)

    song.instruments = [_parse_instrument(data, ptr, i, version) for i, ptr in enumerate(ins_ptrs)]
    for ptr in pat_ptrs:
        # Effect-column count is channel-specific in the INFO/SNG2 table.
        pat = _parse_pattern(data, ptr, version, effect_columns=song.subsong.effect_columns or 1,
                             pattern_length=song.subsong.pattern_length)
        if pat.subsong == 0:
            song.subsong.patterns[(pat.channel, pat.index)] = pat
    if not song.subsong.patterns:
        song.warnings.append("No pattern data was found in the first subsong.")
    return song


# General MIDI program number lookup (0-based); this only supplies editable placeholder timbres.
GM_RULES: List[Tuple[Tuple[str, ...], int]] = [
    (("grand piano", "acoustic piano", "piano"), 0), (("bright piano",), 1),
    (("electric piano", "rhodes", "epiano"), 4), (("honky",), 3),
    (("harpsichord",), 6), (("clav",), 7), (("celesta",), 8),
    (("music box", "musicbox"), 10), (("bell", "chime", "tubular"), 14),
    (("vibraphone", "vibes"), 11), (("marimba",), 12), (("xylophone",), 13),
    (("organ",), 16), (("guitar",), 24), (("bass",), 32),
    (("violin",), 40), (("viola",), 41), (("cello",), 42), (("string",), 48),
    (("brass", "trumpet", "trombone"), 56), (("sax",), 64), (("flute",), 73),
    (("pan flute",), 75), (("voice", "choir"), 52), (("lead", "solo", "square"), 80),
    (("saw", "synth"), 81), (("pad", "atmosphere"), 88), (("metal",), 114),
    (("noise", "snare", "kick", "drum"), 118),
]


def guess_gm_program(name: str, ins_type: int, system_id: int) -> int:
    low = name.casefold()
    # A stable chip-appropriate fallback is preferable to random GM instrument guessing.
    fallback = 80 if ins_type in (0, 1) else 81
    if system_id in (0x03, 0x04, 0x06) and any(x in low for x in ("noise", "drum", "kick", "snare")):
        fallback = 118
    for terms, program in GM_RULES:
        if any(term in low for term in terms):
            return program
    return fallback


def _clamp(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(value))))


def _furnace_note_to_midi(note: Optional[int]) -> Optional[int]:
    if note is None or note >= 180:
        return None
    # Furnace's absolute note numbering starts at C-(-5); MIDI note 12 is C0.
    # This matches the conventional MIDI octave numbering where note 60 is C4.
    return note - 48


def _get_cell(song: FurSong, channel: int, order: int, row: int) -> Cell:
    sub = song.subsong
    if channel >= len(sub.orders) or order >= len(sub.orders[channel]):
        return Cell()
    pattern_index = sub.orders[channel][order]
    pat = sub.patterns.get((channel, pattern_index))
    if not pat:
        return Cell()
    return pat.rows.get(row, Cell())


def _find_effect(cells: List[Cell], code: int) -> Optional[int]:
    for cell in cells:
        for fx, value in cell.effects:
            if fx == code:
                return value
    return None


@dataclass
class RowStep:
    order: int
    row: int
    speed: int
    cells: List[Cell]
    tick_rate: float
    virtual_ratio: float
    markers: List[str] = field(default_factory=list)
    loop_start: Optional[int] = None
    loop_end: Optional[int] = None


def build_playback(song: FurSong, loop_repeats: int) -> List[RowStep]:
    sub = song.subsong
    loop_repeats = max(0, min(32, int(loop_repeats)))
    route: List[RowStep] = []
    if not sub.orders:
        raise FurFormatError("The module has no channel order table")
    current_order, row = 0, 0
    global_row = 0
    tick_rate = sub.hz
    speed1, speed2 = sub.speed1, sub.speed2
    virtual_n, virtual_d = sub.virtual_tempo_n, sub.virtual_tempo_d
    speed_pattern = list(sub.speed_pattern or [])
    grooves = [list(g) for g in sub.grooves]
    speed_index = 0
    loop_counts: Dict[Tuple[int, int], int] = {}
    max_rows = max(1024, sub.orders_length * sub.pattern_length * (loop_repeats + 3) * 4)
    while 0 <= current_order < sub.orders_length and len(route) < max_rows:
        if global_row >= max_rows:
            song.warnings.append("Playback route reached the safety row limit; the module may contain an unbounded jump.")
            break
        cells = [_get_cell(song, ch, current_order, row) for ch in range(song.channel_count)]
        if speed_pattern:
            speed = max(1, int(speed_pattern[speed_index % len(speed_pattern)]))
        else:
            speed = max(1, int(speed1 if (speed_index % 2) == 0 else speed2))
        route.append(RowStep(current_order, row, speed, cells, tick_rate,
                             virtual_d / max(1, virtual_n)))
        # Furnace advances the speed cursor before row effects are processed.
        speed_index += 1
        step = route[-1]
        # Global flow/time commands are read from the first channel carrying one.
        jump_to = None
        break_to = None
        stop = False
        for cell in cells:
            for fx, val in cell.effects:
                if fx == 0x0B and jump_to is None: jump_to = val
                elif fx == 0x0D and break_to is None: break_to = val
                elif fx == 0xFF: stop = True
                elif fx == 0x09:
                    if grooves:
                        if 0 <= val < len(grooves):
                            speed_pattern = list(grooves[val])
                            speed_index = 0
                    elif val > 0:
                        speed1 = val
                        if speed_pattern:
                            speed_pattern[0] = val
                elif fx == 0x0F:
                    if val > 0:
                        if grooves:
                            # With a groove active Furnace changes its first speed entry.
                            if speed_pattern:
                                speed_pattern[0] = val
                        elif speed_pattern and len(speed_pattern) == 2:
                            speed_pattern[1] = val
                        elif speed_pattern:
                            speed_pattern[0] = val
                        else:
                            speed2 = val
                elif fx == 0xF0 and val > 0:
                    # The Furnace effect specifies a direct BPM value.
                    tick_rate = max(1.0, min(1023.0, (val * sub.highlight_a * speed) / 60.0))
                elif fx == 0xC0 and val > 0:
                    tick_rate = float(val)
                elif fx == 0xFD and val > 0:
                    virtual_n = val
                elif fx == 0xFE and val > 0:
                    virtual_d = val
        global_row += 1
        if stop:
            break
        if break_to is not None:
            current_order += 1
            row = max(0, min(sub.pattern_length - 1, break_to))
            continue
        if jump_to is not None:
            target = min(max(0, jump_to), sub.orders_length - 1)
            if target <= current_order:
                key = (current_order, target)
                count = loop_counts.get(key, 0)
                if count < loop_repeats:
                    step.loop_start = target
                    step.loop_end = current_order
                    loop_counts[key] = count + 1
                    current_order, row = target, 0
                    continue
                # Expand a bounded number of repeats, then let the song proceed.
                current_order += 1
                row = 0
                continue
            current_order, row = target, 0
            continue
        row += 1
        if row >= sub.pattern_length:
            current_order += 1
            row = 0
    if len(route) >= max_rows:
        song.warnings.append("Playback route was truncated at the configured safety limit.")
    if not route:
        raise FurFormatError("No playable rows were found")
    return route


class MidiTrackBuilder:
    def __init__(self, name: str, channel: int, ppq: int):
        self.name = name
        self.channel = channel
        self.ppq = ppq
        self.events: List[Tuple[int, int, object]] = []  # abs tick, priority, mido message
        self._serial = 0

    def add(self, tick: int, message, priority: int = 5):
        self.events.append((max(0, int(round(tick))), priority, message))
        self._serial += 1

    def add_marker(self, tick: int, text: str):
        self.add(tick, mido.MetaMessage("marker", text=text), 8)

    def finalize(self, optimize: bool = True) -> mido.MidiTrack:
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=self.name, time=0))
        # Sort note-offs before new note-ons at the same timestamp to keep retriggers clean.
        self.events.sort(key=lambda x: (x[0], x[1]))
        last_tick = 0
        # Compact duplicate program/controller/pitch-bend messages at the same absolute state.
        last_state = {}
        for tick, _priority, msg in self.events:
            key = None
            if not msg.is_meta:
                if msg.type == "control_change": key = (msg.channel, "cc", msg.control)
                elif msg.type == "program_change": key = (msg.channel, "program")
                elif msg.type == "pitchwheel": key = (msg.channel, "pitchwheel")
            if optimize and key is not None:
                val = msg.value if msg.type == "control_change" else msg.program if msg.type == "program_change" else msg.pitch
                if last_state.get(key) == val:
                    continue
                last_state[key] = val
            delta = max(0, tick - last_tick)
            msg.time = delta
            track.append(msg)
            last_tick = tick
        track.append(mido.MetaMessage("end_of_track", time=0))
        return track


def _pitchwheel_from_semitones(semitones: float, bend_range: float = 24.0) -> int:
    return _clamp(8192 + (semitones / bend_range) * 8192, 0, 16383) - 8192


def _pan_to_cc10(pan: float) -> int:
    return _clamp(64 + pan * 63, 0, 127)


def _volume_to_cc(value: int, max_value: int = 127, global_scale: float = 1.0) -> int:
    if max_value <= 0: max_value = 127
    return _clamp((value / max_value) * 127 * global_scale, 0, 127)


def _instrument_for(song: FurSong, index: Optional[int], system_id: int) -> Instrument:
    if index is not None and 0 <= index < len(song.instruments):
        ins = song.instruments[index]
        if ins.gm_program == 80 and ins.name:
            ins.gm_program = guess_gm_program(ins.name, ins.ins_type, system_id)
        return ins
    return Instrument(-1, "Default Furnace Instrument", 0, 80)


def _format_effect(code: int, value: int) -> str:
    return f"Furnace effect {code:02X}{value:02X}"


def convert_song(song: FurSong, output_path: Path, loop_repeats: int = 2,
                 volume_percent: int = 100, ppq: int = 480, optimize: bool = True) -> dict:
    sub = song.subsong
    loop_repeats = max(0, min(32, int(loop_repeats)))
    volume_percent = max(0, min(200, int(volume_percent)))
    route = build_playback(song, loop_repeats)
    channel_meta = song.channel_meta()
    if not channel_meta:
        raise FurFormatError("No channels are available for MIDI export")
    ppq = max(96, min(9600, int(ppq)))
    row_ticks = ppq / max(1, sub.highlight_a)
    midi = mido.MidiFile(type=1, ticks_per_beat=ppq)

    conductor = mido.MidiTrack()
    conductor.append(mido.MetaMessage("track_name", name="Furnace Tempo / Markers", time=0))
    beats_per_bar = max(1, int(round(sub.highlight_b / max(1, sub.highlight_a))))
    conductor.append(mido.MetaMessage("time_signature", numerator=beats_per_bar, denominator=4, time=0))
    conductor_events: List[Tuple[int, int, object]] = []

    # Channel allocation: use unique melodic MIDI channels; do not reserve channel 10
    # so that an actual Furnace noise channel remains independently editable.
    midi_channels = [i for i in range(16) if i != 9][:len(channel_meta)]
    if len(channel_meta) > len(midi_channels):
        song.warnings.append("The module has more than 15 channels; extra channels share a MIDI channel.")
    track_builders: List[MidiTrackBuilder] = []
    for meta in channel_meta:
        channel = midi_channels[meta["index"] % len(midi_channels)]
        name = f"{meta['system']} - {meta['name']}"
        track_builders.append(MidiTrackBuilder(name, channel, ppq))

    state = []
    output_scale = max(0, min(200, volume_percent)) / 100.0
    initial_programs = []
    for meta, builder in zip(channel_meta, track_builders):
        maxvol = 15 if meta["system_id"] in (0x03, 0xBF) else 127
        init_vol = _clamp(127 * song.master_volume * meta["volume"] * output_scale, 0, 127)
        first_ins_index = next((step.cells[meta["index"]].instrument for step in route
                                if meta["index"] < len(step.cells)
                                and step.cells[meta["index"]].instrument is not None), None)
        if first_ins_index is not None:
            init_program = _instrument_for(song, first_ins_index, meta["system_id"]).gm_program
        else:
            init_program = 118 if meta["name"].casefold() == "noise" else 80
        initial_programs.append(init_program)
        builder.add(0, mido.Message("program_change", channel=builder.channel, program=init_program), 2)
        builder.add(0, mido.Message("control_change", channel=builder.channel, control=7, value=init_vol), 1)
        builder.add(0, mido.Message("control_change", channel=builder.channel, control=10, value=_pan_to_cc10(meta["pan"])), 1)
        builder.add(0, mido.Message("control_change", channel=builder.channel, control=1, value=0), 1)
        # Set a known +/-24-semitone pitch-bend range via MIDI RPN 0,0.
        # This makes the generated pitch-bend glides meaningful in common DAWs/synths.
        for control, value in ((101, 0), (100, 0), (6, 24), (38, 0), (101, 127), (100, 127)):
            builder.add(0, mido.Message("control_change", channel=builder.channel, control=control, value=value), 1)
        builder.add(0, mido.Message("pitchwheel", channel=builder.channel, pitch=0), 1)
        state.append({"note": None, "inst": None, "program": None, "volume": init_vol,
                      "maxvol": maxvol, "pan": _pan_to_cc10(meta["pan"]), "pitch": 0.0,
                      "vibrato": None, "tremolo": None, "panbrello": None,
                      "volslide": None, "panslide": None, "pitchslide": None, "arp_speed": 1,
                      "pan_left": 255, "pan_right": 255,
                      "global_scale": song.master_volume * meta["volume"] * output_scale})

    warnings: List[str] = list(song.warnings)
    used_effects: Dict[str, int] = {}
    marker_set = set()
    current_tick_rate = sub.hz
    current_tempo = None
    loop_targets = {step.loop_start for step in route if step.loop_start is not None}
    loop_starts_written = set()
    absolute_row_tick = 0
    last_note_tick = 0

    def mark(tick: int, text: str):
        # Avoid a large amount of repeated identical marker text at the same position.
        key = (tick, text)
        if key not in marker_set:
            conductor_events.append((tick, 8, mido.MetaMessage("marker", text=text)))
            marker_set.add(key)

    for ri, step in enumerate(route):
        row_start = int(round(ri * row_ticks))
        # Each Furnace row is one fraction of a MIDI beat (highlight A rows per beat).
        row_sec = (step.speed / max(1.0, step.tick_rate)) * step.virtual_ratio
        if row_sec <= 0 or not math.isfinite(row_sec): row_sec = 0.1
        bpm = 60.0 / (row_sec * max(1, sub.highlight_a))
        tempo = _clamp(60_000_000 / max(1.0, bpm), 1, 0xFFFFFF)
        if tempo != current_tempo:
            conductor_events.append((row_start, 1, mido.MetaMessage("set_tempo", tempo=tempo)))
            current_tempo = tempo

        # Mark order boundaries and loop expansions for manual arrangement editing.
        if step.row == 0:
            mark(row_start, f"Order {step.order:02d}")
            if step.order in loop_targets and step.order not in loop_starts_written:
                mark(row_start, f"LOOP START - Order {step.order:02d}")
                loop_starts_written.add(step.order)
        if step.loop_start is not None:
            mark(row_start + int(row_ticks), f"LOOP END - Order {step.loop_end:02d} -> {step.loop_start:02d}")

        tracker_ticks = max(1, step.speed)
        tick_size = row_ticks / tracker_ticks
        row_end = row_start + row_ticks

        for ch, (cell, builder, st, meta) in enumerate(zip(step.cells, track_builders, state, channel_meta)):
            midi_ch = builder.channel
            effects = cell.effects
            fx_by_code = {fx: val for fx, val in effects}
            for fx, val in effects:
                used_effects[f"{fx:02X}"] = used_effects.get(f"{fx:02X}", 0) + 1

            # Instrument definitions become GM program changes plus human-readable markers.
            if cell.instrument is not None:
                ins = _instrument_for(song, cell.instrument, meta["system_id"])
                if st["inst"] != cell.instrument or st["program"] != ins.gm_program:
                    builder.add(row_start, mido.Message("program_change", channel=midi_ch, program=ins.gm_program), 2)
                    builder.add_marker(row_start, f"Instrument {cell.instrument:03d}: {ins.name} (GM {ins.gm_program+1:03d})")
                    st["inst"], st["program"] = cell.instrument, ins.gm_program

            # Volume column is chip-relative and is rendered as standard MIDI CC 7.
            if cell.volume is not None and not (0xD3 in fx_by_code or 0xD4 in fx_by_code):
                maxv = st["maxvol"]
                if cell.volume > maxv:
                    maxv = 255 if cell.volume > 127 else 127
                new_vol = _volume_to_cc(cell.volume, maxv, st["global_scale"])
                if new_vol != st["volume"]:
                    builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=7, value=new_vol), 2)
                    st["volume"] = new_vol

            if cell.raw_frequency is not None:
                builder.add_marker(row_start, f"Raw chip frequency: {cell.raw_frequency} (not directly representable in MIDI)")
            if cell.note == 182:
                builder.add_marker(row_start, "Furnace macro release")

            # Main note events and Furnace note-off / release values.
            target_note = _furnace_note_to_midi(cell.note)
            if target_note is not None and not 0 <= target_note <= 127:
                target_note = None
            delayed = fx_by_code.get(0xED, 0)
            cut = fx_by_code.get(0xEC, None)
            release = fx_by_code.get(0xFC, None)
            note_tick = row_start + int(round(min(tracker_ticks, delayed) * tick_size)) if delayed else row_start

            # Tone portamento: bend the held MIDI key to the new pitch, then hand over to
            # the target MIDI key at the end of the glide so the note remains editable.
            if target_note is not None and 0x03 in fx_by_code and st["note"] is not None:
                old_note = st["note"]
                diff = target_note - old_note
                porta_speed = max(1, fx_by_code[0x03])
                glide_ticks = max(1, min(tracker_ticks, int(math.ceil(abs(diff) * 8 / porta_speed))))
                for k in range(glide_ticks + 1):
                    fraction = k / glide_ticks
                    bend = _pitchwheel_from_semitones(diff * fraction)
                    tick = row_start + int(round(k * tick_size))
                    builder.add(tick, mido.Message("pitchwheel", channel=midi_ch, pitch=bend), 0 if k == glide_ticks else 4)
                porta_end = row_start + int(round(glide_ticks * tick_size))
                builder.add(porta_end, mido.Message("note_off", channel=midi_ch, note=old_note, velocity=0), 1)
                builder.add(porta_end, mido.Message("pitchwheel", channel=midi_ch, pitch=0), 2)
                builder.add(porta_end, mido.Message("note_on", channel=midi_ch, note=target_note, velocity=max(1, st["volume"])), 3)
                st["note"] = target_note
            elif target_note is not None:
                if st["note"] is not None:
                    builder.add(note_tick, mido.Message("note_off", channel=midi_ch, note=st["note"], velocity=0), 0)
                builder.add(note_tick, mido.Message("note_on", channel=midi_ch, note=target_note,
                                                   velocity=100), 3)
                st["note"] = target_note
            elif cell.note in (180, 181):
                if st["note"] is not None:
                    builder.add(row_start, mido.Message("note_off", channel=midi_ch, note=st["note"], velocity=0), 0)
                    st["note"] = None

            # Arpeggio (00xy): render the tracker cycle as short editable MIDI notes.
            if 0xE0 in fx_by_code:
                st["arp_speed"] = max(1, fx_by_code[0xE0])
            arp = next((v for c, v in effects if c == 0x00), None)
            if arp is not None and (target_note is not None or st["note"] is not None):
                arp_root = target_note if target_note is not None else st["note"]
                if st["note"] is not None:
                    builder.add(row_start, mido.Message("note_off", channel=midi_ch, note=st["note"], velocity=0), 0)
                x, y = (arp >> 4) & 0xF, arp & 0xF
                arp_notes = [arp_root, arp_root + x, arp_root + y]
                arp_notes = [n for n in arp_notes if 0 <= n <= 127]
                for k in range(0, tracker_ticks, st["arp_speed"]):
                    note = arp_notes[(k // st["arp_speed"]) % len(arp_notes)]
                    t0 = row_start + int(round(k * tick_size))
                    t1 = row_start + int(round(min(tracker_ticks, k + st["arp_speed"]) * tick_size))
                    builder.add(t0, mido.Message("note_on", channel=midi_ch, note=note, velocity=100), 3)
                    builder.add(t1, mido.Message("note_off", channel=midi_ch, note=note, velocity=0), 0)
                st["note"] = None

            # Note cut / delayed release / retrigger effects.
            if st["note"] is not None and cut is not None and cut > 0:
                t = row_start + int(round(min(tracker_ticks, cut) * tick_size))
                builder.add(t, mido.Message("note_off", channel=midi_ch, note=st["note"], velocity=0), 0)
                st["note"] = None
            if st["note"] is not None and release is not None and release > 0:
                t = row_start + int(round(min(tracker_ticks, release) * tick_size))
                builder.add(t, mido.Message("note_off", channel=midi_ch, note=st["note"], velocity=48), 0)
                st["note"] = None
            retrig = fx_by_code.get(0x0C, None)
            if st["note"] is not None and retrig:
                note = st["note"]
                interval = max(1, retrig)
                for k in range(interval, tracker_ticks, interval):
                    t = row_start + int(round(k * tick_size))
                    builder.add(t, mido.Message("note_off", channel=midi_ch, note=note, velocity=0), 0)
                    builder.add(t, mido.Message("note_on", channel=midi_ch, note=note, velocity=100), 3)

            # Furnace vibrato is represented as MIDI modulation, not as a fixed pitch shift.
            if 0x04 in fx_by_code:
                value = fx_by_code[0x04]
                vib_speed, vib_depth = (value >> 4) & 0xF, value & 0xF
                st["vibrato"] = (vib_speed, vib_depth)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=1, value=_clamp(vib_depth * 8, 0, 127)), 2)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=76, value=_clamp(vib_speed * 8, 0, 127)), 2)
            if 0xE4 in fx_by_code:
                # CC 77 is the General MIDI vibrato-depth controller. Furnace range
                # is in 1/16 semitones; 16 therefore maps to a full-scale CC value.
                range_cc = _clamp(fx_by_code[0xE4] * 8, 0, 127)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=77, value=range_cc), 2)
                builder.add_marker(row_start, f"Vibrato range: {fx_by_code[0xE4]}/16 semitone")
            if 0xE3 in fx_by_code:
                shapes = ["sine", "sine upper", "sine lower", "triangle", "ramp up", "ramp down", "square", "random", "square up", "square down", "half sine up", "half sine down"]
                shape = fx_by_code[0xE3]
                builder.add_marker(row_start, "Vibrato shape: " + (shapes[shape] if shape < len(shapes) else f"{shape:02X}"))
            if 0x04 in fx_by_code and fx_by_code[0x04] == 0:
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=1, value=0), 2)
                st["vibrato"] = None

            # Pitch slides are rendered as stepped pitch-bend curves, not a single
            # end-of-row jump. 01xx/02xx remain active until explicitly stopped by 00.
            if 0x01 in fx_by_code:
                st["pitchslide"] = (1, fx_by_code[0x01])
            elif 0x02 in fx_by_code:
                st["pitchslide"] = (-1, fx_by_code[0x02])
            if st["pitchslide"] and st["pitchslide"][1] == 0:
                st["pitchslide"] = None

            if 0xE5 in fx_by_code:
                st["pitch"] = (fx_by_code[0xE5] - 128) / 128.0
                builder.add(row_start, mido.Message("pitchwheel", channel=midi_ch,
                                                    pitch=_pitchwheel_from_semitones(st["pitch"])), 2)

            pitch_delta = 0.0
            if st["pitchslide"]:
                direction, slide_speed = st["pitchslide"]
                pitch_delta += direction * slide_speed * tracker_ticks / 64.0
            if 0xE1 in fx_by_code: pitch_delta += fx_by_code[0xE1] & 0x0F
            if 0xE2 in fx_by_code: pitch_delta -= fx_by_code[0xE2] & 0x0F

            # F1/F2 are single-tick pitch changes; the other slide commands glide
            # across the row at tracker-tick resolution.
            fine_delta = (fx_by_code.get(0xF1, 0) - fx_by_code.get(0xF2, 0)) / 64.0
            if fine_delta:
                st["pitch"] = max(-24.0, min(24.0, st["pitch"] + fine_delta))
                builder.add(row_start + int(round(tick_size)),
                            mido.Message("pitchwheel", channel=midi_ch,
                                         pitch=_pitchwheel_from_semitones(st["pitch"])), 4)
            if pitch_delta:
                start_pitch = st["pitch"]
                target_pitch = max(-24.0, min(24.0, start_pitch + pitch_delta))
                for k in range(1, tracker_ticks + 1):
                    pitch_at_tick = start_pitch + (target_pitch - start_pitch) * (k / tracker_ticks)
                    tick = row_start + int(round(k * tick_size))
                    builder.add(tick, mido.Message("pitchwheel", channel=midi_ch,
                                                   pitch=_pitchwheel_from_semitones(pitch_at_tick)), 4)
                st["pitch"] = target_pitch
            if target_note is not None and 0x03 not in fx_by_code and 0xE5 not in fx_by_code and not pitch_delta and not fine_delta and st["pitch"] != 0:
                builder.add(row_start, mido.Message("pitchwheel", channel=midi_ch, pitch=0), 1)
                st["pitch"] = 0.0

            # Pan controls.
            if 0x80 in fx_by_code:
                st["pan"] = _clamp(fx_by_code[0x80] * 127 / 255, 0, 127)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=10, value=st["pan"]), 2)
            if 0x08 in fx_by_code:
                v = fx_by_code[0x08]
                left, right = (v >> 4) & 0xF, v & 0xF
                total = max(1, left + right)
                pan = (right - left) / total
                st["pan"] = _pan_to_cc10(pan)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=10, value=st["pan"]), 2)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=11, value=_clamp(total / 30 * 127, 0, 127)), 2)
            if 0x81 in fx_by_code:
                st["pan_left"] = fx_by_code[0x81]
                total = max(1, st["pan_left"] + st["pan_right"])
                st["pan"] = _clamp(127 * st["pan_right"] / total, 0, 127)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=10, value=st["pan"]), 2)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=11, value=_clamp(total / 510 * 127, 0, 127)), 2)
            if 0x82 in fx_by_code:
                st["pan_right"] = fx_by_code[0x82]
                total = max(1, st["pan_left"] + st["pan_right"])
                st["pan"] = _clamp(127 * st["pan_right"] / total, 0, 127)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=10, value=st["pan"]), 2)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=11, value=_clamp(total / 510 * 127, 0, 127)), 2)
            if 0x88 in fx_by_code or 0x89 in fx_by_code or 0x8A in fx_by_code:
                builder.add_marker(row_start, "Rear-channel panning/level is not available in standard stereo MIDI")
            if 0x83 in fx_by_code:
                v = fx_by_code[0x83]
                left, right = (v >> 4) & 0xF, v & 0xF
                st["panslide"] = (left, right)
            if st["panslide"]:
                left, right = st["panslide"]
                st["pan"] = _clamp(st["pan"] + (right - left) * tracker_ticks, 0, 127)
                builder.add(row_end, mido.Message("control_change", channel=midi_ch, control=10, value=st["pan"]), 4)
            if 0x84 in fx_by_code:
                v = fx_by_code[0x84]
                rate, depth = (v >> 4) & 0xF, v & 0xF
                st["panbrello"] = (rate, depth) if depth else None
            if st["panbrello"]:
                rate, depth = st["panbrello"]
                for k in range(max(2, tracker_ticks)):
                    t = row_start + int(round(k * row_ticks / max(1, tracker_ticks)))
                    pan = _clamp(st["pan"] + math.sin((k / max(1, tracker_ticks)) * math.tau * max(1, rate)) * depth * 2, 0, 127)
                    builder.add(t, mido.Message("control_change", channel=midi_ch, control=10, value=pan), 4)

            # Volume slides/tremolo, expressed through standard MIDI expression/volume CCs.
            if 0x0A in fx_by_code or 0xFA in fx_by_code:
                v = fx_by_code.get(0x0A, fx_by_code.get(0xFA, 0))
                up, down = (v >> 4) & 0xF, v & 0xF
                scale = 4 if 0xFA in fx_by_code else 1
                st["volslide"] = (up * scale, down * scale)
            if 0xF3 in fx_by_code: st["volslide"] = (fx_by_code[0xF3] / 64.0, 0)
            if 0xF4 in fx_by_code: st["volslide"] = (0, fx_by_code[0xF4] / 64.0)
            if st["volslide"]:
                up, down = st["volslide"]
                newv = _clamp(st["volume"] + (up - down) * tracker_ticks, 0, 127)
                if newv != st["volume"]:
                    builder.add(row_end, mido.Message("control_change", channel=midi_ch, control=7, value=newv), 4)
                    st["volume"] = newv
            if 0xF8 in fx_by_code:
                st["volume"] = _clamp(st["volume"] + fx_by_code[0xF8], 0, 127)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=7, value=st["volume"]), 2)
            if 0xF9 in fx_by_code:
                st["volume"] = _clamp(st["volume"] - fx_by_code[0xF9], 0, 127)
                builder.add(row_start, mido.Message("control_change", channel=midi_ch, control=7, value=st["volume"]), 2)
            if 0x07 in fx_by_code:
                v = fx_by_code[0x07]
                rate, depth = (v >> 4) & 0xF, v & 0xF
                st["tremolo"] = (rate, depth) if depth else None
            if st["tremolo"]:
                rate, depth = st["tremolo"]
                for k in range(max(2, tracker_ticks)):
                    t = row_start + int(round(k * row_ticks / max(1, tracker_ticks)))
                    val = _clamp(st["volume"] - (1 - math.sin((k / max(1, tracker_ticks)) * math.tau * max(1, rate))) * depth * 4, 0, 127)
                    builder.add(t, mido.Message("control_change", channel=midi_ch, control=11, value=val), 4)
            if 0xDC in fx_by_code:
                t = row_start + int(round(min(tracker_ticks, fx_by_code[0xDC]) * tick_size))
                builder.add(t, mido.Message("control_change", channel=midi_ch, control=7, value=0), 4)

            # Volume portamento (D3/D4) approaches the volume column's destination.
            if (0xD3 in fx_by_code or 0xD4 in fx_by_code) and cell.volume is not None:
                slide_speed = max(1, fx_by_code.get(0xD3, fx_by_code.get(0xD4, 1))) * (4 if 0xD4 in fx_by_code else 1)
                target_max = st["maxvol"]
                if cell.volume > target_max:
                    target_max = 255 if cell.volume > 127 else 127
                target = _volume_to_cc(cell.volume, target_max, st["global_scale"])
                start_volume = st["volume"]
                step_count = max(1, min(tracker_ticks, int(math.ceil(abs(target-start_volume) * 4 / slide_speed))))
                for k in range(1, step_count + 1):
                    value = _clamp(start_volume + (target-start_volume) * k / step_count, 0, 127)
                    t = row_start + int(round(k * tracker_ticks / step_count * tick_size))
                    builder.add(t, mido.Message("control_change", channel=midi_ch, control=7, value=value), 4)
                st["volume"] = target

            # Set/clear macros and other chip-specific commands are recorded as markers.
            for fx, val in effects:
                if fx in (0xF5, 0xF6, 0xF7):
                    labels = {0xF5: "Disable macro", 0xF6: "Enable macro", 0xF7: "Restart macro"}
                    builder.add_marker(row_start, f"{labels[fx]} (macro {val:02X})")
                elif fx == 0xE7:
                    release_tick = row_start + int(round(min(tracker_ticks, val) * tick_size))
                    builder.add_marker(release_tick, f"Macro release (after {val} tracker ticks)")
                elif fx in (0x90, 0x91, 0x92):
                    builder.add_marker(row_start, f"Sample offset byte {fx-0x90+1}: {val:02X}")
                elif fx in (0xE6, 0xE8, 0xE9):
                    delay, semitones = (val >> 4) & 0xF, val & 0xF
                    direction = -1 if fx == 0xE9 or (fx == 0xE6 and delay >= 8) else 1
                    t = row_start + int(round(min(tracker_ticks, delay) * tick_size))
                    if st["note"] is not None and semitones:
                        shifted = _clamp(st["note"] + direction * semitones, 0, 127)
                        builder.add(t, mido.Message("note_off", channel=midi_ch, note=st["note"], velocity=0), 0)
                        builder.add(t, mido.Message("note_on", channel=midi_ch, note=shifted, velocity=100), 3)
                        st["note"] = shifted
                elif fx in (0x09, 0x0F, 0x0B, 0x0D, 0xFF, 0xF0, 0xC0, 0x04, 0x03,
                            0x00, 0x01, 0x02, 0x07, 0x08, 0x0A, 0x0C, 0x80, 0x83, 0x84,
                            0x81, 0x82, 0x88, 0x89, 0x8A, 0xD3, 0xD4, 0xDC, 0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5,
                            0xE6, 0xE7, 0xE8, 0xE9, 0xEC, 0xED, 0xFC, 0xFD, 0xFE, 0xF1, 0xF2, 0xF3, 0xF4, 0xF8, 0xF9,
                            0xF5, 0xF6, 0xF7):
                    continue
                else:
                    builder.add_marker(row_start, _format_effect(fx, val))
                    used_effects[f"unmapped_{fx:02X}"] = used_effects.get(f"unmapped_{fx:02X}", 0) + 1

        absolute_row_tick = row_end

    end_tick = int(round(len(route) * row_ticks))
    for builder, st in zip(track_builders, state):
        if st["note"] is not None:
            builder.add(end_tick, mido.Message("note_off", channel=builder.channel, note=st["note"], velocity=0), 0)
            st["note"] = None
        # Center pitch bend and release modulation at the end of the rendered sequence.
        builder.add(end_tick, mido.Message("pitchwheel", channel=builder.channel, pitch=0), 6)
        builder.add(end_tick, mido.Message("control_change", channel=builder.channel, control=1, value=0), 6)

    conductor_events.sort(key=lambda x: (x[0], x[1]))
    last_tick = 0
    for tick, _priority, msg in conductor_events:
        msg.time = max(0, tick - last_tick)
        conductor.append(msg)
        last_tick = tick
    conductor.append(mido.MetaMessage("end_of_track", time=0))
    midi.tracks.append(conductor)
    for builder in track_builders:
        midi.tracks.append(builder.finalize(optimize=optimize))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(str(output_path))

    # Sidecar: human-readable instrument/channel mapping and conversion diagnostics.
    mapping = {
        "tool": "fur2mid", "fur_version": song.version,
        "song": song.name, "author": song.author, "system": song.system_name,
        "midi_file": output_path.name, "rows_rendered": len(route),
        "loop_repeats": max(0, loop_repeats), "master_volume_percent": volume_percent,
        "instruments": [{"index": i.index, "name": i.name, "type": i.ins_type,
                         "gm_program": i.gm_program+1} for i in song.instruments],
        "channels": [{"midi_track": i+2, "name": meta["name"], "system": meta["system"],
                      "midi_channel": track_builders[i].channel+1, "initial_gm_program": initial_programs[i]+1,
                      "chip_volume": meta["volume"],
                      "chip_pan": meta["pan"]} for i, meta in enumerate(channel_meta)],
        "effects_seen": used_effects,
        "warnings": warnings,
    }
    sidecar = output_path.with_suffix(".fur2mid.json")
    sidecar.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    return mapping


def convert_file(input_path: Path, output_path: Optional[Path] = None, loop_repeats: int = 2,
                 volume_percent: int = 100, ppq: int = 480, optimize: bool = True) -> dict:
    song = load_fur(input_path)
    if output_path is None:
        output_path = input_path.with_suffix(".mid")
    return convert_song(song, output_path, loop_repeats, volume_percent, ppq, optimize)


# ---------- Drag-and-drop desktop front end ----------
def launch_gui(initial_file: Optional[str] = None) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
        root = TkinterDnD.Tk()
        dnd_available = True
    except Exception:
        root = tk.Tk()
        dnd_available = False
        DND_FILES = None

    root.title("fur2mid - Furnace to MIDI Converter")
    root.geometry("650x470")
    root.minsize(580, 420)
    root.configure(padx=18, pady=16)

    file_var = tk.StringVar(value=initial_file or "")
    output_var = tk.StringVar(value="")
    loop_var = tk.IntVar(value=2)
    volume_var = tk.IntVar(value=100)
    status_var = tk.StringVar(value="Drop a Furnace .fur module here or browse for a file.")

    title = ttk.Label(root, text="fur2mid", font=("Segoe UI", 20, "bold"))
    title.pack(anchor="w")
    subtitle = ttk.Label(root, text="Furnace Tracker module to editable Standard MIDI", foreground="#666666")
    subtitle.pack(anchor="w", pady=(0, 14))

    drop = tk.Label(root, text="DROP .FUR FILE HERE\n\nor use Browse...", relief="groove", bd=2,
                    bg="#f2f4f7", fg="#27364b", font=("Segoe UI", 12, "bold"), height=6)
    drop.pack(fill="x", pady=(0, 12))

    file_frame = ttk.Frame(root)
    file_frame.pack(fill="x", pady=3)
    ttk.Label(file_frame, text="Input module").pack(anchor="w")
    entry_row = ttk.Frame(file_frame)
    entry_row.pack(fill="x")
    ttk.Entry(entry_row, textvariable=file_var).pack(side="left", fill="x", expand=True)

    def browse_input():
        p = filedialog.askopenfilename(title="Select Furnace module", filetypes=[("Furnace modules", "*.fur"), ("All files", "*.*")])
        if p:
            set_input(p)

    ttk.Button(entry_row, text="Browse...", command=browse_input).pack(side="left", padx=(8, 0))

    out_frame = ttk.Frame(root)
    out_frame.pack(fill="x", pady=(8, 3))
    ttk.Label(out_frame, text="Output MIDI (optional)").pack(anchor="w")
    out_row = ttk.Frame(out_frame)
    out_row.pack(fill="x")
    ttk.Entry(out_row, textvariable=output_var).pack(side="left", fill="x", expand=True)

    def browse_output():
        p = filedialog.asksaveasfilename(title="Save MIDI file", defaultextension=".mid", filetypes=[("MIDI files", "*.mid")])
        if p: output_var.set(p)
    ttk.Button(out_row, text="Save as...", command=browse_output).pack(side="left", padx=(8, 0))

    settings = ttk.LabelFrame(root, text="Conversion settings", padding=10)
    settings.pack(fill="x", pady=12)
    row1 = ttk.Frame(settings)
    row1.pack(fill="x")
    ttk.Label(row1, text="Loop repeats").pack(side="left")
    ttk.Spinbox(row1, from_=0, to=32, width=5, textvariable=loop_var).pack(side="left", padx=(8, 25))
    ttk.Label(row1, text="Master output volume").pack(side="left")
    volume_label = ttk.Label(row1, text="100%", width=5)
    volume_label.pack(side="right")
    volume_slider = ttk.Scale(settings, from_=0, to=200, orient="horizontal", command=lambda v: (volume_var.set(int(float(v))), volume_label.configure(text=f"{int(float(v))}%")))
    volume_slider.set(100)
    volume_slider.pack(fill="x", pady=(7, 0))

    def set_input(value: str):
        file_var.set(value)
        if value and not output_var.get():
            output_var.set(str(Path(value).with_suffix(".mid")))
        if value:
            status_var.set(f"Ready to convert: {Path(value).name}")

    def on_drop(event):
        try:
            paths = root.tk.splitlist(event.data)
            if paths: set_input(paths[0])
        except Exception as exc:
            status_var.set(f"Could not read dropped path: {exc}")

    if dnd_available:
        drop.drop_target_register(DND_FILES)
        drop.dnd_bind("<<Drop>>", on_drop)

    def do_convert():
        src = Path(file_var.get().strip().strip('"'))
        if not src.is_file():
            messagebox.showerror("Missing input", "Choose or drop a valid .fur file first.")
            return
        if src.suffix.lower() != ".fur":
            messagebox.showerror("Unsupported file", "The input file must have a .fur extension.")
            return
        dst = Path(output_var.get().strip()) if output_var.get().strip() else src.with_suffix(".mid")
        try:
            result = convert_file(src, dst, loop_var.get(), volume_var.get())
        except Exception as exc:
            messagebox.showerror("Conversion failed", str(exc))
            status_var.set("Conversion failed.")
            return
        summary = (f"Created {dst.name}\n\n"
                   f"Rendered rows: {result['rows_rendered']}\n"
                   f"Instruments: {len(result['instruments'])}\n"
                   f"Channels: {len(result['channels'])}\n"
                   f"Sidecar: {dst.with_suffix('.fur2mid.json').name}")
        status_var.set(f"Conversion complete: {dst}")
        messagebox.showinfo("Conversion complete", summary)

    button_row = ttk.Frame(root)
    button_row.pack(fill="x")
    ttk.Button(button_row, text="Convert to MIDI", command=do_convert).pack(side="right")
    ttk.Label(root, textvariable=status_var, foreground="#3b536e", wraplength=600).pack(anchor="w", pady=(12, 0))
    if not dnd_available:
        ttk.Label(root, text="Drag-and-drop support is unavailable. Install tkinterdnd2 to enable it; Browse still works.", foreground="#777777", wraplength=600).pack(anchor="w", pady=(5, 0))
    if initial_file:
        set_input(initial_file)
    root.mainloop()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Convert Furnace Tracker .fur modules into editable MIDI files.")
    parser.add_argument("input", nargs="?", help="Input .fur module")
    parser.add_argument("-o", "--output", help="Output .mid path (default: input filename with .mid)")
    parser.add_argument("--loop-repeats", type=int, default=2, help="Number of additional loop passes for 0Bxx order loops (default: 2)")
    parser.add_argument("--volume", type=int, default=100, help="Master output level in percent (0-200, default: 100)")
    parser.add_argument("--ppq", type=int, default=480, help="MIDI ticks per quarter note (default: 480)")
    parser.add_argument("--no-gui", action="store_true", help="Do not open the desktop interface")
    parser.add_argument("--no-optimize", action="store_true", help="Disable redundant-event compaction")
    args = parser.parse_args(argv)

    if not args.input:
        if args.no_gui:
            parser.error("input is required when --no-gui is used")
        return launch_gui()

    src = Path(args.input).expanduser()
    dst = Path(args.output).expanduser() if args.output else None
    try:
        result = convert_file(src, dst, max(0, args.loop_repeats), max(0, min(200, args.volume)), args.ppq, not args.no_optimize)
    except Exception as exc:
        print(f"fur2mid: error: {exc}", file=sys.stderr)
        return 1
    out = dst or src.with_suffix(".mid")
    print(f"Created: {out}")
    print(f"Rows rendered: {result['rows_rendered']}")
    print(f"Instruments: {len(result['instruments'])}; channels: {len(result['channels'])}")
    print(f"Instrument map: {out.with_suffix('.fur2mid.json')}")
    for warning in result.get("warnings", []):
        print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
