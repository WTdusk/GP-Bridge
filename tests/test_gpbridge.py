import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
import struct
from pathlib import Path

from gpbridge import NoteEvent, Score, parse_gpx, convert
from preset_manager import load_preset, validate_preset


def test_special_tuning_channels_and_combo(tmp_path):
    source = tmp_path / "fixture.gpx"
    source.write_text("""<Score><Tempo>100</Tempo><Track><Strings><String number='1'><Pitch>38</Pitch></String><String number='2'><Pitch>45</Pitch></String></Strings><Measure><Beat><Duration><Value>Quarter</Value></Duration><Note><String>1</String><Fret>2</Fret><Velocity>90</Velocity><PalmMute>true</PalmMute><Harmonic>true</Harmonic></Note><Note><String>2</String><Fret>0</Fret><Velocity>80</Velocity><Slide>true</Slide><Vibrato>true</Vibrato></Note></Beat></Measure></Track></Score>""", encoding="utf-8")
    score = parse_gpx(source)
    assert [n.pitch for n in score.notes] == [40, 45]
    config = json.loads(Path("mapping.example.json").read_text(encoding="utf-8"))
    events, report = convert(score, config)
    assert report["notes"] == 2
    assert ["palm_mute", "artificial_harmonic"] in report["used_combinations"]
    assert len(events) >= 8


