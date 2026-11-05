import struct
import xml.etree.ElementTree as ET
import zipfile

import pytest

from gpbridge import NoteEvent, Score, convert, parse_gpx, track_names_from_config, write_midi
from gpx_container import decompress_bcfz, extract_gpif


def midi_tracks(path):
    """Independently read SMF chunks, event timing, names and routing metadata."""
    raw = path.read_bytes()
    _, fmt, count, ppq = struct.unpack(">IHHH", raw[4:14])
    assert ppq == 480
    result, offset = [], 14
    for _ in range(count):
        assert raw[offset:offset + 4] == b"MTrk"
        size = struct.unpack_from(">I", raw, offset + 4)[0]
        data = raw[offset + 8:offset + 8 + size]
        assert len(data) == size
        offset += 8 + size
        index, tick, name, port, notes = 0, 0, "", None, []

        def vlq():
            nonlocal index
            value = 0
            while True:
                byte = data[index]
                index += 1
                value = (value << 7) | (byte & 127)
                if byte < 128:
                    return value

        while index < len(data):
            tick += vlq()
            status = data[index]
            index += 1
            if status == 255:
                kind = data[index]
                index += 1
                length = vlq()
                value = data[index:index + length]
                index += length
                if kind == 3:
                    name = value.decode("utf-8")
                elif kind == 0x21:
                    port = value[0]
                elif kind == 0x2f:
                    assert index == len(data)
            else:
                length = 1 if status & 0xf0 in {0xc0, 0xd0} else 2
                value = data[index:index + length]
                index += length
                if status & 0xf0 in {0x80, 0x90}:
                    notes.append((tick, status, *value))
        result.append((name, port, notes))
    assert offset == len(raw)
    return fmt, result


def musicxml_note(pitch="E", string=1, extra="", duration=1):
    return f"<note><pitch><step>{pitch}</step><octave>4</octave></pitch><duration>{duration}</duration><notations><technical><string>{string}</string>{extra}</technical></notations></note>"


@pytest.mark.parametrize("split", [True, False])
def test_two_musicxml_guitars_keep_independent_tracks_and_channels(tmp_path, split):
    source = tmp_path / "duet.musicxml"
    source.write_text("<score-partwise><part-list><score-part id='A'><part-name>主音</part-name></score-part>"
                      "<score-part id='B'><part-name>节奏</part-name></score-part></part-list>"
                      f"<part id='A'><measure>{musicxml_note('E')}</measure></part>"
                      f"<part id='B'><measure>{musicxml_note('G')}</measure></part></score-partwise>", encoding="utf-8")
    score = parse_gpx(source)
    assert [(n.source_track, n.source_track_name, n.tick) for n in score.notes] == [(1, "主音", 0), (2, "节奏", 0)]
    config = {"default_channel": 1, "string_channels": {"1": 1}, "split_tracks": split}
    events, report = convert(score, config)
    output = tmp_path / "duet.mid"
    write_midi(events, output, score.tempo, track_names_from_config(config), split)
    fmt, tracks = midi_tracks(output)
    assert fmt == 1
    assert len(tracks) == 3
    assert "主音" in tracks[1][0] and "节奏" in tracks[2][0]
    assert [t[1] for t in tracks[1:]] == [0, 1]
    assert [n for n in tracks[1][2] if n[1] == 0x90] == [(0, 0x90, 64, 100)]
    assert [n for n in tracks[2][2] if n[1] == 0x90] == [(0, 0x90, 67, 100)]
    assert not report["warnings"]


def test_many_parts_strum_and_unassigned_never_collapse_to_channel_one(tmp_path):
    score = Score([NoteEvent(0, 480, string, 0, 90, tech, 60 + part,
                             source_track=part, source_track_name="Guitar")
                   for part in range(1, 5) for string, tech in [(1, []), (0, []), (2, ["strum"])]], {1: 64})
    config = {"default_channel": 1, "unassigned_channel": 16, "strum_channel": 15}
    events, report = convert(score, config)
    assert not report["warnings"]
    for _, group in events.parts.values():
        assert {message[0] & 15 for _, message in group} == {0, 14, 15}
    out = tmp_path / "many.mid"
    write_midi(events, out)
    _, tracks = midi_tracks(out)
    assert len(tracks) == 13
    assert len({name for name, _, _ in tracks}) == 13


