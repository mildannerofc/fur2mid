import json
import tempfile
import unittest
from pathlib import Path

import mido

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fur2mid import FurSong, SubSong, Pattern, Cell, Instrument, load_fur, build_playback, convert_file, convert_song


class Fur2MidTests(unittest.TestCase):
    def setUp(self):
        self.sample = ROOT / "examples" / "options music.fur"

    def _make_minimal_v240_module(self, path):
        import struct
        from fur2mid import MAGIC

        def cstr(value):
            return value.encode("utf-8") + b"\0"

        # Build SNG2, PATN and INS2 first; their pointers are patched into INF2 below.
        sng = bytearray(b"SNG2" + b"\0\0\0\0")
        sng += struct.pack("<fBBHHBBHHB", 60.0, 1, 1, 2, 1, 4, 16, 1, 1, 1)
        sng += struct.pack("<16H", 6, *([0] * 15))
        sng += cstr("New Format Test") + cstr("")
        sng += bytes([0])  # channel 0, order 0
        sng += bytes([1])  # one effect column
        sng += bytes([0, 0])  # hidden, collapsed
        sng += cstr("FM1") + cstr("FM1") + bytes(4)  # channel name, short name, RGBA
        struct.pack_into("<I", sng, 4, len(sng) - 8)

        pat = bytearray(b"PATN" + b"\0\0\0\0")
        pat += struct.pack("<BHH", 0, 0, 0) + cstr("Pattern 00")
        pat += bytes([0x01, 108, 0xFF])  # note C-4 and end of pattern data
        struct.pack_into("<I", pat, 4, len(pat) - 8)

        ins = bytearray(b"INS2" + b"\0\0\0\0")
        ins += struct.pack("<HH", 1, 0)
        ins += b"NA" + struct.pack("<H", len(cstr("New Instrument"))) + cstr("New Instrument")
        ins += b"EN" + struct.pack("<H", 0)
        struct.pack_into("<I", ins, 4, len(ins) - 8)

        groove = bytearray(b"GROV" + b"\0\0\0\0")
        groove += bytes([2]) + struct.pack("<16H", 5, 7, *([0] * 14))
        struct.pack_into("<I", groove, 4, len(groove) - 8)

        # INF2 block length is fixed once the element pointer table is included.
        inf_prefix = bytearray(b"INF2" + b"\0\0\0\0")
        inf_prefix += cstr("New Format Test") + cstr("Tester") + cstr("Mega Drive") + cstr("Test")
        inf_prefix += cstr("") * 4
        inf_prefix += struct.pack("<fBfHH", 440.0, 0, 1.0, 1, 1)
        inf_prefix += struct.pack("<HHfff", 0x83, 1, 1.0, 0.0, 0.0)
        inf_prefix += struct.pack("<IB", 0, 0)  # empty patchbay, automatic patchbay off
        element_table_len = (1 + 4 + 4) * 4 + 1  # four elements and terminator
        sng_ptr = 32 + len(inf_prefix) + element_table_len
        ins_ptr = sng_ptr + len(sng)
        pat_ptr = ins_ptr + len(ins)
        groove_ptr = pat_ptr + len(pat)
        inf_prefix += bytes([1]) + struct.pack("<II", 1, sng_ptr)
        inf_prefix += bytes([4]) + struct.pack("<II", 1, ins_ptr)
        inf_prefix += bytes([7]) + struct.pack("<II", 1, pat_ptr)
        inf_prefix += bytes([10]) + struct.pack("<II", 1, groove_ptr)
        inf_prefix += bytes([0])
        struct.pack_into("<I", inf_prefix, 4, len(inf_prefix) - 8)
        header = MAGIC + struct.pack("<HHI", 240, 0, 32) + bytes(8)
        path.write_bytes(header + inf_prefix + sng + ins + pat + groove)

    def test_reads_new_inf2_sng2_module_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new-format.fur"
            self._make_minimal_v240_module(path)
            song = load_fur(path)
        self.assertEqual(song.version, 240)
        self.assertEqual(song.name, "New Format Test")
        self.assertEqual(song.channel_count, 1)
        self.assertEqual(song.instruments[0].name, "New Instrument")
        self.assertEqual(song.subsong.patterns[(0, 0)].rows[0].note, 108)
        self.assertEqual(song.subsong.grooves, [[5, 7]])

    def test_09_selects_grooves_and_0f_updates_the_active_groove(self):
        sub = SubSong(pattern_length=3, orders_length=1, highlight_a=4, highlight_b=16,
                      hz=60.0, speed_pattern=[6, 6], grooves=[[3, 5]],
                      orders=[[0]], effect_columns=[1])
        pattern = Pattern(0, 0, 0, rows={
            0: Cell(effects=[(0x09, 0)]),
            1: Cell(effects=[(0x0F, 7)]),
        })
        sub.patterns[(0, 0)] = pattern
        song = FurSong(version=240, systems=[(0x83, "YM2612", 1, 1.0, 0.0, 0.0)], subsong=sub)
        route = build_playback(song, loop_repeats=0)
        self.assertEqual([step.speed for step in route], [6, 3, 5])

    def test_reads_provided_furnace_module(self):
        song = load_fur(self.sample)
        self.assertEqual(song.version, 232)
        self.assertEqual(len(song.instruments), 14)
        self.assertEqual(song.channel_count, 10)
        self.assertGreaterEqual(len(song.subsong.patterns), 10)
        self.assertEqual(song.systems[0][0], 0x83)
        self.assertEqual(song.systems[1][0], 0x03)

    def test_converts_sample_into_editable_midi(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "sample.mid"
            result = convert_file(self.sample, output, loop_repeats=2, volume_percent=100)
            self.assertTrue(output.exists())
            self.assertTrue(output.with_suffix(".fur2mid.json").exists())
            midi = mido.MidiFile(str(output))
            self.assertEqual(midi.type, 1)
            self.assertEqual(len(midi.tracks), 11)  # conductor + ten native chip channels
            names = [next((m.name for m in t if m.type == "track_name"), "") for t in midi.tracks]
            self.assertIn("YM2612 - FM6/DAC", names)
            self.assertIn("SN76489 - Noise", names)
            note_ons = [m for t in midi.tracks for m in t if m.type == "note_on" and m.velocity]
            programs = [m for t in midi.tracks for m in t if m.type == "program_change"]
            volumes = [m for t in midi.tracks for m in t if m.type == "control_change" and m.control == 7]
            self.assertGreater(len(note_ons), 100)
            self.assertGreater(len(programs), 0)
            for track in midi.tracks[1:]:
                self.assertTrue(any(m.type == "program_change" for m in track), "Each native channel should get an initial GM patch")
            noise_track = next(t for t in midi.tracks if any(m.type == "track_name" and m.name == "SN76489 - Noise" for m in t))
            self.assertTrue(any(m.type == "program_change" and m.program == 118 for m in noise_track))
            self.assertGreater(len(volumes), 10)
            self.assertEqual(result["rows_rendered"], 128)
            sidecar = json.loads(output.with_suffix(".fur2mid.json").read_text(encoding="utf-8"))
            self.assertEqual(len(sidecar["instruments"]), 14)

    def test_furnace_effects_become_editable_midi_controls(self):
        sub = SubSong(pattern_length=3, orders_length=1, highlight_a=4, highlight_b=16,
                      hz=60.0, speed1=6, speed2=6, speed_pattern=[6],
                      orders=[[0]], effect_columns=[4])
        pattern = Pattern(0, 0, 0, rows={
            0: Cell(note=108, instrument=0, volume=100,
                    effects=[(0x04, 0x4F), (0xE4, 16), (0x07, 0x24), (0x84, 0x23)]),
            1: Cell(note=120, volume=80, effects=[(0x03, 12), (0xD3, 8)]),
            2: Cell(effects=[(0x00, 0x37)]),
        })
        sub.patterns[(0, 0)] = pattern
        song = FurSong(version=232, name="Effect Test",
                       systems=[(0x83, "YM2612", 1, 1.0, 0.0, 0.0)],
                       instruments=[Instrument(0, "Synth Bass", 0, 38)], subsong=sub)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "effects.mid"
            convert_song(song, output, loop_repeats=0, volume_percent=100)
            midi = mido.MidiFile(str(output))
        track = midi.tracks[1]
        absolute = 0
        events = []
        for msg in track:
            absolute += msg.time
            events.append((absolute, msg))
        cc1 = [m for _, m in events if m.type == "control_change" and m.control == 1]
        cc76 = [m for _, m in events if m.type == "control_change" and m.control == 76]
        cc77 = [m for _, m in events if m.type == "control_change" and m.control == 77]
        cc11_late = [(tick, m) for tick, m in events if m.type == "control_change" and m.control == 11 and tick >= 240]
        cc10_late = [(tick, m) for tick, m in events if m.type == "control_change" and m.control == 10 and tick >= 240]
        self.assertTrue(any(m.value > 0 for m in cc1))
        self.assertTrue(any(m.value == 32 for m in cc76))
        self.assertTrue(any(m.value == 127 for m in cc77))
        self.assertTrue(cc11_late, "Tremolo should continue on following rows")
        self.assertTrue(cc10_late, "Panbrello should continue on following rows")
        # Pitch-bend sensitivity RPN 0,0 must be configured to +/-24 semitones.
        rpn_data = [(m.control, m.value) for _, m in events if m.type == "control_change" and m.control in (101, 100, 6)]
        self.assertIn((101, 0), rpn_data)
        self.assertIn((100, 0), rpn_data)
        self.assertIn((6, 24), rpn_data)
        bends = [m.pitch for _, m in events if m.type == "pitchwheel"]
        self.assertTrue(any(v != 0 for v in bends))
        # D3xx with a volume-column target ramps rather than jumping at row start.
        cc7 = [(tick, m.value) for tick, m in events if m.type == "control_change" and m.control == 7]
        self.assertTrue(any(tick > 120 and 80 <= value < 100 for tick, value in cc7))
        # Arpeggio without a fresh note reuses the currently held target note.
        note_ons = [(tick, m.note) for tick, m in events if m.type == "note_on" and m.velocity > 0]
        self.assertTrue(any(tick >= 240 and note in (72, 75, 79) for tick, note in note_ons))

    def test_0b_order_jump_is_expanded_as_a_finite_loop(self):
        sub = SubSong(pattern_length=2, orders_length=2, highlight_a=4, highlight_b=16,
                      hz=60.0, speed1=6, speed2=6, orders=[[0, 1]], effect_columns=[1])
        first = Pattern(0, 0, 0, rows={0: Cell(note=108)})
        second = Pattern(0, 0, 1, rows={0: Cell(note=110, effects=[(0x0B, 0)])})
        sub.patterns[(0, 0)] = first
        sub.patterns[(0, 1)] = second
        song = FurSong(version=232, systems=[(0x83, "YM2612", 1, 1.0, 0.0, 0.0)], subsong=sub)
        route = build_playback(song, loop_repeats=2)
        self.assertEqual([r.order for r in route], [0, 0, 1, 0, 0, 1, 0, 0, 1])
        self.assertTrue(any(r.loop_start == 0 for r in route))


if __name__ == "__main__":
    unittest.main()