def test_cli_writes_midi_and_report(tmp_path):
    source = tmp_path / "fixture.gpx"
    source.write_text("<Score><Beat><Duration><Value>Quarter</Value></Duration><Note><String>6</String><Fret>0</Fret></Note></Beat></Score>", encoding="utf-8")
    config = tmp_path / "map.json"
    config.write_text('{"default_channel": 1}', encoding="utf-8")
    output = tmp_path / "out.mid"
    result = subprocess.run([sys.executable, "gpbridge.py", str(source), "-c", str(config), "-o", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes().startswith(b"MThd")
    assert output.with_suffix(".report.json").exists()


def test_shreddage_archtop_tapping_mapping(tmp_path):
    source = tmp_path / "tapping.gpx"
    source.write_text("<Score><Beat><Duration><Value>Quarter</Value></Duration><Note><String>1</String><Fret>12</Fret><Tapping>true</Tapping></Note></Beat></Score>", encoding="utf-8")
    score = parse_gpx(source)
    config = load_preset("GPBridgeData/Profiles/kontakt/shreddage_3_5_archtop.json")
    events, report = convert(score, config)
    assert score.notes[0].techniques == ["tapping"]
    assert any(message == bytes([0x90, 34, 127]) for _, message in events)
    assert not report["warnings"]
    assert not validate_preset(config)


def test_shreddage_bend_vibrato_and_legato(tmp_path):
    config = load_preset("GPBridgeData/Profiles/kontakt/shreddage_3_5_archtop.json")
    score = Score([
        NoteEvent(0, 120, 1, 0, 80, [], 60),
        NoteEvent(120, 120, 1, 2, 80, ["hammer_on"], 62),
        NoteEvent(300, 120, 2, 5, 90, ["vibrato"], 64),
        NoteEvent(500, 120, 3, 7, 90, ["bend"], 66, [(0, 0), (30, 100), (60, 0)]),
    ], {1: 60, 2: 59, 3: 55})
    events, report = convert(score, config)

    assert (125, bytes([0x80, 60, 0])) in events
    assert (299, bytes([0xB0 | 1, 1, 127])) in events
    assert (420, bytes([0xB0 | 1, 1, 0])) in events
    assert (560, bytes([0xE0 | 2, 127, 127])) in events
    assert report["generated_legato_overlaps"][0]["overlap_ticks"] == 5
    assert not report["warnings"]


def test_upward_bends_support_half_and_whole_semitones():
    config = load_preset("GPBridgeData/Profiles/kontakt/shreddage_3_5_archtop.json")
    score = Score([
        NoteEvent(0, 100, 1, 0, 90, ["bend"], 60, [(0, 0), (30, 25)]),
        NoteEvent(200, 100, 1, 0, 90, ["bend"], 60, [(0, 0), (30, 50)]),
        NoteEvent(400, 100, 1, 0, 90, ["bend"], 60, [(0, 0), (30, -50)]),
    ], {1: 64})
    events, report = convert(score, config)

    # +0.5 semitone and +1 semitone are represented by distinct wheel values.
    half = 8192 + round((0.5 / 2) * 8192)
    whole = 8192 + round((1.0 / 2) * 8192)
    assert any(tick == 50 and message == bytes([0xE0, half & 127, (half >> 7) & 127]) for tick, message in events)
    assert any(tick == 250 and message == bytes([0xE0, whole & 127, (whole >> 7) & 127]) for tick, message in events)
    # Negative GP values are clamped to the neutral wheel position.
    assert any(tick == 450 and message == bytes([0xE0, 0, 64]) for tick, message in events)
    assert not report["warnings"]


def test_natural_and_artificial_harmonics_keep_distinct_mappings(tmp_path):
    source = tmp_path / "harmonics.gpx"
    source.write_text("""<Score><Beat><Duration><Value>Quarter</Value></Duration>
    <Note><String>1</String><Fret>12</Fret><Harmonic><Type>Natural</Type></Harmonic></Note></Beat>
    <Beat><Duration><Value>Quarter</Value></Duration>
    <Note><String>1</String><Fret>12</Fret><Harmonic><Type>Artificial</Type></Harmonic></Note></Beat></Score>""", encoding="utf-8")
    config = load_preset("GPBridgeData/Profiles/kontakt/shreddage_3_5_archtop.json")
    score = parse_gpx(source)
    events, report = convert(score, config)
    assert score.notes[0].techniques == ["natural_harmonic"]
    assert score.notes[1].techniques == ["artificial_harmonic"]
    assert any(message[1] == 32 for _, message in events)
    assert any(message[1] == 33 for _, message in events)
    assert not report["warnings"]


def test_generic_harmonic_defaults_to_artificial(tmp_path):
    source = tmp_path / "generic-harmonic.gpx"
    source.write_text("""<Score><Beat><Duration><Value>Quarter</Value></Duration>
    <Note><String>1</String><Fret>12</Fret><Harmonic>true</Harmonic></Note></Beat></Score>""", encoding="utf-8")
    score = parse_gpx(source)
    assert score.notes[0].techniques == ["artificial_harmonic"]


def test_musicxml_preserves_pitch_timing_string_and_techniques(tmp_path):
    source = tmp_path / "score.musicxml"
    source.write_text("""<?xml version='1.0' encoding='UTF-8'?>
    <score-partwise version='3.1'>
      <part-list><score-part id='P1'><part-name>Guitar</part-name></score-part></part-list>
      <part id='P1'>
        <measure number='1'>
          <attributes><divisions>4</divisions><clef><sign>TAB</sign></clef></attributes>
          <note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration>
            <notations><technical><string>1</string><fret>0</fret><hammer-on type='start'/></technical></notations>
          </note>
          <note><chord/><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration>
            <notations><technical><string>2</string><fret>3</fret></technical></notations>
          </note>
          <backup><duration>8</duration></backup>
          <note><rest/><duration>8</duration></note>
        </measure>
        <measure number='2'>
          <note><pitch><step>F</step><octave>4</octave><alter>1</alter></pitch><duration>2</duration>
            <notations><technical><string>1</string><fret>2</fret><pull-off type='stop'/></technical></notations>
          </note>
        </measure>
      </part>
    </score-partwise>""", encoding="utf-8")
    score = parse_gpx(source)
    assert [(note.tick, note.pitch, note.string, note.fret) for note in score.notes] == [
        (0, 64, 1, 0), (0, 67, 2, 3), (960, 66, 1, 2)
    ]
    assert score.notes[0].techniques == ["hammer_on"]
    assert score.notes[2].techniques == ["pull_off"]


def test_musicxml_detects_tapping_and_source_slide_overlap(tmp_path):
    source = tmp_path / "techniques.musicxml"
    source.write_text("""<score-partwise><part id='P1'><measure><attributes><divisions>4</divisions></attributes>
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><notations><technical><string>1</string><fret>0</fret><slide type='start'/></technical></notations></note>
    <note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><notations><technical><string>1</string><fret>1</fret><tap/></technical></notations></note>
    <note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><notations><technical><string>1</string><fret>3</fret></technical></notations></note>
    </measure></part></score-partwise>""", encoding="utf-8")
    score = parse_gpx(source)
    assert score.notes[0].techniques == ["slide"]
    assert score.notes[1].techniques == ["tapping"]
    config = load_preset("GPBridgeData/Profiles/kontakt/shreddage_3_5_archtop.json")
    events, report = convert(score, config)
    # 120 ticks on either side of the slide transition.
    assert (0 + 480 + 120, bytes([0x80, 64, 0])) in events
    assert (480 + 480 + 120, bytes([0x80, 65, 0])) in events
    assert any(message[1] == 34 for _, message in events)


def test_zip_gpx_gpif_dispatches(tmp_path):
    source = tmp_path / "score.gpx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("Content/score.gpif", "<Score><Beat><Duration><Value>Quarter</Value></Duration><Note><String>1</String><Fret>3</Fret></Note></Beat></Score>")
    score = parse_gpx(source)
    assert score.notes[0].pitch == 67


def test_musicxml_missing_string_infers_standard_tuning_but_not_nonstandard(tmp_path):
    standard = tmp_path / "standard.musicxml"
    standard.write_text("""<score-partwise><part id='P1'><measure><attributes><divisions>4</divisions></attributes>
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure></part></score-partwise>""", encoding="utf-8")
    score = parse_gpx(standard)
    assert score.notes[0].pitch == 64
    assert score.notes[0].string == 1

    drop_d = tmp_path / "drop-d.musicxml"
    drop_d.write_text("""<score-partwise><part id='P1'><measure><attributes><divisions>4</divisions>
    <staff-details><staff-tuning line='1'><tuning-step>D</tuning-step><tuning-octave>2</tuning-octave></staff-tuning></staff-details>
    </attributes><note><pitch><step>D</step><octave>3</octave></pitch><duration>4</duration></note>
    </measure></part></score-partwise>""", encoding="utf-8")
    score = parse_gpx(drop_d)
    assert score.notes[0].pitch == 50
    assert score.notes[0].string == 0


def test_midi_is_type1_with_string_and_strum_tracks(tmp_path):
    config = load_preset("GPBridgeData/Profiles/kontakt/shreddage_3_5_archtop.json")
    score = Score([
        NoteEvent(0, 120, 1, 0, 90, [], 64),
        NoteEvent(0, 120, 0, 0, 90, ["strum"], 60),
    ], {1: 64})
    events, report = convert(score, config)
    output = tmp_path / "tracks.mid"
    from gpbridge import track_names_from_config, write_midi
    write_midi(events, output, score.tempo, track_names_from_config(config))
    raw = output.read_bytes()
    assert raw[:4] == b"MThd"
    _, fmt, tracks, _ = struct.unpack(">IHHH", raw[4:14])
    assert fmt == 1
    assert tracks >= 3  # tempo + string 1 + strum
    assert 15 in report["midi_tracks"] and 16 not in report["midi_tracks"]


def test_midi_can_be_combined_into_one_track(tmp_path):
    config = load_preset("GPBridgeData/Profiles/kontakt/shreddage_3_5_archtop.json")
    score = Score([NoteEvent(0, 120, 1, 0, 90, [], 64)], {1: 64})
    events, _ = convert(score, config)
    from gpbridge import write_midi
    output = tmp_path / "combined.mid"
    write_midi(events, output, score.tempo, split_tracks=False)
    raw = output.read_bytes()
    _, fmt, tracks, _ = struct.unpack(">IHHH", raw[4:14])
    assert fmt == 0 and tracks == 1