def test_auto_sustain_extends_across_rests_per_string_and_part():
    notes = [NoteEvent(0, 120, 1, 0, pitch=64), NoteEvent(960, 120, 1, 2, pitch=66),
             NoteEvent(240, 120, 2, 0, pitch=59),
             NoteEvent(0, 120, 1, 0, techniques=["palm_mute"], pitch=64, source_track=2)]
    score = Score(notes, {1: 64, 2: 59}, track_ends={1: 1920, 2: 480})
    config = {"default_channel": 1, "string_channels": {"1": 1, "2": 2}, "sustain_mode": "auto", "techniques": {"palm_mute": {"events": []}}}
    events, report = convert(score, config)
    assert (960, bytes([0x80, 64, 0])) in events.parts[1][1]
    assert (1920, bytes([0x80, 66, 0])) in events.parts[1][1]
    assert (1920, bytes([0x81, 59, 0])) in events.parts[1][1]
    assert (120, bytes([0x80, 64, 0])) in events.parts[2][1]
    assert len(report["generated_sustains"]) == 3
    original, _ = convert(score, {**config, "sustain_mode": "notated"})
    assert (120, bytes([0x80, 64, 0])) in original.parts[1][1]


def test_musicxml_ties_merge_without_retrigger(tmp_path):
    source = tmp_path / "ties.xml"
    source.write_text("<score-partwise><part id='P1'><measure>" +
                      musicxml_note(extra="<tied type='start'/>") +
                      musicxml_note(extra="<tied type='stop'/><tied type='start'/>") +
                      musicxml_note(extra="<tied type='stop'/>") + "</measure></part></score-partwise>")
    score = parse_gpx(source)
    assert len(score.notes) == 1 and score.notes[0].duration == 1440
    events, report = convert(score, {"default_channel": 1})
    assert len(events) == 2 and not report["warnings"]


def test_legato_does_not_use_another_guitar_as_predecessor():
    score = Score([NoteEvent(0, 480, 1, 0, pitch=60),
                   NoteEvent(480, 480, 1, 2, techniques=["hammer_on"], pitch=62, source_track=2)], {1: 64})
    events, report = convert(score, {"default_channel": 1, "techniques": {"hammer_on": {"events": []}}})
    assert any("no earlier note" in w for w in report["warnings"])
    assert (480, bytes([0x80, 60, 0])) in events.parts[1][1]


def indexed_gpif():
    return b"""<GPIF><MasterTrack><Tracks>7 9</Tracks></MasterTrack>
    <Tracks><Track id='7'><Name>Lead</Name><Properties><Property name='Tuning'><Pitches>40 45 50 55 59 64</Pitches></Property></Properties></Track>
    <Track id='9'><Name>Rhythm</Name><Properties><Property name='Tuning'><Pitches>38 45 50 55 59 64</Pitches></Property></Properties></Track></Tracks>
    <MasterBars><MasterBar><Time>4/4</Time><Bars>10 11</Bars></MasterBar><MasterBar><Bars>12 13</Bars></MasterBar></MasterBars>
    <Bars><Bar id='10'><Voices>20</Voices></Bar><Bar id='11'><Voices>21</Voices></Bar><Bar id='12'><Voices>22</Voices></Bar><Bar id='13'><Voices>-1</Voices></Bar></Bars>
    <Voices><Voice id='20'><Beats>30 31</Beats></Voice><Voice id='21'><Beats>32</Beats></Voice><Voice id='22'><Beats>33</Beats></Voice></Voices>
    <Beats><Beat id='30'><Rhythm ref='q'/><Notes>40</Notes></Beat><Beat id='31'><Rhythm ref='q'/><Notes>41</Notes></Beat>
    <Beat id='32'><Rhythm ref='q'/><Notes>42</Notes></Beat><Beat id='33'><Rhythm ref='d'/><Notes>43</Notes></Beat></Beats>
    <Rhythms><Rhythm id='q'><NoteValue>Quarter</NoteValue></Rhythm><Rhythm id='d'><NoteValue>Eighth</NoteValue><AugmentationDot count='1'/></Rhythm></Rhythms>
    <Notes><Note id='40'><Properties><Property name='String'><String>5</String></Property><Property name='Fret'><Fret>0</Fret></Property><Property name='HopoOrigin'><Enable/></Property></Properties></Note>
    <Note id='41'><Properties><Property name='String'><String>5</String></Property><Property name='Fret'><Fret>2</Fret></Property></Properties></Note>
    <Note id='42'><Properties><Property name='String'><String>0</String></Property><Property name='Fret'><Fret>0</Fret></Property></Properties></Note>
    <Note id='43'><LetRing/><Properties><Property name='String'><String>5</String></Property><Property name='Fret'><Fret>3</Fret></Property></Properties></Note></Notes></GPIF>"""


def bcfs(payload):
    sectors = (len(payload) + 4095) // 4096
    data = bytearray((sectors + 2) * 4096)
    struct.pack_into("<I", data, 4096, 2)
    data[4100:4110] = b"score.gpif"
    struct.pack_into("<I", data, 4096 + 0x8c, len(payload))
    for index in range(sectors):
        struct.pack_into("<I", data, 4096 + 0x94 + index * 4, index + 2)
    data[8192:8192 + len(payload)] = payload
    return b"BCFS" + data


def bcfz_literals(raw):
    bits = ""
    for offset in range(0, len(raw), 3):
        chunk = raw[offset:offset + 3]
        bits += "0" + format(len(chunk), "02b")[::-1] + "".join(format(byte, "08b") for byte in chunk)
    bits += "0" * (-len(bits) % 8)
    return b"BCFZ" + struct.pack("<I", len(raw)) + bytes(int(bits[i:i+8], 2) for i in range(0, len(bits), 8))


@pytest.mark.parametrize("container", ["xml", "zip", "bcfs", "bcfz"])
def test_real_gpif_reference_layout_in_all_containers(tmp_path, container):
    payload = indexed_gpif()
    source = tmp_path / "score.gpx"
    if container == "zip":
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("Content/score.gpif", payload)
    else:
        source.write_bytes(payload if container == "xml" else bcfs(payload) if container == "bcfs" else bcfz_literals(bcfs(payload)))
    score = parse_gpx(source)
    assert [(n.source_track, n.tick, n.duration, n.string, n.pitch) for n in score.notes] == [
        (1, 0, 480, 1, 64), (2, 0, 480, 6, 38), (1, 480, 480, 1, 66), (1, 1920, 360, 1, 67)]
    assert score.notes[2].techniques == ["hammer_on"]
    assert score.track_tunings[2][6] == 38


def test_damaged_binary_gpx_fails_without_partial_score(tmp_path):
    payload = bcfs(indexed_gpif())
    with pytest.raises(ValueError, match="outside"):
        extract_gpif(payload[:-4096])
    source = tmp_path / "broken.gpx"
    source.write_bytes(bcfz_literals(payload)[:30])
    with pytest.raises(ValueError):
        parse_gpx(source)


def test_bcfz_back_reference_and_invalid_distance():
    # Literal BCF, literal S, then four bytes copied from distance four.
    bits = "011" + "".join(format(b, "08b") for b in b"BCF")
    bits += "010" + format(ord("S"), "08b")
    bits += "1" + "0011" + "001" + "001"
    bits += "0" * (-len(bits) % 8)
    raw = b"BCFZ" + struct.pack("<I", 8) + bytes(int(bits[i:i+8], 2) for i in range(0, len(bits), 8))
    assert decompress_bcfz(raw) == b"BCFSBCFS"
    with pytest.raises(ValueError, match="back reference"):
        decompress_bcfz(b"BCFZ" + struct.pack("<I", 8) + bytes([0x8f, 0xff]))
